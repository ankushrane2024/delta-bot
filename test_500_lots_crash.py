import time
import sys
sys.stdout.reconfigure(encoding='utf-8')

def simulate_500_lots_crash():
    print("================================================================")
    print("   PROPER SIMULATION: 500 LOTS MASSIVE BTC DOWNTREND CRASH   ")
    print("================================================================\n")
    
    lots = 500
    btc_exposure_per_leg = lots * 0.001 # 0.500 BTC
    total_exposure = btc_exposure_per_leg * 2 # 1.000 BTC
    entry_premium = 200.00 # USD per leg, total $400 collected
    
    print(f"🔹 TRADE ENTERED: 500 Lots Call & 500 Lots Put")
    print(f"🔹 TOTAL PREMIUM COLLECTED: $400.00")
    print(f"🔹 MAX RISK LIMIT (45% Hard Stop): -$180.00\n")
    
    btc_start_price = 70000
    
    # State tracking
    hedge_size_btc = 0.0
    hedge_entry_price = 0.0
    
    steps = [
        {"time": "09:00 AM", "drop": 0, "opt_loss": 0, "delta": 0.05},
        {"time": "09:15 AM", "drop": 200, "opt_loss": -25, "delta": 0.13},
        {"time": "09:30 AM", "drop": 400, "opt_loss": -60, "delta": 0.20},
        {"time": "09:45 AM", "drop": 700, "opt_loss": -110, "delta": 0.35},
        {"time": "10:00 AM", "drop": 1000, "opt_loss": -180, "delta": 0.45},
    ]
    
    for step in steps:
        current_btc = btc_start_price - step["drop"]
        opt_loss = step["opt_loss"]
        delta = step["delta"]
        
        # Calculate hedge PnL
        hedge_pnl = 0
        if hedge_size_btc > 0:
            hedge_pnl = (hedge_entry_price - current_btc) * hedge_size_btc
            
        net_pnl = opt_loss + hedge_pnl
        
        print(f"⏰ {step['time']} | BTC Price: ${current_btc} (Dropped ${step['drop']})")
        print(f"   -> Options P&L: {opt_loss:.2f} USD")
        
        # Hedge Logic
        if net_pnl <= -180:
            print(f"   🚨 [45% HARD STOP TRIGGERED] Net Loss hit ${net_pnl:.2f}. Bot instantly MARKET SELLS all 500 lots and closes hedge.")
            print(f"   🛡️ FINAL SECURED P&L: ${net_pnl:.2f} (Cap Protected)\n")
            break
            
        if opt_loss <= -100 and hedge_size_btc < 1.0: # Emergency Escalation
            new_hedge = 1.000 # Max escalation
            print(f"   ⚠️ [EMERGENCY HEDGE] Loss escalating! Bot scales short to {new_hedge:.3f} BTC!")
            if hedge_size_btc == 0:
                hedge_entry_price = current_btc
            hedge_size_btc = new_hedge
        elif delta >= 0.15 and hedge_size_btc == 0:
            new_hedge = delta * total_exposure * 2.0 # 2.0x Overhedge
            print(f"   🛡️ [HEDGE ACTIVATED] Delta > 0.15. Bot shorts {new_hedge:.3f} BTC futures!")
            hedge_entry_price = current_btc
            hedge_size_btc = new_hedge
            
        if hedge_size_btc > 0:
            print(f"   📈 Futures Hedge P&L: +${hedge_pnl:.2f} (Size: {hedge_size_btc:.3f} BTC)")
            
        print(f"   💰 NET TOTAL P&L: ${net_pnl:.2f}\n")
        
if __name__ == '__main__':
    simulate_500_lots_crash()
