import re

def inject_html_css():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()
        
    css = """
/* PSCE ARES DECISION CARD CSS */
.psce-card {
    background: #0b0f19;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    font-family: 'Inter', sans-serif;
    color: #fff;
    max-width: 1100px;
}
.psce-top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 15px;
}
.psce-logo {
    font-size: 24px;
    font-weight: 800;
    background: linear-gradient(90deg, #00d4ff, #a855f7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 2px;
}
.psce-title {
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 1px;
}
.psce-subtitle {
    font-size: 12px;
    color: #94a3b8;
    text-transform: uppercase;
}
.psce-grid {
    display: grid;
    grid-template-columns: 1fr 1.2fr 1fr;
    gap: 20px;
}
.psce-col-left, .psce-col-right {
    display: flex;
    flex-direction: column;
    gap: 15px;
}
.psce-metric-box {
    background: rgba(20, 25, 40, 0.6);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.psce-metric-label {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 8px;
}
.psce-metric-val {
    font-size: 22px;
    font-weight: 700;
}
.psce-green { color: #10b981; }
.psce-yellow { color: #f59e0b; }
.psce-red { color: #ef4444; }

.psce-center-card {
    background: radial-gradient(circle at 50% 50%, rgba(16, 185, 129, 0.15), transparent 70%);
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 30px 20px;
    text-align: center;
    box-shadow: inset 0 0 40px rgba(16,185,129,0.05), 0 0 20px rgba(16,185,129,0.1);
    transition: all 0.3s ease;
}
.psce-center-card.psce-zone-red {
    background: radial-gradient(circle at 50% 50%, rgba(239, 68, 68, 0.15), transparent 70%);
    border-color: rgba(239, 68, 68, 0.4);
    box-shadow: inset 0 0 40px rgba(239,68,68,0.05), 0 0 20px rgba(239,68,68,0.1);
}
.psce-center-card.psce-zone-yellow {
    background: radial-gradient(circle at 50% 50%, rgba(245, 158, 11, 0.15), transparent 70%);
    border-color: rgba(245, 158, 11, 0.4);
    box-shadow: inset 0 0 40px rgba(245,158,11,0.05), 0 0 20px rgba(245,158,11,0.1);
}

.psce-zone-title {
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: #fff;
    margin-bottom: 5px;
}
.psce-zone-main {
    font-size: 36px;
    font-weight: 800;
    text-shadow: 0 0 10px currentColor;
    margin-bottom: 5px;
}
.psce-zone-sub {
    font-size: 12px;
    color: #10b981;
    text-transform: uppercase;
    margin-bottom: 30px;
}
.psce-center-card.psce-zone-red .psce-zone-sub { color: #ef4444; }
.psce-center-card.psce-zone-yellow .psce-zone-sub { color: #f59e0b; }

.psce-confidence-ring {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    border: 8px solid rgba(16, 185, 129, 0.2);
    border-top-color: #10b981;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin-bottom: 30px;
    position: relative;
}
.psce-center-card.psce-zone-red .psce-confidence-ring {
    border: 8px solid rgba(239, 68, 68, 0.2);
    border-top-color: #ef4444;
}
.psce-center-card.psce-zone-yellow .psce-confidence-ring {
    border: 8px solid rgba(245, 158, 11, 0.2);
    border-top-color: #f59e0b;
}

.psce-conf-val {
    font-size: 28px;
    font-weight: 700;
}
.psce-conf-label {
    font-size: 10px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.psce-action-box {
    background: rgba(0,0,0,0.3);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 15px 30px;
    width: 100%;
    box-sizing: border-box;
}
.psce-action-label {
    font-size: 10px;
    color: #10b981;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 5px;
}
.psce-center-card.psce-zone-red .psce-action-label { color: #ef4444; }
.psce-center-card.psce-zone-yellow .psce-action-label { color: #f59e0b; }

.psce-action-val {
    font-size: 22px;
    font-weight: 800;
}
.psce-reason-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.psce-reason-item {
    display: flex;
    gap: 12px;
    align-items: flex-start;
}
.psce-reason-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: rgba(255,255,255,0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    flex-shrink: 0;
}
.psce-reason-text {
    font-size: 13px;
    color: #e2e8f0;
}

/* Bottom Meter */
.psce-meter-container {
    background: rgba(20, 25, 40, 0.6);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 20px;
}
.psce-meter-bar {
    height: 8px;
    background: linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #10b981 100%);
    border-radius: 4px;
    position: relative;
    margin: 20px 0;
}
.psce-meter-thumb {
    width: 16px;
    height: 16px;
    background: #fff;
    border-radius: 50%;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 0 10px rgba(255,255,255,0.8);
    transition: left 1s ease-in-out;
    left: 50%;
}
.psce-meter-labels {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #94a3b8;
    text-transform: uppercase;
}
.psce-bottom-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
    margin-top: 10px;
    padding-top: 15px;
    border-top: 1px solid rgba(255,255,255,0.05);
}

.psce-block-alert {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.4);
    border-radius: 8px;
    padding: 12px 16px;
    display: none;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
    color: #ef4444;
}
.psce-block-alert.active { display: flex; }

.psce-progressbar-bg {
    height: 4px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
}
.psce-progressbar-fill {
    height: 100%;
    background: #f59e0b;
    border-radius: 2px;
    transition: width 0.5s ease;
}
"""

    html = """
        <!-- PSCE MASTER GATE -->
        <div class="psce-card">
            
            <div class="psce-block-alert" id="psce-block-alert">
                <span style="font-size: 24px;">🚨</span>
                <div style="width: 100%;">
                    <div style="font-weight: 800; font-size: 14px; letter-spacing: 1px;">BLOCKED BY PREMIUM SELLING CONDITIONS</div>
                    <div id="psce-block-reason" style="font-size: 12px; margin-top: 4px; font-weight: 600;">Reason: </div>
                    
                    <div style="margin-top: 12px; background: rgba(0,0,0,0.2); border-radius: 8px; padding: 10px; font-size: 11px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                        <div style="display:flex; justify-content:space-between;"><span>IV Stability:</span><span id="expl-stability">--</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>IV Percentile:</span><span id="expl-percentile">--</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>IV Rank:</span><span id="expl-rank">--</span></div>
                        <div style="display:flex; justify-content:space-between;"><span>1H Expansion:</span><span id="expl-expansion">--</span></div>
                        <div style="grid-column: span 2; display:flex; justify-content:space-between; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 6px; margin-top: 2px;">
                            <span>Premium State:</span><span id="expl-premium">--</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="psce-top-bar">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div class="psce-logo">ARES</div>
                    <div>
                        <div class="psce-title">IV DECISION CARD</div>
                        <div class="psce-subtitle">BTC OPTIONS INTRADAY FILTER</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <div id="psce-btc-price" style="font-size: 16px; font-weight: 700;">BTC $--</div>
                    <div id="psce-last-update" style="font-size: 12px; color: #94a3b8;">--</div>
                </div>
            </div>

            <div class="psce-grid">
                <!-- Left Column -->
                <div class="psce-col-left">
                    <div class="psce-metric-box">
                        <div class="psce-metric-label" style="display:flex; justify-content:space-between;">
                            <span>ATM IV</span>
                            <span id="psce-iv-live" style="color: #10b981; font-size:10px;">● LIVE</span>
                        </div>
                        <div class="psce-metric-val psce-green" id="psce-atm-iv">--%</div>
                    </div>
                    
                    <div class="psce-metric-box">
                        <div class="psce-metric-label">IV Percentile (30D)</div>
                        <div class="psce-metric-val" id="psce-iv-percentile">--%</div>
                        <div class="psce-progressbar-bg"><div class="psce-progressbar-fill" id="psce-iv-pct-bar" style="width:0%"></div></div>
                    </div>

                    <div class="psce-metric-box">
                        <div class="psce-metric-label">IV Rank (30D)</div>
                        <div class="psce-metric-val" id="psce-iv-rank">--</div>
                        <div class="psce-progressbar-bg"><div class="psce-progressbar-fill" id="psce-iv-rank-bar" style="width:0%"></div></div>
                    </div>

                    <div class="psce-metric-box">
                        <div class="psce-metric-label">5 Day IV Trend</div>
                        <div class="psce-metric-val psce-green" id="psce-iv-trend">--</div>
                    </div>

                    <div class="psce-metric-box">
                        <div class="psce-metric-label">IV Stability (Today)</div>
                        <div class="psce-metric-val" id="psce-iv-stability" style="font-size: 16px;">--</div>
                    </div>
                </div>

                <!-- Center Shield Card -->
                <div class="psce-center-card" id="psce-center-shield">
                    <div class="psce-zone-title">IV ZONE</div>
                    <div class="psce-zone-main" id="psce-zone-main">LOADING</div>
                    <div class="psce-zone-sub" id="psce-zone-sub">ANALYZING EDGE...</div>

                    <div class="psce-confidence-ring">
                        <div class="psce-conf-val" id="psce-edge-score">--</div>
                        <div class="psce-conf-label">EDGE SCORE</div>
                    </div>

                    <div class="psce-action-box">
                        <div class="psce-action-label">ACTION</div>
                        <div class="psce-action-val" id="psce-decision">WAITING</div>
                    </div>
                </div>

                <!-- Right Column -->
                <div class="psce-col-right" style="background: rgba(20, 25, 40, 0.6); border-radius: 12px; padding: 20px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="font-size: 12px; color: #10b981; font-weight: 700; margin-bottom: 20px;">WHY THIS ZONE?</div>
                    <div class="psce-reason-list" id="psce-reasons">
                        <div class="psce-reason-item">
                            <div class="psce-reason-icon">⏳</div>
                            <div class="psce-reason-text">Loading live data...</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Bottom Meter -->
            <div class="psce-meter-container">
                <div style="font-size: 12px; font-weight: 700; color: #fff; margin-bottom: 5px;">EDGE ZONE METER</div>
                <div class="psce-meter-bar">
                    <div class="psce-meter-thumb" id="psce-meter-thumb"></div>
                </div>
                <div class="psce-meter-labels">
                    <div style="color: #ef4444; width: 33%;">LOW EDGE<br><span style="font-size:10px;">Skip Trade</span></div>
                    <div style="color: #f59e0b; width: 33%; text-align: center;">CAUTION<br><span style="font-size:10px;">Reduce Size</span></div>
                    <div style="color: #10b981; width: 33%; text-align: right;">HEALTHY<br><span style="font-size:10px;">Optimal Edge</span></div>
                </div>
                
                <div class="psce-bottom-stats">
                    <div>
                        <div class="psce-metric-label">Feed Health</div>
                        <div id="psce-health-feed" style="font-size:14px; font-weight:600; color:#10b981;">ONLINE</div>
                    </div>
                    <div>
                        <div class="psce-metric-label">1H IV Change</div>
                        <div id="psce-1h-change" style="font-size:14px; font-weight:600;">--</div>
                    </div>
                    <div style="grid-column: span 2;">
                        <div class="psce-metric-label">Premium Environment</div>
                        <div id="psce-premium-env" style="font-size:14px; font-weight:600;">--</div>
                    </div>
                </div>
            </div>
        </div>
        <!-- END PSCE MASTER GATE -->
"""

    js = """
// PSCE Updater
function updatePSCE() {
    fetch('/api/premium_conditions')
        .then(r => r.json())
        .then(data => {
            const el = id => document.getElementById(id);
            if (!data.status) return;
            
            // Handle Top level block alert
            const blockAlert = el('psce-block-alert');
            const blockReason = el('psce-block-reason');
            if (!data.trade_allowed && data.decision !== "WAITING") {
                blockAlert.classList.add('active');
                blockReason.innerText = "Reason: " + (data.reasons[0] || "Low Edge");
                
                // Populate explainability panel
                if (data.metrics) {
                    const m = data.metrics;
                    el('expl-stability').innerHTML = m.iv_stability === "Stable" ? `<span style="color:var(--success)">✅ ${m.iv_stability}</span>` : `<span style="color:var(--danger)">❌ ${m.iv_stability}</span>`;
                    el('expl-percentile').innerHTML = parseFloat(m.iv_percentile) > 20 ? `<span style="color:var(--success)">✅ ${parseFloat(m.iv_percentile).toFixed(0)}%</span>` : `<span style="color:var(--danger)">❌ ${parseFloat(m.iv_percentile).toFixed(0)}%</span>`;
                    el('expl-rank').innerHTML = parseFloat(m.iv_rank) > 20 ? `<span style="color:var(--success)">✅ ${parseFloat(m.iv_rank).toFixed(0)}</span>` : `<span style="color:var(--danger)">❌ ${parseFloat(m.iv_rank).toFixed(0)}</span>`;
                    el('expl-expansion').innerHTML = parseFloat(m.iv_change_1h) < 1.0 ? `<span style="color:var(--success)">✅ ${m.iv_change_1h}</span>` : `<span style="color:var(--danger)">❌ ${m.iv_change_1h}</span>`;
                    
                    let pEnv = data.premium_state;
                    if (pEnv.includes("Excellent") || pEnv.includes("Good")) {
                        el('expl-premium').innerHTML = `<span style="color:var(--success)">✅ ${pEnv.replace("Premium Selling Environment: ", "")}</span>`;
                    } else if (pEnv.includes("Average")) {
                        el('expl-premium').innerHTML = `<span style="color:var(--warning)">⚠ ${pEnv.replace("Premium Selling Environment: ", "")}</span>`;
                    } else {
                        el('expl-premium').innerHTML = `<span style="color:var(--danger)">❌ ${pEnv.replace("Premium Selling Environment: ", "")}</span>`;
                    }
                }
            } else {
                blockAlert.classList.remove('active');
            }

            // Update Metrics
            if (data.metrics) {
                el('psce-btc-price').innerText = `BTC $${parseFloat(data.metrics.btc_price).toLocaleString()}`;
                el('psce-atm-iv').innerText = parseFloat(data.metrics.atm_iv).toFixed(1) + "%";
                el('psce-iv-percentile').innerText = parseFloat(data.metrics.iv_percentile).toFixed(0) + "%";
                el('psce-iv-rank').innerText = parseFloat(data.metrics.iv_rank).toFixed(0);
                el('psce-iv-trend').innerText = data.metrics.iv_trend_5d;
                el('psce-iv-stability').innerText = data.metrics.iv_stability;
                el('psce-1h-change').innerText = data.metrics.iv_change_1h;
                
                el('psce-iv-pct-bar').style.width = Math.min(100, Math.max(0, parseFloat(data.metrics.iv_percentile))) + "%";
                el('psce-iv-rank-bar').style.width = Math.min(100, Math.max(0, parseFloat(data.metrics.iv_rank))) + "%";
            }
            
            el('psce-last-update').innerText = "Updated: " + data.last_update;
            el('psce-premium-env').innerText = data.premium_state;

            // Center Card Updates
            const shield = el('psce-center-shield');
            shield.classList.remove('psce-zone-red', 'psce-zone-yellow');
            let mainColor = "var(--success)";
            if (data.zone === "RED" || data.zone === "LOW EDGE") {
                shield.classList.add('psce-zone-red');
                mainColor = "var(--danger)";
            } else if (data.zone === "YELLOW" || data.zone === "CAUTION") {
                shield.classList.add('psce-zone-yellow');
                mainColor = "var(--warning)";
            }
            
            el('psce-zone-main').innerText = data.zone;
            el('psce-zone-main').style.color = mainColor;
            el('psce-zone-sub').innerText = data.trade_allowed ? "OPTIMAL FOR PREMIUM SELLING" : "UNFAVORABLE CONDITIONS";
            
            el('psce-edge-score').innerText = Math.round(data.edge_score) + "";
            el('psce-decision').innerText = data.decision;
            el('psce-decision').style.color = mainColor;

            // Update reasons list
            const reasonsHtml = data.reasons.map(r => `
                <div class="psce-reason-item">
                    <div class="psce-reason-icon" style="color: ${mainColor}">✓</div>
                    <div class="psce-reason-text">${r}</div>
                </div>
            `).join("");
            el('psce-reasons').innerHTML = reasonsHtml;

            // Thumb meter (0 to 100%)
            el('psce-meter-thumb').style.left = Math.min(100, Math.max(0, data.edge_score)) + "%";

            // Feed Health
            if (data.health) {
                const isHealthy = Object.values(data.health).every(v => v === "ONLINE");
                el('psce-health-feed').innerText = isHealthy ? "ALL SYSTEMS ONLINE" : "FEED DEGRADED";
                el('psce-health-feed').style.color = isHealthy ? "var(--success)" : "var(--danger)";
                el('psce-iv-live').innerText = (data.health.iv_feed === "ONLINE") ? "● LIVE" : "● OFFLINE";
                el('psce-iv-live').style.color = (data.health.iv_feed === "ONLINE") ? "var(--success)" : "var(--danger)";
            }
        });
}

// Add it to the main poller
setInterval(updatePSCE, 3000);
setTimeout(updatePSCE, 500);
"""

    if "/* PSCE ARES DECISION CARD CSS */" not in content:
        # 1. Inject CSS right before </style> (which is near the top)
        # Using regex to find the first </style>
        content = re.sub(r'(\s*)</style>', r'\n' + css + r'\1</style>', content, count=1)
        
        # 2. Inject HTML right before <div id="trade-skip-alert-card"
        target_html = r'(<div id="trade-skip-alert-card")'
        content = re.sub(target_html, html + r'\n        \1', content)
        
        # 3. Inject JS before </body>
        content = content.replace('</body>', f'<script>\n{js}\n</script>\n</body>')
        
        with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print("PSCE successfully injected into templates/dashboard.html!")
    else:
        print("PSCE already injected in dashboard.html.")

if __name__ == '__main__':
    inject_html_css()
