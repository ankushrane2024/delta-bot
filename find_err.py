with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'alert("Success!' in line:
        for j in range(max(0, i-2), min(len(lines), i+3)):
            print(f"Line {j}: {repr(lines[j])}")
        break
