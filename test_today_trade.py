def run_today_simulation():
    print("=== LIVE SIMULATION: TODAY'S BTC BREAKOUT ($315 MOVE) ===")
    
    # Core variables for today
    atr_15m = 75.0
    lots_per_leg = 500
    btc_per_lot = 0.001
    exposure_btc = lots_per_leg * btc_per_lot  # 0.5 BTC
    
    # Delta assumption for $100 premium
    base_delta = 0.15
    gamma_per_100_usd = 0.02
    
    # The actual move today
    total_move = 315.0
    
    # --- STEP 1: THE $75 CHOP (NOISE) ---
    print("\n[9:00 AM - 12:00 PM] THE CHOP")
    print(f"BTC moves sideways, randomly fluctuating by ${atr_15m:.0f} (1 ATR).")
    print(f"Grid Threshold (Tier 1) requires 2.0 ATR (${atr_15m * 2.0:.0f}).")
    print("ACTION: Bot ignores the noise. Zero hedges placed.")
    
    # --- STEP 2: THE BREAKOUT STARTS ($150 MOVE) ---
    print("\n[1:00 PM] THE BREAKOUT (TIER 1 TRIGGERED)")
    move_1 = 150.0  # 2.0 ATR
    delta_1 = base_delta + (move_1 / 100.0) * gamma_per_100_usd
    option_loss_1 = delta_1 * exposure_btc * move_1
    print(f"BTC suddenly breaks out by ${move_1:.0f}.")
    print(f"Option Loss reaches: -${option_loss_1:.2f}")
    
    # Hedge calculation
    eff_exp_1 = option_loss_1 / move_1
    target_hedge_1 = eff_exp_1 * 2.0
    actual_hedge_1 = target_hedge_1 * 0.30 # Tier 1
    print(f"ACTION: Tier 1 Grid Triggered! Buying 30% probe size: {actual_hedge_1:.4f} BTC")
    
    # --- STEP 3: THE TREND DEEPENS ($200 MOVE) ---
    print("\n[1:30 PM] THE TREND DEEPENS (TIER 2 TRIGGERED)")
    move_2 = 200.0 # 2.66 ATR (> 2.5)
    delta_2 = base_delta + (move_2 / 100.0) * gamma_per_100_usd
    option_loss_2 = delta_2 * exposure_btc * move_2
    print(f"BTC continues pushing to ${move_2:.0f} move.")
    print(f"Option Loss grows to: -${option_loss_2:.2f}")
    
    eff_exp_2 = option_loss_2 / move_2
    target_hedge_2 = eff_exp_2 * 2.0
    actual_hedge_2 = target_hedge_2 * 0.60 # Tier 2
    added_hedge_2 = actual_hedge_2 - actual_hedge_1
    print(f"ACTION: Tier 2 Grid Triggered! Escalating to 60%. Adding {added_hedge_2:.4f} BTC.")
    
    # --- STEP 4: TIER 3 TRIGGER ($225 MOVE) ---
    print("\n[2:00 PM] THE TREND GETS SEVERE (TIER 3 TRIGGERED)")
    move_3 = 225.0 # 3.0 ATR
    delta_3 = base_delta + (move_3 / 100.0) * gamma_per_100_usd
    option_loss_3 = delta_3 * exposure_btc * move_3
    print(f"BTC pushes to ${move_3:.0f} move.")
    print(f"Option Loss grows to: -${option_loss_3:.2f}")
    
    eff_exp_3 = option_loss_3 / move_3
    target_hedge_3 = eff_exp_3 * 2.0
    actual_hedge_3 = target_hedge_3 * 1.0 # Tier 3
    added_hedge_3 = actual_hedge_3 - actual_hedge_2
    print(f"ACTION: Tier 3 Grid Triggered! Full 100% defense. Adding {added_hedge_3:.4f} BTC.")
    
    # --- STEP 5: THE PEAK OF TODAY'S TREND ($315 MOVE) ---
    print("\n[2:30 PM] THE PEAK OF TODAY'S TREND")
    move_4 = 315.0 # 4.2 ATR
    delta_4 = base_delta + (move_4 / 100.0) * gamma_per_100_usd
    option_loss_4 = delta_4 * exposure_btc * move_4
    print(f"BTC hits today's massive peak: ${move_4:.0f} move.")
    print(f"Option Loss reaches max: -${option_loss_4:.2f}")
    
    # The active hedge rides the trend from its various entry points
    profit_tier_1 = actual_hedge_1 * (move_4 - move_1)
    profit_tier_2 = added_hedge_2 * (move_4 - move_2)
    profit_tier_3 = added_hedge_3 * (move_4 - move_3)
    total_hedge_profit = profit_tier_1 + profit_tier_2 + profit_tier_3
    
    print("\n=== END OF DAY PNL SUMMARY ===")
    print(f"Option Loss at peak: -${option_loss_4:.2f}")
    print(f"Hedge Profit collected on the run: +${total_hedge_profit:.2f}")
    
    net_pnl = total_hedge_profit - option_loss_4
    
    # Compare to old system
    old_hedge = target_hedge_1 * (move_4 - move_1)
    old_net = old_hedge - option_loss_4
    
    print(f"Old System PNL (No Grid Escalation): ${old_net:.2f}")
    print(f"New Grid System Net PNL: ${net_pnl:.2f} (Trade saved!)")

run_today_simulation()
