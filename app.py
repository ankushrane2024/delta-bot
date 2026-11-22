from flask import Flask, render_template, request, jsonify, send_from_directory
from bot_core import bot_instance
import os, threading, time, datetime

# ─── FORWARD TRADER ──────────────────────────────────────────────────────────
try:
    from forward_trader import forward_trader as _ft
except Exception as _ft_err:
    _ft = None
    print(f"[WARN] ForwardTrader not loaded: {_ft_err}")

from werkzeug.exceptions import HTTPException

app = Flask(__name__, template_folder='.')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Global Error Handler to ensure all errors return JSON
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    import traceback
    print(f"[GLOBAL ERROR] {traceback.format_exc()}")
    return jsonify({"status": "error", "message": str(e), "type": str(type(e))}), 500

# ─── KEEP-ALIVE PINGER ────────────────────────────────────────────────────────
def keep_alive_pinger():
    time.sleep(60)
    import requests
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if (not url or url == 'http://localhost:5000') and os.environ.get('RENDER') == 'true':
        url = 'https://delta-btc-options-bot.onrender.com'
    if not url:
        url = 'http://localhost:5000'
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

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

@app.route('/ping')
def ping():
    return "OK", 200, {'Content-Type': 'text/plain'}

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
        'is_connected': bot_instance.is_connected,
        'last_heartbeat': bot_instance.last_heartbeat,
        'has_paper_pos': bool(paper_pos['call'] or paper_pos['put']),
        'has_live_pos':  bool(live_pos['call'] or live_pos['put']),
        'paper_positions': paper_pos,
        'live_positions':  live_pos
    })

@app.route('/api/connect', methods=['POST'])
def connect_api():
    data = request.get_json(silent=True) or {}
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

@app.route('/api/audit_metrics')
def get_audit_metrics():
    from audit_manager import audit_system
    return jsonify(audit_system.get_dashboard_metrics())

# Global PSCE Instance for API
from psce import PremiumSellingConditionsEngine
from api_client import DeltaIndiaClient
from dvol_provider import DVOLProvider
_psce_instance = None
_dvol_provider = None

@app.route('/api/premium_conditions')
def get_premium_conditions():
    try:
        global _psce_instance, _dvol_provider
        if not _psce_instance:
            _dvol_provider = DVOLProvider()
            _dvol_provider.start()
            _psce_instance = PremiumSellingConditionsEngine(DeltaIndiaClient(), _dvol_provider)
            
        return jsonify(_psce_instance.evaluate_conditions(mode="MONITOR"))
    except Exception as e:
        import traceback
        traceback.print_exc()
    return jsonify({
        "status": "error",
        "trade_allowed": False,
        "zone": "RED",
        "decision": "DATA UNAVAILABLE",
        "reasons": ["API Error: Could not reach PSCE Engine."]
    })

@app.route('/api/start', methods=['POST'])
def start_bot():
    data    = request.get_json() or {}
    ok, msg = bot_instance.start(data)
    return jsonify({'status': 'success' if ok else 'error', 'message': msg})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    print("[API] Received stop request.")
    try:
        data = request.get_json(silent=True) or {}
        mode = data.get('mode', 'PAPER').upper()
        print(f"[API] Stopping engine for mode: {mode}")
        bot_instance.stop(mode)
        return jsonify({'status': 'success', 'message': f'{mode} engine stopped.'})
    except Exception as e:
        import traceback
        print(f"[STOP ERROR] {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/execute', methods=['POST'])
def execute():
    data = request.get_json() or {}
    mode = data.get('mode', bot_instance.active_mode or 'PAPER').upper()
    if not bot_instance.state[mode]['running']:
        return jsonify({'status': 'error', 'message': f'Engine not running for {mode}. Start it first.'})
    bot_instance.trigger_execution(mode)
    return jsonify({'status': 'success', 'message': f'Execution triggered for {mode}!'})

@app.route('/api/clear', methods=['POST'])
def clear_positions():
    data = request.get_json() or {}
    mode = data.get('mode', 'PAPER').upper()
    bot_instance.clear_positions(mode)
    return jsonify({'status': 'success', 'message': f'{mode} positions cleared.'})


# ─── STRATEGY CONFIG (Balance BTC Midnight Strangle) ─────────────────────────
STRATEGY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'strategy_config.json')

def _load_strategy_config():
    defaults = {
        'call_straddle_mult': 1.6,
        'put_straddle_mult': 2.3,
        'leg_sl_pct': 100.0,
        'sl_reentry_enabled': True,
        'sl_reentry_max': 1,
        'overall_sl_enabled': False,
        'overall_sl_value': 10.0,
        'overall_target_enabled': False,
        'overall_target_value': 0.0,
        'trailing_enabled': False,
        'trail_if_profit': 11.0,
        'trail_lock_profit': 1.0,
        'trail_increase_by': 5.0,
        'trail_profit_by': 5.0,
        'entry_time': '22:30',
        'exit_time': '17:00',
        'total_lots': 1000,
    }
    try:
        if os.path.exists(STRATEGY_CONFIG_FILE):
            import json
            with open(STRATEGY_CONFIG_FILE) as f:
                saved = json.load(f)
            defaults.update(saved)
    except Exception as e:
        print(f"[CONFIG] Load error: {e}")
    return defaults

