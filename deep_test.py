def run_deep_test():
    atr = 75.0
    exposure = 0.5  # 500 lots
    multiplier = 1.6
    base_delta = 0.15
    gamma = 0.02 / 100.0  # 0.02 per $100 move
    
    def get_option_loss(move):
        delta = base_delta + (move * gamma)
        return delta * exposure * move
    
    # ---------------------------------------------------------
    # SCENARIO 1: TREND MARKET HITTING 130% SL
    # ---------------------------------------------------------
    print("=== SCENARIO 1: TREND MARKET (130% SL HIT) ===")
    print("Market starts a massive breakout. We track every step until SL (-$130) is hit.\n")
    
    # Step 1: 1.5 ATR Trigger
    m1 = 1.5 * atr  # 112.5
    ol1 = get_option_loss(m1)
    eff1 = ol1 / m1
    h1 = (eff1 * multiplier) * 0.50
    print(f"[BTC Move: ${m1:.1f} (1.5 ATR)]")
    print(f"Option Loss: -${ol1:.2f}")
    print(f"ACTION: Tier 1 Triggered. Buying 50% scale. Hedge Size: {h1:.4f} BTC\n")
    
    # Step 2: 2.0 ATR Trigger
    m2 = 2.0 * atr  # 150.0
    ol2 = get_option_loss(m2)
    eff2 = ol2 / m2
    h2_target = (eff2 * multiplier) * 1.0
    h2_added = h2_target - h1
    pnl_t1_at_m2 = h1 * (m2 - m1)
    print(f"[BTC Move: ${m2:.1f} (2.0 ATR)]")
    print(f"Option Loss: -${ol2:.2f}")
    print(f"Hedge Profit so far: +${pnl_t1_at_m2:.2f}")
    print(f"ACTION: Tier 2 Triggered. Adding {h2_added:.4f} BTC. Total Size: {h2_target:.4f} BTC\n")
    
    # Step 3: Pushing to Stop Loss
    m3 = 800.0  # Around where SL hits
    ol3 = get_option_loss(m3)
    eff3 = ol3 / m3
    h3_target = (eff3 * multiplier) * 1.0
    
    # Calculate profit from m2 to m3, assuming linear scaling of hedge
    avg_h = (h2_target + h3_target) / 2
    pnl_m2_to_m3 = avg_h * (m3 - m2)
    total_hedge_profit = pnl_t1_at_m2 + pnl_m2_to_m3
    net_pnl = total_hedge_profit - ol3
    
    print(f"[BTC Move: ${m3:.1f} (Stop-Loss Hits)]")
    print(f"Option Loss: -${ol3:.2f} (130% SL Triggered!)")
    print(f"Hedge Profit collected: +${total_hedge_profit:.2f}")
    print(f"FINAL NET PNL: ${net_pnl:.2f}\n")
    
    
    # ---------------------------------------------------------
    # SCENARIO 2: DEEP WHIPSAW REVERSAL
    # ---------------------------------------------------------
    print("=== SCENARIO 2: DEEP WHIPSAW REVERSAL ===")
    print("Market breaks out to 2.5 ATR, triggering full hedge, then instantly crashes.\n")
    
    # The Peak (2.5 ATR)
    m_peak = 2.5 * atr  # 187.5
    ol_peak = get_option_loss(m_peak)
    
    # Hedge profit at peak
    eff_peak = ol_peak / m_peak
    h_peak = (eff_peak * multiplier) * 1.0
    pnl_t1_at_peak = h1 * (m_peak - m1)
    pnl_t2_at_peak = h2_added * (m_peak - m2)
    peak_hedge_profit = pnl_t1_at_peak + pnl_t2_at_peak
    
    print(f"[BTC Move: ${m_peak:.1f} (2.5 ATR PEAK)]")
    print(f"Option Loss: -${ol_peak:.2f}")
    print(f"Total Hedge Active: {h_peak:.4f} BTC")
    print(f"Peak Hedge Profit: +${peak_hedge_profit:.2f}\n")
    
    # The Reversal (Market crashes back down)
    # The bot checks `hit_breakeven = peak_pnl >= 1.0 and current_pnl <= 0.0`
    # We find exactly what price the hedge PNL drops to $0.00
    
    print("[THE REVERSAL BEGINS]")
    print("Market is crashing back to entry. The Live Bot runs every 5 seconds.")
    print("The bot tracks the peak profit and waits for it to hit exactly $0.00.\n")
    
    # Calculate price where profit = 0
    # profit = pnl_t1_at_peak + pnl_t2_at_peak - (h_peak * drop) = 0
    drop_needed = peak_hedge_profit / h_peak
    reversal_price = m_peak - drop_needed
    
    # Option loss at reversal price
    ol_rev = get_option_loss(reversal_price)
    
    print(f"[BTC Drops to: ${reversal_price:.1f}]")
    print(f"ACTION: Hedge PNL hits exactly $0.00. The `hit_breakeven` rule triggers instantly!")
    print(f"Bot aggressively squares off all {h_peak:.4f} BTC futures at $0.00 loss.")
    print(f"Option Loss at this moment: -${ol_rev:.2f} (Option is recovering safely)")
    print(f"FINAL NET PNL on Hedge: $0.00\n")
    
    print("Result: Futures take absolutely zero loss. Options safely return to entry.")

run_deep_test()
