import sys
with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

live_handlers = '''
// ================== LIVE HANDLERS ==================

async function liveSendCommand(action) {
    try {
        const res = await fetch('/api/live/' + action, { method: 'POST' });
        if (res.ok) {
            fetchLiveStatus();
        } else {
            const errData = await res.json();
            alert('Command failed: ' + (errData.error || 'Unknown error'));
        }
    } catch (e) {
        console.error(action + ' fail', e);
    }
}

async function runLiveManualOrder() {
    console.log("Dashboard: runLiveManualOrder() triggered");
    const btn = document.getElementById('btn-manual-order');
    if (btn) btn.disabled = true;
    
    if (!confirm("Are you sure you want to FORCE trigger the LIVE strangle entry cycle immediately?")) {
        if (btn) btn.disabled = false;
        return;
    }
    
    try {
        const response = await fetch('/api/live/manual_order', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'success') {
            alert("Success!\n" + (result.message || "Manual strangle entry cycle triggered successfully!"));
        } else {
            alert("Failed:\n" + (result.error || result.message || "Unknown error"));
        }
    } catch (error) {
        console.error("Dashboard: Manual order fetch error:", error);
        alert("Network Error: " + error.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function liveEmergencyClose() {
    if (confirm("ARE YOU SURE YOU WANT TO EMERGENCY CLOSE ALL LIVE POSITIONS?")) {
        try {
            const res = await fetch('/api/live/emergency_close', { method: 'POST' });
            if(res.ok) {
                alert("Emergency Square Off Successful! All live positions closed.");
                fetchLiveStatus();
            } else {
                const errData = await res.json();
                alert("Failed to emergency close: " + (errData.error || "Unknown error"));
            }
        } catch(e) { 
            console.error("Emergency fail", e); 
            alert("Network error: Could not reach server for emergency close.");
        }
    }
}

async function liveToggleRegimeFilter() {
    try {
        const res = await fetch('/api/live/toggle_regime', { method: 'POST' });
        if(res.ok) fetchLiveStatus();
    } catch(e) { console.error('Toggle fail', e); }
}

async function liveToggleSmartHedging() {
    try {
        const res = await fetch('/api/live/toggle_hedge', { method: 'POST' });
        if(res.ok) fetchLiveStatus();
    } catch(e) { console.error('Toggle fail', e); }
}

async function runLiveTestOrder() {
    alert("Test orders are not supported in LIVE mode.");
}

async function saveLiveLotSize() {
    const input = document.getElementById('live-manual-lot-size');
    if(!input) return;
    const val = parseFloat(input.value);
    if(isNaN(val) || val <= 0) {
        alert("Invalid lot multiplier.");
        return;
    }
    try {
        const res = await fetch('/api/live/set_lot_multiplier', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ multiplier: val })
        });
        if(res.ok) {
            alert('Live manual lot size updated to ' + val);
            fetchLiveStatus();
        } else {
            const data = await res.json();
            alert('Failed: ' + (data.error || 'Unknown error'));
        }
    } catch(e) { console.error(e); }
}
'''

if 'async function liveSendCommand' not in content:
    content = content.replace('// ================== LIVE MODE JS ==================', '// ================== LIVE MODE JS ==================\n' + live_handlers)
    with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
