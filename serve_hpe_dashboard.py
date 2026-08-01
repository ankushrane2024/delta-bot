import time
import json
import os
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
# local_hpe_engine removed — SmartHedgingManager is now the single live engine.
# Dashboard reads hedge state from bot_state.json (written by the main bot).
hpe_engine = None  # No standalone shadow engine; state comes from bot_state.json

DYNAMIC_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HPE - Ultra Hedge Protection Intelligence</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #030712;
            --card-bg: rgba(15, 23, 42, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover-border: rgba(255, 255, 255, 0.18);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --emerald: #10b981;
            --emerald-glow: rgba(16, 185, 129, 0.25);
            --rose: #f43f5e;
            --rose-glow: rgba(244, 63, 94, 0.25);
            --amber: #f59e0b;
            --amber-glow: rgba(245, 158, 11, 0.25);
            --cyan: #06b6d4;
            --cyan-glow: rgba(6, 182, 212, 0.25);
            --violet: #8b5cf6;
        }

        * { box-sizing: border-box; font-family: 'Outfit', sans-serif; margin: 0; padding: 0; }
        .mono { font-family: 'JetBrains Mono', monospace; }

        body {
            background-color: var(--bg-dark);
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(6, 182, 212, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(16, 185, 129, 0.04) 0%, transparent 60%);
            color: var(--text-main);
            padding: 20px;
            min-height: 100vh;
        }

        .glass-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .glass-card:hover {
            border-color: var(--card-hover-border);
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        }

        .top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .brand-box { display: flex; align-items: center; gap: 14px; }
        .brand-logo {
            width: 44px; height: 44px;
            background: linear-gradient(135deg, #06b6d4, #8b5cf6);
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 20px rgba(6, 182, 212, 0.4);
        }
        .brand-name { font-size: 22px; font-weight: 800; letter-spacing: -0.03em; }
        .brand-tag {
            font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
            background: rgba(139, 92, 246, 0.15); color: #c084fc;
            padding: 4px 10px; border-radius: 20px; border: 1px solid rgba(139, 92, 246, 0.3);
        }

        .status-pill {
            display: flex; align-items: center; gap: 8px;
            background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; color: var(--emerald);
        }
        .pulse-dot {
            width: 8px; height: 8px; background: var(--emerald); border-radius: 50%;
            box-shadow: 0 0 10px var(--emerald);
            animation: pulse 1.8s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } }

        .grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 20px; }
        .card-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px; }
        .val-giant { font-size: 28px; font-weight: 900; letter-spacing: -0.03em; }
        .sub-desc { font-size: 12px; color: var(--text-muted); margin-top: 6px; font-weight: 500; }

        .text-rose { color: var(--rose); text-shadow: 0 0 15px var(--rose-glow); }
        .text-emerald { color: var(--emerald); text-shadow: 0 0 15px var(--emerald-glow); }
        .text-amber { color: var(--amber); text-shadow: 0 0 15px var(--amber-glow); }
        .text-cyan { color: var(--cyan); text-shadow: 0 0 15px var(--cyan-glow); }

        .ring-wrap { display: flex; align-items: center; gap: 14px; }
        .ring-svg { width: 52px; height: 52px; transform: rotate(-90deg); }
        .ring-bg { fill: none; stroke: rgba(255, 255, 255, 0.08); stroke-width: 5; }
        .ring-fill { fill: none; stroke: url(#green-gradient); stroke-width: 5; stroke-dasharray: 126; stroke-dashoffset: 22; stroke-linecap: round; transition: stroke-dashoffset 0.5s ease; }

        .grid-mid { display: grid; grid-template-columns: 1.1fr 1.3fr 1.2fr; gap: 14px; margin-bottom: 20px; }

        .card-bleeding {
            border-left: 4px solid var(--rose);
            background: linear-gradient(135deg, rgba(244, 63, 94, 0.08) 0%, rgba(15, 23, 42, 0.75) 100%);
        }
        .bleeding-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
        .leg-title { font-size: 20px; font-weight: 800; }
        .leg-loss { font-size: 24px; font-weight: 900; color: var(--rose); }

        .progress-track { background: rgba(255, 255, 255, 0.08); height: 8px; border-radius: 4px; overflow: hidden; margin: 14px 0 10px; }
        .progress-bar-rose { background: linear-gradient(90deg, #f43f5e, #fb7185); height: 100%; width: 0%; border-radius: 4px; box-shadow: 0 0 12px var(--rose); transition: width 0.5s ease; }

        .calc-header { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--card-border); margin-bottom: 14px; }
        .direction-pill { font-size: 22px; font-weight: 900; color: var(--emerald); display: flex; align-items: center; gap: 8px; }
        .qty-val { font-size: 24px; font-weight: 900; color: var(--text-main); }

        .trio-wrap { display: flex; justify-content: space-between; }
        .trio-col { text-align: center; }
        .trio-lbl { font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
        .trio-num { font-size: 17px; font-weight: 800; margin-top: 4px; }

        .card-decision {
            border-left: 4px solid var(--amber);
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(15, 23, 42, 0.75) 100%);
        }
        .dec-title { font-size: 18px; font-weight: 800; color: var(--amber); margin-bottom: 8px; }
        .dec-text { font-size: 13px; color: var(--text-muted); line-height: 1.5; font-weight: 500; }
        .timer-box { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--card-border); }
        .timer-num { font-size: 20px; font-weight: 800; color: var(--amber); }

        .grid-ind { display: grid; grid-template-columns: 1fr 1fr 1.5fr 1fr; gap: 14px; margin-bottom: 20px; }

        .pivot-tbl { width: 100%; border-collapse: collapse; margin-top: 8px; text-align: center; }
        .pivot-tbl th { font-size: 10px; color: var(--text-muted); font-weight: 700; padding-bottom: 6px; }
        .pivot-tbl td { font-size: 13px; font-weight: 800; padding: 6px 2px; }

        .grid-bottom { display: grid; grid-template-columns: 1fr 1fr 1fr 2fr; gap: 14px; margin-bottom: 20px; }
        .bar-fill-amber { background: linear-gradient(90deg, #f59e0b, #fbbf24); height: 100%; width: 0%; border-radius: 4px; box-shadow: 0 0 10px var(--amber); transition: width 0.5s ease; }
        .bar-fill-emerald { background: linear-gradient(90deg, #10b981, #34d399); height: 100%; width: 70%; border-radius: 4px; box-shadow: 0 0 10px var(--emerald); }
        .bar-fill-cyan { background: linear-gradient(90deg, #06b6d4, #38bdf8); height: 100%; width: 0%; border-radius: 4px; box-shadow: 0 0 10px var(--cyan); transition: width 0.5s ease; }

        .stepper { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; position: relative; }
        .stepper::before { content: ''; position: absolute; top: 13px; left: 15px; right: 15px; height: 2px; background: rgba(255, 255, 255, 0.08); z-index: 1; }
        .step-item { position: relative; z-index: 2; text-align: center; background: #0f172a; padding: 0 6px; }
        .step-circle {
            width: 26px; height: 26px; border-radius: 50%; background: #1e293b; border: 2px solid #334155;
            margin: 0 auto 6px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: var(--text-muted);
        }
        .circle-done { background: var(--emerald); border-color: var(--emerald); color: #000; box-shadow: 0 0 12px var(--emerald-glow); }
        .circle-active { background: var(--amber); border-color: var(--amber); color: #000; box-shadow: 0 0 15px var(--amber-glow); animation: pulse 1.5s infinite; }

        .banner-glow {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(6, 182, 212, 0.08) 100%);
            border: 1px solid rgba(245, 158, 11, 0.3);
            border-radius: 14px; padding: 14px 20px; font-size: 13px; font-weight: 600; color: #fde68a;
            display: flex; align-items: center; gap: 12px; box-shadow: 0 0 20px rgba(245, 158, 11, 0.1);
        }
    </style>
</head>
<body>

    <svg width="0" height="0">
        <defs>
            <linearGradient id="green-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#10b981" />
                <stop offset="100%" stop-color="#34d399" />
            </linearGradient>
        </defs>
    </svg>

    <!-- Header Bar -->
    <div class="top-nav">
        <div class="brand-box">
            <div class="brand-logo">🛡️</div>
            <div>
                <span class="brand-name">HPE</span>
                <span class="brand-tag">HEDGE PROTECTION ENGINE</span>
            </div>
        </div>
        <div class="status-pill">
            <div class="pulse-dot"></div>
            <span>System State: <strong id="sys-state" style="color: #fff;">DORMANT</strong></span>
            <span style="color: var(--text-muted); margin-left: 10px;">| Last Update: <strong id="time-val" class="mono">--:--:-- IST</strong></span>
        </div>
    </div>

    <!-- Top 5 Cards -->
    <div class="grid-5">
        <div class="glass-card">
            <div class="card-label">Combined Option P&L</div>
            <div class="val-giant text-emerald mono" id="comb-pnl">0.00%</div>
            <div class="sub-desc" id="comb-sub">Portfolio Loss (Threshold: -10%)</div>
        </div>
        <div class="glass-card">
            <div class="card-label">Trigger Status</div>
            <div class="val-giant text-emerald" id="trigger-status">IDLE</div>
            <div class="sub-desc">Activates at -10% Loss</div>
        </div>
        <div class="glass-card">
            <div class="card-label">Market Trend</div>
            <div class="val-giant text-cyan" id="trend-val">NEUTRAL</div>
            <div class="sub-desc" id="st-sub">Supertrend (10,3): --</div>
        </div>
        <div class="glass-card">
            <div class="card-label">Confidence Score</div>
            <div class="ring-wrap">
                <svg class="ring-svg" viewBox="0 0 50 50">
                    <circle class="ring-bg" cx="25" cy="25" r="20"/>
                    <circle class="ring-fill" id="gauge-fill" cx="25" cy="25" r="20"/>
                </svg>
                <div>
                    <div style="font-size: 22px; font-weight: 900; color: var(--emerald);" class="mono" id="conf-score">82%</div>
                    <div style="font-size: 11px; color: var(--text-muted); font-weight: 600;" id="conf-label">Good Trend</div>
                </div>
            </div>
        </div>
        <div class="glass-card">
            <div class="card-label">Engine Core State</div>
            <div class="val-giant text-amber" id="engine-state">⚡ DORMANT</div>
            <div class="sub-desc" id="engine-desc">Monitoring Combined P&L</div>
        </div>
    </div>

    <!-- Middle Row -->
    <div class="grid-mid">
        <!-- Bleeding Leg -->
        <div class="glass-card card-bleeding">
            <div class="card-label">🩸 Bleeding Leg Risk</div>
            <div class="bleeding-row">
                <div>
                    <div class="leg-title" id="bleeding-name">NONE</div>
                    <div class="sub-desc">Premium: <span class="mono" style="color: #fff;" id="bleeding-prem">-- USDT</span></div>
                </div>
                <div class="leg-loss mono" id="bleeding-pnl">0.00%</div>
            </div>
            <div class="progress-track"><div class="progress-bar-rose" id="bleeding-bar"></div></div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700;">
                <span style="color: var(--text-muted);">Loss Contribution</span>
                <span class="text-rose mono" id="loss-contrib">0%</span>
            </div>
        </div>

        <!-- Hedge Calculator -->
        <div class="glass-card">
            <div class="card-label">🧮 Hedge Risk & Sizing Calculator</div>
            <div class="calc-header">
                <div>
                    <div style="font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Direction</div>
                    <div class="direction-pill" id="calc-dir">NONE</div>
                </div>
                <div>
                    <div style="font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Hedge Quantity</div>
                    <div class="qty-val mono" id="calc-qty">0.000 BTC</div>
                    <div style="font-size: 11px; color: var(--text-muted);" class="mono" id="calc-usdt">≈ $0.00 USDT</div>
                </div>
            </div>
            <div class="trio-wrap">
                <div class="trio-col">
                    <div class="trio-lbl">Coverage Target</div>
                    <div class="trio-num text-emerald mono">70%</div>
                </div>
                <div class="trio-col">
                    <div class="trio-lbl">Est. Coverage</div>
                    <div class="trio-num text-cyan mono" id="est-coverage">0%</div>
                </div>
                <div class="trio-col">
                    <div class="trio-lbl">Remaining Risk</div>
                    <div class="trio-num text-amber mono" id="rem-risk">100%</div>
                </div>
            </div>
        </div>

        <!-- Decision Radar -->
        <div class="glass-card card-decision">
            <div class="card-label">🎯 Live Decision Radar</div>
            <div class="dec-title" id="dec-header">DORMANT</div>
            <div class="dec-text" id="dec-desc">Combined Option P&L above -10%. HPE engine idle to save CPU.</div>
            <div class="timer-box">
                <span style="font-size: 12px; color: var(--text-muted); font-weight: 700;">5m Candle Check</span>
                <span class="timer-num mono" id="timer-val">04:59</span>
            </div>
        </div>
    </div>

    <!-- Row 3: Indicators -->
    <div class="grid-ind">
        <div class="glass-card">
            <div class="card-label">Supertrend (10, 3)</div>
            <div class="val-giant text-cyan" id="st-val">NEUTRAL</div>
            <div class="sub-desc">5m Candle Trend</div>
        </div>
        <div class="glass-card">
            <div class="card-label">ADX (14)</div>
            <div class="val-giant text-emerald mono" id="adx-val">0.0</div>
            <div class="sub-desc" id="adx-sub">Trend Strength (> 20)</div>
        </div>
        <div class="glass-card">
            <div class="card-label">Pivot Matrix (Standard)</div>
            <table class="pivot-tbl mono">
                <thead>
                    <tr><th>R2</th><th>R1</th><th>P</th><th>S1</th><th>S2</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td style="color: var(--text-muted);" id="p-r2">--</td>
                        <td style="color: var(--amber);" id="p-r1">--</td>
                        <td style="color: var(--text-main);" id="p-p">--</td>
                        <td style="color: var(--emerald);" id="p-s1">--</td>
                        <td style="color: var(--text-muted);" id="p-s2">--</td>
                    </tr>
                </tbody>
            </table>
        </div>
        <div class="glass-card">
            <div class="card-label">Pivot Status</div>
            <div class="val-giant text-emerald" style="font-size: 18px;" id="p-status">HOLD</div>
            <div class="sub-desc" id="p-breakout">Breakout: --</div>
        </div>
    </div>

    <!-- Row 4: Risk Bars & Timeline Stepper -->
    <div class="grid-bottom">
        <div class="glass-card">
            <div class="card-label">Remaining Risk</div>
            <div class="val-giant text-amber mono" id="bar-rem-val">100%</div>
            <div class="progress-track"><div class="bar-fill-amber" id="bar-rem-fill"></div></div>
        </div>
        <div class="glass-card">
            <div class="card-label">Coverage Target</div>
            <div class="val-giant text-emerald mono">70%</div>
            <div class="progress-track"><div class="bar-fill-emerald"></div></div>
        </div>
        <div class="glass-card">
            <div class="card-label">Expected Coverage</div>
            <div class="val-giant text-cyan mono" id="bar-exp-val">0%</div>
            <div class="progress-track"><div class="bar-fill-cyan" id="bar-exp-fill"></div></div>
        </div>
        <div class="glass-card">
            <div class="card-label">⏱️ Hedge Workflow Timeline</div>
            <div class="stepper">
                <div class="step-item">
                    <div class="step-circle" id="s1">1</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Trade Entry</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s2">2</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Loss >-10%</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s3">3</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Trend Confirmed</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s4">4</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Breakout Pending</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s5">5</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Hedge Open</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s6">6</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Monitoring</div>
                </div>
                <div class="step-item">
                    <div class="step-circle" id="s7">7</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-weight: 700;">Exit</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Bottom Banner -->
    <div class="banner-glow">
        <span style="font-size: 18px;">💡</span>
        <span><strong>DECISION SUMMARY:</strong> <span id="banner-text">Combined Option P&L above -10%. HPE engine idle.</span></span>
    </div>

    <script>
        function readLiveState() {
            // Read bot_state.json or status from server
            if (fs_data) updateUI(fs_data);
        }

        async function updateTelemetry() {
            try {
                const res = await fetch('/api/hpe_telemetry');
                const data = await res.json();
                
                document.getElementById('time-val').innerText = new Date().toLocaleTimeString() + ' IST';
                
                const state = data.state || 'DORMANT';
                document.getElementById('sys-state').innerText = state;

                // Combined PnL
                const loss = data.combined_loss_pct || 0.0;
                const lossElem = document.getElementById('comb-pnl');
                lossElem.innerText = loss.toFixed(2) + '%';
                lossElem.className = loss <= -10 ? 'val-giant text-rose mono' : 'val-giant text-emerald mono';

                // Trigger
                const trigElem = document.getElementById('trigger-status');
                trigElem.innerText = loss <= -10 ? '✔ ACTIVE' : 'IDLE';
                trigElem.className = loss <= -10 ? 'val-giant text-emerald' : 'val-giant text-cyan';

                // Supertrend & ADX
                const st = data.supertrend || 'NEUTRAL';
                document.getElementById('trend-val').innerText = st === 'BUY' ? '↑ UPTREND' : (st === 'SELL' ? '↓ DOWNTREND' : 'NEUTRAL');
                document.getElementById('trend-val').className = st === 'BUY' ? 'val-giant text-emerald' : (st === 'SELL' ? 'val-giant text-rose' : 'val-giant text-cyan');
                document.getElementById('st-sub').innerText = 'Supertrend (10,3): ' + st;
                document.getElementById('st-val').innerText = st;
                document.getElementById('st-val').className = st === 'BUY' ? 'val-giant text-emerald' : (st === 'SELL' ? 'val-giant text-rose' : 'val-giant text-cyan');

                const adx = data.adx || 0.0;
                document.getElementById('adx-val').innerText = adx.toFixed(1);
                document.getElementById('adx-sub').innerText = adx > 20 ? 'Strong Trend (> 20)' : 'Sideways Market (≤ 20)';

                // Bleeding Leg
                const bleeding = data.bleeding_leg || 'NONE';
                document.getElementById('bleeding-name').innerText = bleeding;
                const bleedingLoss = data.bleeding_leg_loss_pct || 0.0;
                document.getElementById('bleeding-pnl').innerText = bleedingLoss.toFixed(2) + '%';
                
                const lossContrib = Math.min(100, Math.abs(bleedingLoss));
                document.getElementById('loss-contrib').innerText = Math.round(lossContrib) + '%';
                document.getElementById('bleeding-bar').style.width = Math.round(lossContrib) + '%';

                // Hedge Calculator
                const hQty = data.hedge_btc_qty || 0.0;
                document.getElementById('calc-qty').innerText = hQty.toFixed(3) + ' BTC';
                const btcP = data.btc_price || 90000;
                document.getElementById('calc-usdt').innerText = `≈ $${(hQty * btcP).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} USDT`;
                
                const dir = (st === 'BUY' || st === 'SELL') ? st + (st === 'BUY' ? ' ⬆' : ' ⬇') : 'NONE';
                document.getElementById('calc-dir').innerText = dir;

                const remRisk = data.remaining_risk_pct || (100 - Math.abs(loss));
                document.getElementById('rem-risk').innerText = Math.round(remRisk) + '%';
                document.getElementById('bar-rem-val').innerText = Math.round(remRisk) + '%';
                document.getElementById('bar-rem-fill').style.width = Math.round(remRisk) + '%';

                const covPct = data.coverage_pct || (loss <= -10 ? 70 : 0);
                document.getElementById('est-coverage').innerText = Math.round(covPct) + '%';
                document.getElementById('bar-exp-val').innerText = Math.round(covPct) + '%';
                document.getElementById('bar-exp-fill').style.width = Math.round(covPct) + '%';

                // Decision
                const actionState = data.action_state || state;
                document.getElementById('dec-header').innerText = actionState;
                const nextDec = data.next_decision || 'Monitoring Combined Option P&L.';
                document.getElementById('dec-desc').innerText = nextDec;
                document.getElementById('banner-text').innerText = nextDec;
                document.getElementById('engine-state').innerText = '⚡ ' + state;
                document.getElementById('engine-desc').innerText = actionState;

                // Stepper update
                for(let i=1; i<=7; i++) {
                    document.getElementById('s' + i).className = 'step-circle';
                }
                if (state === 'DORMANT') {
                    document.getElementById('s1').className = 'step-circle circle-done';
                } else if (state === 'MONITORING') {
                    document.getElementById('s1').className = 'step-circle circle-done';
                    document.getElementById('s2').className = 'step-circle circle-done';
                    document.getElementById('s3').className = 'step-circle circle-active';
                } else if (state === 'HEDGING') {
                    document.getElementById('s1').className = 'step-circle circle-done';
                    document.getElementById('s2').className = 'step-circle circle-done';
                    document.getElementById('s3').className = 'step-circle circle-done';
                    document.getElementById('s4').className = 'step-circle circle-done';
                    document.getElementById('s5').className = 'step-circle circle-done';
                    document.getElementById('s6').className = 'step-circle circle-active';
                } else if (state === 'COOLDOWN') {
                    document.getElementById('s7').className = 'step-circle circle-done';
                }

            } catch (err) {
                console.warn('Telemetry poll warning:', err);
            }
        }

        // Live 5m countdown
        setInterval(() => {
            const now = new Date();
            const secRemaining = 300 - ((now.getMinutes() % 5) * 60 + now.getSeconds());
            const mins = Math.floor(secRemaining / 60);
            const secs = secRemaining % 60;
            document.getElementById('timer-val').innerText = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }, 1000);

        setInterval(updateTelemetry, 1000);
        updateTelemetry();
    </script>
</body>
</html>
"""

def fetch_live_bot_data():
    """Reads real trade state from main bot files."""
    if os.path.exists("bot_state.json"):
        try:
            with open("bot_state.json", "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'options_pnl_pct': -12.43,
        'options_pnl_usd': -124.30,
        'positions': [
            {'symbol': 'CALL (CE)', 'pnl_pct': -42.18, 'delta': 0.35, 'size': 0.1, 'entry_premium_usd': 150.0},
            {'symbol': 'PUT (PE)', 'pnl_pct': 11.20, 'delta': -0.25, 'size': 0.1, 'entry_premium_usd': 150.0}
        ],
        'btc_price': 119250.0,
        'trade_active': True,
        'timestamp': time.time()
    }

@app.route('/')
def index():
    return render_template_string(DYNAMIC_UI_HTML)

@app.route('/api/hpe_telemetry')
def get_telemetry():
    runtime_data = fetch_live_bot_data()
    telemetry = hpe_engine.process_tick(runtime_data)
    telemetry['btc_price'] = runtime_data.get('btc_price', 90000.0)
    return jsonify(telemetry)

if __name__ == "__main__":
    print("[HPE Dynamic Dashboard] Server running on http://127.0.0.1:5050 ...")
    app.run(host="127.0.0.1", port=5050, debug=False)
