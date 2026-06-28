import re

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

live_tab_start = content.find('id="tab-live"')
live_mode_tab_start = content.find('id="tab-livemode"')

if live_tab_start != -1 and live_mode_tab_start != -1:
    tab_live_html = content[live_tab_start:live_mode_tab_start]
    tab_livemode_html = content[live_mode_tab_start:content.find('async function switchTab(name)')]

    ids_paper = set(re.findall(r'id=[\'\"]([a-zA-Z0-9_-]+)[\'\"]', tab_live_html))
    ids_live = set(re.findall(r'id=[\'\"]([a-zA-Z0-9_-]+)[\'\"]', tab_livemode_html))

    common_ids = ids_paper.intersection(ids_live)
    print("Duplicated IDs between tabs:", common_ids)
else:
    print("Tabs not found")
