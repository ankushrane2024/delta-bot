import re

with open('templates/dashboard.html', encoding='utf-8', errors='ignore') as f:
    html = f.read()

ids = set(re.findall(r'id=["\']([a-zA-Z0-9_-]+)["\']', html))
js_ids = set(re.findall(r'getElementById\([\'"]([a-zA-Z0-9_-]+)[\'"]\)', html))

missing = js_ids - ids
print('Missing IDs:', missing)
