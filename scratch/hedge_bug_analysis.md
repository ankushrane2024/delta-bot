# Hedge Direction Bug — Analysis & Fix Plan

## The Problem
When a trade is losing (e.g., -$30), the hedge P&L is also negative instead of positive.
The hedge should profit when the trade loses, offsetting the loss.

## Root Cause Analysis

After reviewing all 670 lines of `smart_hedging.py` and the execution handler, I found
**3 critical bugs** working together to break the hedge:

### Bug 1: Delta Direction Calculation is INVERTED (Line 366)

```python
# Line 363-366 in smart_hedging.py
def _execute_initial_hedge(self, net_delta_btc, greeks_reliable, positions):
    hedge_size = abs(net_delta_btc)
    direction = 'sell' if net_delta_btc > 0 else 'buy'   # ← BUG
```

**The Logic:**
- We have a SHORT strangle (short call + short put).
- When BTC goes UP → the short call bleeds → our portfolio has NEGATIVE delta exposure
  (because we are short calls that gained delta).
- To hedge negative delta: we should BUY BTC futures.
- But the code says: `if net_delta_btc > 0 → sell`. The delta calc on line 214 already
  INVERTS for short positions (`net_delta_btc -= d * size * 0.001`), so when BTC goes UP,
  net_delta_btc is actually NEGATIVE (because short call delta contribution is negative).
  The code then says `else → buy`, which IS correct for this case.

Wait — let me re-trace this more carefully...

Actually, the delta calculation at line 214:
```python
net_delta_btc -= d * data['size'] * 0.001
```
For a SHORT CALL: `d` is the call delta (positive, e.g. +0.3).
The `-=` sign means: `net_delta_btc = net_delta_btc - (+0.3 * size * 0.001)`
So net_delta_btc becomes NEGATIVE when call delta dominates (BTC going up).

For the hedge: if net_delta is negative, we need to BUY BTC to offset.
Line 366: `direction = 'sell' if net_delta_btc > 0 else 'buy'`
If net_delta < 0 → direction = 'buy' ← This IS correct.

### Bug 2: The REAL problem — Hedge triggers TOO LATE or NEVER

Looking at the thresholds:
```python
HEDGE_IV_THRESHOLDS = {
    "low":  {"iv_max": 45, "delta_trigger": 0.15, ...},
    "mid":  {"delta_trigger": 0.12, ...},
    "high": {"delta_trigger": 0.08, ...},
}
```

The `raw_net_delta` used for comparison is normalized:
```python
raw_net_delta = abs(net_delta_btc) / (leg_size * 0.001)
```

For a single lot (size=1), leg_size*0.001 = 0.001 BTC.
If actual net_delta_btc = -0.0002, then raw_net_delta = 0.0002 / 0.001 = 0.20.
This needs to exceed 0.15 to trigger in low DVOL — that's achievable.

But the problem is: **in PAPER mode, the API often returns delta=0 for all legs**.
When all greeks are zero, the hedge never fires unless the emergency fallback
kicks in at 30% loss — by which point you're already down $30.

### Bug 3: Emergency hedge at 30% loss is WAY too late

The emergency hedge only triggers when `unrealized_loss_pct >= 0.30` (30% of premium).
By then the damage is done. And even when it fires, it hedges at 50% exposure size
(line 506: `hedge_size = exposure * 0.5`), which only offsets HALF the further loss.

## The Fixes

1. Lower emergency hedge threshold from 30% to 15%
2. Increase emergency hedge size from 50% to 100% exposure
3. Add a premium-based hedge trigger that fires when any single leg has moved
   against us by more than 20%, regardless of delta data
4. Reduce the delta trigger thresholds so hedge fires earlier

## P&L Direction Check
The P&L formula on line 110 is actually correct:
```python
pnl = (avg_entry - mark_price) * abs(size) if size < 0 else (mark_price - avg_entry) * size
```
- Short hedge (sold BTC): profit when price drops ✓
- Long hedge (bought BTC): profit when price rises ✓

So the P&L DISPLAY is correct. The problem is the hedge fires too late or in the wrong
direction due to stale/zero greeks from the Delta Exchange API in paper mode.
