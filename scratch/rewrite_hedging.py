import os

file_path = "c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/smart_hedging.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace _execute_hedge_decision
old_decision = """    def _execute_hedge_decision(self, net_delta_btc, dvol, positions, profit_usd=0.0):
        \"\"\"
        Step 2 & 3: Check current BTC DVOL to decide hedge size and execute it.
        \"\"\"
        abs_delta = abs(net_delta_btc)
        exposure_btc = self._get_options_exposure_btc(positions)
        
        # Convert absolute net delta in BTC terms back to raw option contract delta terms for comparison
        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs_delta / (leg_size * 0.001) if leg_size > 0 else 0.0
        
        # Decide threshold and action based on DVOL
        if dvol < 45.0:
            trigger_level = HEDGE_IV_THRESHOLDS['low']['delta_trigger'] # 0.20
            action = HEDGE_IV_THRESHOLDS['low']['action'] # full
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger_level = HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] # 0.17
            action = HEDGE_IV_THRESHOLDS['mid']['action'] # full
            tier = "Mid (45-55%)"
        else:
            trigger_level = HEDGE_IV_THRESHOLDS['high']['delta_trigger'] # 0.12
            action = HEDGE_IV_THRESHOLDS['high']['action'] # partial
            tier = "High (>55%)"

        app_logger.info(f"Hedge: DVOL Regime: {tier} | Trigger Level: {trigger_level:.2f} | Action: {action} | Raw Net Delta: {raw_net_delta:.4f}")

        if raw_net_delta > trigger_level:
            if action == 'full':
                app_logger.info(f"Hedge: Triggering FULL hedge since raw net delta {raw_net_delta:.4f} > {trigger_level:.2f}")
                self._execute_full_hedge(net_delta_btc, exposure_btc, profit_usd)
            elif action == 'partial':
                app_logger.info(f"Hedge: Triggering PARTIAL hedge since raw net delta {raw_net_delta:.4f} > {trigger_level:.2f}")
                self._execute_partial_hedge_sequence(net_delta_btc, exposure_btc, positions, profit_usd)
        else:
            app_logger.info(f"Hedge: No post-entry hedge needed. Raw Net Delta {raw_net_delta:.4f} <= {trigger_level:.2f}")"""

new_decision = """    def _execute_hedge_decision(self, net_delta_btc, dvol, positions, profit_usd=0.0):
        \"\"\"
        Step 2 & 3: Check current BTC DVOL to decide if hedge should be activated.
        \"\"\"
        abs_delta = abs(net_delta_btc)
        exposure_btc = self._get_options_exposure_btc(positions)
        
        leg_size = list(positions.values())[0]['size'] if positions else 1
        raw_net_delta = abs_delta / (leg_size * 0.001) if leg_size > 0 else 0.0
        
        if dvol < 45.0:
            trigger_level = HEDGE_IV_THRESHOLDS['low']['delta_trigger'] # 0.20
            tier = "Low (<45%)"
        elif dvol <= 55.0:
            trigger_level = HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] # 0.17
            tier = "Mid (45-55%)"
        else:
            trigger_level = HEDGE_IV_THRESHOLDS['high']['delta_trigger'] # 0.12
            tier = "High (>55%)"

        app_logger.info(f"Hedge: DVOL Regime: {tier} | Trigger Level: {trigger_level:.2f} | Raw Net Delta: {raw_net_delta:.4f}")

        if raw_net_delta > trigger_level:
            app_logger.info(f"Hedge: Triggering 1-to-1 DYNAMIC hedge since raw net delta {raw_net_delta:.4f} > {trigger_level:.2f}")
            self._execute_dynamic_hedge(net_delta_btc)
        else:
            app_logger.info(f"Hedge: No post-entry hedge needed. Raw Net Delta {raw_net_delta:.4f} <= {trigger_level:.2f}")"""

content = content.replace(old_decision, new_decision)

# 2. Replace _execute_full_hedge and _execute_partial_hedge_sequence with _execute_dynamic_hedge and _rebalance_hedge
import re

