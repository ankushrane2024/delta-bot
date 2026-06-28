import random

def run_grid_simulation(scenario_id, scenario_type, max_atr_reached, is_whipsaw):
    atr_15m = 75.0
    multiplier = 2.0
    
    btc_entry = 60000
    btc_peak = btc_entry + (max_atr_reached * atr_15m)
    btc_move = btc_peak - btc_entry
    
    # Realistic base exposure (Delta) for 2 ATR move
    base_delta = 0.01
    option_loss_peak = base_delta * btc_move
    
    target_hedge_size = base_delta * multiplier
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
        # Trend continues massively
        additional_move = 1000.0
        # Realistic average delta as trend continues
        avg_delta = base_delta * 1.25
        additional_option_loss = avg_delta * additional_move
        
        hedge_pnl = actual_hedge_size * additional_move
        option_pnl = -(option_loss_peak + additional_option_loss)
        
    if is_whipsaw and hedge_pnl < -3.0:
        hedge_pnl = -3.0
        
    net_pnl = hedge_pnl + option_pnl
    
    old_hedge_size = target_hedge_size
    if max_atr_reached >= 2.0:
        old_hedge_pnl = old_hedge_size * (-btc_move) if is_whipsaw else old_hedge_size * additional_move
        if is_whipsaw and old_hedge_pnl < -3.0: old_hedge_pnl = -3.0
    else:
        old_hedge_pnl = 0
        
    old_net_pnl = old_hedge_pnl + option_pnl
    
    status = "GREEN" if net_pnl >= 0 else ("ZERO" if -1 < net_pnl < 0 else "RED")
    
    print(f"| {scenario_id} | {scenario_type} | {max_atr_reached:.1f} ATR | {tier_reached} | ${old_net_pnl:.2f} | ${net_pnl:.2f} | {status} |")
    return net_pnl

print("| ID | Scenario | Max Move | Tiers Activated | Old Net PNL | New Grid PNL | Status |")
print("|---|---|---|---|---|---|---|")

for i in range(1, 8): run_grid_simulation(i, "Whipsaw (Early Fakeout)", random.uniform(2.0, 2.4), True)
for i in range(8, 11): run_grid_simulation(i, "Whipsaw (Mid Fakeout)", random.uniform(2.5, 2.9), True)
for i in range(11, 13): run_grid_simulation(i, "Whipsaw (Deep Fakeout)", random.uniform(3.0, 3.5), True)
for i in range(13, 18): run_grid_simulation(i, "True Trend (SL Hit)", random.uniform(3.0, 3.5), False)
for i in range(18, 21): run_grid_simulation(i, "IV Spike (No Trend)", random.uniform(1.0, 1.9), True)
