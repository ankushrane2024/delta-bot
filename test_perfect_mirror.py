import sys
sys.stdout.reconfigure(encoding='utf-8')

def test_perfect_mirror():
    print("=========================================================================")
    print("   PROPER SIMULATION: 1-TO-1 DYNAMIC DELTA HEDGING (WHIPSAW FIX)   ")
    print("=========================================================================\n")
    
    lots = 500
    btc_start_price = 70000
    
    print(f"🔹 TRADE ENTERED: {lots} Lots Strangle")
    print(f"🔹 STARTING BTC PRICE: ${btc_start_price}\n")
    
    # State tracking
    hedge_size_btc = 0.0
    hedge_entry_price = 0.0
    realized_hedge_pnl = 0.0
    
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
        
        # Real-time PnL of holding the CURRENT hedge
        unrealized_hedge_pnl = 0
        if hedge_size_btc > 0:
            unrealized_hedge_pnl = (hedge_entry_price - current_btc) * hedge_size_btc
            
        total_hedge_pnl = realized_hedge_pnl + unrealized_hedge_pnl
            
        if hedge_size_btc > 0 or realized_hedge_pnl != 0:
            print(f"   📈 Futures Hedge P&L: +${total_hedge_pnl:.2f} (Holding {hedge_size_btc:.3f} BTC)")
        
        net_pnl = opt_loss + total_hedge_pnl
        print(f"   💰 NET P&L: ${net_pnl:.2f}")
        
        # Rebalancing Logic (The Fix)
        if abs(target_hedge - hedge_size_btc) >= 0.01:
            diff = target_hedge - hedge_size_btc
            if diff > 0:
                print(f"   🛡️ [REBALANCE] Selling {diff:.3f} BTC to match Option Delta.")
                # When adding to a short, we average the entry price
                if hedge_size_btc == 0:
                    hedge_entry_price = current_btc
                else:
                    total_val = (hedge_entry_price * hedge_size_btc) + (current_btc * diff)
                    hedge_entry_price = total_val / (hedge_size_btc + diff)
            else:
                buy_amount = -diff
                print(f"   🛡️ [REBALANCE] Buying {buy_amount:.3f} BTC to lock in profit and shrink hedge!")
                # When shrinking a short, the realized profit is locked in
                locked_profit = (hedge_entry_price - current_btc) * buy_amount
                realized_hedge_pnl += locked_profit
            
            hedge_size_btc = target_hedge
        
        print("-" * 50)

if __name__ == '__main__':
    test_perfect_mirror()
