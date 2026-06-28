def simulate(multiplier):
    print(f"\n--- Testing Multiplier: {multiplier}x ---")
    
    # 1. Option starts losing
    btc_entry = 60000
    btc_trigger = 60500
    btc_move = btc_trigger - btc_entry
    option_loss_at_trigger = 5.0
    
    # Calculate hedge
    base_exposure = option_loss_at_trigger / btc_move
    hedge_size = base_exposure * multiplier
    print(f"Triggered at BTC=${btc_trigger}. Option Loss: -${option_loss_at_trigger}.")
    print(f"Base Delta: {base_exposure:.4f} | Hedge Size: {hedge_size:.4f} BTC")
    
    # 2. Trend continues to Stop Loss
    btc_sl = 62500
    additional_btc_move = btc_sl - btc_trigger
    
    # Simulating option gamma: delta increases from 0.01 to 0.02
    # So average delta is ~0.015 over the next $2000 move
    additional_option_loss = 30.0 
    total_option_loss = option_loss_at_trigger + additional_option_loss
    
    hedge_profit = hedge_size * additional_btc_move
    
    net_pnl = hedge_profit - total_option_loss
    
    print(f"SL Hit at BTC=${btc_sl}. Total Option Loss: -${total_option_loss:.2f}")
    print(f"Hedge Profit: +${hedge_profit:.2f}")
    if net_pnl >= 0:
        print(f"Net PNL (Trade Result): +${net_pnl:.2f} (GREEN)")
    else:
        print(f"Net PNL (Trade Result): -${abs(net_pnl):.2f} (RED)")

print("=== HEDGE SIZING SIMULATION ===")
simulate(1.0)
simulate(1.5)
simulate(1.75)
simulate(2.0)
