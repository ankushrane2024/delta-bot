"""
Move the News Panel from the Live tab to the Analytics tab.
"""
with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# The panel to move
news_start_marker = '            <!-- News & Events / Volatility Alerts Panel -->'
news_end_marker = '        </div>\n    </div>\n    </div><!-- /tab-live -->'

news_start_idx = content.find(news_start_marker)
if news_start_idx == -1:
    print("Could not find news panel start marker")
    exit(1)

# Find the end of the news panel div. It's just before '        </div>\n    </div>\n    </div><!-- /tab-live -->'
# Let's extract the exact block.
block_start = news_start_idx
# The news panel ends with:
#                 <div style="margin-top: 10px; font-size: 0.8rem; color: var(--text-secondary);">Source: ForexFactory · Updates every 6 hours</div>
#             </div>
block_end_marker = 'Source: ForexFactory · Updates every 6 hours</div>\n            </div>\n'
block_end_idx = content.find(block_end_marker, block_start) + len(block_end_marker)

if block_end_idx < len(block_end_marker):
    print("Could not find block end marker")
    exit(1)

news_block = content[block_start:block_end_idx]

# Remove the block from its current location
content = content[:block_start] + content[block_end_idx:]

# Find where to insert it: at the end of tab-analytics
insert_marker = '    </div><!-- /tab-analytics -->'
insert_idx = content.find(insert_marker)
if insert_idx == -1:
    print("Could not find insert marker")
    exit(1)

# Insert the block, with some spacing
content = content[:insert_idx] + '\n' + news_block + '\n' + content[insert_idx:]

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully moved News Panel to Analytics tab.")
