import re

with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Locate the Right Column stacked container
start_idx = content.find('<!-- Right Column (Stacked) -->')
if start_idx == -1:
    print("Could not find Right Column")
    exit(1)

# The panels to extract are Risk Management and IV & DVOL Status
# They start just after "<!-- Risk Management & Settings Panel -->"
# and end just before "<!-- Smart Hedging Status Panel -->"

start_cut = content.find('<!-- Risk Management & Settings Panel -->')
end_cut = content.find('<!-- Smart Hedging Status Panel -->')

if start_cut == -1 or end_cut == -1:
    print("Could not find panel boundaries")
    exit(1)

panels_html = content[start_cut:end_cut]

# Remove the panels from their original location
content = content[:start_cut] + content[end_cut:]

# Find where to insert them in Analytics tab
analytics_idx = content.find('<!-- TAB 2: ANALYTICS -->')
if analytics_idx == -1:
    print("Could not find Analytics tab")
    exit(1)

# Let's insert them right after the Tomorrow's Trade Probability Panel
# We'll find "<!-- Performance Summary Panel -->" and insert them right before it
insert_idx = content.find('<!-- Performance Summary Panel -->', analytics_idx)
if insert_idx == -1:
    print("Could not find insertion point")
    exit(1)

# Wrap the extracted panels in a grid for side-by-side display on wide screens
wrapped_panels = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 24px; margin-bottom: 24px;">
{panels_html}        </div>
"""

content = content[:insert_idx] + wrapped_panels + content[insert_idx:]

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully moved panels.")
