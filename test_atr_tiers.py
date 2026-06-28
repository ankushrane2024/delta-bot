def simulate_atr_grid(tier1_atr, tier2_atr):
    atr = 75.0
    exposure = 0.5  # 500 lots
    multiplier = 1.6
    base_delta = 0.15
    gamma = 0.02 / 100.0
    
    def get_option_loss(move):
        delta = base_delta + (move * gamma)
        return delta * exposure * move
        
    print(f"\n=======================================================")
    print(f"GRID: TIER 1 @ {tier1_atr} ATR | TIER 2 @ {tier2_atr} ATR")
    print(f"=======================================================")
    
    # 1. THE DRAWDOWN (Unhedged Pain)
    t1_move = tier1_atr * atr
    t1_loss = get_option_loss(t1_move)
    print(f"[!] Unhedged Drawdown: Bot sleeps until -${t1_loss:.2f} loss.")
    
    # 2. SL HIT (The 130% Crash)
    m_sl = 800.0  # approximate SL
    ol_sl = get_option_loss(m_sl)
    
    eff1 = t1_loss / t1_move if t1_move > 0 else 0
    h1 = (eff1 * multiplier) * 0.50
    
    t2_move = tier2_atr * atr
    ol2 = get_option_loss(t2_move)
    eff2 = ol2 / t2_move if t2_move > 0 else 0
    h2_target = (eff2 * multiplier) * 1.0
    
    # At SL
    eff_sl = ol_sl / m_sl
    h_sl_target = (eff_sl * multiplier) * 1.0
    avg_h = (h2_target + h_sl_target) / 2
    
    profit_to_t2 = h1 * (t2_move - t1_move)
    profit_to_sl = avg_h * (m_sl - t2_move)
    total_hedge_profit = profit_to_t2 + profit_to_sl
    net_pnl_sl = total_hedge_profit - ol_sl
    print(f"[SL] At Stop-Loss (-$130): Hedge Profit +${total_hedge_profit:.2f} | Net PNL: ${net_pnl_sl:.2f}")

    # 3. EARLY WHIPSAW (Fakeout at exactly Tier 1)
    dynamic_limit = max(-50.0, min(-3.0, -3.0 * (h1 / 0.01)))
    print(f"[Whipsaw Risk] Early Fakeout Limit: ${dynamic_limit:.2f}")
    
    # 4. FINAL VERDICT
    if net_pnl_sl < 0:
        verdict = "FAILS (Loses money at Stop Loss)"
    elif t1_loss > 40:
        verdict = "DANGEROUS (Allows too much unhedged loss before waking up)"
    else:
        verdict = "EXCELLENT (Strong protection, hits target)"
    print(f"VERDICT: {verdict}")

simulate_atr_grid(1.5, 2.0)
simulate_atr_grid(2.0, 3.0)
simulate_atr_grid(3.0, 4.0)
