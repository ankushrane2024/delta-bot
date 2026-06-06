import os
import re

file_path = "c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/smart_hedging.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Rename _execute_dynamic_hedge to _execute_oneshot_hedge
content = content.replace("def _execute_dynamic_hedge", "def _execute_oneshot_hedge")
content = content.replace("self._execute_dynamic_hedge", "self._execute_oneshot_hedge")
content = content.replace("1-to-1 DYNAMIC hedge", "1-to-1 ONE-SHOT hedge")
content = content.replace("DYNAMIC 1.0x", "ONE-SHOT 1.0x")
content = content.replace("dynamic_1to1", "oneshot_1to1")

# 2. Remove _rebalance_hedge entirely
pattern = re.compile(r'    def _rebalance_hedge\(.*?(?=    def manage_hedge\()', re.DOTALL)
content = pattern.sub("", content)

# 3. Update manage_hedge to not call _rebalance_hedge
old_manage_end = """        if self.hedge_active:
            # Continuously rebalance the 1-to-1 delta neutrality
            self._rebalance_hedge(net_delta_btc)
        else:
            # Trigger hedge if threshold crossed
            self._execute_hedge_decision(net_delta_btc, dvol, positions, profit_usd)"""

new_manage_end = """        if self.hedge_active:
            # One-Shot Hedge is active. We DO NOT dynamically rebalance to avoid Gamma Bleed.
            # The hedge will hold its position until the option positions are cleared or the hard-stop is hit.
            pass
        else:
            # Trigger hedge if threshold crossed
            self._execute_hedge_decision(net_delta_btc, dvol, positions, profit_usd)"""
            
content = content.replace(old_manage_end, new_manage_end)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated smart_hedging.py to One-Shot Static Hedge")
