import sys

def modify():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Expand active positions to full width
    old_line = '<div id="positions-cards" style="display: flex; flex-direction: column; max-width: 800px; margin: 0 auto; gap: 20px; margin-top: 20px;">'
    new_line = '<div id="positions-cards" style="display: flex; flex-direction: column; width: 100%; gap: 20px; margin-top: 20px;">'
    content = content.replace(old_line, new_line)

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Positions cards expanded to full width successfully.")

if __name__ == '__main__':
    modify()