pattern = re.compile(r'    def _execute_full_hedge\(.*?(?=    def manage_hedge\()', re.DOTALL)

new_hedging_logic = """    def _execute_dynamic_hedge(self, net_delta_btc):
        \"\"\"Executes the initial 1.0x Dynamic Delta Hedge.\"\"\"
        target_hedge_size = abs(net_delta_btc) * 1.0 # STRICT 1.0x 1-to-1 Match
        
        direction = 'sell' if net_delta_btc > 0 else 'buy'
        
        app_logger.info(f"Hedge: Placing INITIAL 1-to-1 Dynamic Hedge of size {target_hedge_size:.4f} BTC in direction: {direction}")
        result = self.execution.place_hedge_order(target_hedge_size, direction)
        
        if result and result['success']:
            self.hedge_active = True
            self.hedge_type = "dynamic_1to1"
            self.hedge_size_btc = target_hedge_size if direction == 'buy' else -target_hedge_size
            self.hedge_percentage = 100.0
            self.hedge_order_id = result['order_id']
            self.last_check_time = time.time()
            
            notifier.notify_hedge_executed(
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                iv=self.dvol.get_current_dvol(),
                net_delta=net_delta_btc,
                hedge_type="DYNAMIC 1.0x",
                size_btc=target_hedge_size,
                order_id=result['order_id']
            )
        else:
            app_logger.error("Hedge: Initial dynamic hedge placement failed!")
            notifier.notify_hedge_failed()

    def _rebalance_hedge(self, net_delta_btc):
        \"\"\"Continuously adjusts hedge size to perfectly mirror option delta.\"\"\"
        target_hedge_btc = -net_delta_btc # Perfect mirror: if delta is +0.15, futures must be -0.15
        current_hedge_btc = self.hedge_size_btc
        
        diff = target_hedge_btc - current_hedge_btc
        
        # If the delta drifted by more than 0.01 BTC, execute a rebalancing order
        if abs(diff) >= 0.01:
            direction = 'buy' if diff > 0 else 'sell'
            abs_diff = abs(diff)
            
            app_logger.info(f"Hedge [REBALANCE]: Option Delta changed to {net_delta_btc:.4f}. Adjusting futures hedge by {abs_diff:.4f} BTC in direction {direction}.")
            result = self.execution.place_hedge_order(abs_diff, direction)
            
            if result and result['success']:
                self.hedge_size_btc += diff # Update tracked size
                app_logger.info(f"Hedge [REBALANCE]: Success. New total hedge size is {self.hedge_size_btc:.4f} BTC.")
            else:
                app_logger.error(f"Hedge [REBALANCE]: Failed to place adjustment order of {abs_diff:.4f} BTC.")
        else:
            # Drift is too small, do not rebalance to save fees
            pass

"""
content = pattern.sub(new_hedging_logic, content)

# 3. Modify manage_hedge to remove the 2.5x escalation and use 1.0x dynamically
manage_hedge_old = """        # 4.1: Unrealized Loss > 25% check (Emergency Escalation & SL tightening)
        if unrealized_loss_pct >= HEDGE_EMERGENCY_LOSS_PCT:
            app_logger.warning(f"Hedge: Critical unrealized loss detected ({unrealized_loss_pct:.1%}). Escalating to 2.5x FULL hedge immediately.")
            
            # Tighten option SL via Risk Manager
            if not self.sl_tightened:
                self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                self.sl_tightened = True
                
            # Escalate hedge to 2.5x Delta
            net_delta_btc, _ = self._fetch_net_delta_and_gamma(positions)
            exposure_btc = self._get_options_exposure_btc(positions)
            direction = 'sell' if net_delta_btc > 0 else 'buy'
            
            # Calculate remaining hedge size to reach 2.5x full hedge
            target_emergency_size = abs(net_delta_btc) * 2.5
            target_emergency_size = min(target_emergency_size, exposure_btc) # Cap at exposure
            
            remaining_hedge = target_emergency_size - abs(self.execution.hedge_size_btc)
            if remaining_hedge > 0.0001:
                app_logger.info(f"Hedge: Placing emergency escalation order of size {remaining_hedge:.4f} BTC")
                result = self.execution.place_hedge_order(remaining_hedge, direction)
                if result and result['success']:
                    self.hedge_active = True
                    self.hedge_type = "emergency_full"
                    self.hedge_percentage = 100.0
                    self.hedge_size_btc = target_emergency_size
                    self.hedge_order_id = result['order_id']
                    
                    notifier.notify_hedge_escalated(
                        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                        from_pct=50.0,
                        to_pct=100.0,
                        loss_pct=unrealized_loss_pct * 100
                    )
                else:
                    app_logger.error("Hedge: Emergency escalation failed!")
                    notifier.notify_hedge_failed()"""

