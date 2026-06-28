import sys

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = 0
end_idx = 0
for i, line in enumerate(lines):
    if 'async function fetchStatus()' in line:
        start_idx = i
    if 'setInterval(fetchStatus, 4000);' in line:
        end_idx = i + 2 # include fetchStatus();

if start_idx == 0 or end_idx <= start_idx:
    print('Failed to find fetchStatus boundaries.')
    sys.exit(1)

js_content = ''.join(lines[start_idx:end_idx])

# Modify for LIVE
js_content = js_content.replace('fetchStatus', 'fetchLiveStatus')
js_content = js_content.replace('/api/status', '/api/live/status')
js_content = js_content.replace('document.getElementById(\'total-pnl\')', 'document.getElementById(\'live-total-pnl\')')

# generic replaces for element ids
replacements = [
    ('equity-val', 'live-equity-val'),
    ('mode-val', 'live-mode-val'),
    ('loss-hits-val', 'live-loss-hits-val'),
    ('lot-multiplier-val', 'live-lot-multiplier-val'),
    ('api-status-badge', 'live-api-status-badge'),
    ('next-day-paused-container', 'live-next-day-paused-container'),
    ('next-day-paused-banner', 'live-next-day-paused-banner'),
    ('dvol-badge', 'live-dvol-badge'),
    ('iv-badge', 'live-iv-badge'),
    ('market-regime-badge', 'live-market-regime-badge'),
    ('consecutive-losses-badge', 'live-consecutive-losses-badge'),
    ('call-sym', 'live-call-sym'),
    ('call-strike', 'live-call-strike'),
    ('call-entry', 'live-call-entry'),
    ('call-current', 'live-call-current'),
    ('call-pnl-usd', 'live-call-pnl-usd'),
    ('call-pnl-inr', 'live-call-pnl-inr'),
    ('call-pnl-pct', 'live-call-pnl-pct'),
    ('call-delta', 'live-call-delta'),
    ('call-gamma', 'live-call-gamma'),
    ('call-status', 'live-call-status'),
    ('put-sym', 'live-put-sym'),
    ('put-strike', 'live-put-strike'),
    ('put-entry', 'live-put-entry'),
    ('put-current', 'live-put-current'),
    ('put-pnl-usd', 'live-put-pnl-usd'),
    ('put-pnl-inr', 'live-put-pnl-inr'),
    ('put-pnl-pct', 'live-put-pnl-pct'),
    ('put-delta', 'live-put-delta'),
    ('put-gamma', 'live-put-gamma'),
    ('put-status', 'live-put-status'),
    ('total-pnl-pct', 'live-total-pnl-pct'),
    ('total-pnl-bar', 'live-total-pnl-bar'),
    ('hedge-status-badge', 'live-hedge-status-badge'),
    ('hedge-size', 'live-hedge-size'),
    ('hedge-pnl', 'live-hedge-pnl'),
    ('rules-monitor-content', 'live-rules-monitor-content')
]

for old, new in replacements:
    js_content = js_content.replace(f"'{old}'", f"'{new}'")
    js_content = js_content.replace(f'"{old}"', f'"{new}"')

js_content = js_content.replace('/api/test_order', '/api/live/test_order')
js_content = js_content.replace('/api/manual_order', '/api/live/manual_order')
js_content = js_content.replace('/api/emergency_close', '/api/live/emergency_close')
js_content = js_content.replace('/api/toggle_regime', '/api/live/toggle_regime')
js_content = js_content.replace('/api/toggle_hedge', '/api/live/toggle_hedge')

js_content = js_content.replace('runTestOrder', 'runLiveTestOrder')
js_content = js_content.replace('runManualOrder', 'runLiveManualOrder')
js_content = js_content.replace('emergencyClose', 'liveEmergencyClose')
js_content = js_content.replace('toggleRegimeFilter', 'liveToggleRegimeFilter')
js_content = js_content.replace('toggleSmartHedging', 'liveToggleSmartHedging')
js_content = js_content.replace('fetchPnl', 'fetchLivePnl')

# We should make polling only if the livemode tab is active to save resources, but for now we can just let it run or add a condition.
# A small hack to the setInterval: 
# setInterval(() => { if (document.getElementById('tab-livemode').classList.contains('active')) fetchLiveStatus(); }, 4000);

lines.insert(end_idx, "\n// ================== LIVE MODE JS ==================\n" + js_content)

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Live JS duplicated successfully')
