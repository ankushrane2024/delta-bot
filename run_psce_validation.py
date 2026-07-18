import time
import json
import traceback
from datetime import datetime
from psce import PremiumSellingConditionsEngine
from api_client import DeltaIndiaClient
from dvol_provider import DVOLProvider
from audit_manager import audit_system
from bot_engine import DeltaTradingEngine

# Mocking the client/DVOL for specific tests
class MockAPIClient:
    def __init__(self):
        self.ws_connected = True
        self.current_btc_price = 64000.0
    def get_realtime_ticker(self, symbol):
        if symbol == "BTCUSD":
            return {'mark_price': self.current_btc_price}
        return {'mark_price': 0.0}

class MockDVOL:
    def __init__(self):
        self.data_history = []
        for i in range(60):
            self.data_history.append({"time": time.time() * 1000 - i*60000, "close": 50.0})
    def get_history(self):
        return self.data_history

def run_tests():
    report = []
    
    print("--- 2. API Verification ---")
    dvol = MockDVOL()
    api = MockAPIClient()
    psce = PremiumSellingConditionsEngine(api, dvol)
    
    # 2. API Verification
    eval_result = psce.evaluate_conditions()
    report.append(f"API Payload:\n{json.dumps(eval_result, indent=2)}")
    
    # 4. Data Validation Test (Negative IV, Null Price)
    print("--- 4. Data Validation Test ---")
    dvol.data_history = [{"time": time.time()*1000, "close": -5.0}] # Negative IV
    neg_iv_result = psce.evaluate_conditions()
    report.append(f"Negative IV Decision: {neg_iv_result['trade_allowed']} | Reason: {neg_iv_result['reasons']}")
    
    # 5. Stale Feed Test
    print("--- 5. Stale Feed Test ---")
    dvol.data_history = [{"time": (time.time() - 3600)*1000, "close": 50.0}] # 1 hour old
    stale_result = psce.evaluate_conditions()
    report.append(f"Stale Feed Decision: {stale_result['trade_allowed']} | Reason: {stale_result['reasons']}")
    
    # 6. Exchange Disconnect Test
    print("--- 6. Exchange Disconnect Test ---")
    api.current_btc_price = 0
    disconnect_result = psce.evaluate_conditions()
    report.append(f"Disconnect Decision: {disconnect_result['trade_allowed']} | Reason: {disconnect_result['reasons']}")
    
    # 7. Master Gate & 8. Force Entry Block Verification
    print("--- 7 & 8. Master Gate & Force Entry Test ---")
    # Bot engine with mock api
    bot = DeltaTradingEngine()
    bot.execution.mode = "PAPER"
    bot.premium_engine = psce # Force the offline PSCE
    bot.today_trade_status = ""
    # Test manual entry
    success, msg = bot.run_test_order()
    report.append(f"Test Order Result (Force): Success={success}, Message={msg}")
    
    # Test run_entry_cycle with force=True
    bot.run_entry_cycle(force=True)
    report.append(f"Entry Cycle Status: {bot.today_trade_status} | Reason: {bot.today_skip_reason}")
    
    # 10. Live Monitoring Test
    print("--- 10. Live Monitoring Test ---")
    bot.execution.active_positions = {"C-60000": {"side": "sell", "size": 1}}
    # Trigger deterioration
    api.current_btc_price = 64000.0
    dvol.data_history = [] # Cause failure
    try:
        # Simulate monitor loop psce check
        psce_mon = bot.premium_engine.evaluate_conditions(mode="MONITOR")
        if psce_mon.get('zone') == "LOW EDGE" or not psce_mon.get('trade_allowed', False):
            snapshot = bot._build_audit_snapshot(64000, 0, 0, 0, 0, "PSCE_DETERIORATION_ALERT", "Test Deterioration")
            audit_system.log_critical_event("PSCE Condition Deterioration Alert", "psce", "evaluate_conditions", snapshot, "Test")
            report.append("Live Monitor triggered Deterioration Alert to Audit.")
    except Exception as e:
        report.append(f"Live Monitor Error: {e}")
        
    # 11. Audit Verification
    print("--- 11. Audit Verification ---")
    audit_logs = [e for e in audit_system.session_events if e["Event Type"] in ["Trade Execution Blocked by PSCE", "PSCE Condition Deterioration Alert"]]
    for log in audit_logs[-2:]:
        report.append(f"Audit Log Found: {log['Event Type']} | Reason: {log['Reason']}")

    # 16. Stress Test
    print("--- 16. Stress Test (1000 evals) ---")
    dvol.data_history = [{"time": time.time() * 1000 - i*60000, "close": 50.0} for i in range(60)]
    start_t = time.perf_counter()
    errors = 0
    for _ in range(1000):
        try:
            res = psce.evaluate_conditions()
        except:
            errors += 1
    duration = time.perf_counter() - start_t
    report.append(f"1000 Evals Completed in {duration:.2f}s. Errors: {errors}")

    with open("psce_validation_output.txt", "w") as f:
        f.write("\n".join(report))
        
    print("Test complete. Results saved to psce_validation_output.txt")

if __name__ == "__main__":
    run_tests()
