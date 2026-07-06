// ARES Mission Control V2 JS

// ECharts Instances
let chartPortfolio, chartPnl;
let gaugeRisk, gaugeMargin, gaugeHeat, gaugeSafety;

// AG Grid Instance
let gridOptions;

// Configuration
const POLL_INTERVAL = 1000;

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initCharts();
    initGrid();
    
    // Start polling (No change to frequency as requested)
    pollData();
    setInterval(pollData, POLL_INTERVAL);

    // Auto-scroll logic for terminal
    document.getElementById('btn-scroll').addEventListener('click', () => {
        const term = document.getElementById('sys-terminal');
        term.scrollTop = term.scrollHeight;
    });
});

function initClock() {
    setInterval(() => {
        const now = new Date();
        document.getElementById('sys-clock').innerText = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
    }, 1000);
}

function initCharts() {
    // Colors
    const primary = '#00E5FF';
    const bg = 'transparent';
    const text = '#9CA3AF';
    const gridColor = '#1F2937';

    // 1. Portfolio Area Chart
    chartPortfolio = echarts.init(document.getElementById('chart-portfolio'));
    chartPortfolio.setOption({
        backgroundColor: bg,
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLine: { lineStyle: { color: text } }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLine: { lineStyle: { color: text } }, splitLine: { lineStyle: { color: gridColor } } },
        series: [{
            name: 'Value', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: primary, width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,229,255,0.4)' },
                    { offset: 1, color: 'rgba(0,229,255,0.0)' }
                ])
            },
            data: []
        }]
    });

    // 2. PnL Area Chart (Green/Red)
    chartPnl = echarts.init(document.getElementById('chart-pnl'));
    chartPnl.setOption({
        backgroundColor: bg,
        tooltip: { trigger: 'axis' },
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
    const createMiniGauge = (elementId, name, color, max) => {
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

    gaugeRisk = createMiniGauge('gauge-risk', 'Risk', '#FFB300', 100);
    gaugeMargin = createMiniGauge('gauge-margin', 'Margin', '#00E5FF', 100);
    gaugeHeat = createMiniGauge('gauge-heat', 'Heat', '#FF5252', 100);
    gaugeSafety = createMiniGauge('gauge-safety', 'Safety', '#00C853', 100);

    window.addEventListener('resize', () => {
        chartPortfolio.resize(); chartPnl.resize();
        gaugeRisk.resize(); gaugeMargin.resize(); gaugeHeat.resize(); gaugeSafety.resize();
    });
}

function initGrid() {
    const columnDefs = [
        { field: "timestamp", headerName: "Time", width: 150, valueFormatter: params => params.value ? params.value.split('T')[1]?.substring(0, 8) || params.value : 'N/A' },
        { field: "symbol", headerName: "Instrument", width: 120 },
        { field: "side", headerName: "Side", width: 90, cellStyle: params => ({ color: params.value === 'BUY' ? '#00C853' : '#FF5252', fontWeight: 'bold' }) },
        { field: "quantity", headerName: "Qty", width: 90 },
        { field: "average_fill_price", headerName: "Price", width: 110, valueFormatter: params => params.value ? `$${params.value.toFixed(2)}` : 'N/A' },
        { 
            field: "state", headerName: "Status", width: 120,
            cellStyle: params => {
                let color = '#9CA3AF';
                if (params.value?.includes('FILLED')) color = '#00C853';
                else if (params.value?.includes('SUBMITTED') || params.value?.includes('ACK')) color = '#00E5FF';
                else if (params.value?.includes('REJECTED') || params.value?.includes('FAILED')) color = '#FF5252';
                else if (params.value?.includes('PARTIAL')) color = '#FFB300';
                return { color: color, fontWeight: 'bold' };
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

// Data Polling
async function pollData() {
    try {
        const [statusRes, ordersRes, logsRes] = await Promise.all([
            fetch('/ares/status').then(res => res.json()),
            fetch('/ares/orders').then(res => res.json()),
            fetch('/ares/logs').then(res => res.json())
        ]);
        
        updateUI(statusRes);
        updateGrid(ordersRes);
        updateLogs(logsRes);
        updatePipeline(statusRes);
        updateActivityFeed(statusRes);
        
    } catch (err) {
        console.error("Polling error:", err);
    }
}

// Update DOM elements strictly mapping backend properties
function updateUI(data) {
    if (data.error) return;

    // Formatters
    const fmtUSD = val => val !== undefined && val !== 'N/A' ? `$${Number(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : 'Waiting for data';
    const fmtNum = val => val !== undefined && val !== 'N/A' ? Number(val).toLocaleString() : 'N/A';
    
    // Top Bar
    document.getElementById('bot-mode').innerText = data.bot_mode || 'Waiting for data';

    // Hero Section
    document.getElementById('val-btc-price').innerText = fmtUSD(data.btc_price);
    document.getElementById('val-portfolio').innerText = fmtUSD(data.portfolio_value);
    
    const pnlEl = document.getElementById('val-pnl');
    const pnlVal = data.pnl !== undefined ? Number(data.pnl) : null;
    if (pnlVal !== null) {
        pnlEl.innerText = (pnlVal >= 0 ? '+' : '') + fmtUSD(pnlVal);
        pnlEl.className = 'hero-value ' + (pnlVal >= 0 ? 'val-up' : 'val-down');
    } else {
        pnlEl.innerText = 'Waiting for data';
        pnlEl.className = 'hero-value';
    }

    // Decision Badge
    const decisionEl = document.getElementById('val-decision');
    const action = data.active_hedge || 'N/A';
    decisionEl.innerText = action;
    
    // Greeks Panel (Strict mapping, no fabrication)
    document.getElementById('gk-delta').innerText = fmtNum(data.total_delta);
    // Backend doesn't provide gamma/vega/theta yet, so default to N/A
    document.getElementById('gk-margin').innerText = fmtUSD(data.margin_used);
    
    // Provider Health (Strict mapping)
    const setHealth = (id, val) => {
        const el = document.getElementById(id);
        el.innerText = val !== undefined ? val : 'N/A';
        el.className = 'h-indicator ' + (val === 'ONLINE' || val === 'CONNECTED' ? 'green' : (val === 'N/A' || val === 'UNKNOWN' ? 'yellow' : 'red'));
    };
    setHealth('h-rest', data.exchange_status);
    setHealth('h-lat', 'N/A'); // Not in /status yet
    
    // AI Reasoning Panel (Strict mapping)
    // The backend /status does not currently emit 'confidence', 'trend', 'volatility', etc.
    // They must remain 'Waiting for backend data' as requested.
    document.getElementById('ai-risk').innerText = data.current_risk || 'N/A';
    
    // Charts (Simulation of historical appending since /status only returns current tick)
    const now = new Date().toLocaleTimeString();
    if (data.portfolio_value) appendChartData(chartPortfolio, now, data.portfolio_value);
    if (data.pnl !== undefined) appendChartData(chartPnl, now, data.pnl);

    // Gauges
    // Risk score might be derived from current_risk string if we map it, but user says NO simulation.
    // Wait, risk is a string 'LOW'. We shouldn't fabricate a number.
    // Actually, margin_used is available. Let's assume margin % is not available unless calculated.
    // We will leave gauge values at 0 unless explicitly provided.
}

let timeData = [];
let portData = [];
let pnlData = [];

function appendChartData(chart, time, val) {
    if (timeData.length > 50) { timeData.shift(); }
    
    if (chart === chartPortfolio) {
        if (portData.length > 50) portData.shift();
        portData.push(val);
        timeData.push(time); // Just using one time array for simplicity
        chart.setOption({ xAxis: { data: timeData }, series: [{ data: portData }] });
    } else {
        if (pnlData.length > 50) pnlData.shift();
        pnlData.push(val);
        chart.setOption({ xAxis: { data: timeData }, series: [{ data: pnlData }] });
    }
}

function updateGrid(orders) {
    if (Array.isArray(orders)) {
        gridOptions.api.setRowData(orders);
    }
}

function updateLogs(logs) {
    if (!Array.isArray(logs)) return;
    const term = document.getElementById('sys-terminal');
    const wasAtBottom = term.scrollTop >= (term.scrollHeight - term.clientHeight - 10);
    
    term.innerHTML = logs.map(line => {
        let cls = '';
        if (line.includes('ERROR')) cls = 'log-error';
        else if (line.includes('WARNING')) cls = 'log-warn';
        else if (line.includes('INFO')) cls = 'log-info';
        else if (line.includes('SYSTEM')) cls = 'log-sys';
        return `<span class="${cls}">${line}</span>`;
    }).join('\n');

    if (wasAtBottom) {
        term.scrollTop = term.scrollHeight;
    }
}

// Pipeline visualizer
const stages = ['tick', 'context', 'trend', 'regime', 'risk', 'decision', 'sizing', 'execution'];
let currentStageIndex = 0;
function updatePipeline(data) {
    if (data.error) return;
    // Since backend doesn't output current pipeline stage in /status, 
    // we pulse execution if active_hedge === ACTIVE, else pulse tick (waiting).
    // STRICT RULE: No fabrication. We will just leave it static if backend doesn't support it,
    // or we just highlight based on active_hedge.
    stages.forEach(s => {
        const el = document.getElementById(`node-${s}`);
        el.className = 'pipe-node';
    });
    
    if (data.active_hedge === 'ACTIVE') {
        document.getElementById('node-execution').className = 'pipe-node done';
    } else {
        document.getElementById('node-tick').className = 'pipe-node active';
    }
}

function updateActivityFeed(data) {
    // Populate with basic events from logs or status
    const feed = document.getElementById('activity-feed');
    if (feed.children.length === 0) {
        // Initial dummy insert just to show it works, since we have no feed endpoint
        feed.innerHTML = `
            <div class="feed-item"><span class="feed-time">System</span><span class="feed-msg">ARES Mission Control initialized.</span></div>
            <div class="feed-item"><span class="feed-time">Backend</span><span class="feed-msg">Waiting for event stream...</span></div>
        `;
    }
}
