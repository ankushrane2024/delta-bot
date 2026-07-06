// AG Grid Initialization
let gridOptions = {
    columnDefs: [
        { field: 'client_order_id', headerName: 'Order ID', width: 130 },
        { field: 'symbol', headerName: 'Symbol', width: 140 },
        { 
            field: 'side', 
            headerName: 'Side', 
            width: 90,
            cellRenderer: params => {
                const color = params.value === 'BUY' ? 'var(--accent-success)' : 'var(--accent-danger)';
                return `<span style="color: ${color}; font-weight: bold;">${params.value}</span>`;
            }
        },
        { field: 'quantity', headerName: 'Qty', width: 90 },
        { 
            field: 'price', 
            headerName: 'Price', 
            width: 110,
            valueFormatter: params => params.value > 0 ? '$' + params.value : 'MKT'
        },
        { field: 'state', headerName: 'Status', width: 110 },
        { 
            field: 'time', 
            headerName: 'Time', 
            flex: 1,
            valueFormatter: params => params.value ? new Date(params.value).toLocaleTimeString() : ''
        }
    ],
    defaultColDef: {
        sortable: true,
        resizable: true,
        filter: true,
    },
    rowData: [],
    rowSelection: 'single',
    animateRows: true,
    rowHeight: 32,
    headerHeight: 32,
    overlayNoRowsTemplate: '<span style="padding: 10px; color: var(--text-muted);">No active orders</span>'
};

document.addEventListener('DOMContentLoaded', () => {
    const gridDiv = document.querySelector('#orders-grid');
    new agGrid.Grid(gridDiv, gridOptions);
});

function onFilterTextBoxChanged() {
    gridOptions.api.setQuickFilter(document.getElementById('order-search').value);
}


// ECharts Initialization
const chartCommon = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Inter' },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: '#111827' } } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: [], splitLine: { show: false }, axisLine: { lineStyle: { color: '#1F2937' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1F2937', type: 'dashed' } } }
};

const portChart = echarts.init(document.getElementById('chart-port'));
portChart.setOption({
    ...chartCommon,
    series: [{
        name: 'Portfolio', type: 'line', data: [], smooth: true,
        itemStyle: { color: '#00E5FF' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{offset: 0, color: 'rgba(0, 229, 255, 0.3)'}, {offset: 1, color: 'rgba(0, 229, 255, 0)'}]) }
    }]
});

const pnlChart = echarts.init(document.getElementById('chart-pnl'));
pnlChart.setOption({
    ...chartCommon,
    legend: { data: ['PnL', 'Delta'], textStyle: { color: '#9CA3AF' }, top: 0, right: 0 },
    yAxis: [
        { type: 'value', name: 'PnL', splitLine: { show: false } },
        { type: 'value', name: 'Delta', position: 'right', splitLine: { show: false } }
    ],
    series: [
        { name: 'PnL', type: 'line', data: [], smooth: true, itemStyle: { color: '#00C853' } },
        { name: 'Delta', type: 'line', yAxisIndex: 1, data: [], smooth: true, itemStyle: { color: '#FFB300' } }
    ]
});

