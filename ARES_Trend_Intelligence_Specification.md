# ARES Trend Intelligence Design Specification

## Project Context

ARES is **NOT** a directional trading system seeking to capture breakouts. ARES acts strictly as a defense mechanism for an intraday BTC short-strangle strategy trading next-day expiry options. 

The primary objective is **NOT** to predict the future price of BTC. Instead, the objective is to identify structural market trends early enough to execute necessary delta-hedges against portfolio risk, while aggressively filtering out false breakouts, whipsaws, and liquidity sweeps that would cause unnecessary and costly hedges.

---

## 1. The TrendResult Model

The Trend Intelligence Engine continuously generates a `TrendResult` object. This object synthesizes complex market signals into a standardized format for downstream consumption.

### `trend_direction`
- **What it represents:** The active path of least resistance (e.g., LONG, SHORT, NONE).
- **Why it matters for short strangles:** Identifies exactly which leg (Call or Put) is currently under threat.
- **How the Decision Engine uses it:** Dictates whether to deploy a long hedge or a short hedge.

### `trend_strength` (0-100)
- **What it represents:** The raw, brute-force momentum and depth of the current directional move.
- **Why it matters for short strangles:** A low strength score suggests the current leg is not under immediate threat of blowout.
- **How the Decision Engine uses it:** Determines the aggressive scaling of the hedge size (e.g., delta 0.3 vs delta 1.0).

### `trend_confidence` (0-100)
- **What it represents:** The reliability of the trend signal, based on the alignment of multiple, independent signal providers (e.g., price action + volume + order flow).
- **Why it matters for short strangles:** Prevents the bot from hedging during low-confidence "chop" where signals contradict each other.
- **How the Decision Engine uses it:** Acts as a primary gatekeeper. Hedges are delayed or rejected if confidence is below critical thresholds.

### `trend_persistence` (0-100)
- **What it represents:** How long and how consistently the current trend has maintained its structure without a significant breakdown.
- **Why it matters for short strangles:** Differentiates between a sudden, transient 1-minute candle spike versus a sustained, methodical structural shift.
- **How the Decision Engine uses it:** Prevents knee-jerk hedging reactions to momentary stop-hunts or liquidity sweeps.

### `trend_acceleration` (0-100)
- **What it represents:** The velocity of the trend. Is the trend gaining speed (parabolic) or slowing down?
- **Why it matters for short strangles:** Rapid acceleration creates massive Gamma risk and rapid expansion of unrealized losses.
- **How the Decision Engine uses it:** High acceleration may override standard persistence rules, triggering an emergency delta-lock to stop catastrophic bleeding.

### `continuation_probability` (0-100)
- **What it represents:** The likelihood that the current trend will persist rather than pause or reverse.
- **Why it matters for short strangles:** Helps forecast whether the threatened leg will continue to take damage.
- **How the Decision Engine uses it:** Used to decide if an active hedge should be maintained or allowed to ride.

### `reversal_probability` (0-100)
- **What it represents:** The likelihood that the current directional move is exhausted and is about to reverse sharply.
- **Why it matters for short strangles:** If a reversal is highly probable, an active hedge will quickly become a massive drag on profits.
- **How the Decision Engine uses it:** Triggers the unwinding or reduction of an active hedge before the reversion occurs.

### `whipsaw_probability` (0-100)
- **What it represents:** The likelihood of erratic, bidirectional price action (chop) that destroys both sides of the market.
- **Why it matters for short strangles:** Hedges deployed during a whipsaw will constantly get stopped out, bleeding the portfolio via "death by a thousand cuts."
- **How the Decision Engine uses it:** Disables all hedge initiation until market structure clarifies.

### `signal_reliability` (0-100)
- **What it represents:** The quality and cleanliness of the data currently feeding the engine (e.g., normal market conditions vs. holiday low liquidity).
- **Why it matters for short strangles:** Trading in unreliable data environments drastically increases execution risk.
- **How the Decision Engine uses it:** Low reliability expands risk tolerance thresholds, requiring deeper confirmation before acting.

### `explanation`
- **What it represents:** A human-readable, AI-generated or rules-based text summary of the current synthesis.
- **Why it matters for short strangles:** Provides immediate clarity for human oversight.
- **How the Decision Engine uses it:** Passed directly to the logging and analytics layer for post-trade review.

### `supporting_signals`
- **What it represents:** A key-value dictionary of the raw outputs from the individual signal providers (e.g., VWAP state, Volume state).
- **Why it matters for short strangles:** Allows for deep-dive debugging of exactly which indicator caused a specific behavior.
- **How the Decision Engine uses it:** Stored in the Replay and Analytics engines for later counterfactual analysis.

