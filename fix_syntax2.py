with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix unescaped newlines in alert("Failed:\n")
if 'alert("Failed!\n' in content:
    content = content.replace('alert("Failed!\n', 'alert("Failed!\\n')
if 'alert("Failed:\n' in content:
    content = content.replace('alert("Failed:\n', 'alert("Failed:\\n')

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed failed alert syntax error")
