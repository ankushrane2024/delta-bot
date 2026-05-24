import os

for filename in ['templates/dashboard.html', 'index.html']:
    if not os.path.exists(filename): continue
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Swap the panels
    # Find Performance panel
    perf_start = content.find('<!-- Performance Summary Panel -->')
    perf_end = content.find('<!-- Active Positions Panel -->')
    if perf_start != -1 and perf_end != -1:
        # Tomorrow's Trade Chance is below Performance right now (wait, let's check order)
        # Actually in the HTML we saw earlier, Performance is at 505, Tomorrow's is at 649, Skip is at 695.
        # Let's extract the Tomorrow block.
        tom_start = content.find("<!-- Tomorrow's Trade Chance Panel -->")
        if tom_start == -1: 
            tom_start = content.find("<!-- Tomorrow's Trade Chance") # It might not have 'Panel' in comment
        
        tom_end = content.find('<!-- Skip & Schedule Info Panel -->')
        
        if tom_start != -1 and tom_end != -1:
            tomorrow_html = content[tom_start:tom_end]
            
            # Now remove tomorrow_html from its original place
            content = content[:tom_start] + content[tom_end:]
            
            # Re-find perf_start because string length changed
            perf_start = content.find('<!-- Performance Summary Panel -->')
            # Insert tomorrow_html right before perf_start
            content = content[:perf_start] + tomorrow_html + content[perf_start:]

    # 2. Fix the flex layouts for the height match
    content = content.replace('align-items: start;', 'align-items: stretch;')
    
    # Add height 100% to the columns
    content = content.replace(
        '<div style="display: flex; flex-direction: column; gap: 24px;">',
        '<div style="display: flex; flex-direction: column; gap: 24px; height: 100%;">',
        2 # only the first 2 which are the left and right columns
    )
    
    # Ensure news panel flexes internally so the table container takes up the space
    old_news = '<div class="panel" id="news-panel" style="flex: 1;">'
    new_news = '<div class="panel" id="news-panel" style="flex: 1; display: flex; flex-direction: column;">'
    content = content.replace(old_news, new_news)

    # Make the manual lot size panel flex too just in case left column is shorter
    old_lot = '<div class="panel" id="lot-size-panel">'
    new_lot = '<div class="panel" id="lot-size-panel" style="flex: 1; display: flex; flex-direction: column;">'
    content = content.replace(old_lot, new_lot)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Applied layout changes to {filename}")

