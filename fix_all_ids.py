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

    common_ids = list(ids_paper.intersection(ids_live))
    
    # We also manually add any known IDs that were duplicated but might not have "id=" in the HTML or dynamically generated
    # Actually if they are in common_ids they definitely have id= in both HTMLs.
    
    lines = content.split('\n')
    
    # Update HTML
    in_live_tab = False
    for i, line in enumerate(lines):
        if 'id="tab-livemode"' in line:
            in_live_tab = True
        
        if in_live_tab:
            for cid in common_ids:
                lines[i] = lines[i].replace(f'id="{cid}"', f'id="live-{cid}"')
                lines[i] = lines[i].replace(f"id='{cid}'", f"id='live-{cid}'")
                
        if 'async function fetchLiveStatus()' in line:
            break

    # Update JS
    in_live_js = False
    for i, line in enumerate(lines):
        if 'async function fetchLiveStatus()' in line:
            in_live_js = True
            
        if in_live_js:
            for cid in common_ids:
                lines[i] = lines[i].replace(f"getElementById('{cid}')", f"getElementById('live-{cid}')")
                lines[i] = lines[i].replace(f'getElementById("{cid}")', f'getElementById("live-{cid}")')
                # Also replace querySelectorAll('#cid')
                lines[i] = lines[i].replace(f"querySelectorAll('#{cid}')", f"querySelectorAll('#live-{cid}')")
                lines[i] = lines[i].replace(f'querySelectorAll("#{cid}")', f'querySelectorAll("#live-{cid}")')

        if 'async function switchTab(name)' in line:
            break

    with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Fixed {len(common_ids)} duplicated IDs globally in the Live tab and JS.")
else:
    print("Could not find tabs.")
