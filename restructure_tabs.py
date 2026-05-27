"""
Restructures index.html into a 4-tab layout.
Only modifies HTML structure - no Python trading logic touched.
"""
import re

with open("index.html", "r", encoding="utf-8") as f:
    content = f.read()

# ── 1. Inject Tab CSS before </style> ──────────────────────────────────────
tab_css = """
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        /* ── Tab Navigation ─────────────────────────────── */
        .tab-nav {
            max-width: 1100px;
            width: 100%;
            display: flex;
            gap: 4px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 6px;
            position: sticky;
            top: 16px;
            z-index: 100;
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
        }
        .tab-btn {
            flex: 1;
            padding: 10px 16px;
            border: none;
            border-radius: 10px;
            background: transparent;
            color: var(--text-secondary);
            font-family: 'Inter', sans-serif;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.25s ease;
            white-space: nowrap;
        }
        .tab-btn:hover {
            background: rgba(255,255,255,0.06);
            color: #fff;
        }
        .tab-btn.active {
            background: linear-gradient(135deg, rgba(0,212,255,0.15), rgba(99,102,241,0.15));
            color: #00d4ff;
            border-bottom: 2px solid #00d4ff;
            box-shadow: 0 0 12px rgba(0,212,255,0.15);
        }
        .tab-pane {
            display: none;
            max-width: 1100px;
            width: 100%;
            flex-direction: column;
            gap: 24px;
            animation: fadeIn 0.25s ease;
        }
        .tab-pane.active { display: flex; }
        .tab-live-dot {
            display: inline-block;
            width: 7px; height: 7px;
            border-radius: 50%;
            background: #34d399;
            box-shadow: 0 0 6px #34d399;
            animation: pulse-green 2s infinite;
            margin-right: 5px;
            vertical-align: middle;
        }
"""
content = content.replace("    </style>\n</head>", tab_css + "    </style>\n</head>")

# ── 2. Add Tab Nav after </header> ─────────────────────────────────────────
tab_nav = """
    <!-- Tab Navigation -->
    <nav class="tab-nav">
        <button class="tab-btn active" id="tab-btn-live"      onclick="switchTab('live')"><span class="tab-live-dot"></span>Live Trade</button>
        <button class="tab-btn"        id="tab-btn-analytics"  onclick="switchTab('analytics')">&#128202; Analytics</button>
        <button class="tab-btn"        id="tab-btn-market"     onclick="switchTab('market')">&#128225; Market</button>
        <button class="tab-btn"        id="tab-btn-config"     onclick="switchTab('config')">&#9881;&#65039; Config</button>
    </nav>
"""

# Replace: </header>\n\n    <div class="container"> -> </header> + tabnav + tab-live open
content = content.replace(
    '</header>\n\n    <div class="container">',
    '</header>\n' + tab_nav + '\n    <!-- TAB 1: LIVE TRADE -->\n    <div class="tab-pane active" id="tab-live">\n    <div class="container">'
)

# ── 3. The 2-col container closes at </div>\n\n        <!-- Tomorrow's ...
# We need to: close the container, close tab-live, open tab-analytics
# The sequence at line 585: "    </div>\n\n        <!-- Tomorrow's Trade Probability Panel -->"
content = content.replace(
    '    </div>\n\n        <!-- Tomorrow\'s Trade Probability Panel -->',
    '    </div>\n    </div><!-- /tab-live -->\n\n    <!-- TAB 2: ANALYTICS -->\n    <div class="tab-pane" id="tab-analytics">\n\n        <!-- Tomorrow\'s Trade Probability Panel -->'
)

# ── 4. Active Positions panel - move to tab-live, it's full-width
# Find the positions panel - it's after Performance Summary
# We'll close analytics before positions and reopen live for positions
# Actually the layout we want is:
# Tab1 (Live): 2col container + Active Positions panel
# Tab2 (Analytics): Trade Probability + Performance Summary
# Tab3 (Market): IV/DVOL + News + Schedule
# Tab4 (Config): Rule Compliance + Logs + Reports + Backtesting
# Since positions is after Performance in the file, let's re-split:

# Step A: Move Active Positions BEFORE Performance (it's already after in file).
# Actually it's easier to close tab-analytics before positions and re-open:
content = content.replace(
    '\n        <!-- Active Positions Panel -->\n        <div class="panel full-width" id="positions-panel">',
    '\n    </div><!-- /tab-analytics -->\n\n    <!-- POSITIONS (pinned back in Live tab) -->\n    <div class="tab-pane" id="tab-live-positions" style="display:none;">\n    </div>\n\n    <!-- TAB 2b: Positions always visible under Live -->\n    <!-- We embed positions directly -->\n    <div id="positions-outer" style="max-width:1100px;width:100%;">\n        <!-- Active Positions Panel -->\n        <div class="panel full-width" id="positions-panel">'
)

content = content.replace(
    '        </div>\n\n        <!-- Rule Compliance Panel -->',
    '        </div>\n    </div><!-- /positions-outer -->\n\n    <!-- TAB 3: CONFIG -->\n    <div class="tab-pane" id="tab-config">\n        <!-- Rule Compliance Panel -->'
)

# ── 5. Close tab-config and open tab-market before the Schedule panel
# Rule Compliance ends, then Skip & Schedule Info
content = content.replace(
    '        <!-- Skip &amp; Schedule Info Panel -->',
    '    </div><!-- /tab-config-rules -->\n\n    <!-- TAB 4: MARKET -->\n    <div class="tab-pane" id="tab-market">\n        <!-- Skip &amp; Schedule Info Panel -->'
)

# Live Terminal and Daily Reports -> go into Config tab, so close market before logs
content = content.replace(
    '        <!-- Live Terminal Panel -->',
    '    </div><!-- /tab-market -->\n\n    <!-- TAB 3b: CONFIG remainder -->\n    <div class="tab-pane" id="tab-config-b">\n        <!-- Live Terminal Panel -->'
)

# Close the very last tab at </body>
content = content.replace('</body>', '    </div><!-- /tab-config-b -->\n</body>')

# ── 6. Inject switchTab() JavaScript before closing </script> ──────────────
switch_tab_js = """
        function switchTab(name) {
            // Hide all panes
            document.querySelectorAll('.tab-pane').forEach(p => { p.classList.remove('active'); });
            // Update buttons
            document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); });

            if (name === 'live') {
                document.getElementById('tab-live').classList.add('active');
                document.getElementById('positions-outer').style.display = 'block';
                document.getElementById('tab-btn-live').classList.add('active');
            } else if (name === 'analytics') {
                document.getElementById('tab-analytics').classList.add('active');
                document.getElementById('positions-outer').style.display = 'none';
                document.getElementById('tab-btn-analytics').classList.add('active');
            } else if (name === 'market') {
                document.getElementById('tab-market').classList.add('active');
                document.getElementById('positions-outer').style.display = 'none';
                document.getElementById('tab-btn-market').classList.add('active');
            } else if (name === 'config') {
                document.getElementById('tab-config').classList.add('active');
                document.getElementById('tab-config-b').classList.add('active');
                document.getElementById('positions-outer').style.display = 'none';
                document.getElementById('tab-btn-config').classList.add('active');
            }
        }
"""
# Inject just before the last </script> in the file
last_script_close = content.rfind('    </script>')
content = content[:last_script_close] + switch_tab_js + content[last_script_close:]

with open("index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done! index.html restructured into 4 tabs.")
