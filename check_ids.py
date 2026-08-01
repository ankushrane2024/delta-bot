import re

with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

ids_in_html = set(re.findall(r'id=[\"\']([a-zA-Z0-9_-]+)[\"\']', content))
js_gets = set(re.findall(r'getElementById\([\"\']([a-zA-Z0-9_-]+)[\"\']\)', content))

missing = js_gets - ids_in_html
print('Missing IDs used in JS:', missing)