def _save_strategy_config(cfg):
    import json
    try:
        # Cross-sync leg1, leg2, overall and top-level fields so they never diverge
        leg1 = cfg.get('leg1', {})
        leg2 = cfg.get('leg2', {})
        overall = cfg.get('overall', {})

        if 'strike_multiplier' in leg1 and leg1['strike_multiplier']:
            cfg['call_straddle_mult'] = float(leg1['strike_multiplier'])
        elif 'call_straddle_mult' in cfg and cfg['call_straddle_mult']:
            leg1['strike_multiplier'] = float(cfg['call_straddle_mult'])

        if 'strike_multiplier' in leg2 and leg2['strike_multiplier']:
            cfg['put_straddle_mult'] = float(leg2['strike_multiplier'])
        elif 'put_straddle_mult' in cfg and cfg['put_straddle_mult']:
            leg2['strike_multiplier'] = float(cfg['put_straddle_mult'])

        if 'stop_loss_value' in leg1 and leg1['stop_loss_value'] is not None:
            cfg['leg_sl_pct'] = float(leg1['stop_loss_value'])
        elif 'leg_sl_pct' in cfg and cfg['leg_sl_pct'] is not None:
            leg1['stop_loss_value'] = float(cfg['leg_sl_pct'])

        if 'lots' in leg1 and leg1['lots']:
            cfg['total_lots'] = int(leg1['lots']) * 2
        elif 'total_lots' in cfg and cfg['total_lots']:
            leg1['lots'] = int(cfg['total_lots']) // 2
            leg2['lots'] = int(cfg['total_lots']) // 2

        if 'trail_if_profit' in overall:
            cfg['trail_if_profit'] = float(overall['trail_if_profit'])
        if 'trail_lock_profit' in overall:
            cfg['trail_lock_profit'] = float(overall['trail_lock_profit'])
        if 'trail_increase_by' in overall:
            cfg['trail_increase_by'] = float(overall['trail_increase_by'])
        if 'trail_profit_by' in overall:
            cfg['trail_profit_by'] = float(overall['trail_profit_by'])

        with open(STRATEGY_CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)

        # Push values into live config module
        import config as _cfg
        _cfg.CALL_STRADDLE_MULT   = float(cfg.get('call_straddle_mult', 1.6))
        _cfg.PUT_STRADDLE_MULT    = float(cfg.get('put_straddle_mult', 2.3))
        _cfg.LEG_SL_PCT           = float(cfg.get('leg_sl_pct', 100.0))
        _cfg.SL_PERCENT           = float(cfg.get('leg_sl_pct', 100.0)) / 100.0
        _cfg.SL_REENTRY_ENABLED   = bool(cfg.get('sl_reentry_enabled', leg1.get('reentry_sl_on', True)))
        _cfg.SL_REENTRY_MAX_COUNT = int(cfg.get('sl_reentry_max', leg1.get('reentry_sl_count', 1)))
        _cfg.TRAILING_ENABLED     = bool(cfg.get('trailing_enabled', overall.get('trailing_on', False)))
        _cfg.TRAIL_IF_PROFIT      = float(cfg.get('trail_if_profit', 11.0))
        _cfg.TRAIL_LOCK_PROFIT    = float(cfg.get('trail_lock_profit', 1.0))
        _cfg.TRAIL_INCREASE_BY    = float(cfg.get('trail_increase_by', 5.0))
        _cfg.TRAIL_PROFIT_BY      = float(cfg.get('trail_profit_by', 5.0))
        _cfg.TRAILING_CONFIRM_THRESHOLD = float(cfg.get('trail_if_profit', 11.0)) / 100.0
        _cfg.DYNAMIC_TRAIL_GAP    = float(cfg.get('trail_profit_by', 5.0)) / 100.0

        if _ft:
            try:
                _ft.reload_config()
            except Exception as _rerr:
                print(f"[WARN] ForwardTrader reload error: {_rerr}")

        return True
    except Exception as e:
        print(f"[CONFIG] Save error: {e}")
        return False

@app.route('/api/strategy_config', methods=['GET'])
def get_strategy_config():
    return jsonify(_load_strategy_config())

@app.route('/api/strategy_config', methods=['POST'])
def save_strategy_config():
    data = request.get_json(silent=True) or {}
    current = _load_strategy_config()
    current.update(data)
    ok = _save_strategy_config(current)
    rules = {}
    if _ft:
        try:
            _ft.reload_config()
            rules = _ft.status().get('rules', {})
        except Exception as _rerr:
            print(f"[WARN] ForwardTrader reload error: {_rerr}")
    return jsonify({'success': ok, 'config': current, 'rules': rules})