const heatChart = echarts.init(document.getElementById('chart-heat'));
heatChart.setOption({
    series: [{
        type: 'gauge',
        startAngle: 180, endAngle: 0,
        min: 0, max: 100,
        splitNumber: 4,
        itemStyle: { color: '#00E5FF' },
        progress: { show: true, width: 8 },
        pointer: { show: false },
        axisLine: { lineStyle: { width: 8 } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: { valueAnimation: true, fontSize: 20, offsetCenter: [0, '20%'], color: '#FFFFFF', formatter: '{value}%' },
        data: [{ value: 0 }]
    }]
});

window.addEventListener('resize', () => {
    portChart.resize();
    pnlChart.resize();
    heatChart.resize();
});


// Auto-Scroll Toggle
let autoScroll = true;
function toggleLogScroll() {
    autoScroll = !autoScroll;
    const icon = document.getElementById('icon-scroll');
    if (autoScroll) {
        icon.setAttribute('data-lucide', 'pause-circle');
    } else {
        icon.setAttribute('data-lucide', 'play-circle');
    }
    lucide.createIcons();
}

function updateValueWithAnimation(elementId, newValue) {
    const el = document.getElementById(elementId);
    if (!el) return;
    if (el.innerText !== String(newValue)) {
        el.innerText = newValue;
        el.classList.remove('value-update');
        void el.offsetWidth; // trigger reflow
        el.classList.add('value-update');
    }
}

// Data Polling
async function fetchAresData() {
    try {
        const now = new Date().toLocaleTimeString();

        // 1. Status
        let resStatus = await fetch('/ares/status');
        let status = await resStatus.json();
        
        if (!status.error) {
            updateValueWithAnimation('metric-mode', status.bot_mode);
            updateValueWithAnimation('metric-btc', '$' + (status.btc_price || 0).toFixed(2));
            updateValueWithAnimation('metric-port', '$' + (status.portfolio_value || 0).toFixed(2));
            updateValueWithAnimation('metric-pnl', '$' + (status.pnl || 0).toFixed(2));
            updateValueWithAnimation('metric-delta', (status.total_delta || 0).toFixed(4));
            updateValueWithAnimation('metric-margin', '$' + (status.margin_used || 0).toFixed(2));
            updateValueWithAnimation('metric-risk', status.current_risk || 'NORMAL');
            
            document.getElementById('stat-hash').innerText = status.portfolio_hash || '--';
            
            const isConn = status.exchange_status === 'CONNECTED';
            document.getElementById('stat-rest').className = isConn ? 'status-dot dot-green' : 'status-dot dot-red';
            document.getElementById('stat-rest-sb').className = isConn ? 'status-dot dot-green' : 'status-dot dot-red';
            document.getElementById('stat-ws-sb').className = isConn ? 'status-dot dot-green' : 'status-dot dot-red';

            const hlth = status.health_status;
            const hlthCls = hlth === 'GREEN' ? 'dot-green' : (hlth === 'YELLOW' ? 'dot-yellow' : 'dot-red');
            document.getElementById('stat-eb').className = 'status-dot ' + hlthCls;

            // Update charts
            portChart.setOption({
                xAxis: { data: [...(portChart.getOption().xAxis[0].data.slice(-30)), now] },
                series: [{ data: [...(portChart.getOption().series[0].data.slice(-30)), status.portfolio_value || 0] }]
            });
            pnlChart.setOption({
                xAxis: { data: [...(pnlChart.getOption().xAxis[0].data.slice(-30)), now] },
                series: [
                    { data: [...(pnlChart.getOption().series[0].data.slice(-30)), status.pnl || 0] },
                    { data: [...(pnlChart.getOption().series[1].data.slice(-30)), status.total_delta || 0] }
                ]
            });
            
            let heatVal = Math.min(100, Math.max(0, (status.margin_used / (status.portfolio_value || 1)) * 100));
            heatChart.setOption({ series: [{ data: [{ value: heatVal.toFixed(1) }] }] });
        }

        // 2. System
        let resSys = await fetch('/ares/system');
        let sys = await resSys.json();
        if (!sys.error) {
            updateValueWithAnimation('sys-cpu', sys.cpu_percent.toFixed(1));
            updateValueWithAnimation('sys-ram', sys.memory_percent.toFixed(1));
            document.getElementById('stat-threads').innerText = sys.active_threads;
        }

        // 3. Analytics (Pipeline)
        let resAn = await fetch('/ares/analytics');
        let an = await resAn.json();
        if (!an.error) {
            updateValueWithAnimation('pipe-lat', (an.avg_latency_ms || 0).toFixed(1) + ' ms');
            
            document.getElementById('val-tick').innerText = now;
            document.getElementById('val-ctx').innerText = an.market_regime || 'CALM';
            document.getElementById('val-trend').innerText = an.trend_direction || 'NEUTRAL';
            document.getElementById('val-regime').innerText = an.volatility_regime || 'NORMAL';
            document.getElementById('val-risk').innerText = an.risk_level || 'OK';
            document.getElementById('val-dec').innerText = an.last_decision || 'HOLD';
            document.getElementById('val-size').innerText = an.last_size || '0.00';
            document.getElementById('val-exec').innerText = an.last_execution || 'NONE';

            // Animation for pipeline node logic based on decision
            const nodes = ['node-tick', 'node-ctx', 'node-trend', 'node-regime', 'node-risk', 'node-dec', 'node-size', 'node-exec'];
            nodes.forEach(n => document.getElementById(n).className = 'timeline-node'); // reset
            
            // Randomly simulate pipeline activity for UI fidelity (since backend is fast, we just show it all active or success)
            if (an.last_decision && an.last_decision !== 'HOLD') {
                nodes.forEach(n => document.getElementById(n).classList.add('node-success'));
                document.getElementById('ai-insight-text').innerText = `ARES executed ${an.last_decision} due to ${an.trend_direction} trend and ${an.volatility_regime} volatility.`;
                document.getElementById('ai-insight-text').style.display = 'block';
                document.querySelector('.insight-shimmer').style.display = 'none';
            } else {
                nodes.slice(0, 5).forEach(n => document.getElementById(n).classList.add('node-active'));
                document.getElementById('ai-insight-text').style.display = 'none';
                document.querySelector('.insight-shimmer').style.display = 'block';
            }
        }

        // 4. Portfolio Greeks
        let resPort = await fetch('/ares/portfolio');
        let portData = await resPort.json();
        if (!portData.error) {
            let nd = 0, ng = 0, nv = 0, nt = 0;
            if (Array.isArray(portData)) {
                portData.forEach(p => {
                    if (p.delta) nd += p.delta;
                    if (p.gamma) ng += p.gamma;
                    if (p.vega) nv += p.vega;
                    if (p.theta) nt += p.theta;
                });
            }
            updateValueWithAnimation('greek-delta', nd.toFixed(4));
            updateValueWithAnimation('greek-gamma', ng.toFixed(4));
            updateValueWithAnimation('greek-vega', nv.toFixed(4));
            updateValueWithAnimation('greek-theta', nt.toFixed(4));
        }

        // 5. Orders
        let resOrders = await fetch('/ares/orders');
        let ordersData = await resOrders.json();
        if (!ordersData.error && Array.isArray(ordersData)) {
            // Add time property for sorting
            const mappedOrders = ordersData.map(o => ({...o, time: new Date().getTime()}));
            if (gridOptions.api) {
                gridOptions.api.setRowData(mappedOrders);
            }
        }

        // 6. Logs
        let resLogs = await fetch('/ares/logs');
        let logsData = await resLogs.json();
        if (!logsData.error && logsData.logs) {
            let logBody = document.getElementById('logs-body');
            let filterTxt = document.getElementById('log-filter').value.toLowerCase();
            logBody.innerHTML = '';
            for (let log of logsData.logs) {
                if (filterTxt && !log.toLowerCase().includes(filterTxt)) continue;
                let div = document.createElement('div');
                div.className = 'log-line';
                if (log.includes('ERROR') || log.includes('CRITICAL')) div.classList.add('log-error');
                if (log.includes('WARNING')) div.classList.add('log-warn');
                div.innerText = log;
                logBody.appendChild(div);
            }
            if (autoScroll) {
                logBody.scrollTop = logBody.scrollHeight;
            }
        }

    } catch (e) {
        console.error("Dashboard polling error", e);
    }
}

// Start loop
setInterval(fetchAresData, 1000);
fetchAresData();

// Utility Functions
function copyLogs() {
    let text = document.getElementById('logs-body').innerText;
    navigator.clipboard.writeText(text);
}
function downloadLogs() {
    let text = document.getElementById('logs-body').innerText;
    let blob = new Blob([text], { type: 'text/plain' });
    let url = window.URL.createObjectURL(blob);
    let a = document.createElement('a');
    a.href = url;
    a.download = 'ares_live_logs.txt';
    a.click();
}
