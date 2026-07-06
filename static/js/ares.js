// ARES Mission Control V2 JS — Module 46 Data Pipeline Fix

// ECharts Instances
let chartPortfolio, chartPnl;
let gaugeRisk, gaugeMargin, gaugeHeat, gaugeSafety;

// AG Grid Instance
let gridOptions;

// Historical chart data arrays
let timeData = [];
let portData = [];
let pnlData = [];

// Configuration — polling interval unchanged from original
const POLL_INTERVAL = 1000;

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initCharts();
    initGrid();
    
    // Start polling (frequency unchanged as mandated)
    pollData();
    setInterval(pollData, POLL_INTERVAL);
});

function initClock() {
    setInterval(() => {
        const now = new Date();
        document.getElementById('sys-clock').innerText = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    }, 1000);
}

function initCharts() {
    const text = '#9CA3AF';
    const gridColor = '#1F2937';

    // 1. Portfolio Area Chart
    chartPortfolio = echarts.init(document.getElementById('chart-portfolio'));
    chartPortfolio.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: '#111827', borderColor: '#1F2937', textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLine: { lineStyle: { color: text } }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLine: { lineStyle: { color: text } }, splitLine: { lineStyle: { color: gridColor } } },
        series: [{
            name: 'Value', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00E5FF', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,229,255,0.4)' },
                    { offset: 1, color: 'rgba(0,229,255,0.0)' }
                ])
            },
            data: []
        }]
    });

    // 2. PnL Area Chart
    chartPnl = echarts.init(document.getElementById('chart-pnl'));
    chartPnl.setOption({
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: '#111827', borderColor: '#1F2937', textStyle: { color: '#fff' } },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLine: { lineStyle: { color: text } }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLine: { lineStyle: { color: text } }, splitLine: { lineStyle: { color: gridColor } } },
        series: [{
            name: 'PnL', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00C853', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,200,83,0.4)' },
                    { offset: 1, color: 'rgba(0,200,83,0.0)' }
                ])
            },
            data: []
        }]
    });

    // Gauges Factory
    const createMiniGauge = (elementId, color, max) => {
        const chart = echarts.init(document.getElementById(elementId));
        chart.setOption({
            series: [{
                type: 'gauge', startAngle: 180, endAngle: 0, min: 0, max: max,
                pointer: { show: true, length: '60%', width: 4 },
                progress: { show: true, overlap: false, roundCap: true, clip: false, itemStyle: { color: color } },
                axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(255,255,255,0.1)']] } },
                splitLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false },
                detail: { fontSize: 16, color: '#fff', offsetCenter: [0, '30%'], formatter: '{value}' },
                data: [{ value: 0 }]
            }]
        });
        return chart;
    };

    gaugeRisk = createMiniGauge('gauge-risk', '#FFB300', 100);
    gaugeMargin = createMiniGauge('gauge-margin', '#00E5FF', 100);
    gaugeHeat = createMiniGauge('gauge-heat', '#FF5252', 100);
    gaugeSafety = createMiniGauge('gauge-safety', '#00C853', 100);

    window.addEventListener('resize', () => {
        chartPortfolio.resize(); chartPnl.resize();
        gaugeRisk.resize(); gaugeMargin.resize(); gaugeHeat.resize(); gaugeSafety.resize();
    });
}

function initGrid() {
    const columnDefs = [
        { field: "timestamp", headerName: "Time", width: 150, valueFormatter: p => {
            if (!p.value) return 'N/A';
            try { return p.value.split('T')[1]?.substring(0, 8) || p.value.substring(0, 19); } catch(e) { return p.value; }
        }},
        { field: "symbol", headerName: "Instrument", width: 120 },
        { field: "side", headerName: "Side", width: 90, cellStyle: p => ({ color: p.value === 'BUY' ? '#00C853' : '#FF5252', fontWeight: 'bold' }) },
        { field: "quantity", headerName: "Qty", width: 90 },
        { field: "average_fill_price", headerName: "Price", width: 110, valueFormatter: p => p.value ? `$${Number(p.value).toFixed(2)}` : 'N/A' },
        { 
            field: "state", headerName: "Status", width: 120,
            cellStyle: p => {
                let color = '#9CA3AF';
                const v = (p.value || '').toUpperCase();
                if (v.includes('FILLED')) color = '#00C853';
                else if (v.includes('SUBMITTED') || v.includes('ACK') || v.includes('PENDING')) color = '#00E5FF';
                else if (v.includes('REJECTED') || v.includes('FAILED')) color = '#FF5252';
                else if (v.includes('PARTIAL')) color = '#FFB300';
                return { color, fontWeight: 'bold' };
            }
        }
    ];

    gridOptions = {
        columnDefs: columnDefs,
        rowData: [],
        rowSelection: 'single',
        animateRows: true,
        headerHeight: 40,
        rowHeight: 35
    };

    const gridDiv = document.querySelector('#ordersGrid');
    new agGrid.Grid(gridDiv, gridOptions);
}

