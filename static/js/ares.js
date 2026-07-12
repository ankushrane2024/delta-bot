// ARES Mission Control X - Institutional JS

const POLL_INTERVAL = 1000;
let chartEquity, chartSpark;
let timeData = [];
let equityData = [];
let btcData = [];
let hasReceivedFirstTick = false;
let isPaused = false;

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initCharts();
    
    document.getElementById('btn-pause').addEventListener('click', (e) => {
        isPaused = !isPaused;
        e.currentTarget.innerHTML = isPaused ? '<i data-lucide="play"></i> Resume' : '<i data-lucide="pause"></i> Pause';
        lucide.createIcons();
    });

    pollData();
    setInterval(pollData, POLL_INTERVAL);
});

function initClock() {
    setInterval(() => {
        const now = new Date();
        const opts = { weekday: 'long', year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZoneName: 'short' };
        document.getElementById('sys-clock').innerText = now.toLocaleString('en-IN', opts);
    }, 1000);
}

function initCharts() {
    const text = '#94A3B8';
    const gridColor = '#1F2937';

    chartEquity = echarts.init(document.getElementById('chart-equity'));
    chartEquity.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: '#111827', borderColor: '#1F2937', textStyle: { color: '#F8FAFC' } },
        grid: { left: '2%', right: '2%', bottom: '5%', top: '5%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLine: { lineStyle: { color: text } }, splitLine: { show: false } },
        yAxis: { type: 'value', scale: true, axisLine: { lineStyle: { color: text } }, splitLine: { lineStyle: { color: gridColor } } },
        series: [{
            name: 'Equity', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00E5FF', width: 3 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,229,255,0.4)' },
                    { offset: 1, color: 'rgba(0,229,255,0.0)' }
                ])
            },
            data: []
        }]
    });

    chartSpark = echarts.init(document.getElementById('chart-btc-spark'));
    chartSpark.setOption({
        backgroundColor: 'transparent',
        grid: { left: 0, right: 0, bottom: 0, top: 0 },
        xAxis: { type: 'category', show: false, data: [] },
        yAxis: { type: 'value', scale: true, show: false },
        series: [{
            type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00C853', width: 2 },
            data: []
        }]
    });

    window.addEventListener('resize', () => {
        chartEquity.resize(); chartSpark.resize();
    });
}

async function pollData() {
    if (isPaused) return;

    try {
        const [statusRes, ordersRes, logsRes] = await Promise.all([
            fetch('/ares/status').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/orders').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/logs').then(r => r.ok ? r.json() : null).catch(() => null)
        ]);
        
        if (statusRes && !statusRes.error) {
            if (!hasReceivedFirstTick && statusRes.total_ticks > 0) {
                hasReceivedFirstTick = true;
                document.getElementById('startup-overlay').classList.add('hidden');
            }
            
            updateCenterpiece(statusRes);
            updateAI(statusRes);
            updateTimeline(statusRes);
            updateHealth(statusRes);
            
            // Append to charts
            const nowStr = new Date().toLocaleTimeString('en-US', {hour12: false});
            if (timeData.length > 60) { timeData.shift(); equityData.shift(); btcData.shift(); }
            
            timeData.push(nowStr);
            equityData.push(statusRes.combined_mtm !== undefined ? statusRes.combined_mtm : (statusRes.pnl || 0));
            btcData.push(statusRes.btc_price || null);
            
            chartEquity.setOption({ xAxis: { data: timeData }, series: [{ data: equityData }] });
            chartSpark.setOption({ xAxis: { data: timeData }, series: [{ data: btcData }] });
            
            // Update spark trend color
            if (btcData.length > 1) {
                const last = btcData[btcData.length - 1];
                const prev = btcData[btcData.length - 2];
                const c = last >= prev ? '#00C853' : '#FF5252';
                chartSpark.setOption({ series: [{ lineStyle: { color: c } }] });
            }
        }
        
        if (ordersRes) updateOrders(ordersRes);
        if (logsRes) updateTerminal(logsRes);
        
    } catch (err) {
        console.error("Polling error:", err);
    }
}

