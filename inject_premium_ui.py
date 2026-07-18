import re
import sys

def remove_old_and_inject():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to strip out old CSS
    content = re.sub(r'/\* PSCE ARES DECISION CARD CSS \*/.*?(?=</style>)', '', content, flags=re.DOTALL)
    
    # Regex to strip out old HTML
    content = re.sub(r'<!-- PSCE MASTER GATE -->.*?<!-- END PSCE MASTER GATE -->', '', content, flags=re.DOTALL)
    
    # Regex to strip out old JS
    content = re.sub(r'// PSCE Updater.*?setTimeout\(updatePSCE, 500\);', '', content, flags=re.DOTALL)

    css = """
/* ARES IV DECISION CARD CSS */
.ares-iv-container {
    background: #0b0f19;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 24px;
    font-family: 'Inter', sans-serif;
    color: #fff;
    max-width: 1200px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    box-shadow: 0 20px 40px rgba(0,0,0,0.6);
}

/* TOP BAR */
.ares-iv-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding-bottom: 16px;
}
.ares-logo-container {
    display: flex;
    align-items: center;
    gap: 16px;
}
.ares-logo-text {
    font-size: 32px;
    font-weight: 800;
    background: linear-gradient(90deg, #38bdf8, #a855f7);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 2px;
    font-style: italic;
}
.ares-title-text {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
}
.ares-subtitle-text {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 2px;
}
.ares-header-right {
    display: flex;
    gap: 24px;
}
.ares-header-stat {
    display: flex;
    align-items: center;
    gap: 12px;
    background: rgba(255,255,255,0.03);
    padding: 8px 16px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.05);
}
.ares-stat-icon {
    font-size: 20px;
    color: #f59e0b;
}

/* MAIN GRID */
.ares-iv-grid {
    display: grid;
    grid-template-columns: 1fr 1.3fr 1fr;
    gap: 20px;
}

/* LEFT COLUMN */
.ares-left-col {
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.ares-metric-box {
    background: rgba(20,25,40,0.4);
    border: 1px solid rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}
.ares-metric-header {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #94a3b8;
    margin-bottom: 8px;
}
.ares-metric-live {
    color: #10b981;
    font-size: 9px;
    display: flex;
    align-items: center;
    gap: 4px;
}
.ares-metric-live::before {
    content: '';
    display: block;
    width: 6px;
    height: 6px;
    background: #10b981;
    border-radius: 50%;
    animation: pulse-green 2s infinite;
}
.ares-metric-value-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}
.ares-metric-val {
    font-size: 24px;
    font-weight: 700;
}
.text-green { color: #10b981; }
.text-red { color: #ef4444; }

.ares-progress-bg {
    height: 4px;
    background: rgba(255,255,255,0.1);
    border-radius: 2px;
    margin-top: 8px;
    width: 100%;
}
.ares-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #f59e0b, #10b981);
    border-radius: 2px;
    position: relative;
}
.ares-progress-thumb {
    width: 4px;
    height: 12px;
    background: #fff;
    position: absolute;
    right: 0;
    top: -4px;
    box-shadow: 0 0 5px rgba(255,255,255,0.8);
}

/* CENTER COLUMN (SHIELD) */
.ares-center-card {
    background: radial-gradient(circle at 50% 30%, rgba(16, 185, 129, 0.15) 0%, rgba(11, 15, 25, 0) 70%);
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 16px;
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    box-shadow: inset 0 0 60px rgba(16,185,129,0.05), 0 0 20px rgba(16,185,129,0.1);
    position: relative;
    overflow: hidden;
}
.ares-center-card.zone-red {
    background: radial-gradient(circle at 50% 30%, rgba(239, 68, 68, 0.15) 0%, rgba(11, 15, 25, 0) 70%);
    border-color: rgba(239, 68, 68, 0.3);
    box-shadow: inset 0 0 60px rgba(239,68,68,0.05), 0 0 20px rgba(239,68,68,0.1);
}
.ares-center-card.zone-yellow {
    background: radial-gradient(circle at 50% 30%, rgba(245, 158, 11, 0.15) 0%, rgba(11, 15, 25, 0) 70%);
    border-color: rgba(245, 158, 11, 0.3);
    box-shadow: inset 0 0 60px rgba(245,158,11,0.05), 0 0 20px rgba(245,158,11,0.1);
}

.ares-shield-icon {
    width: 60px;
    height: 70px;
    background: url('data:image/svg+xml;utf8,<svg viewBox="0 0 24 24" fill="none" stroke="%2310b981" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>') no-repeat center;
    background-size: contain;
    margin-bottom: 12px;
}
.ares-center-card.zone-red .ares-shield-icon { stroke: %23ef4444; }

.ares-zone-label {
    font-size: 12px;
    color: #94a3b8;
    letter-spacing: 2px;
}
.ares-zone-main {
    font-size: 38px;
    font-weight: 800;
    color: #10b981;
    text-shadow: 0 0 15px rgba(16,185,129,0.5);
    margin: 4px 0;
}
.ares-zone-sub {
    font-size: 11px;
    color: #10b981;
    background: rgba(16, 185, 129, 0.1);
    padding: 4px 12px;
    border-radius: 12px;
    letter-spacing: 1px;
}

.ares-confidence-circle {
    margin: 24px 0;
    width: 110px;
    height: 110px;
    border-radius: 50%;
    border: 8px solid rgba(16,185,129,0.2);
    border-top-color: #10b981;
    border-right-color: #10b981;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 20px rgba(16,185,129,0.2);
}
.ares-conf-val {
    font-size: 32px;
    font-weight: 800;
}
.ares-conf-lbl {
    font-size: 9px;
    color: #94a3b8;
    letter-spacing: 1px;
}

.ares-action-box {
    border: 1px solid rgba(16,185,129,0.4);
    background: rgba(16,185,129,0.05);
    border-radius: 12px;
    width: 100%;
    padding: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 16px;
}
.ares-action-label {
    font-size: 10px;
    color: #10b981;
    letter-spacing: 1px;
    margin-bottom: 4px;
}
.ares-action-val {
    font-size: 22px;
    font-weight: 800;
    display: flex;
    align-items: center;
    gap: 8px;
}

.ares-center-footer {
    display: flex;
    width: 100%;
    justify-content: space-between;
    border-top: 1px solid rgba(255,255,255,0.05);
    padding-top: 16px;
}
.ares-cf-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}
.ares-cf-lbl {
    font-size: 9px;
    color: #94a3b8;
}
.ares-cf-val {
    font-size: 11px;
    font-weight: 700;
    color: #10b981;
}

/* RIGHT COLUMN */
.ares-right-col {
    background: rgba(20,25,40,0.4);
    border: 1px solid rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 20px;
}
.ares-right-title {
    font-size: 13px;
    color: #10b981;
    font-weight: 700;
    margin-bottom: 20px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding-bottom: 12px;
}
.ares-reasons-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.ares-reason-row {
    display: flex;
    gap: 12px;
    align-items: flex-start;
}
.ares-reason-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    flex-shrink: 0;
    color: #10b981;
}
.ares-reason-text-main {
    font-size: 13px;
    font-weight: 600;
    color: #e2e8f0;
}
.ares-reason-text-sub {
    font-size: 11px;
    color: #64748b;
    margin-top: 2px;
}

/* ZONE METER */
.ares-zone-meter {
    background: rgba(20,25,40,0.4);
    border: 1px solid rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 20px;
}
.ares-zm-header {
    font-size: 12px;
    font-weight: 700;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
}
.ares-zm-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    text-align: center;
    position: relative;
    padding-bottom: 20px;
}
.ares-zm-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}
.ares-zm-title { font-size: 12px; font-weight: 700; }
.ares-zm-range { font-size: 11px; color: #94a3b8; }
.ares-zm-sub { font-size: 11px; }

.ares-zm-bar-container {
    height: 6px;
    background: linear-gradient(90deg, #ef4444 0%, #f59e0b 50%, #10b981 100%);
    border-radius: 3px;
    margin-top: 10px;
    position: relative;
}
.ares-zm-thumb {
    width: 14px;
    height: 14px;
    background: #fff;
    border-radius: 50%;
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 0 10px #fff;
    transition: left 0.5s;
}

/* BOTTOM MODULES */
.ares-bottom-strip {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
}
.ares-strip-box {
    background: rgba(20,25,40,0.4);
    border: 1px solid rgba(255,255,255,0.03);
    border-radius: 12px;
    padding: 16px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.ares-strip-icon {
    font-size: 20px;
    color: #38bdf8;
    opacity: 0.8;
}
.ares-strip-title {
    font-size: 9px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.ares-strip-val {
    font-size: 14px;
    font-weight: 700;
    margin: 2px 0;
}
.ares-strip-sub {
    font-size: 10px;
    color: #64748b;
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
"""

    html = """
        <!-- ARES IV DECISION CARD (EXACT REPLICA) -->
        <div class="ares-iv-container">
            
            <div class="psce-block-alert" id="psce-block-alert">
                <span style="font-size: 24px;">🚨</span>
                <div style="width: 100%;">
                    <div style="font-weight: 800; font-size: 14px; letter-spacing: 1px;">BLOCKED BY TRADE READINESS MASTER GATE</div>
                    <div id="psce-block-reason" style="font-size: 12px; margin-top: 4px; font-weight: 600;">Reason: </div>
                </div>
            </div>

            <!-- Header -->
            <div class="ares-iv-header">
                <div class="ares-logo-container">
                    <div class="ares-logo-text">ARES</div>
                    <div>
                        <div class="ares-title-text">IV DECISION CARD</div>
                        <div class="ares-subtitle-text">BTC OPTIONS INTRADAY FILTER</div>
                    </div>
                </div>
                <div class="ares-header-right">
                    <div class="ares-header-stat">
                        <div class="ares-stat-icon">₿</div>
                        <div>
                            <div style="font-size: 10px; color: #94a3b8;">BTC</div>
                            <div id="ares-btc-price" style="font-weight: 700; font-size: 13px;">$--</div>
                        </div>
                    </div>
                    <div class="ares-header-stat">
                        <div class="ares-stat-icon" style="color: #64748b;">🕒</div>
                        <div>
                            <div id="ares-time-main" style="font-size: 13px; font-weight: 700;">--:--</div>
                            <div id="ares-date-main" style="font-size: 10px; color: #94a3b8;">-- --- ----</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Grid -->
            <div class="ares-iv-grid">
                
                <!-- Left Column -->
                <div class="ares-left-col">
                    <div class="ares-metric-box">
                        <div class="ares-metric-header">
                            <span>ATM IV (1DTE)</span>
                            <span class="ares-metric-live" id="ares-live-dot">LIVE</span>
                        </div>
                        <div class="ares-metric-value-row">
                            <span class="ares-metric-val text-green" id="ares-atm-iv">--%</span>
                            <!-- Mock sparkline via SVG -->
                            <svg width="60" height="20" viewBox="0 0 60 20" style="stroke: #10b981; fill: none; stroke-width: 1.5px;"><path d="M0,15 L10,5 L20,12 L30,2 L40,10 L50,0 L60,8"/></svg>
                        </div>
                    </div>

                    <div class="ares-metric-box">
                        <div class="ares-metric-header"><span>IV Percentile (30D)</span></div>
                        <div class="ares-metric-val" id="ares-iv-pct">--%</div>
                        <div class="ares-progress-bg"><div class="ares-progress-fill" id="ares-bar-pct" style="width: 0%;"><div class="ares-progress-thumb"></div></div></div>
                    </div>

                    <div class="ares-metric-box">
                        <div class="ares-metric-header"><span>IV Rank (30D)</span></div>
                        <div class="ares-metric-val" id="ares-iv-rank">--</div>
                        <div class="ares-progress-bg"><div class="ares-progress-fill" id="ares-bar-rank" style="width: 0%; background: linear-gradient(90deg, #ef4444, #f59e0b);"><div class="ares-progress-thumb"></div></div></div>
                    </div>

                    <div class="ares-metric-box">
                        <div class="ares-metric-header"><span>5 Day IV Trend</span></div>
                        <div class="ares-metric-value-row">
                            <span class="ares-metric-val text-green" id="ares-iv-trend">--</span>
                            <svg width="60" height="20" viewBox="0 0 60 20" style="stroke: #10b981; fill: none; stroke-width: 1.5px;"><path d="M0,10 L15,10 L30,8 L45,12 L60,10"/></svg>
                        </div>
                    </div>

                    <div class="ares-metric-box">
                        <div class="ares-metric-header"><span>IV Change (Past 1H)</span></div>
                        <div class="ares-metric-value-row">
                            <span class="ares-metric-val text-green" id="ares-iv-change">--</span>
                            <!-- Mock bar chart -->
                            <div style="display:flex; gap:2px; align-items:flex-end; height: 20px;">
                                <div style="width:4px; height:8px; background:#10b981;"></div>
                                <div style="width:4px; height:12px; background:#10b981;"></div>
                                <div style="width:4px; height:6px; background:#ef4444;"></div>
                                <div style="width:4px; height:16px; background:#10b981;"></div>
                                <div style="width:4px; height:10px; background:#10b981;"></div>
                            </div>
                        </div>
                    </div>

                    <div class="ares-metric-box">
                        <div class="ares-metric-header"><span>IV vs Realized Vol (5D)</span></div>
                        <div class="ares-metric-value-row">
                            <span class="ares-metric-val text-green" id="ares-iv-vs-rv">+18%</span>
                            <div style="font-size:24px;">🎛️</div>
                        </div>
                    </div>
                </div>

                <!-- Center Shield -->
                <div class="ares-center-card" id="ares-center-shield">
                    <div class="ares-shield-icon"></div>
                    <div class="ares-zone-label">IV ZONE</div>
                    <div class="ares-zone-main" id="ares-zone-main">LOADING</div>
                    <div class="ares-zone-sub" id="ares-zone-sub">ANALYZING EDGE...</div>

                    <div class="ares-confidence-circle">
                        <div class="ares-conf-val" id="ares-edge-score">--%</div>
                        <div class="ares-conf-lbl">CONFIDENCE</div>
                    </div>

                    <div class="ares-action-box" id="ares-action-box">
                        <div class="ares-action-label">ACTION</div>
                        <div class="ares-action-val" id="ares-decision"><span style="font-size:20px;">🎯</span> WAITING</div>
                    </div>

                    <div class="ares-center-footer">
                        <div class="ares-cf-item">
                            <span class="ares-cf-lbl">RISK LEVEL</span>
                            <span class="ares-cf-val" id="ares-cf-risk">LOW</span>
                        </div>
                        <div class="ares-cf-item">
                            <span class="ares-cf-lbl">REWARD</span>
                            <span class="ares-cf-val" id="ares-cf-reward">★★★★★</span>
                        </div>
                        <div class="ares-cf-item">
                            <span class="ares-cf-lbl">MARKET CONDITION</span>
                            <span class="ares-cf-val" id="ares-cf-market">RANGE</span>
                        </div>
                    </div>
                </div>

                <!-- Right Column -->
                <div class="ares-right-col">
                    <div class="ares-right-title">WHY THIS ZONE?</div>
                    <div class="ares-reasons-list" id="ares-reasons-list">
                        <div class="ares-reason-row"><div class="ares-reason-icon">⏳</div><div><div class="ares-reason-text-main">Loading...</div></div></div>
                    </div>
                </div>

            </div>

            <!-- IV Zone Meter -->
            <div class="ares-zone-meter">
                <div class="ares-zm-header"><span>📉</span> IV ZONE METER</div>
                <div class="ares-zm-grid">
                    <div class="ares-zm-col">
                        <div style="font-size:24px; color:#ef4444; margin-bottom:4px;">🐻</div>
                        <div class="ares-zm-title" style="color:#ef4444;">LOW IV</div>
                        <div class="ares-zm-range">0 - 25%</div>
                        <div class="ares-zm-sub" style="color:#ef4444;">High Risk<br>Skip Trade</div>
                    </div>
                    <div class="ares-zm-col">
                        <div style="font-size:24px; color:#f59e0b; margin-bottom:4px;">😐</div>
                        <div class="ares-zm-title" style="color:#f59e0b;">MEDIUM IV</div>
                        <div class="ares-zm-range">25 - 70%</div>
                        <div class="ares-zm-sub" style="color:#f59e0b;">Low Risk<br>Trade</div>
                    </div>
                    <div class="ares-zm-col">
                        <div style="font-size:24px; color:#10b981; margin-bottom:4px;">🐂</div>
                        <div class="ares-zm-title" style="color:#10b981;">HEALTHY IV</div>
                        <div class="ares-zm-range">70 - 100%</div>
                        <div class="ares-zm-sub" style="color:#10b981;">Perfect Zone<br>Trade with Confidence</div>
                    </div>
                </div>
                <div class="ares-zm-bar-container">
                    <div class="ares-zm-thumb" id="ares-zm-thumb" style="left: 0%;"></div>
                </div>
            </div>

            <!-- Bottom Strip -->
            <div class="ares-bottom-strip">
                <div class="ares-strip-box">
                    <div class="ares-strip-icon">🔄</div>
                    <div>
                        <div class="ares-strip-title">NEXT IV UPDATE</div>
                        <div class="ares-strip-val">15:00</div>
                        <div class="ares-strip-sub">Minutes</div>
                    </div>
                </div>
                <div class="ares-strip-box">
                    <div class="ares-strip-icon">📅</div>
                    <div>
                        <div class="ares-strip-title">BEST ENTRY WINDOW</div>
                        <div class="ares-strip-val">08:00 AM - 09:30 AM</div>
                        <div class="ares-strip-sub">IST</div>
                    </div>
                </div>
                <div class="ares-strip-box">
                    <div class="ares-strip-icon text-green">🛡️</div>
                    <div>
                        <div class="ares-strip-title">NEWS FILTER</div>
                        <div class="ares-strip-val text-green">CLEAR</div>
                        <div class="ares-strip-sub">No High Impact News</div>
                    </div>
                </div>
                <div class="ares-strip-box">
                    <div class="ares-strip-icon" style="color:#f59e0b;">🥧</div>
                    <div>
                        <div class="ares-strip-title">POSITION SIZE ADVICE</div>
                        <div class="ares-strip-val">100%</div>
                        <div class="ares-strip-sub">Normal Size</div>
                    </div>
                </div>
            </div>
            
        </div>
        <!-- END ARES IV DECISION CARD -->
"""

    js = """
// ARES Premium UI Updater
function updateAresPremium() {
    // Update local clock
    const now = new Date();
    document.getElementById('ares-time-main').innerText = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    document.getElementById('ares-date-main').innerText = now.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});

    fetch('/api/premium_conditions')
        .then(r => r.json())
        .then(data => {
            const el = id => document.getElementById(id);
            if (!data.status) return;
            
            const isRed = data.zone === "RED" || data.zone === "LOW EDGE";
            const isYellow = data.zone === "YELLOW" || data.zone === "CAUTION";
            const mainColor = isRed ? "#ef4444" : (isYellow ? "#f59e0b" : "#10b981");

            // Block alert
            if (!data.trade_allowed && data.decision !== "WAITING") {
                el('psce-block-alert').classList.add('active');
                el('psce-block-reason').innerText = "Reason: " + (data.reasons[0] || "Low Edge");
            } else {
                el('psce-block-alert').classList.remove('active');
            }

            if (data.metrics) {
                el('ares-btc-price').innerText = "$" + parseFloat(data.metrics.btc_price).toLocaleString();
                el('ares-atm-iv').innerText = parseFloat(data.metrics.atm_iv).toFixed(1) + "%";
                el('ares-iv-pct').innerText = parseFloat(data.metrics.iv_percentile).toFixed(0) + "%";
                el('ares-bar-pct').style.width = Math.min(100, Math.max(0, parseFloat(data.metrics.iv_percentile))) + "%";
                el('ares-iv-rank').innerText = parseFloat(data.metrics.iv_rank).toFixed(0);
                el('ares-bar-rank').style.width = Math.min(100, Math.max(0, parseFloat(data.metrics.iv_rank))) + "%";
                el('ares-iv-trend').innerText = data.metrics.iv_trend_5d;
                el('ares-iv-change').innerText = data.metrics.iv_change_1h;
                
                el('ares-live-dot').innerText = (data.health.iv_feed === "ONLINE") ? "LIVE" : "OFFLINE";
                el('ares-live-dot').style.color = (data.health.iv_feed === "ONLINE") ? "#10b981" : "#ef4444";
            }

            // Center Card
            const shield = el('ares-center-shield');
            shield.classList.remove('zone-red', 'zone-yellow');
            if (isRed) shield.classList.add('zone-red');
            if (isYellow) shield.classList.add('zone-yellow');

            el('ares-zone-main').innerText = isRed ? "LOW EDGE" : (isYellow ? "CAUTION" : "HEALTHY");
            el('ares-zone-main').style.color = mainColor;
            el('ares-zone-sub').innerText = data.trade_allowed ? "OPTIMAL FOR PREMIUM SELLING" : "UNFAVORABLE FOR STRANGLES";
            el('ares-zone-sub').style.color = mainColor;
            el('ares-zone-sub').style.background = `rgba(${isRed?239:16}, ${isRed?68:185}, ${isRed?68:129}, 0.1)`;

            el('ares-edge-score').innerText = Math.round(data.edge_score) + "%";
            el('ares-decision').innerHTML = `<span style="font-size:20px;">🎯</span> ` + data.decision;
            el('ares-action-box').style.borderColor = `rgba(${isRed?239:16}, ${isRed?68:185}, ${isRed?68:129}, 0.4)`;
            el('ares-action-box').style.background = `rgba(${isRed?239:16}, ${isRed?68:185}, ${isRed?68:129}, 0.05)`;
            
            el('ares-cf-risk').innerText = isRed ? "HIGH" : (isYellow ? "MEDIUM" : "LOW");
            el('ares-cf-risk').style.color = mainColor;
            el('ares-cf-reward').innerText = isRed ? "★☆☆☆☆" : (isYellow ? "★★★☆☆" : "★★★★★");
            el('ares-cf-market').innerText = data.premium_state.includes("Excellent") ? "RANGE" : "DIRECTIONAL";

            // Reasons mapping (matching the 5 icons design roughly)
            const iconMap = ["✓", "〰", "📊", "🛡️", "🕒"];
            const reasonsHtml = data.reasons.map((r, i) => `
                <div class="ares-reason-row">
                    <div class="ares-reason-icon" style="color:${mainColor}; border-color:rgba(${isRed?239:16}, ${isRed?68:185}, ${isRed?68:129},0.3)">${iconMap[i%5]}</div>
                    <div>
                        <div class="ares-reason-text-main">${r}</div>
                        <div class="ares-reason-text-sub">${isRed ? "Condition blocking trade" : "Supporting edge metric"}</div>
                    </div>
                </div>
            `).join("");
            el('ares-reasons-list').innerHTML = reasonsHtml;

            // Slider thumb
            el('ares-zm-thumb').style.left = Math.min(100, Math.max(0, data.edge_score)) + "%";
        });
}

setInterval(updateAresPremium, 3000);
setTimeout(updateAresPremium, 500);
"""

    # Inject
    content = re.sub(r'</style>', r'\n' + css + r'\n</style>', content, count=1)
    
    target_html = r'(<div id="trade-skip-alert-card")'
    content = re.sub(target_html, html + r'\n        \1', content)
    
    content = content.replace('</body>', f'<script>\n{js}\n</script>\n</body>')
    
    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Re-injected premium ARES replica UI successfully!")

if __name__ == '__main__':
    remove_old_and_inject()
