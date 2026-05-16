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
        'current_adx_value': bot_engine.current_adx_value
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
