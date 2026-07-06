// ARES Mission Control V3 JS

let chartPortfolio, chartPnl, chartDelta, gaugeRisk;
const POLL_INTERVAL = 1000;

let timeData = [];
let portData = [];
let pnlData = [];
let deltaData = [];

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initCharts();
    pollData();
    setInterval(pollData, POLL_INTERVAL);
});

function initClock() {
    setInterval(() => {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { hour12: true }) + ' UTC';
        const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        document.getElementById('ft-time').innerText = timeStr;
        document.getElementById('ft-date').innerText = dateStr;
    }, 1000);
}

function initCharts() {
    const text = '#94A3B8';
    const gridColor = '#1E293B';

    // Shared chart options
    const baseOpt = {
        backgroundColor: 'transparent',
        tooltip: { trigger: 'axis', backgroundColor: '#11151C', borderColor: '#1E293B', textStyle: { color: '#F8FAFC' } },
        grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: [], axisLine: { lineStyle: { color: text } }, splitLine: { show: false } },
        yAxis: { type: 'value', axisLine: { lineStyle: { color: text } }, splitLine: { lineStyle: { color: gridColor } } },
    };

    chartPortfolio = echarts.init(document.getElementById('chart-portfolio'));
    chartPortfolio.setOption({
        ...baseOpt,
        series: [{
            name: 'Value', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00C853', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,200,83,0.3)' },
                    { offset: 1, color: 'rgba(0,200,83,0.0)' }
                ])
            },
            data: []
        }]
    });

    chartPnl = echarts.init(document.getElementById('chart-pnl'));
    chartPnl.setOption({
        ...baseOpt,
        series: [{
            name: 'PnL', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#B388FF', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(179,136,255,0.3)' },
                    { offset: 1, color: 'rgba(179,136,255,0.0)' }
                ])
            },
            data: []
        }]
    });

    chartDelta = echarts.init(document.getElementById('chart-delta'));
    chartDelta.setOption({
        ...baseOpt,
        series: [{
            name: 'Delta', type: 'line', smooth: true, symbol: 'none',
            lineStyle: { color: '#00E5FF', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(0,229,255,0.3)' },
                    { offset: 1, color: 'rgba(0,229,255,0.0)' }
                ])
            },
            data: []
        }]
    });

    gaugeRisk = echarts.init(document.getElementById('gauge-risk'));
    gaugeRisk.setOption({
        series: [{
            type: 'gauge', startAngle: 180, endAngle: 0, min: 0, max: 100,
            pointer: { show: true, length: '60%', width: 4 },
            progress: { show: true, overlap: false, roundCap: true, clip: false, itemStyle: { color: '#FFB300' } },
            axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(255,255,255,0.1)']] } },
            splitLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false },
            detail: { fontSize: 24, color: '#F8FAFC', offsetCenter: [0, '20%'], formatter: '{value}%' },
            data: [{ value: 0 }]
        }]
    });

    window.addEventListener('resize', () => {
        chartPortfolio.resize(); chartPnl.resize(); chartDelta.resize(); gaugeRisk.resize();
    });
}

async function pollData() {
    try {
        const [statusRes, ordersRes, logsRes, portfolioRes] = await Promise.all([
            fetch('/ares/status').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/orders').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/logs').then(r => r.ok ? r.json() : null).catch(() => null),
            fetch('/ares/portfolio').then(r => r.ok ? r.json() : null).catch(() => null)
        ]);
        
        if (statusRes && !statusRes.error) {
            updateHero(statusRes);
            updateAI(statusRes);
            updatePipeline(statusRes);
            updateSystem(statusRes);
            updateEvents(statusRes, logsRes);
            
            // Append to charts
            const now = new Date().toLocaleTimeString('en-US', {hour12: false});
            if (timeData.length > 60) timeData.shift();
            if (portData.length > 60) portData.shift();
            if (pnlData.length > 60) pnlData.shift();
            if (deltaData.length > 60) deltaData.shift();
            
            timeData.push(now);
            portData.push(statusRes.portfolio_value || 0);
            pnlData.push(statusRes.pnl || 0);
            deltaData.push(statusRes.total_delta || 0);
            
            chartPortfolio.setOption({ xAxis: { data: timeData }, series: [{ data: portData }] });
            chartPnl.setOption({ xAxis: { data: timeData }, series: [{ data: pnlData }] });
            chartDelta.setOption({ xAxis: { data: timeData }, series: [{ data: deltaData }] });
            
            // Risk Gauge
            const riskMap = { 'LOW': 28, 'MEDIUM': 55, 'HIGH': 85, 'CRITICAL': 95 };
            const riskScore = riskMap[(statusRes.current_risk || '').toUpperCase()] || 0;
            gaugeRisk.setOption({ series: [{ data: [{ value: riskScore }] }] });
        }
        
        if (ordersRes) updateOrders(ordersRes);
        if (portfolioRes) updatePositions(portfolioRes, statusRes);
        
    } catch (err) {
        console.error("Polling error:", err);
    }
}

function fmtUSD(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return '$' + Number(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function fmtNum(val) {
    if (val === undefined || val === null || val === 'N/A') return 'N/A';
    return Number(val).toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4});
}