manage_hedge_new = """        # 4.1: Unrealized Loss > 25% check (Tighten SL)
        if unrealized_loss_pct >= HEDGE_EMERGENCY_LOSS_PCT:
            # Tighten option SL via Risk Manager
            if not self.sl_tightened:
                app_logger.warning(f"Hedge: Critical unrealized loss detected ({unrealized_loss_pct:.1%}). Tightening SL.")
                self.risk_manager.tighten_stop_loss(HEDGE_EMERGENCY_SL_TIGHTEN)
                self.sl_tightened = True"""
content = content.replace(manage_hedge_old, manage_hedge_new)

# 4. Add _rebalance_hedge call in manage_hedge
manage_hedge_end_old = """        # 4.3: Standard Hedge Management
        net_delta_btc, total_gamma_btc = self._fetch_net_delta_and_gamma(positions)
        dvol = self.dvol.get_current_dvol()
        
        # We only escalate or manage if hedge is not active. If it is active, it runs its course.
        if not self.hedge_active:
            self._execute_hedge_decision(net_delta_btc, dvol, positions, profit_usd)"""

manage_hedge_end_new = """        # 4.3: Standard Hedge Management
        net_delta_btc, total_gamma_btc = self._fetch_net_delta_and_gamma(positions)
        dvol = self.dvol.get_current_dvol()
        
        if self.hedge_active:
            # Continuously rebalance the 1-to-1 delta neutrality
            self._rebalance_hedge(net_delta_btc)
        else:
            # Trigger hedge if threshold crossed
            self._execute_hedge_decision(net_delta_btc, dvol, positions, profit_usd)"""
            
content = content.replace(manage_hedge_end_old, manage_hedge_end_new)

# Also fix the emergency loss trigger logic in manage_hedge to use dynamic size not exposure * 0.5
emergency_old = """            # If delta data is unavailable, use full exposure as hedge size
            hedge_size = abs(net_delta_btc) if abs(net_delta_btc) > 0.0001 else exposure_btc * 0.5
            direction = 'sell' if net_delta_btc >= 0 else 'buy'
            app_logger.info(
                f"Hedge [EMERGENCY]: Hedging {hedge_size:.4f} BTC in direction {direction} "
                f"(net_delta={net_delta_btc:.4f}, exposure={exposure_btc:.4f})"
            )
            result = self.execution.place_hedge_order(hedge_size, direction)
            if result and result['success']:
                self.hedge_active = True
                self.hedge_type = "emergency_loss_trigger"
                self.hedge_size_btc = hedge_size"""

emergency_new = """            # Strict 1-to-1 Emergency Hedge
            hedge_size = abs(net_delta_btc) if abs(net_delta_btc) > 0.0001 else 0.0
            direction = 'sell' if net_delta_btc >= 0 else 'buy'
            
            if hedge_size > 0:
                app_logger.info(
                    f"Hedge [EMERGENCY]: 1-to-1 DYNAMIC Hedging {hedge_size:.4f} BTC in direction {direction} "
                    f"(net_delta={net_delta_btc:.4f})"
                )
                result = self.execution.place_hedge_order(hedge_size, direction)
                if result and result['success']:
                    self.hedge_active = True
                    self.hedge_type = "dynamic_1to1"
                    self.hedge_size_btc = hedge_size if direction == 'buy' else -hedge_size"""
                    
content = content.replace(emergency_old, emergency_new)


with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated smart_hedging.py")
