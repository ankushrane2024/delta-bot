import sys

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

ids_to_replace = [
    'positions-cards',
    'pos-total-bar',
    'active-positions-container',
    'pos-total-entry',
    'pos-total-capital',
    'pos-btc-price',
    'pos-total-pnl-usd',
    'pos-total-pnl-inr',
    'log-terminal'
]

# 1. Update tab-livemode HTML
in_live_tab = False
for i, line in enumerate(lines):
    if 'id="tab-livemode"' in line:
        in_live_tab = True
    
    if in_live_tab:
        for dom_id in ids_to_replace:
            lines[i] = lines[i].replace(f'id="{dom_id}"', f'id="live-{dom_id}"')
            lines[i] = lines[i].replace(f"id='{dom_id}'", f"id='live-{dom_id}'")
            
    if 'async function fetchLiveStatus()' in line:
        break

# 2. Update fetchLiveStatus JS
in_fetch_live = False
for i, line in enumerate(lines):
    if 'async function fetchLiveStatus()' in line:
        in_fetch_live = True
    
    if in_fetch_live:
        for dom_id in ids_to_replace:
            lines[i] = lines[i].replace(f"getElementById('{dom_id}')", f"getElementById('live-{dom_id}')")
            lines[i] = lines[i].replace(f'getElementById("{dom_id}")', f'getElementById("live-{dom_id}")')

        # Stop when hitting the end of LIVE mode JS
        if 'async function liveSendCommand(action)' in line or 'function switchTab(name)' in line:
            break

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("DOM IDs properly scoped for LIVE mode.")
