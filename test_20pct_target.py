import random

def run_20pct_simulation(scenario_id, scenario_type, max_atr_reached, is_whipsaw):
    atr_15m = 75.0
    multiplier = 1.5  # Adjusted from 2.0x to 1.5x to target exactly +20% overall profit
    
    # ── Live Trade Parameters (User Specified) ──
    lots_per_leg = 500
    btc_per_lot = 0.001
    exposure_btc = lots_per_leg * btc_per_lot  # 0.5 BTC
    
    premium_per_leg = 100.0  # $100
    total_premium = premium_per_leg * 2  # $200
    target_profit_usd = total_premium * 0.20 # $40.00 Target
    
    btc_entry = 60000
    btc_peak = btc_entry + (max_atr_reached * atr_15m)
    btc_move = btc_peak - btc_entry
    
    # Realistic delta expansion
    base_delta = 0.15
    gamma_per_100_usd = 0.02
    current_delta = base_delta + (btc_move / 100.0) * gamma_per_100_usd
    
    option_loss_peak = current_delta * exposure_btc * btc_move
    
    # Effective exposure required
    effective_exposure = option_loss_peak / btc_move if btc_move > 0 else 0
    target_hedge_size = effective_exposure * multiplier
    
    actual_hedge_size = 0.0
    tier_reached = 0
    
    # AGGRESSIVE GRID (1.5 ATR = 50%, 2.0 ATR = 100%)
    if max_atr_reached >= 1.5:
        actual_hedge_size += target_hedge_size * 0.50
        tier_reached = 1
    if max_atr_reached >= 2.0:
        actual_hedge_size += target_hedge_size * 0.50
        tier_reached = 2
        
    if is_whipsaw:
        # Reversal Market: Market spikes to peak, then completely reverses
        hedge_pnl = actual_hedge_size * (-btc_move)
        option_pnl = 0.0 
    else:
        # TRUE TREND: Market grinds to 130% Stop Loss (~$130 loss)
        additional_move = 1500.0
        final_move = btc_move + additional_move
        
        final_delta = base_delta + (final_move / 100.0) * gamma_per_100_usd
        total_option_loss = final_delta * exposure_btc * final_move
        
        # Escalation engine recalculates sizing as loss grows
        final_effective_exposure = total_option_loss / final_move
        final_hedge_size = final_effective_exposure * multiplier
        
        # Average size held during the run
        avg_hedge_size = (actual_hedge_size + final_hedge_size) / 2
        
        hedge_pnl = (actual_hedge_size * btc_move) + (avg_hedge_size * additional_move)
        option_pnl = -total_option_loss
        
    # Reversal Square-Off Logic (Dynamic Limit)
    if actual_hedge_size > 0:
        dynamic_whipsaw_limit = max(-50.0, min(-3.0, -3.0 * (actual_hedge_size / 0.01)))
    else:
        dynamic_whipsaw_limit = -3.0
        
    if is_whipsaw and hedge_pnl < dynamic_whipsaw_limit:
        hedge_pnl = dynamic_whipsaw_limit
        
    net_pnl = hedge_pnl + option_pnl
    
    # Simulate Moderate Trend (like today's $315 move)
    if scenario_type == "Moderate Trend ($300 Move)":
        mod_move = 300.0
        mod_delta = base_delta + (mod_move / 100.0) * gamma_per_100_usd
        mod_option_loss = mod_delta * exposure_btc * mod_move
        
        t1_move = 112.5
        t2_move = 150.0
        
        t1_delta = base_delta + (t1_move / 100.0) * gamma_per_100_usd
        t1_size = (t1_delta * exposure_btc * t1_move / t1_move) * multiplier * 0.50
        
        t2_delta = base_delta + (t2_move / 100.0) * gamma_per_100_usd
        t2_total = (t2_delta * exposure_btc * t2_move / t2_move) * multiplier * 1.0
        t2_added = t2_total - t1_size
        
        mod_hedge_profit = t1_size * (mod_move - t1_move) + t2_added * (mod_move - t2_move)
        
        net_pnl = mod_hedge_profit - mod_option_loss
        tier_reached = 2
        max_atr_reached = mod_move / 75.0
        
    status = "GREEN" if net_pnl >= 0 else ("ZERO" if -15 < net_pnl < 0 else "RED")
    
    print(f"| {scenario_id} | {scenario_type} | {max_atr_reached:.1f} ATR | {tier_reached} | ${net_pnl:.2f} | {status} |")
    return net_pnl

print("| ID | Scenario | Max Move | Tiers Activated | Net PNL | Status |")
print("|---|---|---|---|---|---|")

for i in range(1, 5): run_20pct_simulation(i, "Whipsaw Reversal (Early)", random.uniform(1.5, 1.9), True)
for i in range(5, 9): run_20pct_simulation(i, "Whipsaw Reversal (Deep)", random.uniform(2.0, 2.5), True)
for i in range(9, 13): run_20pct_simulation(i, "Moderate Trend ($300 Move)", 4.0, False)
for i in range(13, 18): run_20pct_simulation(i, "True Trend (130% SL Hit)", random.uniform(3.0, 3.5), False)
for i in range(18, 21): run_20pct_simulation(i, "IV Spike (No Trend)", random.uniform(1.0, 1.4), True)
