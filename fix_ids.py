import sys

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

in_live_tab = False
for i, line in enumerate(lines):
    if 'id="tab-livemode"' in line:
        in_live_tab = True
    
    if in_live_tab:
        lines[i] = lines[i].replace('id="consecutive-losses-val"', 'id="live-consecutive-losses-val"')
        lines[i] = lines[i].replace('id="sizing-cooldown-val"', 'id="live-sizing-cooldown-val"')

for i, line in enumerate(lines):
    if 'async function fetchLiveStatus()' in line:
        for j in range(i, i+250):
            if j < len(lines):
                lines[j] = lines[j].replace("document.getElementById('consecutive-losses-val')", "document.getElementById('live-consecutive-losses-val')")
                lines[j] = lines[j].replace("document.getElementById('sizing-cooldown-val')", "document.getElementById('live-sizing-cooldown-val')")
        break

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
