from flask import Flask, render_template, request, jsonify
from bot_core import bot_instance
import os
import threading
import time
import requests
import datetime

app = Flask(__name__, template_folder='.')

# ─── AUTO-START ENGINE IN PAPER MODE ON SERVER BOOT ───────────────────────────
def auto_start_paper_engine():
    """Auto-starts paper trading engine when the server boots up.
    This ensures the 8 AM IST scheduler runs even after Render restarts."""
    time.sleep(5)  # Give Flask a moment to fully start
    if not bot_instance.running:
        print("[BOOT] Auto-starting PAPER trading engine...")
        bot_instance.start({
            'mode': 'PAPER',
            'api_key': '',
            'api_secret': '',
            'target_premium': 100.0,
            'allocation_pct': 50.0,
            'call_stop_loss': 100.0,
            'call_take_profit': 95.0,
            'put_stop_loss': 100.0,
            'put_take_profit': 95.0,
        })
        print("[BOOT] PAPER engine started. Scheduled for 08:00 IST daily.")

# ─── KEEP-ALIVE SELF-PINGER ───────────────────────────────────────────────────
def keep_alive_pinger():
    """Pings this server's own /health endpoint every 10 minutes.
    Prevents Render free tier from spinning down and killing the scheduler."""
    time.sleep(30)  # Wait for server to fully start
    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    while True:
        try:
            requests.get(f"{render_url}/health", timeout=10)
            print(f"[KEEPALIVE] Pinged {render_url}/health at {datetime.datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[KEEPALIVE] Ping failed: {e}")
        time.sleep(600)  # Every 10 minutes

# Start background threads on boot (only once in production, not during reload)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':  # Prevents double-start in dev mode
    threading.Thread(target=auto_start_paper_engine, daemon=True).start()
    threading.Thread(target=keep_alive_pinger, daemon=True).start()

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Keep-alive endpoint. Returns engine status."""
    return jsonify({
        'status': 'alive',
        'engine_running': bot_instance.running,
        'mode': bot_instance.active_mode,
        'btc_price': bot_instance.current_btc_price,
        'time_ist': (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d %H:%M:%S IST')
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    mode = request.args.get('mode', 'PAPER')
    return jsonify({
        'running': bot_instance.running,
        'running_mode': bot_instance.active_mode if bot_instance.running else None,
        'logs': bot_instance.get_logs(mode)
    })

@app.route('/api/state', methods=['GET'])
def get_state():
    mode = request.args.get('mode', 'PAPER')
    return jsonify(bot_instance.get_state(mode))

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json
    success = bot_instance.start(data)
    if success:
        return jsonify({'status': 'success', 'message': 'Engine initialized.'})
    return jsonify({'status': 'error', 'message': 'Engine is already running.'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    success = bot_instance.stop()
    if success:
        return jsonify({'status': 'success', 'message': 'Engine halted.'})
    return jsonify({'status': 'error', 'message': 'Engine is not running.'})

@app.route('/api/execute', methods=['POST'])
def trigger_execution():
    if not bot_instance.running:
        return jsonify({'status': 'error', 'message': 'Please Initialize Engine first.'})
    bot_instance.trigger_execution()
    return jsonify({'status': 'success', 'message': 'Execution sweep triggered.'})

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
