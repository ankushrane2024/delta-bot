with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('Total lines:', len(lines))
for i in range(1695, min(2210, len(lines))):
    l = lines[i]
    if any(k in l for k in ['<h2', '<h3', '<h4', '<div class="glass-panel"', 'id=']):
        print(f'{i+1}: {l.strip()[:100].encode("ascii", errors="replace").decode()}')
