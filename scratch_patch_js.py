import re

def safe_wrap(match):
    # original is like: document.getElementById('dvol-val').textContent = ...
    full_match = match.group(0)
    id_name = match.group(1)
    prop = match.group(2)
    # We create a safe wrapper
    # e.g., if(document.getElementById('xyz')) document.getElementById('xyz').prop
    
    # Check if it's already inside an if(...) statement or assignment
    # We can just blindly wrap it on the same line if it's a standalone statement
    return f"if(document.getElementById('{id_name}')) {full_match}"

with open('templates/dashboard.html', encoding='utf-8') as f:
    html = f.read()

# Pattern to find statements like: document.getElementById('dvol-val').textContent = ...
# Or document.getElementById('dvol-percentile-bar').style.width = ...
# We want to find cases that start at the beginning of a line (ignoring whitespace)
pattern = re.compile(r'^(\s*)document\.getElementById\([\'"]([a-zA-Z0-9_-]+)[\'"]\)\.([a-zA-Z0-9_\-\.]+)\s*=', re.MULTILINE)

def replacer(match):
    indent = match.group(1)
    id_name = match.group(2)
    prop = match.group(3)
    full_expr = match.group(0).strip()
    return f"{indent}if(document.getElementById('{id_name}')) {full_expr}"

new_html = pattern.sub(replacer, html)

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

print("Patched document.getElementById(...) assignments.")
