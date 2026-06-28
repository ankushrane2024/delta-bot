with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'id="tab-livemode"' in line:
        start = i
    if 'async function fetchLiveStatus()' in line:
        end = i

print(f"Lines between: {end - start}")
