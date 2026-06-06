import re

with open('templates/dashboard_backup.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. ADD NEW CSS CLASSES
new_css = """
        /* NEW GLASSMORPHISM & GRID CSS */
        .glass-panel {
            background: rgba(30, 41, 59, 0.6);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .glass-panel:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
            border-color: rgba(255, 255, 255, 0.12);
        }
        .summary-bar-hero {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.9), rgba(30, 41, 59, 0.9));
            border-radius: 16px;
            padding: 20px 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            flex-wrap: wrap;
            gap: 20px;
        }
        .hero-item {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .hero-label {
            font-size: 0.85rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .hero-val {
            font-size: 1.8rem;
            font-weight: 800;
            color: #f8fafc;
        }
        .hero-divider {
            width: 1px;
            height: 40px;
            background: rgba(255, 255, 255, 0.1);
        }
        .mode-val-color { color: #38bdf8 !important; }
        .loss-val-color { color: #f87171 !important; }
        .size-val-color { color: #fbbf24 !important; }
        
        .stat-box-modern {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .stat-row-modern {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 10px;
        }
        .badge-modern {
            font-weight: 700;
            font-size: 0.85rem;
            padding: 4px 10px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.1);
        }
        .progress-box-modern {
            padding: 16px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .progress-bar-bg {
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            transition: width 0.5s ease;
        }
        
        .btn-modern {
            padding: 14px 20px;
            border: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
            letter-spacing: 0.5px;
        }
        .btn-green { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
        .btn-green:hover { background: rgba(16, 185, 129, 0.25); }
        .btn-red { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .btn-red:hover { background: rgba(239, 68, 68, 0.25); }
        .btn-alert { background: linear-gradient(135deg, #ef4444, #b91c1c); color: #fff; box-shadow: 0 4px 15px rgba(239, 68, 68, 0.4); }
        .btn-alert:hover { transform: scale(1.02); }
        .btn-purple { background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(126, 34, 206, 0.2)); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
        .btn-purple:hover { background: rgba(168, 85, 247, 0.3); }
        .btn-purple-solid { background: linear-gradient(135deg, #a855f7, #7e22ce); color: #fff; }
        .btn-ghost { background: rgba(255, 255, 255, 0.05); color: #94a3b8; border: 1px dashed rgba(255, 255, 255, 0.2); }
        .btn-ghost:hover { background: rgba(255, 255, 255, 0.1); color: #fff; }
        
        .input-modern {
            padding: 10px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #fff;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        .input-modern:focus { border-color: #a855f7; }
        
        /* Re-styled Position Cards */
        .pos-card-modern {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .pos-card-modern:hover {
            border-color: rgba(168, 85, 247, 0.4);
            transform: translateY(-2px);
        }
        .leg-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 12px;
            border-bottom: 1px dashed rgba(255, 255, 255, 0.1);
        }
        .leg-title {
            font-size: 1.2rem;
            font-weight: 800;
        }
        .leg-pnl {
            font-size: 1.2rem;
            font-weight: 800;
            padding: 4px 12px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.05);
        }
        .leg-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            font-size: 0.9rem;
        }
        .leg-stat {
            display: flex;
            justify-content: space-between;
            color: #94a3b8;
        }
        .leg-stat span:last-child {
            color: #f8fafc;
            font-weight: 600;
        }
"""
html = html.replace('</style>', new_css + '\n    </style>')

# 2. EXTRACT SECTIONS
tab_live_start = html.find('<!-- TAB 1: LIVE TRADE -->')
tab_analytics_start = html.find('<!-- TAB 2: ANALYTICS -->')
positions_outer_start = html.find('<!-- TAB 2b: Positions always visible under Live -->')
tab_config_start = html.find('<!-- TAB 3: CONFIG -->')

if -1 in [tab_live_start, tab_analytics_start, positions_outer_start, tab_config_start]:
    print("Could not find section boundaries")
    exit(1)

html_before_live = html[:tab_live_start]
html_analytics = html[tab_analytics_start:positions_outer_start]
html_config_and_js = html[tab_config_start:]

# 3. CONSTRUCT NEW TAB-LIVE
new_tab_live = """
    <!-- TAB 1: LIVE TRADE -->
    <div class="tab-pane active" id="tab-live" style="max-width: 1100px; width: 100%; display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.3s ease;">
        
        <!-- TOP SUMMARY BAR -->
        <div class="summary-bar-hero">
            <div class="hero-item">
                <span class="hero-label">Current Equity</span>
                <span class="hero-val" id="equity-val">$0.00</span>
            </div>
            <div class="hero-divider" style="display:none;"></div>
            <div class="hero-item">
                <span class="hero-label">Mode</span>
                <span class="hero-val mode-val-color" id="mode-val">-</span>
            </div>
            <div class="hero-divider" style="display:none;"></div>
            <div class="hero-item">
                <span class="hero-label">Daily Loss Hits</span>
                <span class="hero-val loss-val-color" id="loss-hits-val">0 / 2</span>
            </div>
            <div class="hero-divider" style="display:none;"></div>
            <div class="hero-item">
                <span class="hero-label">Current Size</span>
                <span class="hero-val size-val-color" id="lot-multiplier-val">100%</span>
            </div>
            <div class="hero-divider" style="display:none;"></div>
            <div class="hero-item">
                <span class="hero-label">API Status</span>
                <span class="hero-val" id="api-status-badge" style="font-size:1.1rem; padding: 4px 12px; background: rgba(255,255,255,0.1); border-radius: 8px;">Unknown</span>
            </div>
        </div>

        <div id="paper-mode-note" style="display: none; padding: 14px 20px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; font-size: 0.95rem; color: #38bdf8; display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 1.4rem;">ℹ️</span>
            <div><strong>PAPER MODE ACTIVE</strong> - Realistic slippage + Smart Position Sizing enabled (No USDT balance required).</div>
        </div>

        <div id="next-day-paused-container" style="display: none;">
            <div style="padding: 14px 20px; border-radius: 12px; background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.3); color: var(--danger); font-weight: 700; text-align: center; font-size: 1.1rem; animation: pulse-red 2.5s infinite;">
                ⏸️ Trading Paused for Tomorrow (Daily Loss Limit Hit)
            </div>
        </div>

        <!-- TWO COLUMN GRID FOR OVERVIEW AND HEDGING -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 24px;">
            
            <!-- Section 1: Live Trade Overview -->
            <div class="glass-panel">
                <h2>📊 Live Trade Overview</h2>
                <div id="pos-total-bar" style="display: flex; flex-direction: column; gap: 16px; margin-top: 20px; display: none;">
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div class="stat-box-modern">
                            <span class="stat-label">Total P&L (USD)</span>
                            <span id="pos-total-pnl-usd" class="stat-val pnl-pos" style="font-size:1.6rem;">$0.00</span>
                        </div>
                        <div class="stat-box-modern">
                            <span class="stat-label">Total P&L (INR)</span>
                            <span id="pos-total-pnl-inr" class="stat-val pnl-pos" style="font-size:1.6rem;">₹0</span>
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div class="stat-box-modern">
                            <span class="stat-label">Capital Used</span>
                            <span class="stat-val" style="font-size:1.2rem;">$<span id="pos-total-capital">0.00</span></span>
                        </div>
                        <div class="stat-box-modern">
                            <span class="stat-label">Total Premium Collected</span>
                            <span class="stat-val" style="font-size:1.2rem;">$<span id="pos-total-entry">0.00</span></span>
                        </div>
                    </div>

                    <div class="stat-box-modern" style="background: rgba(16, 185, 129, 0.05); border-color: rgba(16, 185, 129, 0.2); flex-direction: row; justify-content: space-between; align-items: center;">
                        <span class="stat-label" style="color: #34d399;">Time to Square-off</span>
                        <span id="pos-time-remaining" class="stat-val" style="color: #34d399; font-size:1.4rem;">--</span>
                    </div>
                </div>
            </div>

            <!-- Section 2: Smart Hedging Status -->
            <div class="glass-panel" id="hedge-panel">
                <h2>🛡️ Smart Hedging Status</h2>
                <div style="display: flex; flex-direction: column; gap: 14px; margin-top: 20px;">
                    <div class="stat-row-modern">
                        <span class="stat-label">Hedge Status</span>
                        <span id="hedge-active-badge" class="badge-modern">Evaluating...</span>
                    </div>
                    <div class="stat-row-modern">
                        <span class="stat-label">Hedge Type</span>
                        <span id="hedge-type-val" style="font-weight:700; font-size:1.1rem;">-</span>
                    </div>
                    <div class="stat-row-modern">
                        <span class="stat-label">Hedge Size</span>
                        <span id="hedge-size-val" style="font-weight:700; color:#38bdf8; font-size:1.1rem;">0.000000 BTC</span>
                    </div>
                    <div class="stat-row-modern">
                        <span class="stat-label">Live Hedge P&L</span>
                        <span id="hedge-pnl-val" style="font-weight:700; color:#94a3b8; font-size:1.1rem;">$0.00</span>
                    </div>
                    
                    <div class="progress-box-modern">
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px;">
                            <span>Hedge Percentage</span>
                            <span id="hedge-percentage-val" style="font-weight: 800; color: #fff;">0%</span>
                        </div>
                        <div class="progress-bar-bg">
                            <div id="hedge-percentage-bar" class="progress-bar-fill"></div>
                        </div>
                    </div>

                    <div id="sl-tightened-badge" style="display: none; padding: 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 10px; font-size: 0.95rem; color: var(--danger); text-align: center; font-weight: 700; animation: pulse-red 2s infinite;">
                        ⚠️ Options SL Tightened to 105%
                    </div>
                </div>
            </div>

        </div>

        <!-- Section 3: Active Positions -->
        <div class="glass-panel" style="padding-bottom: 30px;">
            <h2>📈 Active Positions</h2>
            <div id="positions-cards" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin-top: 20px;">
                <div style="text-align: center; padding: 50px; background: rgba(255,255,255,0.02); border-radius: 16px; border: 1px dashed rgba(255,255,255,0.1); grid-column: 1 / -1;">
                    <div style="font-size: 3.5rem; margin-bottom: 15px;">📭</div>
                    <div style="font-weight: 700; color: #94a3b8; font-size: 1.2rem;">No Active Positions</div>
                    <div style="font-size: 0.95rem; margin-top: 8px; opacity: 0.5;">The bot has no open trades right now.</div>
                </div>
            </div>
        </div>

        <!-- Section 4: Live Trade Rules Monitor -->
        <div class="glass-panel" id="rule-compliance-panel">
            <h2>⚖️ Live Trade Rules Monitor</h2>
            <div style="margin-top: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
                    <div style="font-size: 0.95rem; color: #94a3b8;">Real-time monitoring of all entry conditions.</div>
                    <div id="compliance-badge" style="font-weight: 800; font-size: 1.1rem; padding: 8px 16px; border-radius: 8px; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: var(--success);">
                        100% Compliant
                    </div>
                </div>
                <div id="rules-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px;">
                    <!-- Populated by JS -->
                </div>
            </div>
        </div>

        <!-- Section 5: Controls Panel -->
        <div class="glass-panel" style="border: 1px solid rgba(168, 85, 247, 0.2); background: linear-gradient(180deg, rgba(30, 41, 59, 0.6) 0%, rgba(168, 85, 247, 0.05) 100%);">
            <h2>⚙️ Manual Controls</h2>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 20px;">
                <button class="btn-modern btn-green" onclick="sendCommand('start')">▶ START BOT</button>
                <button class="btn-modern btn-red" onclick="sendCommand('stop')">⏹ STOP BOT</button>
                <button class="btn-modern btn-alert" onclick="emergencyClose()">🚨 EMERGENCY SQUARE OFF</button>
                <button id="btn-manual-order" class="btn-modern btn-purple" onclick="runManualOrder()">⚡ FORCE STRANGLE ENTRY</button>
                <button id="btn-test-order" class="btn-modern btn-ghost" onclick="runTestOrder()">🧪 TEST ORDER (1 Lot)</button>
            </div>

            <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid rgba(255,255,255,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                    <div>
                        <div style="font-weight: 700; font-size: 1.05rem; color: #f8fafc;">Manual Lot Size Override</div>
                        <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 4px;">Currently active: <strong id="active-lot-display" style="color: #c084fc; font-size:1.1rem;">— lots</strong> <span id="active-lot-perleg"></span></div>
                    </div>
                    <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                        <input id="lotSizeInput" type="number" min="1" max="10000" placeholder="e.g. 200" class="input-modern" style="width: 140px;" />
                        <button id="saveLotSizeBtn" onclick="saveLotSize()" class="btn-modern btn-purple-solid" style="padding: 10px 24px;">Save Override</button>
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 20px; margin-top: 20px;">
                <div>
                    <div class="stat-label">Consecutive Losses</div>
                    <div id="consecutive-losses-val" style="font-weight: 600; color: var(--danger); font-size: 1.1rem;">0</div>
                </div>
                <div>
                    <div class="stat-label">Sizing Cooldown</div>
                    <div id="sizing-cooldown-val" style="font-weight: 600; color: var(--text-secondary); font-size: 1.1rem;">No Cooldown</div>
                </div>
            </div>
        </div>

    </div><!-- /tab-live -->

"""

# We need to change JS for `posCards.innerHTML`
js_old = """                        const isCall = pos.leg_type === 'call';
                        const legLabel = isCall
                            ? '<span class="pos-call-label">🟢 CALL</span>'
                            : '<span class="pos-put-label">🔴 PUT</span>';

                        return `
                        <div class="pos-card">
                            <div class="pos-header-row">
                                <div style="font-weight: 800; font-size: 1.15rem; color: var(--text-primary);">
                                    ${legLabel} &nbsp; ${pos.strike}
                                </div>
                                <div class="${pos.pnl_usd >= 0 ? 'pnl-pos' : 'pnl-neg'}" style="font-weight: 800; font-size: 1.1rem;">
                                    ${pos.pnl_usd >= 0 ? '+' : ''}${pos.pnl_usd.toFixed(2)} USDT
                                    <span style="font-size: 0.8em; opacity: 0.8;">(${pos.pnl_usd >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</span>
                                </div>
                            </div>
                            
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px;">
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Entry Premium</div>
                                    <div style="font-weight: 600; font-size:0.95rem;">$${pos.entry_price.toFixed(2)}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Current Premium</div>
                                    <div style="font-weight: 600; font-size:0.95rem; color: #a78bfa;">$${pos.current_price.toFixed(2)}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Size</div>
                                    <div style="font-weight: 600; font-size:0.95rem;">${pos.size.toFixed(4)} BTC</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Capital Used</div>
                                    <div style="font-weight: 600; font-size:0.95rem;">$${pos.capital_used.toFixed(2)}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Delta / Gamma</div>
                                    <div style="font-weight: 600; font-size:0.95rem; color: #cbd5e1;">${(pos.delta||0).toFixed(4)} / ${(pos.gamma||0).toFixed(4)}</div>
                                </div>
                                <div>
                                    <div class="stat-label" style="font-size:0.75rem;">Live IV</div>
                                    <div style="font-weight: 600; font-size:0.95rem; color: #38bdf8;">${((pos.iv||0)*100).toFixed(1)}%</div>
                                </div>
                            </div>
                        </div>
                        `;"""

js_new = """                        const isCall = pos.leg_type === 'call';
                        const legLabel = isCall
                            ? '<span style="color: #34d399;">🟢 CALL</span>'
                            : '<span style="color: #f87171;">🔴 PUT</span>';
                        
                        const pnlColor = pos.pnl_usd >= 0 ? '#34d399' : '#f87171';
                        const pnlBg = pos.pnl_usd >= 0 ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';

                        return `
                        <div class="pos-card-modern">
                            <div class="leg-header">
                                <div class="leg-title">${legLabel} &nbsp; <span style="color:#f8fafc;">${pos.strike}</span></div>
                                <div class="leg-pnl" style="color: ${pnlColor}; background: ${pnlBg}; border: 1px solid ${pnlBg};">
                                    ${pos.pnl_usd >= 0 ? '+' : ''}${pos.pnl_usd.toFixed(2)} USDT
                                    <span style="font-size: 0.8em; opacity: 0.8;">(${pos.pnl_usd >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</span>
                                </div>
                            </div>
                            
                            <div class="leg-grid">
                                <div class="leg-stat"><span>Entry Premium</span> <span>$${pos.entry_price.toFixed(2)}</span></div>
                                <div class="leg-stat"><span>Current Premium</span> <span style="color: #c084fc;">$${pos.current_price.toFixed(2)}</span></div>
                                <div class="leg-stat"><span>Size</span> <span>${pos.size.toFixed(4)} BTC</span></div>
                                <div class="leg-stat"><span>Capital Used</span> <span>$${pos.capital_used.toFixed(2)}</span></div>
                                <div class="leg-stat"><span>Delta / Gamma</span> <span style="color: #94a3b8;">${(pos.delta||0).toFixed(4)} / ${(pos.gamma||0).toFixed(4)}</span></div>
                                <div class="leg-stat"><span>Live IV</span> <span style="color: #38bdf8;">${((pos.iv||0)*100).toFixed(1)}%</span></div>
                            </div>
                        </div>
                        `;"""

html_config_and_js = html_config_and_js.replace(js_old, js_new)

# 4. We also need to remove positions-outer logic from JS switchTab
js_switch_old = """            if (name === 'live') {
                document.getElementById('tab-live').classList.add('active');
                document.getElementById('positions-outer').style.display = 'block';
            } else if (name === 'analytics') {"""

js_switch_new = """            if (name === 'live') {
                document.getElementById('tab-live').classList.add('active');
            } else if (name === 'analytics') {"""

html_config_and_js = html_config_and_js.replace(js_switch_old, js_switch_new)

js_switch_old2 = """            } else if (name === 'config') {
                document.getElementById('tab-config').classList.add('active');
                document.getElementById('positions-outer').style.display = 'none';
            }"""

js_switch_new2 = """            } else if (name === 'config') {
                document.getElementById('tab-config').classList.add('active');
            }"""
html_config_and_js = html_config_and_js.replace(js_switch_old2, js_switch_new2)

js_switch_old3 = """                document.getElementById('tab-analytics').classList.add('active');
                document.getElementById('positions-outer').style.display = 'none';"""

js_switch_new3 = """                document.getElementById('tab-analytics').classList.add('active');"""
html_config_and_js = html_config_and_js.replace(js_switch_old3, js_switch_new3)

# 5. ASSEMBLE EVERYTHING
final_html = html_before_live + new_tab_live + "\n\n" + html_analytics + html_config_and_js

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(final_html)

print("Redesign applied successfully.")
