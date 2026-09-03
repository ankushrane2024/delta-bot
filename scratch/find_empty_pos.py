with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'open trades right now' in line or 'No Active Positions' in line or 'positions-cards' in line:
            print(f'Line {i+1}: {line.strip()[:100]}')