### `timestamp`
- **What it represents:** The exact microsecond the trend was evaluated.

### `debug_information`
- **What it represents:** Internal engine metrics, latency, and calculation state data.

---

## 2. Future Signal Providers

ARES relies on Dependency Injection. The Trend Engine aggregates insights from multiple independent providers.

- **Price Action:** Evaluates raw candlestick behavior, wick rejection, and candle body momentum.
- **Market Structure:** Evaluates higher-highs, lower-lows, and the breaking of major support/resistance zones.
- **Volume:** Evaluates whether price moves are backed by significant market participation (real) or thin liquidity (fake).
- **Volatility:** Evaluates the width of price swings to contextualize whether a move is normal noise or an anomaly.
- **IV Behaviour:** Evaluates how options pricing is reacting to the underlying price move (e.g., is the market pricing in fear?).
- **VWAP:** Evaluates price position relative to the daily volume-weighted average price to determine macro intraday control (buyers vs. sellers).
- **Open Interest:** Evaluates whether a price move is driven by new positions opening or old positions being liquidated.
- **Funding Rate:** Evaluates the aggression of perpetual futures traders.
- **Order Flow:** Evaluates the real-time aggression of market buyers hitting the ask versus market sellers hitting the bid.

---

## 3. Examples

*(Note: These are conceptual examples illustrating how the Trend Engine synthesizes signals into a `TrendResult`.)*

### Example 1: Strong Bull Trend
- **trend_direction:** LONG
- **trend_strength:** 92
- **trend_confidence:** 88
- **trend_persistence:** 75
- **trend_acceleration:** 60
- **whipsaw_probability:** 5
- **explanation:** "Price has cleanly broken major resistance with heavy volume and expanding OI. VWAP heavily supports buyers."

### Example 2: Strong Bear Trend
- **trend_direction:** SHORT
- **trend_strength:** 95
- **trend_confidence:** 90
- **trend_persistence:** 80
- **trend_acceleration:** 85
- **whipsaw_probability:** 2
- **explanation:** "Panic selling observed. Price is cascading through structural support with extreme order flow imbalance and massive liquidations."

### Example 3: Range
- **trend_direction:** NONE
- **trend_strength:** 10
- **trend_confidence:** 15
- **trend_persistence:** 5
- **trend_acceleration:** 0
- **whipsaw_probability:** 85
- **explanation:** "Price oscillating aimlessly near daily VWAP. Volume is nonexistent. Market is waiting for a catalyst."

### Example 4: Fake Breakout
- **trend_direction:** LONG
- **trend_strength:** 30
- **trend_confidence:** 20
- **trend_persistence:** 10
- **trend_acceleration:** 15
- **reversal_probability:** 80
- **whipsaw_probability:** 70
- **explanation:** "Price spiked above resistance but volume divergence is severe. Open Interest is dropping, indicating a short-squeeze liquidity hunt rather than a real breakout."

### Example 5: Trend Exhaustion
- **trend_direction:** LONG
- **trend_strength:** 40
- **trend_confidence:** 45
- **trend_persistence:** 90
- **trend_acceleration:** 5
- **reversal_probability:** 75
- **whipsaw_probability:** 30
- **explanation:** "The bull trend is intact structurally, but momentum has died. Price is stalling at major supply. Bearish divergences forming across order flow."

---

## 4. Complete Data Flow

### How TrendResult Flows Through ARES

The `TrendResult` is **never** used to execute a trade directly. It flows sequentially through the intelligence stack:

1. **Market Regime Engine**
   - Ingests the `TrendResult`.
   - Uses fields like `trend_confidence` and `whipsaw_probability` to dictate whether the overarching market state should transition (e.g., moving from `SAFE_RANGE` to `EARLY_TREND`).
   
2. **Position Risk Engine**
   - Ingests the `TrendResult` and the newly minted `MarketRegime`.
   - Evaluates the current active short strangle portfolio.
   - Calculates how much damage the current `trend_strength` and `trend_acceleration` will mathematically inflict on the portfolio's Delta and Gamma exposures.

3. **Decision Engine**
   - Ingests everything: `TrendResult`, `MarketRegime`, and `PositionRisk`.
   - Makes the final, binary decision (e.g., `OPEN_HEDGE`).
   - For example, if the `TrendResult` indicates a fake breakout (high whipsaw probability), the Decision Engine explicitly rejects opening a hedge, saving the portfolio from a costly whipsaw loss, despite the Position Risk Engine flashing warning signs.
