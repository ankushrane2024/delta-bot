from flask import Flask, render_template, jsonify, request
from logger import app_logger
import os

app = Flask(__name__, template_folder='templates')

# Global reference to the engine
bot_engine = None

def init_web_server(engine):
    global bot_engine
    bot_engine = engine

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/ping')
def ping():
    # Lightweight endpoint for Keep-Alive pinger and UptimeRobot
    return jsonify({'status': 'OK', 'message': 'Keep-alive ping successful.'})

@app.route('/api/status')
def get_status():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    # Read last 20 lines of the trading_bot.log
    logs = []
    try:
        with open('trading_bot.log', 'r') as f:
            lines = f.readlines()
            logs = [line.strip() for line in lines[-20:]]
    except Exception:
        logs = ["Log file not found."]

    # Format active positions
    positions = []
    for sym, data in bot_engine.execution.active_positions.items():
        positions.append({
            'symbol': sym,
            'side': data.get('side', ''),
            'size': data.get('size', 0),
            'entry_price': data.get('entry_price', 0)
        })

    return jsonify({
        'is_running': bot_engine.is_running,
        'mode': getattr(bot_engine.execution, 'mode', 'UNKNOWN'),
        'equity': round(bot_engine.risk_manager.current_equity, 2),
        'daily_loss_hits': bot_engine.daily_loss_hits,
        'positions': positions,
        'logs': logs,
        'performance': bot_engine.performance_tracker.get_metrics(bot_engine.risk_manager.current_equity),
        'rule_report': bot_engine.latest_rule_report,
        'schedule_info': bot_engine.get_schedule_info(),
        'regime_filter_enabled': bot_engine.market_regime_filter_enabled,
        'current_market_regime': bot_engine.current_market_regime,
        'current_adx_value': bot_engine.current_adx_value,
        'paper_lot_multiplier': getattr(bot_engine, 'paper_lot_multiplier', 1.0),
        'api_connected': bot_engine.api_client.ws_connected if bot_engine.api_client else False,
        'current_iv': getattr(bot_engine, 'current_iv', 0.0),
        'avg_7d_iv': getattr(bot_engine, 'avg_7d_iv', 0.0),
        'iv_status': getattr(bot_engine, 'iv_status', 'Normal'),
        'today_skip_reason': getattr(bot_engine, 'today_skip_reason', None)
    })

