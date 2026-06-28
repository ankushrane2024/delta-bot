import re
with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

live_fetch_code = content.split('async function fetchLiveStatus()')[1].split('} catch (e) {')[0]
ids = re.findall(r'document\.getElementById\([\'\"](.*?)[\'\"]\)', live_fetch_code)

for i in ids:
    if f'id="{i}"' not in content and f"id='{i}'" not in content:
        print(f'Missing ID: {i}')
