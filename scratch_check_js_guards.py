import re

with open('templates/dashboard.html', encoding='utf-8', errors='ignore') as f:
    html = f.read()

ids = set(re.findall(r'id=["\']([a-zA-Z0-9_-]+)["\']', html))

# Find all document.getElementById calls
matches = re.finditer(r'document\.getElementById\([\'"]([a-zA-Z0-9_-]+)[\'"]\)', html)

for match in matches:
    id_name = match.group(1)
    if id_name not in ids:
        # Get the line this occurs on
        start_idx = match.start()
        line_num = html.count('\n', 0, start_idx) + 1
        line_text = html.split('\n')[line_num - 1].strip()
        print(f"Missing ID: {id_name} on line {line_num}: {line_text}")
