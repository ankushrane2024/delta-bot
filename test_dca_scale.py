import logging
from local_hpe_engine import HedgeProtectionEngine

# Configure basic logging for visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_test():
    engine = HedgeProtectionEngine()
    print("Testing Tier 1 Trigger (-7.0%)")
    
    # Mock evaluate trigger
    # evaluate(self, combined_option_loss_pct, bleeding_leg_loss_usd, bleeding_leg_premium_usd, btc_delta, btc_mark_price, supertrend_dir, adx_value, pivot_status, rejection_signal='SAFE', option_positions_active=True)
    engine.evaluate(-7.5, -500, 1000, 0.10, 64000, 'SELL', 30, 'BREAKDOWN_DOWN')
    print(f"Engine State after Tier 1: {engine.state}")
    if engine.active_hedge:
        print(f"Hedge: Qty = {engine.active_hedge['qty']}, Tier = {engine.active_hedge.get('scale_tier')}")

    print("\nTesting Tier 2 Trigger (-9.0%)")
    engine.evaluate(-9.5, -600, 1000, 0.10, 63000, 'SELL', 30, 'BREAKDOWN_DOWN')
    if engine.active_hedge:
        print(f"Hedge: Qty = {engine.active_hedge['qty']}, Tier = {engine.active_hedge.get('scale_tier')}")

    print("\nTesting Tier 3 Trigger (-11.0%)")
    engine.evaluate(-11.5, -700, 1000, 0.10, 62000, 'SELL', 30, 'BREAKDOWN_DOWN')
    if engine.active_hedge:
        print(f"Hedge: Qty = {engine.active_hedge['qty']}, Tier = {engine.active_hedge.get('scale_tier')}")

if __name__ == "__main__":
    run_test()
