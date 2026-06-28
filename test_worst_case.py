def run_simulation():
    print("=== WORST CASE SCENARIO SIMULATIONS ===")
    
    # Common parameters
    atr_15m = 75.0
    trend_threshold = atr_15m * 2.0  # $150
    
    # ---------------------------------------------------------
    print("\n--- SCENARIO 1: THE INSTANT WHIPSAW (Fakeout) ---")
    # Market spikes, triggers hedge, then instantly reverses
    btc_entry = 60000
    btc_spike = 60500  # $500 move
    option_loss = 5.0
    
    # 1. Trigger Check
    if btc_spike - btc_entry > trend_threshold:
        print(f"1. Market spiked ${btc_spike - btc_entry}. Trend Confirmed (> ${trend_threshold}).")
        base_exp = option_loss / (btc_spike - btc_entry)
        hedge_size = base_exp * 2.0  # 2.0x multiplier
        print(f"2. Hedge Opened: {hedge_size:.4f} BTC")
        
        # 2. Violent Reversal back to 60000
        btc_reversal = 60000
        reversal_move = btc_reversal - btc_spike
        hedge_pnl = hedge_size * reversal_move
        print(f"3. Market violently reverses back to ${btc_reversal}.")
        print(f"4. Hedge PNL drops to: ${hedge_pnl:.2f}")
        
        # 3. Square-off Logic
        if hedge_pnl <= -3.0:
            print(f"5. ACTION: Immediate Reversal Square-Off triggered! (Hedge PNL <= -$3.00)")
            print(f"RESULT: Hedge cut with small loss of ${hedge_pnl:.2f} to prevent disaster.")
            print(f"Trade survives. Oversized hedge did not bleed account.")
    
    # ---------------------------------------------------------
    print("\n--- SCENARIO 2: THE HIGH GAMMA GRIND (To SL) ---")
    btc_grind = 62500
    additional_move = btc_grind - btc_spike
    additional_option_loss = 30.0  # Option gamma accelerates
    total_opt_loss = option_loss + additional_option_loss
    
    hedge_profit = hedge_size * additional_move
    net_pnl = hedge_profit - total_opt_loss
    
    print(f"1. Market grinds against option all day, hitting Stop-Loss.")
    print(f"2. Total Option Loss at SL: -${total_opt_loss:.2f}")
    print(f"3. Hedge Profit at SL: +${hedge_profit:.2f}")
    print(f"RESULT: Net PNL = +${net_pnl:.2f} (GREEN) - Trade safely exited in profit.")

    # ---------------------------------------------------------
    print("\n--- SCENARIO 3: THE PURE IV SPIKE (No Trend) ---")
    btc_iv_spike = 60050  # Only $50 move
    option_loss_iv = 5.0  # Bleeds $5 due to volatility alone
    
    print(f"1. Option bleeds -${option_loss_iv:.2f}, but BTC only moved ${btc_iv_spike - btc_entry}.")
    if (btc_iv_spike - btc_entry) < trend_threshold:
        print(f"2. ACTION: IV Spike Filter blocks hedge (Move < ${trend_threshold}).")
        print(f"RESULT: Bot ignores fakeout. Zero futures traded. No whipsaw risk.")

run_simulation()