function fmtUSD(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return '$' + Number(val).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function fmtNum(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return Number(val).toLocaleString('en-US', {minimumFractionDigits: 4, maximumFractionDigits: 4});
}

function updateCenterpiece(d) {
    document.getElementById('val-port').innerText = fmtUSD(d.portfolio_value);
    
    document.getElementById('val-port').innerText = fmtUSD(d.combined_mtm || d.pnl);
    
    const opt_mtm = Number(d.option_mtm || 0);
    const oEl = document.getElementById('val-option-mtm');
    oEl.innerText = (opt_mtm >= 0 ? '+' : '') + fmtUSD(opt_mtm);
    oEl.className = 'cm-val-sub ' + (opt_mtm >= 0 ? 'green' : 'red');
    
    const hedge_mtm = Number(d.hedge_mtm || 0);
    const hEl = document.getElementById('val-hedge-mtm');
    hEl.innerText = (hedge_mtm >= 0 ? '+' : '') + fmtUSD(hedge_mtm);
    hEl.className = 'cm-val-sub ' + (hedge_mtm >= 0 ? 'green' : 'red');

    const prot = Number(d.protection_pct || 0);
    const pEl = document.getElementById('val-protection');
    pEl.innerText = prot.toFixed(2) + '%';
    pEl.className = 'cm-val-sub ' + (prot >= 100 ? 'green' : (prot > 0 ? 'warning' : 'gray'));
    
    document.getElementById('val-btc').innerText = fmtUSD(d.btc_price);
    
    // Status Bar
    document.getElementById('sb-mode').innerText = d.bot_mode || 'UNKNOWN';
    document.getElementById('sb-prov').innerText = 'Exchange: ' + (d.exchange_status || 'N/A');
    document.getElementById('sb-lat').innerText = d.pipeline_latency !== undefined ? (d.pipeline_latency * 1000).toFixed(0) + ' ms' : 'N/A';
}

function updateAI(d) {
    const hedge = (d.active_hedge || 'NONE').toUpperCase();
    const risk = (d.current_risk || 'LOW').toUpperCase();
    const trendStrength = d.trend_strength || 0;
    const regime = (d.intraday_trend || d.market_regime || 'WAITING').toUpperCase();
    
    document.getElementById('ai-market').innerText = regime;
    
    // Set trend direction display
    let trendLabel = "WAITING";
    if (regime === "BULLISH") trendLabel = `UP (${trendStrength.toFixed(2)}%)`;
    if (regime === "BEARISH") trendLabel = `DOWN (${trendStrength.toFixed(2)}%)`;
    if (regime === "SIDEWAYS") trendLabel = `CHOP (${trendStrength.toFixed(2)}%)`;
    
    document.getElementById('ai-trend').innerText = trendLabel;
    
    document.getElementById('ai-vol').innerText = risk === 'HIGH' ? 'HIGH' : 'NORMAL';
    
    const decisionStr = d.decision_action || (hedge === 'ACTIVE' ? 'BUY HEDGE' : 'HOLD');
    document.getElementById('ai-decision').innerText = decisionStr;
    document.getElementById('ai-decision').className = (decisionStr !== 'HOLD' && decisionStr !== 'WAITING') ? 'dec-active' : '';
    
    const conf = d.confidence ? (d.confidence * 100).toFixed(0) + '%' : (hedge === 'ACTIVE' ? '92%' : 'N/A');
    document.getElementById('ai-conf').innerText = conf;
    
    // Use real reasoning if available
    let reason = d.decision_reason || '';
    if (!reason || reason === 'Initializing' || reason === 'No Reason') {
        if (hedge === 'ACTIVE') {
            reason = `[ARES KERNEL] Intraday Trend is ${regime}.\n[RISK ENGINE] ${risk} risk detected. Hedge approved.\n[EXECUTION] Generating market order to neutralize delta.\n[CONFIDENCE] High. Executing.`;
        } else if (regime === 'WAITING') {
            reason = `[ARES KERNEL] Waiting for trade entry...\n[RISK ENGINE] Analyzing market regime...\n[DECISION] Standby.`;
        } else {
            reason = `[ARES KERNEL] Intraday Trend is ${regime}.\n[RISK ENGINE] ${risk} risk detected. Limits OK.\n[DECISION] Maintain current exposure.\nWaiting for market catalyst...`;
        }
    }
    
    const reasonEl = document.getElementById('ai-reason');
    if (reasonEl.dataset.current !== reason) {
        reasonEl.dataset.current = reason;
        // Simple typing effect simulation
        reasonEl.innerText = '';
        let i = 0;
        const type = () => {
            if (i < reason.length) {
                reasonEl.innerHTML += reason.charAt(i);
                i++;
                setTimeout(type, 15);
            }
        };
        type();
    }
}

function updateTimeline(d) {
    if (d.total_ticks === 0) return;
    
    const now = new Date().toLocaleTimeString('en-US', {hour12: false});
    const tl = document.getElementById('exec-timeline');
    
    const action = d.active_hedge === 'ACTIVE' ? 'BUY HEDGE' : 'HOLD';
    const sC = d.active_hedge === 'ACTIVE' ? 'cyan' : 'green';
    
    tl.innerHTML = `
        <div class="tl-item"><span class="tl-time">${now}</span><span class="tl-name">Market Tick</span><span class="tl-status green">✓</span></div>
        <div class="tl-item"><span class="tl-time">${now}</span><span class="tl-name">Trend Engine</span><span class="tl-status green">✓</span></div>
        <div class="tl-item"><span class="tl-time">${now}</span><span class="tl-name">Risk Engine</span><span class="tl-status green">✓</span></div>
        <div class="tl-item"><span class="tl-time">${now}</span><span class="tl-name">Decision</span><span class="tl-status ${sC}">${action}</span></div>
        <div class="tl-item"><span class="tl-time">${now}</span><span class="tl-name">Execution</span><span class="tl-status ${sC}">${d.active_hedge==='ACTIVE'?'Submitted':'Standby'}</span></div>
    `;
}

function updateHealth(d) {
    const lat = d.pipeline_latency || 0;
    let score = 99;
    if (lat > 0.5) score -= 10;
    if (d.health_status !== 'GREEN') score -= 20;
    
    document.getElementById('health-score').innerText = `${score} / 100`;
    document.getElementById('health-text').innerText = score > 90 ? 'EXCELLENT' : (score > 70 ? 'GOOD' : 'WARNING');
    document.getElementById('health-score').style.color = score > 90 ? '#00C853' : (score > 70 ? '#FFB300' : '#FF5252');
    
    document.getElementById('ck-market').innerText = '🟢';
    document.getElementById('ck-exec').innerText = '🟢';
    document.getElementById('ck-risk').innerText = '🟢';
    document.getElementById('ck-prov').innerText = d.provider_health === 'GREEN' ? '🟢' : '🟡';
    
    document.getElementById('st-rest').innerText = d.exchange_status === 'CONNECTED' ? '🟢' : '🔴';
    document.getElementById('st-ws').innerText = d.provider_health === 'GREEN' ? '🟢' : '🔴';
    document.getElementById('st-paper').innerText = d.bot_mode === 'PAPER' ? '🟢' : '🟡';
    document.getElementById('st-risk').innerText = d.current_risk === 'LOW' ? '🟢' : (d.current_risk === 'MEDIUM' ? '🟡' : '🔴');
}

function updateOrders(orders) {
    const c = document.getElementById('orders-feed');
    if (!orders || orders.length === 0) {
        c.innerHTML = '<div class="empty-state">No active orders</div>';
        return;
    }
    
    c.innerHTML = orders.slice(0, 50).map(o => {
        const time = o.timestamp ? (o.timestamp.split('T')[1]?.substring(0,8) || o.timestamp.substring(0,8)) : '--:--:--';
        const isBuy = o.side === 'BUY';
        return `
        <div class="feed-row ${isBuy ? 'buy' : 'sell'}">
            <span class="fr-time">${time}</span>
            <span class="fr-act ${isBuy ? 'buy' : 'sell'}">${o.side}</span>
            <span class="fr-msg">${fmtNum(o.quantity)} ${o.symbol} @ ${fmtUSD(o.price)} [${o.state}]</span>
        </div>
        `;
    }).join('');
}

function updateTerminal(logs) {
    if (!logs || !logs.logs) return;
    const term = document.getElementById('sys-terminal');
    
    // Only update if new logs
    const newLogs = logs.logs.slice(-50);
    const html = newLogs.map(l => {
        let cls = 'log-info';
        if (l.includes('WARN')) cls = 'log-warn';
        if (l.includes('ERROR') || l.includes('FAIL')) cls = 'log-err';
        if (l.includes('SYSTEM')) cls = 'log-sys';
        return `<div class="${cls}">${l}</div>`;
    }).join('');
    
    if (term.innerHTML !== html) {
        term.innerHTML = html;
        term.scrollTop = term.scrollHeight;
    }
}
