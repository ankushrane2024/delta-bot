from flask import Flask, render_template, request, jsonify
from bot_core import bot_instance
import os
import threading
import time
import datetime

app = Flask(__name__, template_folder='.')

# ─── KEEP-ALIVE PINGER (prevents Render free tier spin-down) ─────────────────
def keep_alive_pinger():
    """Pings /health every 10 min to prevent Render from sleeping.
    Also auto-restarts engine if it dies unexpectedly."""
    time.sleep(45)
    import requests
    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    while True:
        try:
            requests.get(f"{render_url}/health", timeout=15)
            ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
            print(f"[KEEPALIVE] {ist.strftime('%H:%M IST')} — server alive, engine={'ON' if bot_instance.running else 'OFF'}")
        except Exception as e:
            print(f"[KEEPALIVE] ping failed: {e}")
        time.sleep(600)

# Start keep-alive only in production (not Flask dev reloader child)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    threading.Thread(target=keep_alive_pinger, daemon=True).start()

# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    return jsonify({
        'status': 'alive',
        'engine_running': bot_instance.running,
        'mode': bot_instance.active_mode,
        'btc_price': bot_instance.current_btc_price,
        'ist_time': ist.strftime('%Y-%m-%d %H:%M:%S IST')
    })

@app.route('/api/status')
def get_status():
    mode = request.args.get('mode', 'PAPER')
    return jsonify({
        'running': bot_instance.running,
        'running_mode': bot_instance.active_mode if bot_instance.running else None,
        'logs': bot_instance.get_logs(mode)
    })

@app.route('/api/state')
def get_state():
    mode = request.args.get('mode', 'PAPER')
    return jsonify(bot_instance.get_state(mode))

@app.route('/api/history')
def get_history():
    symbol = request.args.get('symbol', 'MARK:BTCUSD')
    resolution = request.args.get('resolution', '1h')
    return jsonify(bot_instance.india_client.get_history(symbol, resolution))

@app.route('/myip')
def my_ip():
    """Returns the outbound IP of this Render server — used for Delta Exchange IP whitelisting."""
    import requests as req
    try:
        ip = req.get('https://api.ipify.org', timeout=10).text.strip()
        return jsonify({'render_outbound_ip': ip, 'whitelist_this_ip': ip})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.get_json() or {}
    success, message = bot_instance.start(data)
    status = 'success' if success else 'error'
    return jsonify({'status': status, 'message': message})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    bot_instance.stop()
    return jsonify({'status': 'success', 'message': 'Engine stopped.'})

@app.route('/api/execute', methods=['POST'])
def execute():
    if not bot_instance.running:
        return jsonify({'status': 'error', 'message': 'Engine not running. Start it first.'})
    bot_instance.trigger_execution()
    return jsonify({'status': 'success', 'message': 'Execution sweep started.'})

@app.route('/api/clear', methods=['POST'])
def clear_positions():
    data = request.get_json() or {}
    mode = data.get('mode', 'PAPER')
    bot_instance.clear_positions(mode)
    return jsonify({'status': 'success', 'message': f'{mode} positions cleared.'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
