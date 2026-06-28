"""
test_hedge_v2.py — Mock Bleeding Test for Advanced Smart Hedging
================================================================
Simulates real market scenarios to verify the hedge engine works correctly.
Tests: BTC pump, BTC dump, reversal, and sideways scenarios.
"""

import sys
import os
import time

# ─── Mock Classes ───────────────────────────────────────────────

class MockAPIClient:
    """Simulates Delta Exchange API with controllable BTC price and option greeks."""
    
    def __init__(self):
        self.btc_price = 63000.0
        self.ws_connected = True
        self.option_prices = {}  # sym -> mark_price
        self.option_deltas = {}  # sym -> delta
    
    def get_tickers(self, params):
        sym = params.get('symbol', '')
        if sym == 'BTCUSD':
            return {
                'success': True,
                'result': [{
                    'symbol': 'BTCUSD',
                    'product_id': 1,
                    'mark_price': str(self.btc_price)
                }]
            }
        return {'success': False, 'result': []}
    
    def get_realtime_ticker(self, sym):
        price = self.option_prices.get(sym, 50.0)
        delta = self.option_deltas.get(sym, 0.0)
        return {
            'mark_price': str(price),
            'greeks': {'delta': delta, 'gamma': 0.001}
        }
    
    def place_order(self, prod_id, direction, size, order_type, limit_price=None):
        return {
            'success': True,
            'result': {
                'id': f'MOCK-{int(time.time())}',
                'average_fill_price': self.btc_price
            }
        }
    
    def move_btc(self, delta_usd):
        """Simulate BTC price movement."""
        self.btc_price += delta_usd
    
    def set_option_price(self, sym, price):
        self.option_prices[sym] = price


class MockDVOLProvider:
    def get_current_dvol(self):
        return 42.0
    def get_status(self):
        return {'current_dvol': 42.0, 'dvol_percentile': 50.0}


class MockRiskManager:
    def __init__(self):
        self.current_equity = 10000.0
    def tighten_stop_loss(self, factor):
        pass
    def update_equity(self):
        pass


class MockExecutionHandler:
    """Simulates order execution in paper mode."""
    
    def __init__(self, api_client):
        self.api_client = api_client
        self.mode = 'PAPER'
        self.hedge_size_btc = 0.0
        self.hedge_order_id = None
        self.hedge_entry_price = 0.0
        self.hedge_position = 0
        self.active_positions = {}
    
    def place_hedge_order(self, size_btc, direction, use_limit=False):
        import random
        fill_price = self.api_client.btc_price
        signed_change = size_btc if direction == 'buy' else -size_btc
        self.hedge_size_btc += signed_change
        self.hedge_position += signed_change
        order_id = f"PAPER-HEDGE-{random.randint(10000, 99999)}"
        self.hedge_order_id = order_id
        if self.hedge_entry_price <= 0:
            self.hedge_entry_price = fill_price
        return {'success': True, 'order_id': order_id, 'fill_price': fill_price}
    
    def close_hedge(self):
        self.hedge_size_btc = 0.0
        self.hedge_position = 0
        self.hedge_order_id = None
        self.hedge_entry_price = 0.0


# ─── Build Positions ────────────────────────────────────────────

def build_positions(call_sym, put_sym, call_entry, put_entry, lot_size=10):
    """Create a mock positions dict like execution.active_positions."""
    return {
        call_sym: {
            'symbol': call_sym,
            'entry_price': call_entry,
            'size': lot_size,
            'leg_type': 'call',
            'option_type': 'call'
        },
        put_sym: {
            'symbol': put_sym,
            'entry_price': put_entry,
            'size': lot_size,
            'leg_type': 'put',
            'option_type': 'put'
        }
    }


# ─── Test Scenarios ─────────────────────────────────────────────

