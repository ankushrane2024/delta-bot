import sys

def modify():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update Grid
    old_grid = 'display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr))'
    new_grid = 'display: flex; flex-direction: column; max-width: 800px; margin: 0 auto'
    content = content.replace(old_grid, new_grid)

    # 2. Hide Hedge Panel
    old_panel = '<div class="glass-panel" id="hedge-panel">'
    new_panel = '<div class="glass-panel" id="hedge-panel" style="display: none !important;">'
    content = content.replace(old_panel, new_panel)

    # 3. Hide Hedge Pill Button
    old_button = '<button id="hedge-pill"'
    new_button = '<button id="hedge-pill" style="display: none !important;"'
    content = content.replace(old_button, new_button)

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Dashboard cleaned successfully.")

if __name__ == '__main__':
    modify()
