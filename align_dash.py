import sys

def modify():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update Grid back to full width
    old_grid = '<div style="display: flex; flex-direction: column; max-width: 800px; margin: 0 auto; gap: 24px;">'
    new_grid = '<div style="display: flex; flex-direction: column; width: 100%; gap: 24px;">'
    content = content.replace(old_grid, new_grid)

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Dashboard aligned to full width successfully.")

if __name__ == '__main__':
    modify()
