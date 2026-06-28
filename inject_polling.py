with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if 'fetchStatus();' in line and '// Poll every 2 seconds' in lines[len(new_lines)-3]:
        # We found the fetchStatus() initial call. Let's inject live polling here.
        new_lines.append("\n// Poll Live Mode\n")
        new_lines.append("setInterval(() => {\n")
        new_lines.append("    if (document.getElementById('tab-livemode').classList.contains('active')) {\n")
        new_lines.append("        fetchLiveStatus();\n")
        new_lines.append("    }\n")
        new_lines.append("}, 4000);\n")
        new_lines.append("setInterval(() => {\n")
        new_lines.append("    if (document.getElementById('tab-livemode').classList.contains('active')) {\n")
        new_lines.append("        fetchLivePnl();\n")
        new_lines.append("    }\n")
        new_lines.append("}, 3000);\n")
        new_lines.append("setTimeout(() => { fetchLiveStatus(); fetchLivePnl(); }, 500);\n")

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("Injected live polling successfully.")
