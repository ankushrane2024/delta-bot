import sys
with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'data.positions' in line:
        for j in range(i-5, i+40):
            print(f"Line {j}: {lines[j].strip().encode('ascii', 'ignore').decode('ascii')}")
        break
