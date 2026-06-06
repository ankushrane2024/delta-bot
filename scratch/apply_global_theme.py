import re

def process_file():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. REPLACE ALL CSS IN <head>
    # We find the first <style> and the </head>
    style_start = html.find('<style>')
    head_end = html.find('</head>')
    
    if style_start == -1 or head_end == -1:
        print("Could not find <style> or </head>")
        return
        
    unified_css = """<style>
        /* ========================================================
           GLOBAL EMBOSSED THEME - DELTA OPTIONS ENGINE
           ======================================================== */
        :root {
            --bg-color: #0a0f1c; /* Deep futuristic space blue/black */
            --panel-bg: rgba(16, 20, 30, 0.65); /* Glassmorphism base */
            --border-color: rgba(255, 255, 255, 0.04);
            
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            
            /* Accents */
            --emerald: #10b981;
            --rose: #f43f5e;
            --cyan: #06b6d4;
            --violet: #8b5cf6;
            
            /* Neumorphic / Embossed Depth Variables */
            --btn-bg: #131824;
            --btn-border: rgba(255, 255, 255, 0.08);
            --emboss-inner: inset 0 1px 1px rgba(255, 255, 255, 0.15), inset 0 -2px 4px rgba(0, 0, 0, 0.4);
            --emboss-drop: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 15% 0%, rgba(6, 182, 212, 0.08), transparent 40%),
                radial-gradient(circle at 85% 100%, rgba(139, 92, 246, 0.08), transparent 40%);
            color: var(--text-primary);
            margin: 0;
            padding: 40px 20px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 24px;
        }

        header {
            max-width: 1100px;
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        h1 {
            font-weight: 800;
            margin: 0;
            font-size: 2rem;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        h2 {
            font-size: 1.1rem;
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 20px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* ----- GLASSMORPHISM CARDS ----- */
        .glass-panel {
            background: var(--panel-bg);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid var(--border-color);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.02);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            width: 100%;
            box-sizing: border-box;
        }
        .glass-panel:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 40px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.03);
            border-color: rgba(255, 255, 255, 0.08);
        }

        /* ----- TAB NAVIGATION ----- */
        .tab-nav {
            display: flex;
            gap: 12px;
            margin-bottom: 30px;
            background: rgba(0, 0, 0, 0.2);
            padding: 8px;
            border-radius: 14px;
            border: 1px solid rgba(255,255,255,0.03);
            max-width: 1100px;
            width: 100%;
            box-sizing: border-box;
            overflow-x: auto;
        }
        .tab-btn {
            background: transparent;
            color: var(--text-secondary);
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.3s ease;
            white-space: nowrap;
        }
        .tab-btn:hover {
            color: #fff;
            background: rgba(255, 255, 255, 0.05);
        }
        .tab-btn.active {
            background: var(--btn-bg);
            color: #fff;
            box-shadow: var(--emboss-drop), var(--emboss-inner);
            border: 1px solid var(--border-color);
        }
        .tab-pane {
            display: none;
            animation: fadeIn 0.3s ease;
            width: 100%;
            max-width: 1100px;
            box-sizing: border-box;
        }
        .tab-pane.active {
            display: block;
        }
        #tab-live.active { display: flex !important; }

        /* ----- EMBOSSED PREMIUM BUTTONS ----- */
        .btn-embossed {
            padding: 14px 24px;
            border: 1px solid var(--btn-border);
            border-radius: 12px;
            font-weight: 800;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            text-align: center;
            letter-spacing: 0.5px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            background: var(--btn-bg);
            color: var(--text-primary);
            box-shadow: var(--emboss-drop), var(--emboss-inner);
            position: relative;
            overflow: hidden;
        }
        
        .btn-embossed:hover {
            transform: translateY(-2px);
            filter: brightness(1.15);
        }
        
        .btn-embossed:active {
            transform: translateY(1px);
            box-shadow: 0 1px 2px rgba(0,0,0,0.5), inset 0 2px 6px rgba(0,0,0,0.8);
            border-color: rgba(0,0,0,0.5);
        }

        /* Specific Button Accents */
        .btn-green {
            color: var(--emerald);
            border-color: rgba(16, 185, 129, 0.2);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 0 10px rgba(16, 185, 129, 0.05);
        }
        .btn-green:hover {
            border-color: rgba(16, 185, 129, 0.4);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 5px 15px rgba(16, 185, 129, 0.2);
            color: #34d399;
        }

        .btn-red {
            color: var(--rose);
            border-color: rgba(244, 63, 94, 0.2);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 0 10px rgba(244, 63, 94, 0.05);
        }
        .btn-red:hover {
            border-color: rgba(244, 63, 94, 0.4);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 5px 15px rgba(244, 63, 94, 0.2);
            color: #fb7185;
        }

        .btn-cyan {
            color: var(--cyan);
            border-color: rgba(6, 182, 212, 0.2);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 0 10px rgba(6, 182, 212, 0.05);
        }
        .btn-cyan:hover {
            border-color: rgba(6, 182, 212, 0.4);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 5px 15px rgba(6, 182, 212, 0.2);
            color: #22d3ee;
        }

        .btn-violet {
            color: var(--violet);
            border-color: rgba(139, 92, 246, 0.2);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 0 10px rgba(139, 92, 246, 0.05);
        }
        .btn-violet:hover {
            border-color: rgba(139, 92, 246, 0.4);
            box-shadow: var(--emboss-drop), var(--emboss-inner), 0 5px 15px rgba(139, 92, 246, 0.2);
            color: #a78bfa;
        }

        /* EXTREME EMERGENCY BUTTON */
        .btn-emergency-pulse {
            background: linear-gradient(180deg, #be123c, #881337);
            color: #fff;
            border: 1px solid #fda4af;
            box-shadow: 0 4px 15px rgba(190, 18, 60, 0.4), inset 0 2px 2px rgba(255, 255, 255, 0.2), inset 0 -2px 4px rgba(0,0,0,0.5);
            animation: pulse-red-alert 2s infinite;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-size: 1.05rem;
        }
        .btn-emergency-pulse:hover {
            background: linear-gradient(180deg, #e11d48, #9f1239);
            transform: translateY(-2px);
            animation: none;
            box-shadow: 0 8px 25px rgba(225, 29, 72, 0.6), inset 0 2px 2px rgba(255, 255, 255, 0.3);
        }
        .btn-emergency-pulse:active {
            transform: translateY(2px);
            box-shadow: 0 1px 2px rgba(0,0,0,0.5), inset 0 3px 8px rgba(0,0,0,0.8);
        }

        /* ----- TYPOGRAPHY & STATS ----- */
        .stat-label {
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 800;
            margin: 8px 0;
        }
        .pnl-pos { color: var(--emerald); text-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
        .pnl-neg { color: var(--rose); text-shadow: 0 0 15px rgba(244, 63, 94, 0.2); }
        
        .status-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            background: rgba(16, 185, 129, 0.1);
            color: var(--emerald);
            border: 1px solid rgba(16, 185, 129, 0.2);
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.1);
        }
        .status-badge.offline {
            background: rgba(244, 63, 94, 0.1);
            color: var(--rose);
            border: 1px solid rgba(244, 63, 94, 0.2);
            box-shadow: 0 0 15px rgba(244, 63, 94, 0.1);
        }

        /* TABLES */
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            text-align: left;
        }
        th {
            padding: 14px 12px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        td {
            padding: 16px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.02);
            font-size: 0.95rem;
            background: rgba(255,255,255,0.01);
        }
        tr:hover td {
            background: rgba(255,255,255,0.03);
        }

        /* INPUTS */
        .input-modern {
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            color: #fff;
            font-size: 1rem;
            outline: none;
            transition: all 0.2s;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
        }
        .input-modern:focus { border-color: var(--violet); box-shadow: inset 0 2px 4px rgba(0,0,0,0.5), 0 0 10px rgba(139, 92, 246, 0.2); }

        /* HERO BAR */
        .summary-bar-hero {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--panel-bg);
            border-radius: 16px;
            padding: 24px 30px;
            border: 1px solid var(--border-color);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.02);
            flex-wrap: wrap;
            gap: 20px;
        }
        .hero-item { display: flex; flex-direction: column; gap: 6px; }
        .hero-label { font-size: 0.85rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }
        .hero-val { font-size: 1.8rem; font-weight: 800; color: #f8fafc; }
        
        .mode-val-color { color: var(--cyan) !important; text-shadow: 0 0 10px rgba(6, 182, 212, 0.2); }
        .loss-val-color { color: var(--rose) !important; text-shadow: 0 0 10px rgba(244, 63, 94, 0.2); }
        .size-val-color { color: #fbbf24 !important; text-shadow: 0 0 10px rgba(251, 191, 36, 0.2); }

        /* LIVE TRADE COMPONENTS */
        .stat-box-modern {
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
        }
        .stat-row-modern {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: rgba(0, 0, 0, 0.15);
            border: 1px solid var(--border-color);
            border-radius: 10px;
        }
        .progress-box-modern {
            padding: 16px;
            background: rgba(0, 0, 0, 0.15);
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }
        .progress-bar-bg {
            height: 8px;
            background: rgba(0, 0, 0, 0.4);
            border-radius: 4px;
            overflow: hidden;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--cyan), var(--violet));
            transition: width 0.5s ease;
            box-shadow: 0 0 10px rgba(139, 92, 246, 0.5);
        }
        .pos-card-modern {
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
            display: flex;
            flex-direction: column;
            gap: 16px;
            box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
        }
        .pos-card-modern:hover {
            border-color: rgba(139, 92, 246, 0.4);
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.3), inset 0 2px 10px rgba(0,0,0,0.2);
        }
        
        /* TERMINALS */
        .log-terminal {
            background: rgba(0, 0, 0, 0.4);
            border-radius: 12px;
            padding: 16px;
            height: 300px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.85rem;
            color: #a7f3d0;
            border: 1px solid var(--border-color);
            box-shadow: inset 0 4px 15px rgba(0,0,0,0.5);
        }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse-red-alert {
            0% { box-shadow: 0 4px 15px rgba(190, 18, 60, 0.4), inset 0 2px 2px rgba(255, 255, 255, 0.2), inset 0 -2px 4px rgba(0,0,0,0.5); }
            50% { box-shadow: 0 4px 30px rgba(244, 63, 94, 0.8), inset 0 2px 2px rgba(255, 255, 255, 0.3), inset 0 -2px 4px rgba(0,0,0,0.5); }
            100% { box-shadow: 0 4px 15px rgba(190, 18, 60, 0.4), inset 0 2px 2px rgba(255, 255, 255, 0.2), inset 0 -2px 4px rgba(0,0,0,0.5); }
        }
    </style>
"""

    html = html[:style_start] + unified_css + html[head_end:]

    # 2. UPGRADE PANELS
    # We replace 'class="panel"' and 'class="panel full-width"' with 'class="glass-panel"' globally
    html = re.sub(r'class="panel\s*full-width"', 'class="glass-panel"', html)
    html = re.sub(r'class="panel"', 'class="glass-panel"', html)

    # 3. UPGRADE LIVE TRADE BUTTONS
    html = html.replace('btn-modern btn-theme-filled', 'btn-embossed btn-green')
    html = html.replace('btn-modern btn-neu-red', 'btn-embossed btn-red')
    html = html.replace('btn-modern btn-red-filled', 'btn-embossed btn-emergency-pulse')
    html = html.replace('btn-modern btn-theme-outline" onclick="runManualOrder()', 'btn-embossed btn-violet" onclick="runManualOrder()')
    html = html.replace('btn-modern btn-theme-outline" onclick="runTestOrder()', 'btn-embossed btn-cyan" onclick="runTestOrder()')
    html = html.replace('btn-modern btn-purple-solid', 'btn-embossed btn-violet') # Save lot size button

    # 4. UPGRADE OTHER BUTTONS
    html = re.sub(r'class="btn-start"', 'class="btn-embossed btn-green"', html)
    html = re.sub(r'class="btn-stop"', 'class="btn-embossed btn-red"', html)
    html = re.sub(r'class="btn-emergency"', 'class="btn-embossed btn-emergency-pulse"', html)
    html = re.sub(r'class="btn-test"', 'class="btn-embossed btn-cyan"', html)
    html = re.sub(r'<button([^>]+)style="background: linear-gradient[^>]*>([^<]*FORCE STRANGLE[^<]*)</button>', r'<button\1class="btn-embossed btn-violet">\2</button>', html)
    
    # Specific buttons in Analytics/Config
    html = html.replace('id="btn-run-backtest" class="btn-start"', 'id="btn-run-backtest" class="btn-embossed btn-violet"')
    # Any remaining raw buttons with inline styles we want to standardise:
    html = html.replace('class="btn-modern btn-green"', 'class="btn-embossed btn-green"')
    html = html.replace('class="btn-modern btn-red"', 'class="btn-embossed btn-red"')
    html = html.replace('class="btn-modern btn-alert"', 'class="btn-embossed btn-emergency-pulse"')
    html = html.replace('class="btn-modern btn-purple"', 'class="btn-embossed btn-violet"')
    html = html.replace('class="btn-modern btn-ghost"', 'class="btn-embossed btn-cyan"')
    html = html.replace('class="btn-modern btn-purple-solid"', 'class="btn-embossed btn-violet"')

    # Fix button HTML if icon tags are used:
    # Ensure they look good. The new embossed buttons will wrap the existing text seamlessly.

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("Global theme applied successfully.")

if __name__ == "__main__":
    process_file()