def run_scenario(name, api, execution, hedger, positions, price_steps, call_sym, put_sym, call_entry, put_entry):
    """
    Run a scenario through the hedge engine.
    price_steps: list of (btc_delta, call_price, put_price) tuples
    """
    print(f"\n{'='*70}")
    print(f"  SCENARIO: {name}")
    print(f"{'='*70}")
    print(f"  Entry: Call={call_sym} @ ${call_entry:.2f} | Put={put_sym} @ ${put_entry:.2f}")
    print(f"  BTC Start: ${api.btc_price:,.2f}")
    print(f"{'='*70}")
    
    # Cache entry premiums
    hedger.set_entry_premiums(positions)
    
    total_premium = (call_entry + put_entry) * positions[call_sym]['size'] * 0.001
    
    results = []
    
    for step, (btc_delta, call_price, put_price) in enumerate(price_steps):
        # Move BTC
        api.move_btc(btc_delta)
        api.set_option_price(call_sym, call_price)
        api.set_option_price(put_sym, put_price)
        
        # Update positions with current prices
        positions[call_sym]['entry_price'] = call_entry
        positions[put_sym]['entry_price'] = put_entry
        
        # Calculate option P&L (short position: entry - current)
        call_pnl = (call_entry - call_price) * positions[call_sym]['size'] * 0.001
        put_pnl = (put_entry - put_price) * positions[put_sym]['size'] * 0.001
        option_pnl = call_pnl + put_pnl
        
        # Calculate unrealized loss percentage
        unrealized_loss_pct = max(0.0, -option_pnl / total_premium) if total_premium > 0 else 0.0
        
        # Run hedge management
        hedger.manage_hedge(positions, unrealized_loss_pct, option_pnl)
        
        # Get hedge P&L
        hedge_pnl = hedger.get_live_hedge_pnl()
        net_pnl = option_pnl + hedge_pnl
        
        results.append({
            'step': step + 1,
            'btc': api.btc_price,
            'call_price': call_price,
            'put_price': put_price,
            'option_pnl': option_pnl,
            'hedge_pnl': hedge_pnl,
            'net_pnl': net_pnl,
            'hedge_active': hedger.hedge_active,
            'hedge_size': execution.hedge_size_btc,
            'hedge_dir': 'LONG' if execution.hedge_size_btc > 0 else 'SHORT' if execution.hedge_size_btc < 0 else 'NONE'
        })
        
        # Print step
        hedge_icon = "🛡️" if hedger.hedge_active else "  "
        pnl_color = "✅" if net_pnl >= 0 else "❌"
        print(f"  Step {step+1:2d} | BTC: ${api.btc_price:>9,.0f} | "
              f"Call: ${call_price:6.1f} Put: ${put_price:6.1f} | "
              f"OptPnL: ${option_pnl:>+7.2f} | "
              f"{hedge_icon} HedgePnL: ${hedge_pnl:>+7.2f} ({hedger.hedge_type}) | "
              f"{pnl_color} Net: ${net_pnl:>+7.2f}")
    
    # Summary
    print(f"\n  {'─'*60}")
    final = results[-1]
    print(f"  RESULT: Option P&L: ${final['option_pnl']:+.2f} | Hedge P&L: ${final['hedge_pnl']:+.2f} | Net: ${final['net_pnl']:+.2f}")
    
    hedge_ever_negative = any(r['hedge_pnl'] < -0.50 and r['hedge_active'] for r in results)
    if hedge_ever_negative:
        print(f"  ⚠️  FAIL: Hedge went negative during this scenario!")
    else:
        print(f"  ✅ PASS: Hedge never bled below -$0.50")
    
    if final['hedge_pnl'] >= 0 or not any(r['hedge_active'] for r in results):
        print(f"  ✅ PASS: Hedge closed at profit or breakeven")
    else:
        print(f"  ⚠️  FAIL: Hedge closed at a loss (${final['hedge_pnl']:.2f})")
    
    if final['option_pnl'] < 0 and final['hedge_pnl'] > 0:
        recovery = abs(final['hedge_pnl'] / final['option_pnl']) * 100
        print(f"  📊 Loss Recovery: {recovery:.1f}% of option loss offset by hedge")
    
    # Reset for next scenario
    hedger.close_hedge()
    hedger.hedge_stopped_out = False
    execution.hedge_size_btc = 0.0
    execution.hedge_position = 0
    execution.hedge_entry_price = 0.0
    
    return results


