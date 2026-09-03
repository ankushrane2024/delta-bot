with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'id="active-positions-container"' in line:
            print(f'Line {i+1}: {line.strip()}')
