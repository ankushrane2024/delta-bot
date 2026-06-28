import random

def run_grid_simulation(scenario_id, scenario_type, max_atr_reached, is_whipsaw):
    atr_15m = 75.0
    multiplier = 1.2
    
    # ── Live Trade Parameters (User Specified) ──
    lots_per_leg = 500
    btc_per_lot = 0.001
    exposure_btc = lots_per_leg * btc_per_lot  # 0.5 BTC
    
    premium_per_leg = 100.0  # $100
    total_premium = premium_per_leg * 2  # $200
    
    btc_entry = 60000
    btc_peak = btc_entry + (max_atr_reached * atr_15m)
    btc_move = btc_peak - btc_entry
    
    # Realistic delta expansion
    base_delta = 0.15
    gamma_per_100_usd = 0.02
    current_delta = base_delta + (btc_move / 100.0) * gamma_per_100_usd
    
    option_loss_peak = current_delta * exposure_btc * btc_move
    
    # The Grid Engine calculates hedge size required to cover option loss
    effective_exposure = option_loss_peak / btc_move if btc_move > 0 else 0
    target_hedge_size = effective_exposure * multiplier
    
    actual_hedge_size = 0.0
    tier_reached = 0
    
    if max_atr_reached >= 2.0:
        actual_hedge_size += target_hedge_size * 0.30
        tier_reached = 1
    if max_atr_reached >= 2.5:
        actual_hedge_size += target_hedge_size * 0.30
        tier_reached = 2
    if max_atr_reached >= 3.0:
        actual_hedge_size += target_hedge_size * 0.40
        tier_reached = 3
        
    if is_whipsaw:
        hedge_pnl = actual_hedge_size * (-btc_move)
        option_pnl = 0.0 
    else:
        # TRUE TREND: Market grinds to Stop Loss
        additional_move = 1500.0
        final_move = btc_move + additional_move
        
        final_delta = base_delta + (final_move / 100.0) * gamma_per_100_usd
        total_option_loss = final_delta * exposure_btc * final_move
        
        # In the LIVE BOT, the Escalation engine recalculates sizing as the loss grows.
        # Final effective exposure at SL:
        final_effective_exposure = total_option_loss / final_move
        # Final escalated hedge size (Tier 3 = 100%)
        final_hedge_size = final_effective_exposure * multiplier
        
        # Hedge profit is accumulated as it scales up.
        # For simplicity, average the size over the move
        avg_hedge_size = (actual_hedge_size + final_hedge_size) / 2
        
        hedge_pnl = (actual_hedge_size * btc_move) + (avg_hedge_size * additional_move)
        option_pnl = -total_option_loss
        
    max_whipsaw_loss = -20.0
    if is_whipsaw and hedge_pnl < max_whipsaw_loss:
        hedge_pnl = max_whipsaw_loss
        
    net_pnl = hedge_pnl + option_pnl
    
    # Simulate Old System
    if max_atr_reached >= 2.0:
        if is_whipsaw:
            old_hedge_pnl = target_hedge_size * (-btc_move)
            if old_hedge_pnl < max_whipsaw_loss: old_hedge_pnl = max_whipsaw_loss
        else:
            # Old system also escalated
            old_final_hedge_size = final_effective_exposure * multiplier
            old_avg_hedge = (target_hedge_size + old_final_hedge_size) / 2
            old_hedge_pnl = (target_hedge_size * btc_move) + (old_avg_hedge * additional_move)
    else:
        old_hedge_pnl = 0
        
    old_net_pnl = old_hedge_pnl + option_pnl
    
    status = "GREEN" if net_pnl >= 0 else ("ZERO" if -15 < net_pnl < 0 else "RED")
    
    print(f"| {scenario_id} | {scenario_type} | {max_atr_reached:.1f} ATR | {tier_reached} | ${old_net_pnl:.2f} | ${net_pnl:.2f} | {status} |")
    return net_pnl

print("| ID | Scenario | Max Move | Tiers Activated | Old Net PNL | New Grid PNL | Status |")
print("|---|---|---|---|---|---|---|")

for i in range(1, 8): run_grid_simulation(i, "Whipsaw (Early Fakeout)", random.uniform(2.0, 2.4), True)
for i in range(8, 11): run_grid_simulation(i, "Whipsaw (Mid Fakeout)", random.uniform(2.5, 2.9), True)
for i in range(11, 13): run_grid_simulation(i, "Whipsaw (Deep Fakeout)", random.uniform(3.0, 3.5), True)
for i in range(13, 18): run_grid_simulation(i, "True Trend (SL Hit)", random.uniform(3.0, 3.5), False)
for i in range(18, 21): run_grid_simulation(i, "IV Spike (No Trend)", random.uniform(1.0, 1.9), True)
