from local_hpe_engine import HedgeProtectionEngine

def test_hedge_math():
    print("\n" + "="*50)
    print(" HEDGE MATHEMATICS & LOSS RECOVERY SIMULATION ")
    print("="*50)

    # Initial Portfolio State
    # You sold 1 BTC of PUT options (bullish). Delta is +0.20
    # Premium collected = $1000. Stop Loss is when loss hits -$1000.
    btc_entry_price = 65000
    option_premium = 1000
    option_delta = 0.20
    
    print(f"Option Premium Collected: ${option_premium}")
    print(f"Option Delta: +{option_delta} (Long Exposure)")
    
    # Engine Setup
    engine = HedgeProtectionEngine()
    
    # Market drops, Option starts losing. 
    # At -11.5% loss (approx -$115 loss), Tier 1 Triggers.
    btc_price_tier1 = 64000
    option_loss_tier1 = -115
    print(f"\n[MARKET CRASH] BTC drops to {btc_price_tier1}.")
    print(f"Option Loss: ${option_loss_tier1} (-11.5%)")
    
    engine.evaluate(-11.5, option_loss_tier1, option_premium, option_delta, btc_price_tier1, 'SELL', 30, 'BREAKDOWN_DOWN')
    
    print(f"-> Hedge Opened! Side: {engine.active_hedge['side']}, Qty: {engine.active_hedge['qty']:.4f} BTC")
    
    # Market crashes heavily. BTC drops to $60,000.
    btc_price_crash = 60000
    
    # Calculate Option Loss at $60,000
    # BTC dropped $5,000. Delta is 0.20. Loss = 5000 * 0.20 = $1,000 loss
    option_loss_crash = -1000
    
    print(f"\n[BLACK SWAN CRASH] BTC drops to {btc_price_crash}.")
    print(f"Option Portfolio is bleeding heavily. Loss: ${option_loss_crash} (-100%)")
    
    # Trigger Tier 2 and Tier 3 on the way down
    engine.evaluate(-15.5, -155, option_premium, option_delta, 63000, 'SELL', 30, 'BREAKDOWN_DOWN') # Tier 2
    engine.evaluate(-20.5, -205, option_premium, option_delta, 62000, 'SELL', 30, 'BREAKDOWN_DOWN') # Tier 3
    
    hedge_qty = engine.active_hedge['qty']
    hedge_avg_entry = engine.active_hedge['entry_price']
    
    print(f"-> Hedge Scaled to Tier 3! Final Qty: {hedge_qty:.4f} BTC @ Avg Price: {hedge_avg_entry:.2f}")
    
    # Calculate Hedge Profit
    # It's a SHORT hedge. Profit = (Avg Entry - Current Price) * Qty
    hedge_profit = (hedge_avg_entry - btc_price_crash) * hedge_qty
    
    print("\n" + "="*50)
    print(" FINAL PNL REPORT ")
    print("="*50)
    print(f"Option Trade Loss: -${abs(option_loss_crash):.2f}")
    print(f"Hedge Trade Profit: +${hedge_profit:.2f}")
    
    net_pnl = option_loss_crash + hedge_profit
    print(f"\nNET PORTFOLIO IMPACT: ${net_pnl:.2f}")
    
    if net_pnl > -600: # We expect around -580 because of the DCA scale-in sacrifice
        print("[SUCCESS] The Hedge absorbed the massive crash and reduced the option loss by over 40%!")
        print("Note: Because we use DCA Scaling (entering late at 63k and 62k instead of 64k), we sacrifice some coverage to prevent whipsaw losses.")
    else:
        print("[FAILURE] The Hedge did not cover enough loss.")

if __name__ == "__main__":
    test_hedge_math()