// ---- Data Polling ----
async function pollData() {
    try {
        const [statusRes, ordersRes, logsRes, portfolioRes] = await Promise.all([
            fetch('/ares/status').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/orders').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/logs').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/portfolio').then(r => r.ok ? r.json() : null).catch(() => null)
        ]);
        
        if (statusRes && !statusRes.error) {
            updateUI(statusRes);
            updatePipeline(statusRes);
            updateGauges(statusRes);
            updateActivityFeed(statusRes);
        }
        if (ordersRes) updateGrid(ordersRes);
        if (logsRes) updateLogs(logsRes);
        if (portfolioRes) updatePortfolio(portfolioRes);
        
    } catch (err) {
        console.error("Polling error:", err);
    }
}

// ---- UI Updaters ----

function fmtUSD(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return '$' + Number(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function fmtNum(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return Number(val).toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4});
}

function updateUI(data) {
    // Top Bar
    setText('bot-mode', data.bot_mode || 'N/A');

    // Hero Section — BTC Price
    setText('val-btc-price', fmtUSD(data.btc_price));
    
    // Hero Section — Portfolio Value
    setText('val-portfolio', fmtUSD(data.portfolio_value));
    
    // Hero Section — PnL with color
    const pnlEl = document.getElementById('val-pnl');
    const pnlVal = data.pnl !== undefined ? Number(data.pnl) : null;
    if (pnlVal !== null) {
        pnlEl.innerText = (pnlVal >= 0 ? '+' : '') + fmtUSD(pnlVal);
        pnlEl.className = 'hero-value ' + (pnlVal >= 0 ? 'val-up' : 'val-down');
    } else {
        pnlEl.innerText = 'N/A';
        pnlEl.className = 'hero-value';
    }

    // Hero Section — Decision Badge
    const decisionEl = document.getElementById('val-decision');
    decisionEl.innerText = data.active_hedge || 'N/A';
    
    // Greeks Panel — strict mapping, only what backend provides
    setText('gk-delta', fmtNum(data.total_delta));
    setText('gk-margin', fmtUSD(data.margin_used));
    // Gamma/Vega/Theta: N/A until backend exposes them
    
    // AI Reasoning Panel — strict mapping
    setText('ai-risk', data.current_risk || 'N/A');
    // All other AI fields remain "Waiting for data" until backend exposes them
    
    // Provider Health
    setHealth('h-rest', data.exchange_status);
    if (data.provider_health) {
        setHealth('h-hb', data.provider_health);
    }
    if (data.avg_latency !== undefined && data.avg_latency > 0) {
        const latEl = document.getElementById('h-lat');
        latEl.innerText = data.avg_latency.toFixed(1) + ' ms';
        latEl.className = 'h-indicator ' + (data.avg_latency < 100 ? 'green' : data.avg_latency < 500 ? 'yellow' : 'red');
    }

    // Append to charts
    const now = new Date().toLocaleTimeString();
    if (data.portfolio_value !== undefined) appendChartData(chartPortfolio, now, data.portfolio_value, portData);
    if (data.pnl !== undefined) appendChartData(chartPnl, now, data.pnl, pnlData);
}

