from local_hpe_engine import HedgeProtectionEngine

def test_whipsaw_logic():
    engine = HedgeProtectionEngine()
    
    print("--- SCENARIO 1: WHIPSAW BLOCKER ---")
    status1 = engine.evaluate(
        combined_option_loss_pct=-11.0, 
        bleeding_leg_loss_usd=-150, 
        bleeding_leg_premium_usd=100, 
        btc_delta=0.05, 
        btc_mark_price=64000, 
        supertrend_dir='SELL', 
        adx_value=25, 
        pivot_status='LIVE', 
        rejection_signal='BULLISH_REJECTION'
    )
    print(f"Status: {status1['state']} | Reason: {status1.get('standby_reason')}")
    print(f"Hedge Open? {status1['hedge_active']}")
    
    print("\n--- SCENARIO 2: NORMAL HEDGE ACTIVATION ---")
    status2 = engine.evaluate(
        combined_option_loss_pct=-11.0, 
        bleeding_leg_loss_usd=-150, 
        bleeding_leg_premium_usd=100, 
        btc_delta=0.05, 
        btc_mark_price=64000, 
        supertrend_dir='SELL', 
        adx_value=25, 
        pivot_status='LIVE', 
        rejection_signal='SAFE'
    )
    print(f"Status: {status2['state']} | Reason: {status2.get('standby_reason')}")
    print(f"Hedge Open? {status2['hedge_active']}")
        
    print("\n--- SCENARIO 3: INSTANT KILL SWITCH ON LATE WHIPSAW ---")
    status3 = engine.evaluate(
        combined_option_loss_pct=-11.0, 
        bleeding_leg_loss_usd=-150, 
        bleeding_leg_premium_usd=100, 
        btc_delta=0.05, 
        btc_mark_price=64200, 
        supertrend_dir='SELL', 
        adx_value=25, 
        pivot_status='LIVE', 
        rejection_signal='BULLISH_REJECTION'
    )
    print(f"Status: {status3['state']} | Reason: {status3.get('standby_reason')}")
    print(f"Hedge Open? {status3['hedge_active']}")
    print(f"Last Exit Reason: {status3.get('exit_reason')}")
    
    print("\n--- SCENARIO 4: OPTIONS RECOVERY DE-HEDGE ---")
    engine.state = 'MONITORING'
    engine.evaluate(
        combined_option_loss_pct=-11.0, bleeding_leg_loss_usd=-150, bleeding_leg_premium_usd=100, btc_delta=0.05, 
        btc_mark_price=64000, supertrend_dir='SELL', adx_value=25, pivot_status='LIVE', rejection_signal='SAFE'
    )
    
    status4 = engine.evaluate(
        combined_option_loss_pct=-3.0, 
        bleeding_leg_loss_usd=-20, 
        bleeding_leg_premium_usd=100, 
        btc_delta=0.05, 
        btc_mark_price=64500, 
        supertrend_dir='SELL', 
        adx_value=25, 
        pivot_status='LIVE', 
        rejection_signal='SAFE'
    )
    print(f"Status: {status4['state']} | Reason: {status4.get('standby_reason')}")
    print(f"Hedge Open? {status4['hedge_active']}")
    print(f"Last Exit Reason: {status4.get('exit_reason')}")

if __name__ == "__main__":
    test_whipsaw_logic()