@app.route('/api/start', methods=['POST'])
def start_bot():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
    
    bot_engine.is_running = True
    app_logger.info("Web: Engine started via dashboard.")
    return jsonify({'status': 'success'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.is_running = False
    app_logger.warning("Web: Engine stopped via dashboard.")
    return jsonify({'status': 'success'})

@app.route('/api/emergency_close', methods=['POST'])
def emergency_close():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.execution.close_all(reason="Emergency Manual Square-Off")
    bot_engine.today_trade_status = "Emergency Manual Closed"
    bot_engine.today_skip_reason = "User Triggered Emergency"
    
    from notifier import notify_error
    notify_error("🚨 USER EMERGENCY 🚨\nAll positions squared off manually via Dashboard.")
    
    return jsonify({'status': 'success'})

@app.route('/api/toggle_regime', methods=['POST'])
def toggle_regime():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.market_regime_filter_enabled = not bot_engine.market_regime_filter_enabled
    state = "ENABLED" if bot_engine.market_regime_filter_enabled else "DISABLED"
    app_logger.info(f"Web: Market Regime Filter {state}")
    
    return jsonify({'status': 'success', 'enabled': bot_engine.market_regime_filter_enabled})
    
@app.route('/api/test_order', methods=['POST'])
def test_order():
    try:
        if not bot_engine:
            app_logger.error("Web [test_order]: Engine not initialized")
            return jsonify({'success': False, 'error': 'Engine not initialized'}), 200

        mode = getattr(bot_engine.execution, 'mode', 'PAPER')
        if mode != 'PAPER':
            app_logger.warning(f"Web [test_order]: Blocked — mode is {mode}, not PAPER")
            return jsonify({'success': False, 'error': 'Test Order is only available in PAPER mode.'}), 200

        app_logger.info("Web [test_order]: Running test order via bot_engine...")
        success, message = bot_engine.run_test_order()

        if success:
            app_logger.info(f"Web [test_order]: SUCCESS — {message}")
            return jsonify({'success': True, 'message': message}), 200
        else:
            app_logger.error(f"Web [test_order]: FAILED — {message}")
            return jsonify({'success': False, 'error': message}), 200

    except AttributeError as e:
        msg = f"run_test_order() not found on engine: {e}"
        app_logger.error(f"Web [test_order]: AttributeError — {msg}")
        return jsonify({'success': False, 'error': msg}), 200
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app_logger.error(f"Web [test_order]: Unhandled exception — {e}\n{tb}")
        return jsonify({'success': False, 'error': str(e)}), 200

@app.route('/api/manual_order', methods=['POST'])
def manual_order():
    try:
        if not bot_engine:
            app_logger.error("Web [manual_order]: Engine not initialized")
            return jsonify({'success': False, 'error': 'Engine not initialized'}), 200

        app_logger.info("Web [manual_order]: Manual strangle entry cycle triggered via dashboard.")
        
        # Temporarily bypass the "1 trade per day limit" just for manual force execution
        bot_engine.trades_taken_today = 0
        
        # Trigger the entry cycle asynchronously in a background thread
        import threading
        threading.Thread(target=bot_engine.run_entry_cycle, daemon=True).start()
        
        return jsonify({'status': 'success', 'message': 'Manual strangle entry cycle triggered successfully!'}), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app_logger.error(f"Web [manual_order]: Unhandled exception — {e}\n{tb}")
        return jsonify({'status': 'error', 'error': str(e)}), 200

@app.route('/api/news', methods=['GET'])
def get_news():
    """Fetch this week's high/medium impact USD & global events from ForexFactory calendar."""
    import requests as req
    from datetime import datetime, timezone, timedelta
    
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = req.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return jsonify([])
        
        all_events = r.json()
        now_utc = datetime.now(timezone.utc)
        week_end = now_utc + timedelta(days=7)
        
        filtered = []
        for e in all_events:
            impact = e.get('impact', '')
            country = e.get('country', '')
            
            # Only show High/Medium impact events for BTC-relevant currencies
            if impact not in ('High', 'Medium'):
                continue
            if country not in ('USD', 'EUR', 'GBP', 'JPY', 'CNY', 'BTC'):
                continue
            
            # Parse event date
            raw_date = e.get('date', '')
            try:
                dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
                if dt < now_utc or dt > week_end:
                    continue
                date_str = dt.strftime('%b %d  %H:%M UTC')
            except Exception:
                date_str = raw_date
            
            filtered.append({
                'date': date_str,
                'title': e.get('title', 'Unknown Event'),
                'country': country,
                'impact': impact,
                'previous': e.get('previous', ''),
                'forecast': e.get('forecast', '')
            })
        
        # Sort by date string (they come chronologically from the feed)
        return jsonify(filtered)
        
    except Exception as ex:
        app_logger.error(f"News API error: {ex}")
        return jsonify([])

@app.route('/reports/<path:filename>')
def serve_report(filename):
    from flask import send_from_directory
    return send_from_directory('reports', filename)

@app.route('/api/reports')
def list_reports():
    import json
    if os.path.exists('daily_reports.json'):
        try:
            with open('daily_reports.json', 'r') as f:
                return jsonify(json.load(f))
        except:
            return jsonify({})
    return jsonify({})

@app.route('/api/generate_report', methods=['POST'])
def generate_report_now():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
    
    success, message = bot_engine.generate_actual_report()
    if success:
        return jsonify({'status': 'success', 'message': message})
    else:
        return jsonify({'status': 'error', 'message': message}), 500

# ─── Lot Size Settings Endpoints ──────────────────────────────────────────────

LOT_SIZE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lot_size.json')

def _read_lot_size_file():
    """Read current saved lot size. Falls back to MANUAL_TOTAL_LOTS from config."""
    import json
    try:
        from config import MANUAL_TOTAL_LOTS as cfg_lots
        if os.path.exists(LOT_SIZE_FILE):
            with open(LOT_SIZE_FILE, 'r') as f:
                data = json.load(f)
            return int(data.get('total_lots', cfg_lots))
        return int(cfg_lots)
    except Exception:
        return 200  # hard fallback

@app.route('/api/get_lot_size', methods=['GET'])
def get_lot_size():
    """Return the currently active saved lot size."""
    total = _read_lot_size_file()
    return jsonify({'total_lots': total, 'per_leg': int(total / 2)})

@app.route('/api/save_lot_size', methods=['POST'])
def save_lot_size():
    """Save a new lot size to lot_size.json (persists across restarts)."""
    import json
    try:
        data = request.get_json(force=True)
        if not data or 'total_lots' not in data:
            return jsonify({'success': False, 'error': 'Missing total_lots field'}), 400

        new_lots = int(data['total_lots'])
        if new_lots < 1:
            return jsonify({'success': False, 'error': 'Lot size must be at least 1'}), 400
        if new_lots > 10000:
            return jsonify({'success': False, 'error': 'Lot size too large (max 10 000)'}), 400

        payload = {'total_lots': new_lots}
        with open(LOT_SIZE_FILE, 'w') as f:
            json.dump(payload, f)

        app_logger.info(f"Web [save_lot_size]: Saved new lot size → {new_lots} total ({new_lots // 2} per leg)")
        return jsonify({'success': True, 'total_lots': new_lots, 'per_leg': new_lots // 2})

    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid value – must be a whole number'}), 400
    except Exception as e:
        app_logger.error(f"Web [save_lot_size]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