# ─── LOT SIZE ─────────────────────────────────────────────────────────────────
LOT_SIZE_FILE = os.path.join(os.path.dirname(__file__), 'lot_size.json')

@app.route('/api/get_lot_size')
def get_lot_size():
    import json
    try:
        if os.path.exists(LOT_SIZE_FILE):
            with open(LOT_SIZE_FILE) as f:
                data = json.load(f)
            total = int(data.get('total_lots', 1000))
        else:
            total = 1000
        return jsonify({'total_lots': total, 'per_leg': total // 2})
    except Exception as e:
        return jsonify({'total_lots': 1000, 'per_leg': 500, 'error': str(e)})

@app.route('/api/save_lot_size', methods=['POST'])
def save_lot_size():
    import json
    data = request.get_json(silent=True) or {}
    total = int(data.get('total_lots', 1000))
    live_lots = int(data.get('live_lots', 1))
    live_mode = bool(data.get('live_mode', False))
    try:
        payload = {'total_lots': total, 'per_leg': total // 2,
                   'live_lots': live_lots, 'live_mode': live_mode}
        with open(LOT_SIZE_FILE, 'w') as f:
            json.dump(payload, f, indent=2)
        return jsonify({'success': True, 'total_lots': total, 'per_leg': total // 2})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ─── ALGOTEST BACKTEST RUNNER ─────────────────────────────────────────────────
@app.route('/api/run_backtest', methods=['GET', 'POST'])
def run_backtest_api():
    try:
        data = request.get_json(silent=True) or request.args.to_dict() or {}
        from algotest_backtester import AlgoTestBacktester

        cfg = _load_strategy_config()
        start_date = data.get('start_date') or cfg.get('backtest', {}).get('start_date', '2025-01-21')
        end_date   = data.get('end_date')   or cfg.get('backtest', {}).get('end_date',   '2026-11-21')
        call_mult  = float(data.get('call_mult') or cfg.get('call_straddle_mult', 1.6))
        put_mult   = float(data.get('put_mult')  or cfg.get('put_straddle_mult', 2.3))
        leg_sl     = float(data.get('leg_sl_pct') or cfg.get('leg_sl_pct', 100.0))
        reentry_max = int(data.get('reentry_max') or cfg.get('sl_reentry_max', 1))
        lots       = int(data.get('lots') or (cfg.get('total_lots', 1000) // 2))

        bt = AlgoTestBacktester(
            start_date=start_date,
            end_date=end_date,
            call_mult=call_mult,
            put_mult=put_mult,
            leg_sl_pct=leg_sl,
            sl_reentry_max=reentry_max,
            lots_per_leg=lots
        )
        summary = bt.run()
        # Return summary plus last 50 individual trades
        recent_trades = bt.trades[-50:] if bt.trades else []
        return jsonify({
            'success': True,
            'summary': summary,
            'recent_trades': recent_trades,
            'equity_curve': bt.equity_curve[-100:] if bt.equity_curve else []
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ─── FORWARD TRADER ROUTES ───────────────────────────────────────────────────
@app.route('/api/forward_trader/status')
def ft_status():
    if not _ft:
        return jsonify({'error': 'ForwardTrader not loaded'}), 503
    return jsonify(_ft.status())

@app.route('/api/forward_trader/start', methods=['POST'])
def ft_start():
    if not _ft:
        return jsonify({'success': False, 'error': 'ForwardTrader not loaded'}), 503
    _ft.start()
    return jsonify({'success': True, 'message': 'Forward Trader started (Mon–Fri, 22:30 IST)'})

@app.route('/api/forward_trader/stop', methods=['POST'])
def ft_stop():
    if not _ft:
        return jsonify({'success': False, 'error': 'ForwardTrader not loaded'}), 503
    _ft.stop()
    return jsonify({'success': True, 'message': 'Forward Trader stopped'})

@app.route('/api/forward_trader/force_entry', methods=['POST'])
def ft_force_entry():
    if not _ft:
        return jsonify({'success': False, 'error': 'ForwardTrader not loaded'}), 503
    ok = _ft.force_enter_now()
    return jsonify({'success': ok, 'message': 'Force entry executed' if ok else 'Force entry failed (Trade already active or market closed)'})

@app.route('/api/forward_trader/manual_off', methods=['POST'])
def ft_manual_off():
    if not _ft:
        return jsonify({'success': False, 'error': 'ForwardTrader not loaded'}), 503
    ok, msg = _ft.manual_squareoff()
    return jsonify({'success': ok, 'message': msg})

@app.route('/api/forward_trader/records')
def ft_records():
    if not _ft:
        return jsonify({'error': 'ForwardTrader not loaded'}), 503
    return jsonify({
        'trades': _ft.recorder.get_all_trades(),
        'summary': _ft.recorder.get_summary()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=port, threaded=True)