def main():
    print("\n" + "🔬 " * 20)
    print("   ADVANCED SMART HEDGE — MOCK BLEEDING TEST")
    print("🔬 " * 20)
    
    # Mock notifier to prevent Telegram timeouts during test
    import notifier as notifier_module
    class MockNotifier:
        def send_message(self, *a, **k): pass
        def send_document(self, *a, **k): pass
        def notify_hedge_executed(self, *a, **k): pass
        def notify_hedge_escalated(self, *a, **k): pass
        def notify_hedge_failed(self, *a, **k): pass
        def notify_error(self, *a, **k): pass
    notifier_module.notifier = MockNotifier()
    
    # Import the actual hedge engine
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from smart_hedging import SmartHedgingManager
    
    call_sym = "C-BTC-65000-210626"
    put_sym = "P-BTC-61000-210626"
    call_entry = 45.0   # Entry premium per lot
    put_entry = 40.0    # Entry premium per lot
    lot_size = 10       # 10 lots = 0.01 BTC exposure
    
    # ═══════════════════════════════════════════════════════════
    # SCENARIO 1: BTC PUMPS $3000 (Call bleeds)
    # ═══════════════════════════════════════════════════════════
    api = MockAPIClient()
    api.btc_price = 63000.0
    execution = MockExecutionHandler(api)
    hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
    positions = build_positions(call_sym, put_sym, call_entry, put_entry, lot_size)
    
    # BTC goes from 63000 → 66000 in steps
    # Call premium rises (losing for us), Put premium drops (winning for us)
    pump_steps = [
        # (btc_delta, call_price, put_price)
        (200,   48.0, 38.0),   # Small move
        (300,   53.0, 35.0),   # Call starts bleeding
        (500,   62.0, 30.0),   # Call bleeds hard (+38%)
        (500,   72.0, 25.0),   # Continues
        (500,   85.0, 20.0),   # Major move +$2000
        (500,   98.0, 16.0),   # +$2500
        (500,  112.0, 13.0),   # +$3000 from entry
    ]
    run_scenario("BTC PUMPS +$3000 (Call Bleeds)", api, execution, hedger, positions, pump_steps, call_sym, put_sym, call_entry, put_entry)
    
    # ═══════════════════════════════════════════════════════════
    # SCENARIO 2: BTC DUMPS $3000 (Put bleeds)
    # ═══════════════════════════════════════════════════════════
    api = MockAPIClient()
    api.btc_price = 63000.0
    execution = MockExecutionHandler(api)
    hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
    positions = build_positions(call_sym, put_sym, call_entry, put_entry, lot_size)
    
    dump_steps = [
        (-200,  43.0, 42.0),
        (-300,  40.0, 47.0),
        (-500,  35.0, 55.0),   # Put starts bleeding
        (-500,  30.0, 65.0),
        (-500,  25.0, 78.0),
        (-500,  20.0, 92.0),
        (-500,  16.0, 108.0),
    ]
    run_scenario("BTC DUMPS -$3000 (Put Bleeds)", api, execution, hedger, positions, dump_steps, call_sym, put_sym, call_entry, put_entry)
    
    # ═══════════════════════════════════════════════════════════
    # SCENARIO 3: BTC PUMPS THEN REVERSES (Direction flip)
    # ═══════════════════════════════════════════════════════════
    api = MockAPIClient()
    api.btc_price = 63000.0
    execution = MockExecutionHandler(api)
    hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
    positions = build_positions(call_sym, put_sym, call_entry, put_entry, lot_size)
    
    reversal_steps = [
        (300,   50.0, 37.0),   # BTC goes up
        (500,   58.0, 33.0),   # Call bleeding
        (700,   70.0, 28.0),   # Hedge should fire (BUY BTC)
        (500,   82.0, 23.0),   # Continues up — hedge profits
        (-500,  72.0, 28.0),   # REVERSAL starts
        (-700,  60.0, 38.0),   # Full reversal — hedge should close at breakeven
        (-800,  48.0, 52.0),   # Now PUT is bleeding — should re-hedge (SELL BTC)
        (-500,  42.0, 65.0),   # Put bleeds more
    ]
    run_scenario("BTC PUMPS THEN REVERSES", api, execution, hedger, positions, reversal_steps, call_sym, put_sym, call_entry, put_entry)
    
    # ═══════════════════════════════════════════════════════════
    # SCENARIO 4: SIDEWAYS (No hedge needed)
    # ═══════════════════════════════════════════════════════════
    api = MockAPIClient()
    api.btc_price = 63000.0
    execution = MockExecutionHandler(api)
    hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
    positions = build_positions(call_sym, put_sym, call_entry, put_entry, lot_size)
    
    sideways_steps = [
        (100,  45.5, 39.5),
        (-50,  45.2, 39.8),
        (80,   45.8, 39.2),
        (-120, 44.8, 40.2),
        (50,   45.1, 39.9),
        (-60,  44.9, 40.1),
        (30,   45.0, 40.0),
    ]
    run_scenario("SIDEWAYS (No Hedge Needed)", api, execution, hedger, positions, sideways_steps, call_sym, put_sym, call_entry, put_entry)
    
    # ═══════════════════════════════════════════════════════════
    # SCENARIO 5: SLOW BLEED (Gradual loss)
    # ═══════════════════════════════════════════════════════════
    api = MockAPIClient()
    api.btc_price = 63000.0
    execution = MockExecutionHandler(api)
    hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
    positions = build_positions(call_sym, put_sym, call_entry, put_entry, lot_size)
    
    slow_bleed_steps = [
        (100,  46.0, 39.5),
        (100,  47.0, 39.0),
        (100,  48.5, 38.5),
        (100,  50.0, 38.0),
        (100,  51.5, 37.5),   # Gradual bleed on call
        (100,  53.0, 37.0),
        (100,  55.0, 36.5),
        (100,  57.0, 36.0),
        (100,  59.0, 35.5),
        (100,  61.0, 35.0),
    ]
    run_scenario("SLOW BLEED +$1000 (Gradual Call Loss)", api, execution, hedger, positions, slow_bleed_steps, call_sym, put_sym, call_entry, put_entry)
    
    print("\n\n" + "="*70)
    print("   TEST COMPLETE — Review results above")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