function updateHero(data) {
    document.getElementById('h-btc').innerText = fmtUSD(data.btc_price);
    document.getElementById('h-port').innerText = fmtUSD(data.portfolio_value);
    
    const pnl = Number(data.pnl || 0);
    const pnlEl = document.getElementById('h-pnl');
    pnlEl.innerText = (pnl >= 0 ? '+' : '') + fmtUSD(pnl);
    pnlEl.className = 'hm-value ' + (pnl >= 0 ? 'green' : 'red');
    
    document.getElementById('h-delta').innerText = fmtNum(data.total_delta);
    
    const risk = (data.current_risk || 'LOW').toUpperCase();
    const rEl = document.getElementById('h-risk');
    let color = 'green';
    if (risk === 'MEDIUM') color = 'yellow';
    if (risk === 'HIGH' || risk === 'CRITICAL') color = 'red';
    rEl.innerHTML = `<span class="dot ${color}"></span> ${risk}`;
    
    if (data.pipeline_latency !== undefined) {
        document.getElementById('h-latency').innerText = (data.pipeline_latency * 1000).toFixed(0) + ' ms';
    }
    
    // Mode
    if (data.bot_mode) {
        document.getElementById('ft-mode').innerText = data.bot_mode;
    }
}

function updateAI(data) {
    const action = (data.active_hedge || 'NONE').toUpperCase();
    document.getElementById('ai-action').innerText = action === 'ACTIVE' ? 'BUY HEDGE' : 'HOLD';
    document.getElementById('ai-icon').innerText = action === 'ACTIVE' ? '↗' : '⊗';
    document.getElementById('ai-icon').style.borderColor = action === 'ACTIVE' ? '#00C853' : '#94A3B8';
    document.getElementById('ai-icon').style.color = action === 'ACTIVE' ? '#00C853' : '#94A3B8';
    
    document.getElementById('ai-conf').innerText = action === 'ACTIVE' ? '96%' : '—';
    document.getElementById('ai-bias').innerText = data.btc_price > 50000 ? 'BULLISH' : 'NEUTRAL';
    document.getElementById('ai-bias').style.color = data.btc_price > 50000 ? '#00C853' : '#F8FAFC';
}

const stages = ['tick', 'context', 'trend', 'regime', 'risk', 'decision', 'sizing', 'exec'];
function updatePipeline(data) {
    stages.forEach(s => {
        const el = document.getElementById(`pn-${s}`);
        if (el) el.className = 'pnode';
    });
    
    if (data.total_ticks > 0) {
        document.getElementById('pipe-status').innerText = 'PROCESSING';
        if (data.active_hedge === 'ACTIVE') {
            document.getElementById('pn-exec').className = 'pnode highlight';
        } else {
            document.getElementById('pn-decision').className = 'pnode highlight';
        }
    }
}

function updateSystem(data) {
    document.getElementById('pv-rest').innerText = data.exchange_status || 'N/A';
    document.getElementById('pv-ws').innerText = data.provider_health || 'N/A';
    document.getElementById('pv-eb').innerText = 'ONLINE';
    document.getElementById('pv-cb').innerText = data.health_status || 'UNKNOWN';
    
    document.getElementById('sys-cpu').style.width = (data.cpu || 0) + '%';
    document.getElementById('sys-cpu-v').innerText = (data.cpu || 0) + '%';
    
    document.getElementById('sys-mem').style.width = (data.ram || 0) + '%';
    document.getElementById('sys-mem-v').innerText = (data.ram || 0) + '%';
    
    const lat = data.pipeline_latency || 0;
    document.getElementById('sys-hb').innerText = lat.toFixed(3) + ' sec';
}

function updateOrders(orders) {
    const tbody = document.getElementById('orders-body');
    if (!orders || orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No orders yet</td></tr>';
        return;
    }
    
    let html = '';
    orders.slice(0, 5).forEach(o => {
        let sc = '#F8FAFC';
        const st = (o.state || '').toUpperCase();
        if (st.includes('FILLED')) sc = '#00C853';
        if (st.includes('PARTIAL')) sc = '#FFB300';
        if (st.includes('CANCEL') || st.includes('FAIL')) sc = '#FF5252';
        
        let sideC = o.side === 'BUY' ? '#00C853' : '#FF5252';
        
        const time = o.timestamp ? o.timestamp.split('T')[1]?.substring(0,8) || o.timestamp.substring(0,8) : 'N/A';
        
        html += `<tr>
            <td>${time}</td>
            <td>HEDGE</td>
            <td><strong style="color:${sideC}">${o.side}</strong></td>
            <td>${o.symbol}</td>
            <td>${o.quantity}</td>
            <td>${fmtUSD(o.price)}</td>
            <td style="color:${sc}; font-weight:bold">${o.state}</td>
            <td>N/A</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

function updatePositions(portRes, statusRes) {
    let positions = [];
    if (Array.isArray(portRes)) positions = portRes;
    else if (portRes.positions) positions = portRes.positions;
    
    document.getElementById('pos-count').innerText = positions.length;
    document.getElementById('pos-delta').innerText = fmtNum(statusRes.total_delta);
    
    // Rough estimate for mockup
    document.getElementById('pos-exposure').innerText = fmtUSD(positions.length * 50000 * 0.1); 
    document.getElementById('pos-margin').innerText = fmtUSD(statusRes.margin_used);
}

let eventsList = [];
function updateEvents(status, logs) {
    const now = new Date().toLocaleTimeString('en-US', {hour12: true});
    if (status.total_ticks > 0 && (eventsList.length === 0 || status.total_ticks % 10 === 0)) {
        eventsList.unshift({time: now, msg: `Pipeline processed tick #${status.total_ticks}`});
    }
    
    const el = document.getElementById('events-feed');
    el.innerHTML = eventsList.slice(0, 5).map(e => `
        <div class="ev-item">
            <span class="ev-time dot green" style="width:6px;height:6px;margin-right:8px;margin-top:4px"></span>
            <span class="ev-time">${e.time}</span>
            <span class="ev-msg">${e.msg}</span>
        </div>
    `).join('');
}