function updatePortfolio(data) {
    // Handle both array and object responses
    if (data && !Array.isArray(data)) {
        // New enriched portfolio response with snapshot
        if (data.net_delta !== undefined && data.net_delta !== null) setText('gk-delta', fmtNum(data.net_delta));
        if (data.net_gamma !== undefined && data.net_gamma !== null) setText('gk-gamma', fmtNum(data.net_gamma));
        if (data.net_vega !== undefined && data.net_vega !== null) setText('gk-vega', fmtNum(data.net_vega));
        if (data.net_theta !== undefined && data.net_theta !== null) setText('gk-theta', fmtNum(data.net_theta));
        if (data.margin_used !== undefined && data.margin_used !== null) setText('gk-margin', fmtUSD(data.margin_used));
        if (data.available_margin !== undefined && data.available_margin !== null) setText('gk-avail', fmtUSD(data.available_margin));
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.innerText = val;
}

function setHealth(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerText = val || 'N/A';
    const v = (val || '').toUpperCase();
    if (v === 'CONNECTED' || v === 'ONLINE' || v === 'GREEN' || v === 'UP') {
        el.className = 'h-indicator green';
    } else if (v === 'N/A' || v === 'UNKNOWN' || v === 'YELLOW') {
        el.className = 'h-indicator yellow';
    } else {
        el.className = 'h-indicator red';
    }
}

function appendChartData(chart, time, val, dataArr) {
    if (timeData.length > 60) timeData.shift();
    if (dataArr.length > 60) dataArr.shift();
    
    // Only push time once (shared X axis)
    if (chart === chartPortfolio) timeData.push(time);
    dataArr.push(val);
    
    chart.setOption({ xAxis: { data: timeData }, series: [{ data: dataArr }] });
}

function updateGauges(data) {
    // Map risk level string to numeric score for gauge
    const riskMap = { 'LOW': 25, 'MEDIUM': 50, 'HIGH': 75, 'CRITICAL': 95 };
    const riskScore = riskMap[(data.current_risk || '').toUpperCase()] || 0;
    gaugeRisk.setOption({ series: [{ data: [{ value: riskScore }] }] });
    
    // Margin gauge (percentage)
    const marginPct = data.margin_used !== undefined ? Math.min(Number(data.margin_used) * 100, 100) : 0;
    gaugeMargin.setOption({ series: [{ data: [{ value: marginPct.toFixed(1) }] }] });
    
    // Heat = max_drawdown (percentage)
    const heat = data.max_drawdown !== undefined ? Math.min(Math.abs(Number(data.max_drawdown)) * 100, 100) : 0;
    gaugeHeat.setOption({ series: [{ data: [{ value: heat.toFixed(1) }] }] });
    
    // Safety = inverse of risk (higher = safer)
    gaugeSafety.setOption({ series: [{ data: [{ value: Math.max(0, 100 - riskScore) }] }] });
}

function updateGrid(orders) {
    if (Array.isArray(orders) && gridOptions.api) {
        gridOptions.api.setRowData(orders);
    }
}

function updateLogs(logs) {
    // Backend now returns a raw array of strings
    const logArray = Array.isArray(logs) ? logs : (logs && logs.logs ? logs.logs : []);
    if (logArray.length === 0) return;
    
    const term = document.getElementById('sys-terminal');
    const wasAtBottom = term.scrollTop >= (term.scrollHeight - term.clientHeight - 10);
    
    term.innerHTML = logArray.map(line => {
        let cls = '';
        if (line.includes('ERROR')) cls = 'log-error';
        else if (line.includes('WARNING') || line.includes('WARN')) cls = 'log-warn';
        else if (line.includes('INFO')) cls = 'log-info';
        else if (line.includes('SYSTEM') || line.includes('ARES')) cls = 'log-sys';
        return `<span class="${cls}">${escapeHtml(line)}</span>`;
    }).join('\n');

    if (wasAtBottom) {
        term.scrollTop = term.scrollHeight;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Pipeline visualizer
const stages = ['tick', 'context', 'trend', 'regime', 'risk', 'decision', 'sizing', 'execution'];
function updatePipeline(data) {
    if (data.error) return;
    
    // Reset all nodes
    stages.forEach(s => {
        const el = document.getElementById(`node-${s}`);
        if (el) el.className = 'pipe-node';
    });
    
    // If ticks are happening, animate based on total_ticks
    const ticks = data.total_ticks || 0;
    if (ticks > 0) {
        // All stages completed for this tick
        stages.forEach(s => {
            const el = document.getElementById(`node-${s}`);
            if (el) el.className = 'pipe-node done';
        });
        
        // Last stage pulses
        if (data.active_hedge === 'ACTIVE') {
            document.getElementById('node-execution').className = 'pipe-node active';
        } else {
            document.getElementById('node-tick').className = 'pipe-node active';
        }
    } else {
        // Waiting for first tick
        document.getElementById('node-tick').className = 'pipe-node active';
    }
}

let feedEvents = [];
function updateActivityFeed(data) {
    const feed = document.getElementById('activity-feed');
    const now = new Date().toLocaleTimeString();
    
    // Generate events from status data
    const newEvents = [];
    
    if (data.exchange_status === 'CONNECTED' && feedEvents.length === 0) {
        newEvents.push({ time: now, msg: 'Exchange Connected', cls: 'green' });
    }
    if (data.total_ticks > 0 && (feedEvents.length === 0 || data.total_ticks % 10 === 0)) {
        newEvents.push({ time: now, msg: `Tick #${data.total_ticks} processed`, cls: '' });
    }
    if (data.health_status && data.health_status !== 'UNKNOWN') {
        newEvents.push({ time: now, msg: `Health: ${data.health_status}`, cls: data.health_status === 'GREEN' ? 'green' : 'yellow' });
    }
    
    if (newEvents.length > 0) {
        feedEvents = [...newEvents, ...feedEvents].slice(0, 20);
        feed.innerHTML = feedEvents.map(e => 
            `<div class="feed-item"><span class="feed-time">${e.time}</span><span class="feed-msg">${e.msg}</span></div>`
        ).join('');
    } else if (feedEvents.length === 0) {
        feed.innerHTML = `
            <div class="feed-item"><span class="feed-time">${now}</span><span class="feed-msg">ARES Mission Control initialized.</span></div>
            <div class="feed-item"><span class="feed-time">${now}</span><span class="feed-msg">Waiting for first tick...</span></div>
        `;
    }
}
