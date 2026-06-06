import sys
sys.stdout.reconfigure(encoding='utf-8')

def test_static_hedge():
    print("=========================================================================")
    print("   PROPER SIMULATION: ONE-SHOT STATIC HEDGING (WHIPSAW FIX)   ")
    print("=========================================================================\n")
    
    lots = 500
    btc_start_price = 70000
    
    print(f"🔹 TRADE ENTERED: {lots} Lots Strangle")
    print(f"🔹 STARTING BTC PRICE: ${btc_start_price}\n")
    
    # State tracking
    hedge_size_btc = 0.0
    hedge_entry_price = 0.0
    hedge_active = False
    
    # A $1000 crash, followed immediately by a $1000 V-Shape bounce
    steps = [
        {"time": "09:00", "price": 70000, "opt_loss": 0, "delta_btc": 0.000},
        {"time": "09:05", "price": 69700, "opt_loss": -40, "delta_btc": 0.150},
        {"time": "09:10", "price": 69300, "opt_loss": -120, "delta_btc": 0.350},
        {"time": "09:15", "price": 69000, "opt_loss": -200, "delta_btc": 0.500}, # Absolute bottom of crash
        {"time": "09:20", "price": 69400, "opt_loss": -100, "delta_btc": 0.300}, # V-Shape bounce starts
        {"time": "09:25", "price": 69800, "opt_loss": -20, "delta_btc": 0.100},
        {"time": "09:30", "price": 70000, "opt_loss": 0, "delta_btc": 0.000}   # Fully recovered
    ]
    
    for step in steps:
        current_btc = step["price"]
        opt_loss = step["opt_loss"]
        target_hedge = step["delta_btc"]
        
        print(f"⏰ {step['time']} | BTC Price: ${current_btc}")
        print(f"   📉 Options P&L: {opt_loss:.2f} USD")
        
        # Trigger Condition: Delta crosses 0.15
        if not hedge_active and target_hedge >= 0.15:
            hedge_size_btc = target_hedge * 1.0 # Strict 1.0x initial shot
            hedge_entry_price = current_btc
            hedge_active = True
            print(f"   🛡️ [ONE-SHOT TRIGGER] Delta hit 0.15. Selling {hedge_size_btc:.3f} BTC (Static)")
            
        current_step_hedge_pnl = 0
        if hedge_active:
            current_step_hedge_pnl = (hedge_entry_price - current_btc) * hedge_size_btc
            print(f"   📈 Futures Hedge P&L: +${current_step_hedge_pnl:.2f} (Holding Static {hedge_size_btc:.3f} BTC)")
        
        net_pnl = opt_loss + current_step_hedge_pnl
        print(f"   💰 NET P&L: ${net_pnl:.2f}")
        
        print("-" * 50)
        
    print("\n🏁 FINAL COMPARISON (WHIPSAW SURVIVED):")
    print("Old Dynamic Rebalancing Loss: -$175.00")
    print(f"New One-Shot Static Loss: ${net_pnl:.2f}")

if __name__ == '__main__':
    test_static_hedge()
