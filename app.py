from flask import Flask, render_template, request, jsonify
from bot_core import bot_instance
import os, threading, time, datetime

app = Flask(__name__, template_folder='.')

# ─── KEEP-ALIVE PINGER ────────────────────────────────────────────────────────
def keep_alive_pinger():
    time.sleep(60)
    import requests
    url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    while True:
        try:
            requests.get(f"{url}/health", timeout=15)
            ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
            print(f"[KEEPALIVE] {ist.strftime('%H:%M IST')} — alive, engine={'ON' if bot_instance.running else 'OFF'}")
        except Exception as e:
            print(f"[KEEPALIVE] ping failed: {e}")
        time.sleep(600)

if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    threading.Thread(target=keep_alive_pinger, daemon=True).start()

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    return jsonify({
        'status':         'alive',
        'engine_running': bot_instance.running,
        'mode':           bot_instance.active_mode,
        'btc_price':      bot_instance.current_btc_price,
        'ist_time':       ist.strftime('%Y-%m-%d %H:%M:%S IST')
    })

@app.route('/api/status')
def get_status():
    mode = request.args.get('mode', 'PAPER').upper()
    s = bot_instance.get_state(mode)
    
    # Global position indicators
    paper_pos = bot_instance.state['PAPER']['positions']
    live_pos  = bot_instance.state['LIVE']['positions']
    
    return jsonify({
        'running':      s['running'],
        'running_mode': mode if s['running'] else None,
        'logs':         bot_instance.get_logs(mode),
        'has_paper_pos': bool(paper_pos['call'] or paper_pos['put']),
        'has_live_pos':  bool(live_pos['call'] or live_pos['put'])
    })

@app.route('/api/connect', methods=['POST'])
def connect_api():
    data = request.json
    ok, msg = bot_instance.test_live_connection(data.get('api_key'), data.get('api_secret'))
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/api/state')
def get_state():
    mode = request.args.get('mode', 'PAPER').upper()
    return jsonify(bot_instance.get_state(mode))

@app.route('/api/chain')
def get_chain():
    return jsonify(bot_instance.india_client.get_option_chain())

@app.route('/api/history')
def get_history():
    # Strip MARK: prefix — Delta India candles don't accept it
    symbol     = request.args.get('symbol', 'BTCUSD').replace('MARK:', '')
    resolution = request.args.get('resolution', '1h')
    data       = bot_instance.india_client.get_history(symbol, resolution)
    return jsonify(data)

@app.route('/myip')
def my_ip():
    import requests as req
    try:
        ip = req.get('https://api.ipify.org', timeout=10).text.strip()
        return jsonify({'render_outbound_ip': ip, 'whitelist_this_ip': ip})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/start', methods=['POST'])
def start_bot():
    data    = request.get_json() or {}
    ok, msg = bot_instance.start(data)
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    bot_instance.stop()
    return jsonify({'status': 'success', 'message': 'Engine stopped.'})

@app.route('/api/execute', methods=['POST'])
def execute():
    if not bot_instance.running:
        return jsonify({'status': 'error', 'message': 'Engine not running. Start it first.'})
    bot_instance.trigger_execution()
    return jsonify({'status': 'success', 'message': 'Execution triggered!'})

@app.route('/api/clear', methods=['POST'])
def clear_positions():
    data = request.get_json() or {}
    mode = data.get('mode', 'PAPER').upper()
    bot_instance.clear_positions(mode)
    return jsonify({'status': 'success', 'message': f'{mode} positions cleared.'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
