import time
import json
import requests

def update_simulated_trade(loss_pct, call_pct, put_pct, btc_price=89500.0, trade_active=True):
    """Feeds simulated trade data into local state so dashboard updates live."""
    sim_data = {
        'options_pnl_pct': loss_pct,
        'options_pnl_usd': loss_pct * 10.0,
        'positions': [
            {'symbol': 'BTC-26JUL26-90000-C', 'pnl_pct': call_pct, 'delta': 0.35, 'size': 0.1, 'entry_premium_usd': 150.0},
            {'symbol': 'BTC-26JUL26-90000-P', 'pnl_pct': put_pct, 'delta': -0.25, 'size': 0.1, 'entry_premium_usd': 150.0}
        ],
        'btc_price': btc_price,
        'trade_active': trade_active,
        'timestamp': time.time()
    }
    with open("bot_state.json", "w") as f:
        json.dump(sim_data, f, indent=2)
    return sim_data

def run_simulation():
    print("==================================================================")
    print(" LIVE HPE SANDBOX LOSS & RECOVERY SIMULATION ")
    print("==================================================================")
    
    # Phase 1: Healthy Trade (-2% loss) -> Engine should be DORMANT
    print("\n[STEP 1] Setting Trade PnL = -2.0% (Healthy Trade)")
    update_simulated_trade(loss_pct=-2.0, call_pct=-5.0, put_pct=1.0)
    time.sleep(3)
    
    # Phase 2: Loss reaches -12% -> Engine should activate MONITORING & identify Bleeding Leg (Call)
    print("\n[STEP 2] Loss Worsens to -12.0% (Threshold -10% Reached!) -> Activating MONITORING")
    update_simulated_trade(loss_pct=-12.0, call_pct=-32.0, put_pct=8.0)
    time.sleep(4)

    # Phase 3: Loss deepens to -22% -> Bleeding leg Call at -55%
    print("\n[STEP 3] Loss Deepens to -22.0% -> Bleeding Leg Call at -55.0%")
    update_simulated_trade(loss_pct=-22.0, call_pct=-55.0, put_pct=11.0)
    time.sleep(4)

    # Phase 4: Recovery Sequence (-22% -> -16% -> -8%) -> Triggers Exit & Return to DORMANT
    print("\n[STEP 4] Recovery Phase: Loss Improves to -8.0% (> -10%) -> Triggering Trade Recovery Exit")
    update_simulated_trade(loss_pct=-8.0, call_pct=-18.0, put_pct=2.0)
    time.sleep(4)
    
    print("\n[STEP 5] Trade Completed -> Resetting State to Healthy")
    update_simulated_trade(loss_pct=0.0, call_pct=0.0, put_pct=0.0, trade_active=False)
    print("Simulation Complete!")

if __name__ == "__main__":
    run_simulation()
