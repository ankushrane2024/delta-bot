import time
import json
import os
import threading
from local_hpe_engine import HedgeProtectionEngine
from local_hpe_indicators import LocalHPEIndicators

STATE_FILE = "local_hpe_state.json"
AUDIT_FILE = "local_hpe_audit.json"

class LocalHPEShadowRunner:
    def __init__(self):
        self.engine = HedgeProtectionEngine()
        self.indicators = LocalHPEIndicators()
        self.running = False
        
        # Mocks for demonstration
        self.mock_combined_loss = -5.0
        self.mock_btc_price = 60000.0
        
    def start(self):
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()
        
    def stop(self):
        self.running = False
        
    def _run_loop(self):
        print("HPE Shadow Runner Started on localhost... Connecting to live API...")
        import urllib.request
        while self.running:
            try:
                # 1. Fetch live bot state (defaults to localhost)
                api_url = os.environ.get("BOT_API_URL", "http://127.0.0.1:5000/api/status")
                try:
                    req = urllib.request.Request(api_url)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        bot_data = json.loads(response.read().decode())
                except Exception as e:
                    print(f"Failed to fetch from main bot: {e}")
                    bot_data = None
                
                if not bot_data:
                    print("Waiting for bot API to become available...")
                    time.sleep(2)
                    continue

                # 2. Extract live parameters
                positions = bot_data.get('positions', [])
                positions_active = len(positions) > 0
                
                # Calculate combined option loss pct
                total_pnl_usd = bot_data.get('options_pnl_usd', 0)
                total_entry_premium = bot_data.get('total_entry_premium', 0)
                
                if total_entry_premium > 0:
                    combined_loss_pct = (total_pnl_usd / total_entry_premium) * 100
                else:
                    combined_loss_pct = 0.0
                    
                btc_mark_price = bot_data.get('btc_price', 60000.0)
                
                # Find worst bleeding leg
                worst_leg = None
                worst_leg_pnl = 0
                worst_leg_delta = 0
                worst_leg_premium = 0
                for p in positions:
                    if p.get('leg_pnl_usd', 0) < worst_leg_pnl:
                        worst_leg_pnl = p.get('leg_pnl_usd', 0)
                        worst_leg = p.get('symbol', 'Unknown')
                        worst_leg_delta = p.get('delta', 0.05)
                        worst_leg_premium = p.get('entry_premium_usd', 150.0)
                        
                bleeding_leg_loss_usd = worst_leg_pnl

                # 3. Get real indicators
                ind_data = self.indicators.fetch_and_calculate()
                
                # 4. Evaluate using the actual Engine
                import os
                if os.path.exists('force_hedge.flag'):
                    status = self.engine.force_hedge_trigger(bot_data, btc_mark_price)
                    try:
                        os.remove('force_hedge.flag')
                    except Exception:
                        pass
                elif os.path.exists('close_hedge.flag'):
                    if getattr(self.engine, 'active_hedge', None):
                        status = self.engine.force_close_hedge("Manual Square Off")
                    try:
                        os.remove('close_hedge.flag')
                    except Exception:
                        pass
                    if not getattr(self.engine, 'active_hedge', None):
                        # Force a re-evaluation if it closed successfully, or just let it evaluate normally next loop
                        pass
                else:
                    status = self.engine.evaluate(
                        combined_option_loss_pct=combined_loss_pct,
                        bleeding_leg_loss_usd=bleeding_leg_loss_usd,
                        bleeding_leg_premium_usd=worst_leg_premium,
                        btc_delta=worst_leg_delta,
                        btc_mark_price=btc_mark_price,
                        supertrend_dir=ind_data['supertrend'],
                        adx_value=ind_data['adx'],
                        pivot_status=ind_data['pivot_status'],
                        rejection_signal=ind_data.get('rejection_signal', 'SAFE'),
                        option_positions_active=positions_active
                    )
                
                # 5. Enrich status for the dashboard (Rule 13 Payload)
                full_payload = {
                    "monitoring_active": status['state'] != 'DORMANT',
                    "trigger_status": "Breached -10%" if combined_loss_pct <= -10.0 else "Safe",
                    "combined_loss": combined_loss_pct,
                    "supertrend": ind_data['supertrend'],
                    "adx": ind_data['adx'],
                    "pivot_status": ind_data['pivot_status'],
                    "trend": "BEARISH" if ind_data['supertrend'] == 'SELL' else "BULLISH",
                    "bleeding_leg": worst_leg or "None",
                    "remaining_risk": abs(worst_leg_pnl) if worst_leg_pnl < 0 else 0,
                    "expected_btc_move": 500,
                    "hedge_btc_qty": status.get('hedge_qty', 0),
                    "hedge_side": status.get('hedge_side', None),
                    "coverage_pct": 70,
                    "hedge_pnl": status.get('hedge_pnl_pct', 0),
                    "hedge_pnl_usd": status.get('hedge_pnl_usd', 0),
                    "hedge_entry_price": status.get('hedge_entry_price', 0),
                    "hedge_current_price": status.get('hedge_current_price', 0),
                    "exit_reason": status.get('exit_reason', ''),
                    "state": status['state'],
                    "standby_reason": status.get('standby_reason', ''),
                    "last_updated": time.time()
                }
                
                with open(STATE_FILE, 'w') as f:
                    json.dump(full_payload, f)
                    
                with open(AUDIT_FILE, 'a') as f:
                    f.write(json.dumps(full_payload) + "\n")
                    
                time.sleep(2) # Update every 2 seconds for UI visualization
            except Exception as e:
                print(f"Shadow Runner Error: {e}")
                time.sleep(2)

if __name__ == "__main__":
    runner = LocalHPEShadowRunner()
    runner.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        runner.stop()
