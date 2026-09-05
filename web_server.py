from flask import Flask, render_template, jsonify, request, send_from_directory
from logger import app_logger
import config
from config import LOT_TO_BTC
import os
import time

app = Flask(__name__, template_folder='templates')
app.config['TEMPLATES_AUTO_RELOAD'] = True

try:
    import numpy as np
    from flask.json.provider import DefaultJSONProvider

    class NumpyJSONProvider(DefaultJSONProvider):
        def default(self, obj):
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
    
    app.json = NumpyJSONProvider(app)
except ImportError:
    pass

# Global reference to the engine
bot_engine = None
ares_runner = None

def init_web_server(engine):
    global bot_engine
    bot_engine = engine

@app.route('/')
def index():
    # Read directly from disk to bypass Jinja2 template bytecode cache.
    # This ensures live edits to dashboard.html are reflected immediately.
    import os
    from flask import Response
    tmpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'dashboard.html')
    with open(tmpl_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return Response(content, mimetype='text/html')

@app.route('/ping')
def ping():
    # Lightweight endpoint for Keep-Alive pinger and UptimeRobot
    return "OK", 200

@app.route('/sw.js')
def serve_sw():
    response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/json')

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/premium_conditions')
def get_premium_conditions():
    if not bot_engine:
        return jsonify({
            "status": "error",
            "trade_allowed": False,
            "zone": "RED",
            "decision": "DATA UNAVAILABLE",
            "reasons": ["API Error: Engine not initialized."]
        })
    try:
        if hasattr(bot_engine, 'premium_engine') and bot_engine.premium_engine:
            return jsonify(bot_engine.premium_engine.evaluate_conditions(mode="MONITOR"))
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

def _read_local_hpe_state():
    import json
    import os
    res = {}
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, 'local_hpe_state.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                res = json.load(f)
                
        # Read history
        res['history'] = []
        hist_path = os.path.join(base_dir, 'hpe_history.json')
        if os.path.exists(hist_path):
            with open(hist_path, 'r') as f:
                res['history'] = json.load(f)
                
        return res
    except Exception as e:
        app_logger.error(f"Error reading local HPE state: {e}")
    return res

@app.route('/api/status')
def get_status():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    import db_manager
    # Read last 50 lines of the trading_bot.log and ares.log
    logs = []
    try:
        with open('trading_bot.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            logs.extend([line.strip() for line in lines[-150:]])
    except Exception as e:
        logs.append(f"Error reading trading_bot.log: {e}")

    try:
        import os
        ares_log_path = os.path.join("logs", "system.log")
        if os.path.exists(ares_log_path):
            with open(ares_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                if lines:
                    logs.append("--- ARES SYSTEM LOGS ---")
                    logs.extend([line.strip() for line in lines[-30:]])
    except Exception as e:
        pass

    if not logs:
        logs = ["Log file not found."]

    # Format active positions with rich real-time data
    if bot_engine and getattr(bot_engine.execution, 'mode', 'PAPER') == 'LIVE':
        now_ts = time.time()
        if now_ts - getattr(bot_engine.execution, '_last_live_sync_ts', 0) > 4.0:
            bot_engine.execution._last_live_sync_ts = now_ts
            try:
                bot_engine.execution.sync_live_positions()
            except Exception as _sync_err:
                app_logger.debug(f"Web status: Failed to sync live positions: {_sync_err}")

    from datetime import datetime, timezone, timedelta
    positions = []
    
    # Get trade status from engine for position cards
    trail_state = bot_engine.risk_manager.get_trailing_state()
    total_entry_premium = getattr(bot_engine, 'total_entry_premium', 0)
    
    # Compute time remaining to 17:00 IST (BTC Options trade 24/7)
    # When past today's 17:00 IST, show countdown to NEXT day's 17:00 IST
    try:
        from utils import get_ist_now
        now_ist = get_ist_now()
        target_ist = now_ist.replace(hour=17, minute=0, second=0, microsecond=0)
        if now_ist >= target_ist:
            # Past today's squareoff — calculate to next day's 17:00
            target_ist = target_ist + timedelta(days=1)
        mins_remaining = int((target_ist - now_ist).total_seconds() / 60)
        if mins_remaining < 0:
            mins_remaining = 0
    except Exception:
        mins_remaining = 0
    
    current_iv_pct = getattr(bot_engine, 'current_iv', 0.0)  # already in % scale
    
    # ── Get Current BTC Price for Capital Used calculation (5-Tier Fallback) ──
    btc_price = 0.0
    try:
        btc_ws = bot_engine.api_client.get_realtime_ticker("BTCUSD")
        if btc_ws and 'mark_price' in btc_ws:
            btc_price = float(btc_ws['mark_price'])
    except Exception as btc_err:
        app_logger.debug(f"Web status: Failed to get BTC price from WS cache: {btc_err}")
        
    if not btc_price or btc_price <= 0:
        # Fallback 1: check spot/mark price from option symbols' greeks or spot_price
        for sym in bot_engine.execution.active_positions.keys():
            try:
                ws_data = bot_engine.api_client.get_realtime_ticker(sym)
                if ws_data:
                    spot = float(ws_data.get('spot_price') or ws_data.get('greeks', {}).get('spot') or 0)
                    if spot > 0:
                        btc_price = spot
                        break
            except Exception:
                pass
                
    if not btc_price or btc_price <= 0:
        # Fallback 2: fetch from API tickers (REMOVED)
        # Synchronous API calls from the web thread cause catastrophic UI hangs.
        pass
            
    if not btc_price or btc_price <= 0:
        # Fallback 3: check if bot_engine has cached btc price in btc_price_history
        if getattr(bot_engine, 'btc_price_history', None) and len(bot_engine.btc_price_history) > 0:
            btc_price = bot_engine.btc_price_history[-1][1]
            
    if not btc_price or btc_price <= 0:
        # Fallback 4: Binance public API (REMOVED)
        # Synchronous API calls from the web thread cause catastrophic UI hangs.
        pass
            
    # Absolute fallback (e.g. 70000) so we never crash/divide by zero
    if not btc_price or btc_price <= 0:
        btc_price = 70000.0

    def _calculate_pos_metrics(pos_dict):
        pos_list = []
        for sym, data in pos_dict.items():
            entry_price = data.get('entry_price', 0)
            size = data.get('entry_size', data.get('size', 0))
            leg_type = data.get('leg_type', 'unknown')
            if leg_type == 'unknown':
                if sym.startswith('C-BTC'):
                    leg_type = 'call'
                elif sym.startswith('P-BTC'):
                    leg_type = 'put'
            entry_time_str = data.get('entry_time', '')
            strike = data.get('strike', 0)
            
            current_price = entry_price
            delta_val = 0.0
            gamma_val = 0.0
            try:
                ws_data = bot_engine.api_client.get_realtime_ticker(sym)
                if ws_data and 'mark_price' in ws_data:
                    candidate_price = float(ws_data['mark_price'])
                    price_is_valid = (
                        candidate_price > 0.01 and
                        entry_price > 0 and
                        abs(candidate_price - entry_price) / entry_price < 10.0
                    )
                    if price_is_valid:
                        current_price = candidate_price
                        data['last_good_price'] = candidate_price
                        greeks = ws_data.get('greeks') or {}
                        delta_val = float(greeks.get('delta', 0))
                        gamma_val = float(greeks.get('gamma', 0))
                    else:
                        lgp = data.get('last_good_price')
                        if lgp and lgp > 0.01:
                            current_price = lgp
                        else:
                            current_price = entry_price
            except Exception as ex:
                app_logger.debug(f"Status: Price fetch error for {sym}: {ex}")
            
            btc_quantity = size * LOT_TO_BTC
            leg_pnl_usd = (entry_price - current_price) * btc_quantity
            leg_pnl_inr = leg_pnl_usd * 95.5
            leg_entry_premium_total = entry_price * btc_quantity
            leg_pnl_pct_premium = (leg_pnl_usd / leg_entry_premium_total * 100) if leg_entry_premium_total > 0 else 0.0
            leg_capital_used = size * LOT_TO_BTC * btc_price
            leg_pnl_pct_capital = (leg_pnl_usd / leg_capital_used * 100) if leg_capital_used > 0 else 0.0
            
            if trail_state['trailing_confirmed'] and trail_state['current_trailing_sl'] is not None:
                trade_status = f"Locked +{trail_state['current_trailing_sl']}% SL"
            elif len(pos_dict) > 0:
                trade_status = "Running"
            else:
                trade_status = "Unknown"
            
            pos_list.append({
                'symbol': sym,
                'leg_type': leg_type,
                'strike': strike,
                'side': data.get('side', 'SELL'),
                'size': size,
                'entry_price': round(entry_price, 4),
                'current_price': round(current_price, 4),
                'leg_pnl_usd': round(leg_pnl_usd, 2),
                'leg_pnl_inr': round(leg_pnl_inr, 2),
                'leg_pnl_pct_premium': round(leg_pnl_pct_premium, 2),
                'leg_pnl_pct_capital': round(leg_pnl_pct_capital, 2),
                'leg_entry_premium_total': round(leg_entry_premium_total, 4),
                'leg_capital_used': round(leg_capital_used, 2),
                'delta': round(delta_val, 4),
                'gamma': round(gamma_val, 5),
                'entry_time': entry_time_str,
                'mins_to_squareoff': mins_remaining,
                'current_iv_pct': current_iv_pct,
                'trade_status': trade_status,
            })
        
        total_entry_prem = sum(p.get('leg_entry_premium_total', 0) for p in pos_list)
        total_cap_used = round(sum(p['leg_capital_used'] for p in pos_list), 2)
        opt_pnl_usd = sum(p['leg_pnl_usd'] for p in pos_list)
        return pos_list, total_entry_prem, total_cap_used, opt_pnl_usd

    # Compute for both engines separately
    current_mode = getattr(bot_engine.execution, 'mode', 'PAPER')
    paper_dict = getattr(bot_engine.execution, 'paper_active_positions', {})
    live_dict = getattr(bot_engine.execution, 'live_active_positions', {})

    paper_positions, paper_entry_prem, paper_cap_used, paper_opt_pnl = _calculate_pos_metrics(paper_dict)
    live_positions, live_entry_prem, live_cap_used, live_opt_pnl = _calculate_pos_metrics(live_dict)

    # Hedge Status (Smart Hedging Fallback)
    hedge_status = bot_engine.smart_hedging.get_status() if getattr(bot_engine, 'smart_hedging', None) else {}
    hedge_pnl_usd = hedge_status.get('hedge_pnl_usd', 0.0)

    paper_pnl_usd = round(paper_opt_pnl + (hedge_pnl_usd if current_mode == 'PAPER' else 0.0), 2)
    paper_pnl_inr = round(paper_pnl_usd * 95.5, 2)
    live_pnl_usd = round(live_opt_pnl + (hedge_pnl_usd if current_mode == 'LIVE' else 0.0), 2)
    live_pnl_inr = round(live_pnl_usd * 95.5, 2)

    # Compute dedicated SL and TP targets for both engines
    paper_trail = bot_engine.risk_manager.get_paper_trailing_state()
    paper_pnl_pct_prem = (paper_pnl_usd / paper_entry_prem * 100) if paper_entry_prem > 0 else 0.0
    paper_peak_pct = max(paper_trail.get('highest_profit_pct', 0.0), paper_pnl_pct_prem if paper_positions else 0.0)
    paper_peak_usd = round(paper_entry_prem * (paper_peak_pct / 100.0), 2) if paper_entry_prem > 0 else 0.0

    if paper_trail.get('trailing_confirmed') and paper_trail.get('current_trailing_sl') is not None:
        paper_sl_pct = paper_trail['current_trailing_sl']
        paper_sl_usd = round(paper_entry_prem * (paper_sl_pct / 100.0), 2)
        paper_sl_type = 'LOCKED'
        paper_sl_label = f"+{paper_sl_pct:.1f}% SL Locked"
    else:
        paper_sl_pct = -round(config.SL_PERCENT * 100, 1)
        paper_sl_usd = -round(paper_entry_prem * config.SL_PERCENT, 2)
        paper_sl_type = 'HARD'
        paper_sl_label = f"{paper_sl_pct:.1f}% Hard SL"

    paper_tp_pct = round(config.TRAILING_CONFIRM_TARGET * 100, 1)
    paper_tp_usd = round(paper_entry_prem * config.TRAILING_CONFIRM_TARGET, 2)
    paper_tp_status = "LOCKED" if paper_trail.get('trailing_confirmed') else "PENDING"

    live_trail = bot_engine.risk_manager.get_live_trailing_state()
    live_pnl_pct_prem = (live_pnl_usd / live_entry_prem * 100) if live_entry_prem > 0 else 0.0
    live_peak_pct = max(live_trail.get('highest_profit_pct', 0.0), live_pnl_pct_prem if live_positions else 0.0)
    live_peak_usd = round(live_entry_prem * (live_peak_pct / 100.0), 2) if live_entry_prem > 0 else 0.0

    if live_trail.get('trailing_confirmed') and live_trail.get('current_trailing_sl') is not None:
        live_sl_pct = live_trail['current_trailing_sl']
        live_sl_usd = round(live_entry_prem * (live_sl_pct / 100.0), 2)
        live_sl_type = 'LOCKED'
        live_sl_label = f"+{live_sl_pct:.1f}% SL Locked"
    else:
        live_sl_pct = -round(config.SL_PERCENT * 100, 1)
        live_sl_usd = -round(live_entry_prem * config.SL_PERCENT, 2)
        live_sl_type = 'HARD'
        live_sl_label = f"{live_sl_pct:.1f}% Delta Stop"

    live_tp_pct = round(config.TRAILING_CONFIRM_TARGET * 100, 1)
    live_tp_usd = round(live_entry_prem * config.TRAILING_CONFIRM_TARGET, 2)
    live_tp_status = "LOCKED" if live_trail.get('trailing_confirmed') else "PENDING"

    # Active engine selected according to current execution mode
    if current_mode == 'LIVE':
        positions = live_positions
        total_entry_premium = live_entry_prem
        total_capital_used = live_cap_used
        options_pnl_usd = live_opt_pnl
        total_pnl_usd = live_pnl_usd
        total_pnl_inr = live_pnl_inr
    else:
        positions = paper_positions
        total_entry_premium = paper_entry_prem
        total_capital_used = paper_cap_used
        options_pnl_usd = paper_opt_pnl
        total_pnl_usd = paper_pnl_usd
        total_pnl_inr = paper_pnl_inr

    total_pnl_pct_premium = (total_pnl_usd / total_entry_premium * 100) if total_entry_premium > 0 else 0.0
    total_pnl_pct_capital = (total_pnl_usd / total_capital_used * 100) if total_capital_used > 0 else 0.0
    
    dvol_status = bot_engine.dvol_provider.get_status() if getattr(bot_engine, 'dvol_provider', None) else {}
    
    paper_eq = float(getattr(bot_engine.risk_manager, 'paper_equity', 50000.0))
    live_eq = float(getattr(bot_engine.risk_manager, 'live_equity', 0.0))
    active_eq = live_eq if (current_mode == 'LIVE' and live_eq > 0) else paper_eq

    paper_perf = bot_engine.performance_tracker.get_metrics(paper_eq, mode='PAPER')
    live_perf = bot_engine.performance_tracker.get_metrics(live_eq, mode='LIVE')
    active_perf = live_perf if current_mode == 'LIVE' else paper_perf

    return jsonify({
        'is_running': bot_engine.is_running,
        'mode': current_mode,
        'equity': round(active_eq, 2),
        'paper_equity': round(paper_eq, 2),
        'live_equity': round(live_eq, 2),
        'daily_loss_hits': bot_engine.daily_loss_hits,
        'positions': positions,
        'paper_positions': paper_positions,
        'live_positions': live_positions,
        'paper_pnl': {
            'total_pnl_usd': paper_pnl_usd,
            'total_pnl_inr': paper_pnl_inr,
            'total_capital_used': paper_cap_used,
            'total_entry_premium': round(paper_entry_prem, 4),
            'positions_count': len(paper_positions),
            'trail_state': paper_trail,
            'peak_pct': round(paper_peak_pct, 2),
            'peak_usd': paper_peak_usd,
            'sl_pct': paper_sl_pct,
            'sl_usd': paper_sl_usd,
            'sl_type': paper_sl_type,
            'sl_label': paper_sl_label,
            'tp_pct': paper_tp_pct,
            'tp_usd': paper_tp_usd,
            'tp_status': paper_tp_status,
        },
        'live_pnl': {
            'total_pnl_usd': live_pnl_usd,
            'total_pnl_inr': live_pnl_inr,
            'total_capital_used': live_cap_used,
            'total_entry_premium': round(live_entry_prem, 4),
            'positions_count': len(live_positions),
            'trail_state': live_trail,
            'peak_pct': round(live_peak_pct, 2),
            'peak_usd': live_peak_usd,
            'sl_pct': live_sl_pct,
            'sl_usd': live_sl_usd,
            'sl_type': live_sl_type,
            'sl_label': live_sl_label,
            'tp_pct': live_tp_pct,
            'tp_usd': live_tp_usd,
            'tp_status': live_tp_status,
        },
        'paper_trail_state': paper_trail,
        'live_trail_state': live_trail,
        'trail_state': live_trail if current_mode == 'LIVE' else paper_trail,
        'total_entry_premium': round(total_entry_premium, 4),
        'total_capital_used': total_capital_used,
        'btc_price': round(btc_price, 2),
        'options_pnl_usd': round(options_pnl_usd, 2),
        'total_pnl_usd': total_pnl_usd,
        'total_pnl_inr': total_pnl_inr,
        'total_pnl_pct_premium': round(total_pnl_pct_premium, 2),
        'total_pnl_pct_capital': round(total_pnl_pct_capital, 2),
        'total_pnl_pct': round(total_pnl_pct_capital, 2),
        'logs': logs,
        'performance': active_perf,
        'paper_performance': paper_perf,
        'live_performance': live_perf,
        'rule_report': bot_engine.latest_rule_report,
        'schedule_info': bot_engine.get_schedule_info(),
        'regime_filter_enabled': bot_engine.market_regime_filter_enabled,
        'smart_hedging_enabled': getattr(bot_engine, 'smart_hedging_enabled', True),
        'current_market_regime': bot_engine.current_market_regime,
        'current_adx_value': bot_engine.current_adx_value,
        'adx_history': getattr(bot_engine, 'adx_history', []),
        'paper_lot_multiplier': getattr(bot_engine, 'paper_lot_multiplier', 1.0),
        'api_connected': bot_engine.api_client.ws_connected if bot_engine.api_client else False,
        'active_api_slot': getattr(db_manager, 'get_active_api_slot', lambda: 'live')() if 'db_manager' in locals() else 'live',
        'active_api_label': ('Delta Demo' if (getattr(db_manager, 'get_active_api_slot', lambda: 'live')() if 'db_manager' in locals() else 'live') == 'demo' else 'Delta Live'),
        'active_api_badge': ('🧪 Delta Demo' if (getattr(db_manager, 'get_active_api_slot', lambda: 'live')() if 'db_manager' in locals() else 'live') == 'demo' else '⚡ Delta Live'),
        'current_iv': getattr(bot_engine, 'current_iv', 0.0),
        'avg_7d_iv': getattr(bot_engine, 'avg_7d_iv', 0.0),
        'iv_status': getattr(bot_engine, 'iv_status', 'Normal'),
        'today_skip_reason': getattr(bot_engine, 'today_skip_reason', None),
        # New advanced metrics
        'dvol_status': dvol_status,
        'hedge_status': hedge_status,
        'local_hpe_status': _read_local_hpe_state(),
        'size_multiplier': round(getattr(bot_engine, 'size_multiplier', 1.0), 2),
        'consecutive_loss_count': getattr(bot_engine, 'consecutive_loss_count', 0),
        'next_day_paused': getattr(bot_engine, 'next_day_paused', False),
        'reduced_size_trades_remaining': getattr(bot_engine, 'reduced_size_trades_remaining', 0),
        'trail_state': trail_state,
        # Data Freshness & Health
        'data_age_seconds': round(time.time() - bot_engine.api_client.last_price_update_time) if bot_engine.api_client.last_price_update_time > 0 else 999,
        'ws_connected': bot_engine.api_client.ws_connected if bot_engine.api_client else False,
        'last_api_update': bot_engine.api_client.last_price_update_time if bot_engine.api_client else 0,
        'runtime_state': bot_engine.runtime_state.to_dict() if hasattr(bot_engine, 'runtime_state') else {}
    })

@app.route('/api/start', methods=['POST'])
def start_bot():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    if bot_engine.is_running:
        return jsonify({'status': 'success', 'message': 'Engine is already running.'})
        
    bot_engine.is_running = True
    import threading
    threading.Thread(target=bot_engine.start, daemon=True).start()
    
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

    # Calculate closed P&L and log it to performance tracker before wiping positions
    if bot_engine.execution.active_positions:
        current_total_value = 0
        collected_premium = bot_engine.total_entry_premium
        
        # If hot-recovery didn't run (e.g. network crash loop), reconstruct premium manually
        if collected_premium <= 0:
            collected_premium = sum(
                data.get('entry_price', 0) * data.get('size', 0) * LOT_TO_BTC
                for sym, data in bot_engine.execution.active_positions.items()
                if not sym.startswith('__') and isinstance(data, dict) and 'size' in data
            )
            bot_engine.total_entry_premium = collected_premium

        for sym, data in bot_engine.execution.active_positions.items():
            # Skip internal meta-keys (__dpl_state__, __chart_data__, etc.)
            if sym.startswith('__') or not isinstance(data, dict) or 'size' not in data:
                continue
            ws_data = bot_engine.api_client.get_realtime_ticker(sym)
            if ws_data and 'mark_price' in ws_data:
                btc_qty = data['size'] * LOT_TO_BTC
                current_total_value += float(ws_data['mark_price']) * btc_qty

        # Fallback to entry prices if live ticker not received
        if current_total_value == 0:
            current_total_value = sum(
                data['entry_price'] * data['size'] * LOT_TO_BTC
                for sym, data in bot_engine.execution.active_positions.items()
                if not sym.startswith('__') and isinstance(data, dict) and 'size' in data
            )

        profit = bot_engine.total_entry_premium - current_total_value

        # ── CRITICAL FIX ──────────────────────────────────────────────────
        # _log_and_reset_trade checks current_trade_info["calls"] to decide
        # whether to save the trade. During manual close, the bot loop may
        # not have populated this yet → the trade gets silently skipped.
        # We force-populate it here from active_positions so it is ALWAYS saved.
        if not bot_engine.current_trade_info.get("calls"):
            from utils import get_ist_now
            calls = [sym for sym, d in bot_engine.execution.active_positions.items() 
                     if isinstance(d, dict) and d.get('side', '').lower() == 'sell' and (sym.startswith('C-') or sym.endswith('-C') or d.get('leg_type') == 'call')]
            puts  = [sym for sym, d in bot_engine.execution.active_positions.items() 
                     if isinstance(d, dict) and d.get('side', '').lower() == 'sell' and (sym.startswith('P-') or sym.endswith('-P') or d.get('leg_type') == 'put')]
            # Fallback: split all symbols into calls/puts if side not tagged
            if not calls and not puts:
                for sym in bot_engine.execution.active_positions:
                    if sym.startswith('C-') or sym.endswith('-C'):
                        calls.append(sym)
                    elif sym.startswith('P-') or sym.endswith('-P'):
                        puts.append(sym)
            bot_engine.current_trade_info["calls"] = calls
            bot_engine.current_trade_info["puts"]  = puts
            if not bot_engine.current_trade_info.get("entry_time"):
                bot_engine.current_trade_info["entry_time"] = get_ist_now().isoformat()
            app_logger.info(f"Emergency Close: Force-populated current_trade_info → calls={calls}, puts={puts}")
        # ─────────────────────────────────────────────────────────────────
        # ── CRITICAL FIX ──────────────────────────────────────────────────
        # Close positions FIRST, before logging and resetting the trade.
        # This is because _log_and_reset_trade will trigger the Auto-Deactivate
        # safety switch, which flips the mode to PAPER. If mode is PAPER,
        # close_all will just simulate the close and leave live positions orphaned!
        bot_engine.execution.close_all(reason="Emergency Manual Square-Off")
        bot_engine.smart_hedging.close_hedge()
        
        bot_engine._log_and_reset_trade(profit, "Manual Square-Off")
        from notifier import notifier
        notifier.notify_full_exit("Manual Square-Off", profit)
    else:
        # If no active positions, just ensure everything is closed anyway
        bot_engine.execution.close_all(reason="Emergency Manual Square-Off")
        bot_engine.smart_hedging.close_hedge()

    bot_engine.reset_daily_state()

    bot_engine.today_trade_status = "Emergency Manual Closed"
    bot_engine.today_skip_reason  = "User Triggered Emergency"

    from notifier import notifier
    notifier.notify_error("🚨 USER EMERGENCY 🚨\nAll positions squared off manually via Dashboard.")

    return jsonify({'status': 'success'})

@app.route('/api/force_clean', methods=['POST'])
def force_clean():
    res = bot_engine.api_client.request("GET", "/v2/positions/margined")
    positions = res.get('result', [])
    closed = []
    for p in positions:
        size = int(p.get('size', 0))
        if size != 0:
            side = 'buy' if size < 0 else 'sell'
            abs_size = abs(size)
            out = bot_engine.api_client.place_order(p.get('product_id'), side, abs_size)
            closed.append({'symbol': p.get('product', {}).get('symbol'), 'size': abs_size, 'out': out})
    return jsonify({'status': 'success', 'closed': closed, 'res': res})

@app.route('/api/toggle_regime', methods=['POST'])
def toggle_regime():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.market_regime_filter_enabled = not bot_engine.market_regime_filter_enabled
    state = "ENABLED" if bot_engine.market_regime_filter_enabled else "DISABLED"
    app_logger.info(f"Web: Market Regime Filter {state}")
    
    return jsonify({'status': 'success', 'enabled': bot_engine.market_regime_filter_enabled})

@app.route('/api/force_shadow_hedge', methods=['POST'])
def force_shadow_hedge():
    try:
        import os
        with open('force_hedge.flag', 'w') as f:
            f.write("1")
        app_logger.info("Web: Manual Shadow Hedge triggered.")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/close_shadow_hedge', methods=['POST'])
def close_shadow_hedge():
    try:
        if bot_engine and getattr(bot_engine, 'smart_hedging', None):
            bot_engine.smart_hedging.close_hedge()
        app_logger.info("Web: Manual Live Hedge Close triggered.")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/toggle_hedge', methods=['POST'])
def toggle_hedge():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.smart_hedging_enabled = not bot_engine.smart_hedging_enabled
    state = "ENABLED" if bot_engine.smart_hedging_enabled else "DISABLED"
    app_logger.info(f"Web: Smart Hedging {state}")
    
    return jsonify({'status': 'success', 'enabled': bot_engine.smart_hedging_enabled})
    
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
@app.route('/api/live/manual_order', methods=['POST'])
def manual_order():
    try:
        if not bot_engine:
            app_logger.error("Web [manual_order]: Engine not initialized")
            return jsonify({'success': False, 'error': 'Engine not initialized'}), 200

        if bot_engine.execution.mode != 'LIVE':
            app_logger.warning("Web [manual_order]: Rejected manual order - engine is in PAPER mode")
            return jsonify({
                'status': 'error',
                'message': 'Manual orders can only be placed in LIVE mode. Toggle Live Mode ON first.'
            }), 200

        app_logger.info("Web [manual_order]: Manual strangle entry cycle triggered via dashboard.")
        
        # Temporarily bypass the "1 trade per day limit" just for manual force execution
        bot_engine.trades_taken_today = 0
        bot_engine.today_skip_reason = None
        
        initial_keys = set(k for k in bot_engine.execution.active_positions.keys() if not k.startswith('__'))
        
        # Trigger the entry cycle synchronously to bubble up failures
        bot_engine.run_entry_cycle(force=True)
        
        current_keys = set(k for k in bot_engine.execution.active_positions.keys() if not k.startswith('__'))
        
        if bot_engine.today_trade_status == "Trade Taken" or (current_keys - initial_keys) or (len(current_keys) > 0 and len(initial_keys) == 0):
            return jsonify({
                'status': 'success',
                'message': f'Manual strangle entry cycle triggered and trade executed successfully ({bot_engine.execution.mode} mode)!'
            }), 200
        else:
            msg = bot_engine.today_skip_reason or "Trade was not executed or strikes could not be found."
            return jsonify({
                'status': 'error',
                'message': f'Trade was not executed. Reason: {msg}'
            }), 200

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
                # Show events from the last 3 days up to the next 7 days
                if dt < now_utc - timedelta(days=3) or dt > week_end:
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
        from config import MANUAL_TOTAL_LOTS as cfg_lots
        return int(cfg_lots)  # Always use config default, never hardcoded 200

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
            
        import db_manager
        db_manager.trigger_cloud_sync()

        app_logger.info(f"Web [save_lot_size]: Saved new lot size → {new_lots} total ({new_lots // 2} per leg)")
        return jsonify({'success': True, 'total_lots': new_lots, 'per_leg': new_lots // 2})

    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid value – must be a whole number'}), 400
    except Exception as e:
        app_logger.error(f"Web [save_lot_size]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Live Trading Mode Endpoints ──────────────────────────────────────────────

@app.route('/api/live_mode', methods=['GET'])
def get_live_mode():
    """Return current live mode state, live lots, and pre-flight checklist."""
    import json
    try:
        data = {}
        if os.path.exists(LOT_SIZE_FILE):
            with open(LOT_SIZE_FILE, 'r') as f:
                data = json.load(f)

        live_mode = bool(data.get('live_mode', False))
        live_lots = int(data.get('live_lots', 1))
        paper_lots = int(data.get('total_lots', 1000))

        # Pre-flight checklist - Check LIVE positions only (paper simulation never blocks live trading)
        from config import DELTA_API_KEY, DELTA_API_SECRET
        api_key_ok = bool(DELTA_API_KEY) and DELTA_API_KEY not in ('testnet_key', '', 'YOUR_KEY_HERE')
        api_secret_ok = bool(DELTA_API_SECRET) and DELTA_API_SECRET not in ('testnet_secret', '', 'YOUR_SECRET_HERE')
        
        has_live_positions = False
        if bot_engine:
            has_live_positions = bool(getattr(bot_engine.execution, 'live_active_positions', {}))
            if not has_live_positions and api_key_ok and api_secret_ok:
                try:
                    pos_res = bot_engine.api_client.get_positions()
                    if pos_res.get('success'):
                        real_open = [p for p in pos_res.get('result', []) if abs(float(p.get('size', 0) or 0)) > 0]
                        has_live_positions = len(real_open) > 0
                except Exception:
                    pass

        wallet_balance_inr = 0.0
        available_balance_inr = 0.0
        net_equity_usd = 0.0

        api_error_detail = None
        if api_key_ok and api_secret_ok and bot_engine:
            try:
                bal_res = bot_engine.api_client.get_balances()
                if bal_res.get('success'):
                    meta = bal_res.get('meta', {})
                    net_equity_usd = float(meta.get('net_equity', 0.0) or 0.0)
                    for b in bal_res.get('result', []):
                        if b.get('asset_symbol') in ('USD', 'INR', 'USDT'):
                            b_inr = float(b.get('balance_inr') or 0.0)
                            a_inr = float(b.get('available_balance_inr') or 0.0)
                            if b_inr > wallet_balance_inr:
                                wallet_balance_inr = b_inr
                            if a_inr > available_balance_inr:
                                available_balance_inr = a_inr
                else:
                    err = bal_res.get('error', {})
                    err_code = err.get('code') if isinstance(err, dict) else str(err)
                    if err_code == 'ip_not_whitelisted_for_api_key':
                        client_ip = err.get('context', {}).get('client_ip', '') if isinstance(err, dict) else ''
                        api_key_ok = False
                        api_error_detail = f"IP {client_ip} not whitelisted on Delta Exchange"
                    else:
                        api_key_ok = False
                        api_error_detail = f"API Error: {err.get('message') or err_code}"
            except Exception as test_err:
                api_key_ok = False
                api_error_detail = f"Connection error: {test_err}"

        current_mode = getattr(bot_engine.execution, 'mode', 'PAPER') if bot_engine else 'PAPER'
        import db_manager
        active_slot = db_manager.get_active_api_slot()

        return jsonify({
            'live_mode': live_mode,
            'active_slot': active_slot,
            'live_lots': live_lots,
            'current_execution_mode': current_mode,
            'wallet_balance_inr': round(wallet_balance_inr, 2),
            'available_balance_inr': round(available_balance_inr, 2),
            'net_equity_usd': round(net_equity_usd, 2),
            'preflight': {
                'api_key_valid': api_key_ok,
                'api_secret_valid': api_secret_ok,
                'no_active_positions': not has_live_positions,
                'portfolio_margin_enabled': True,  # User confirmed enabled
                'api_error_detail': api_error_detail
            },
            'safe_to_activate': api_key_ok and api_secret_ok and not has_live_positions
        })
    except Exception as e:
        app_logger.error(f"Web [live_mode GET]: Error – {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/toggle_live_mode', methods=['POST'])
def toggle_live_mode():
    """Toggle the bot between PAPER and LIVE execution mode at runtime.
    
    Safety guards:
    1. Refuses if API key is testnet placeholder
    2. Refuses to activate LIVE if there are active LIVE positions on Delta Exchange
    3. On deactivate: switches back to PAPER, positions stay tracked
    """
    if not bot_engine:
        return jsonify({'success': False, 'error': 'Engine not initialized'}), 500

    import json
    try:
        body = request.get_json(force=True) or {}
        activate = bool(body.get('activate', body.get('live_mode', False)))

        # ── Safety Gate 1: Validate real API credentials ──────────────────────
        from config import DELTA_API_KEY, DELTA_API_SECRET
        if activate:
            if not DELTA_API_KEY or DELTA_API_KEY in ('testnet_key', '', 'YOUR_KEY_HERE'):
                return jsonify({
                    'success': False,
                    'error': 'Cannot activate LIVE mode: API Key is a testnet placeholder. Set a real key in .env and restart.'
                }), 400
            if not DELTA_API_SECRET or DELTA_API_SECRET in ('testnet_secret', '', 'YOUR_SECRET_HERE'):
                return jsonify({
                    'success': False,
                    'error': 'Cannot activate LIVE mode: API Secret is a testnet placeholder. Set a real secret in .env and restart.'
                }), 400

        # ── Safety Gate 2: No active LIVE positions on Delta Exchange when switching ─
        real_live_positions = []
        if bot_engine and hasattr(bot_engine.execution, 'live_active_positions'):
            real_live_positions = [k for k in bot_engine.execution.live_active_positions.keys() if not k.startswith('__')]
        if activate and real_live_positions:
            return jsonify({
                'success': False,
                'error': 'Cannot switch to LIVE mode while live positions are open on Delta Exchange.'
            }), 400

        # ── Switch execution mode at runtime ──────────────────────────────────
        new_mode = 'LIVE' if activate else 'PAPER'
        bot_engine.execution.mode = new_mode
        config.BOT_MODE = new_mode

        # ── Persist to lot_size.json ──────────────────────────────────────────
        data = {}
        if os.path.exists(LOT_SIZE_FILE):
            with open(LOT_SIZE_FILE, 'r') as f:
                data = json.load(f)
        data['live_mode'] = activate
        with open(LOT_SIZE_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        action_text = "ACTIVATED 🔴 LIVE" if activate else "DEACTIVATED → PAPER"
        app_logger.warning(f"Web [toggle_live_mode]: Live mode {action_text}. New execution mode: {new_mode}")

        if activate:
            try:
                bot_engine.risk_manager.update_equity()
                bot_engine.execution.prune_orphan_stop_orders()
                bot_engine.execution.sync_live_positions()
            except Exception as _sync_err:
                app_logger.warning(f"Web [toggle_live_mode]: Error preparing live mode: {_sync_err}")
        else:
            try:
                # Sweep and cancel all exchange stop orders upon deactivating live mode
                bot_engine.execution.cancel_all_exchange_stop_orders()
            except Exception as _clean_err:
                app_logger.warning(f"Web [toggle_live_mode]: Error cleaning exchange stop orders: {_clean_err}")

        # Notify via Telegram if notifier available
        try:
            from notifier import notifier
            if activate:
                notifier.notify_error(
                    f"🔴 LIVE TRADING MODE ACTIVATED\n"
                    f"Real orders will now execute on Delta Exchange.\n"
                    f"Live Lot Size: {data.get('live_lots', 1)} lot(s)\n"
                    f"Portfolio Margin: ENABLED\n"
                    f"⚠️ Real capital at risk!"
                )
            else:
                notifier.notify_error(
                    f"📄 Switched back to PAPER MODE\n"
                    f"No real orders will be placed."
                )
        except Exception:
            pass

        return jsonify({
            'success': True,
            'live_mode': activate,
            'current_execution_mode': new_mode,
            'message': f'Mode switched to {new_mode}'
        })

    except Exception as e:
        app_logger.error(f"Web [toggle_live_mode]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save_live_lots', methods=['POST'])
def save_live_lots():
    """Save the live-specific lot size (separate from paper lots)."""
    import json
    try:
        body = request.get_json(force=True)
        if not body or 'live_lots' not in body:
            return jsonify({'success': False, 'error': 'Missing live_lots field'}), 400

        new_live_lots = int(body['live_lots'])
        if new_live_lots < 2:
            return jsonify({'success': False, 'error': 'Live lot size must be at least 2 (= 1 lot per leg)'}), 400
        if new_live_lots > 500:
            return jsonify({'success': False, 'error': 'Live lot size capped at 500 for safety. Increase manually if needed.'}), 400

        data = {}
        if os.path.exists(LOT_SIZE_FILE):
            with open(LOT_SIZE_FILE, 'r') as f:
                data = json.load(f)
        data['live_lots'] = new_live_lots
        with open(LOT_SIZE_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        app_logger.info(f"Web [save_live_lots]: Live lot size set to {new_live_lots} ({new_live_lots} per leg x 2 = {new_live_lots * 2} total contracts)")
        return jsonify({'success': True, 'live_lots': new_live_lots})

    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid value – must be a whole number'}), 400
    except Exception as e:
        app_logger.error(f"Web [save_live_lots]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── API Key Management (Add, Update & Disable) ───────────────────────────────

DELTA_GATEWAYS = [
    {
        "id": "demo",
        "name": "Delta Demo (demo.delta.exchange)",
        "base_url": "https://testnet-api.delta.exchange",
        "is_demo": True
    },
    {
        "id": "india_live",
        "name": "Delta India Live (api.india.delta.exchange)",
        "base_url": "https://api.india.delta.exchange",
        "is_demo": False
    },
    {
        "id": "india_demo",
        "name": "Delta India Demo (cdn-ind.testnet.deltaex.org)",
        "base_url": "https://cdn-ind.testnet.deltaex.org",
        "is_demo": True
    },
    {
        "id": "global_live",
        "name": "Delta Global Live (api.delta.exchange)",
        "base_url": "https://api.delta.exchange",
        "is_demo": False
    }
]

def validate_delta_credentials(api_key: str, api_secret: str, preferred_env: str = None):
    """
    Probes Delta Exchange gateways to validate API credentials.
    Supports Delta Demo (demo.delta.exchange), Delta India Live, India Demo, and Global Live.
    Returns (success, matched_gateway, profile_data, error_message).
    """
    from api_client import DeltaIndiaClient

    candidates = []
    if preferred_env and preferred_env != 'auto':
        for g in DELTA_GATEWAYS:
            if g["id"] == preferred_env or g["base_url"] == preferred_env:
                candidates.append(g)
                break

    for g in DELTA_GATEWAYS:
        if g not in candidates:
            candidates.append(g)

    attempted_errs = []
    for gw in candidates:
        try:
            client = DeltaIndiaClient(api_key=api_key, api_secret=api_secret, base_url=gw["base_url"])
            prof_res = client.get_profile()
            if prof_res and isinstance(prof_res, dict) and prof_res.get('success'):
                res_p = prof_res.get('result', {})
                return True, gw, res_p, None

            # Fallback to wallet balances if profile endpoint is restricted by API key permissions
            bal_res = client.get_balances()
            if bal_res and isinstance(bal_res, dict) and bal_res.get('success'):
                res_items = bal_res.get('result') or []
                uid = ""
                if isinstance(res_items, list) and len(res_items) > 0:
                    uid = str(res_items[0].get('user_id', ''))
                res_p = {
                    'id': uid,
                    'user_id': uid,
                    'email': '',
                    'margin_mode': 'cross'
                }
                return True, gw, res_p, None

            err = prof_res.get('error') if isinstance(prof_res, dict) else prof_res
            if isinstance(err, dict):
                msg = err.get('message') or err.get('code') or str(err)
            else:
                msg = str(err)
            attempted_errs.append(f"{gw['name']}: {msg}")
        except Exception as e:
            attempted_errs.append(f"{gw['name']}: {e}")

    summary_err = " | ".join(attempted_errs)
    return False, None, None, summary_err


@app.route('/api/api_credentials', methods=['GET'])
def get_api_credentials():
    """Returns dual-slot (Live & Demo) API credentials status and active profile."""
    try:
        import db_manager
        all_creds = db_manager.load_all_api_credentials()
        active_slot = all_creds.get('active_slot', 'live')

        def format_slot(slot_name, data):
            if not isinstance(data, dict):
                data = {}
            key = (data.get('api_key') or '').strip()
            secret = (data.get('api_secret') or '').strip()
            is_conf = bool(key and secret and key not in ('testnet_key', 'YOUR_KEY_HERE', '') and secret not in ('testnet_secret', 'YOUR_SECRET_HERE', ''))
            masked = f"{key[:4]}...{key[-4:]}" if len(key) >= 8 else ("***" if key else "")
            prof = data.get('profile') or {}
            connected = bool(is_conf and (prof.get('user_id') or prof.get('id') or prof.get('email')))
            
            default_base = "https://api.india.delta.exchange" if slot_name == "live" else "https://testnet-api.delta.exchange"
            base_url = data.get('base_url') or default_base
            env_name = "Delta India Live" if slot_name == "live" else "Delta Demo (demo.delta.exchange)"
            if "testnet-api.delta.exchange" in base_url:
                env_name = "Delta Demo (demo.delta.exchange)"
            elif "cdn-ind.testnet.deltaex.org" in base_url:
                env_name = "Delta India Demo"
            elif "api.india.delta.exchange" in base_url:
                env_name = "Delta India Live"

            return {
                'configured': is_conf,
                'connected': connected,
                'masked_key': masked,
                'environment': data.get('environment', 'india_live' if slot_name == 'live' else 'demo'),
                'gateway_name': env_name,
                'base_url': base_url,
                'profile': prof
            }

        live_info = format_slot('live', all_creds.get('live', {}))
        demo_info = format_slot('demo', all_creds.get('demo', {}))
        active_info = demo_info if active_slot == 'demo' else live_info

        live_m = False
        try:
            if bot_engine and hasattr(bot_engine, 'execution') and bot_engine.execution:
                live_m = bool(getattr(bot_engine.execution, 'mode', 'PAPER') == 'LIVE')
        except Exception:
            live_m = False

        return jsonify({
            'success': True,
            'active_slot': active_slot,
            'live': live_info,
            'demo': demo_info,
            'configured': active_info['configured'],
            'connected': active_info['connected'],
            'masked_key': active_info['masked_key'],
            'profile': active_info['profile'],
            'live_mode': live_m
        })
    except Exception as e:
        app_logger.error(f"Web [get_api_credentials]: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'active_slot': 'live',
            'configured': False,
            'connected': False,
            'live': {},
            'demo': {},
            'live_mode': False
        }), 200


@app.route('/api/save_api_credentials', methods=['POST'])
def save_api_credentials():
    """Validates and applies Delta Exchange API credentials live with auto-gateway detection."""
    try:
        body = request.get_json(force=True) or {}
        new_key = body.get('api_key', '').strip()
        new_secret = body.get('api_secret', '').strip()
        preferred_env = body.get('environment', 'auto')
        target_slot = body.get('slot', 'auto')

        if not new_key or not new_secret:
            return jsonify({'success': False, 'error': 'Both API Key and API Secret are required.'}), 400

        # Multi-Gateway verification
        ok, matched_gw, prof_data, err_msg = validate_delta_credentials(new_key, new_secret, preferred_env)
        if not ok:
            return jsonify({
                'success': False,
                'error': f'Delta Exchange validation failed across gateways: {err_msg}. Check API Key, Secret, and IP Whitelist.'
            }), 400

        # Determine target slot
        if target_slot not in ('live', 'demo'):
            target_slot = 'demo' if matched_gw.get('is_demo') else 'live'

        profile_info = {
            'user_id': str(prof_data.get('id', '')),
            'email': prof_data.get('email', ''),
            'username': prof_data.get('username', ''),
            'margin_mode': prof_data.get('margin_mode', 'cross')
        }

        # Persist permanently to Cloud & local file
        import db_manager
        db_manager.save_api_credentials(
            api_key=new_key,
            api_secret=new_secret,
            slot=target_slot,
            environment=matched_gw['id'],
            base_url=matched_gw['base_url'],
            profile=profile_info
        )

        # Update bot runtime if this is the active slot or target slot matches current
        current_active = db_manager.get_active_api_slot()
        if target_slot == current_active or not config.DELTA_API_KEY:
            db_manager.set_active_api_slot(target_slot)
            config.DELTA_API_KEY = new_key
            config.DELTA_API_SECRET = new_secret
            config.DELTA_BASE_URL = matched_gw['base_url']
            os.environ['DELTA_API_KEY'] = new_key
            os.environ['DELTA_API_SECRET'] = new_secret
            os.environ['DELTA_BASE_URL'] = matched_gw['base_url']

            if bot_engine and bot_engine.api_client:
                bot_engine.api_client.api_key = new_key
                bot_engine.api_client.api_secret = new_secret
                bot_engine.api_client.base_url = matched_gw['base_url']
                try:
                    bot_engine.risk_manager.update_equity()
                except Exception:
                    pass

        # Write to local .env for permanent local persistence
        try:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
            key_var = 'DELTA_API_KEY' if target_slot == 'live' else 'DELTA_DEMO_API_KEY'
            sec_var = 'DELTA_API_SECRET' if target_slot == 'live' else 'DELTA_DEMO_API_SECRET'
            lines = []
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            new_lines = []
            k_found, s_found = False, False
            for l in lines:
                if l.startswith(f'{key_var}='):
                    new_lines.append(f'{key_var}={new_key}\n')
                    k_found = True
                elif l.startswith(f'{sec_var}='):
                    new_lines.append(f'{sec_var}={new_secret}\n')
                    s_found = True
                else:
                    new_lines.append(l)
            if not k_found: new_lines.append(f'{key_var}={new_key}\n')
            if not s_found: new_lines.append(f'{sec_var}={new_secret}\n')
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        except Exception as _e:
            app_logger.warning(f"Web [save_api_credentials]: .env write skipped – {_e}")

        masked = f"{new_key[:4]}...{new_key[-4:]}" if len(new_key) >= 8 else "***"
        app_logger.info(f"Web [save_api_credentials]: API Key verified on {matched_gw['name']} for {target_slot.upper()} slot (User ID: {profile_info['user_id']})")

        return jsonify({
            'success': True,
            'message': f"Connected and verified on {matched_gw['name']}! (User ID: {profile_info['user_id']})",
            'slot': target_slot,
            'gateway_name': matched_gw['name'],
            'environment': matched_gw['id'],
            'base_url': matched_gw['base_url'],
            'masked_key': masked,
            'profile': profile_info
        })

    except Exception as e:
        app_logger.error(f"Web [save_api_credentials]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/switch_api_slot', methods=['POST'])
def switch_api_slot():
    """Switches active API slot between 'live' and 'demo' at runtime."""
    try:
        body = request.get_json(force=True) or {}
        target_slot = body.get('slot', 'live').lower()
        if target_slot not in ('live', 'demo'):
            return jsonify({'success': False, 'error': 'Invalid slot specified.'}), 400

        import db_manager
        ok, slot_dict = db_manager.set_active_api_slot(target_slot)
        if not ok or not slot_dict.get('api_key'):
            return jsonify({'success': False, 'error': f'No credentials configured for {target_slot.upper()} slot.'}), 400

        k = slot_dict.get('api_key', '')
        s = slot_dict.get('api_secret', '')
        b = slot_dict.get('base_url', config.DELTA_INDIA_BASE_URL)

        config.DELTA_API_KEY = k
        config.DELTA_API_SECRET = s
        config.DELTA_BASE_URL = b
        os.environ['DELTA_API_KEY'] = k
        os.environ['DELTA_API_SECRET'] = s
        os.environ['DELTA_BASE_URL'] = b

        if bot_engine and bot_engine.api_client:
            bot_engine.api_client.api_key = k
            bot_engine.api_client.api_secret = s
            bot_engine.api_client.base_url = b
            try:
                bot_engine.risk_manager.update_equity()
            except Exception:
                pass

        if target_slot == 'demo':
            # Safely disarm real-money LIVE execution when in demo slot
            if bot_engine and hasattr(bot_engine, 'execution') and bot_engine.execution:
                bot_engine.execution.mode = 'PAPER'
            config.BOT_MODE = 'PAPER'
            try:
                if os.path.exists(LOT_SIZE_FILE):
                    with open(LOT_SIZE_FILE, 'r') as f:
                        ls_data = json.load(f)
                    ls_data['live_mode'] = False
                    with open(LOT_SIZE_FILE, 'w') as f:
                        json.dump(ls_data, f, indent=4)
            except Exception:
                pass

        app_logger.info(f"Web [switch_api_slot]: Active slot switched to {target_slot.upper()} ({b})")
        return jsonify({
            'success': True,
            'active_slot': target_slot,
            'base_url': b,
            'message': f"Active account switched to {target_slot.upper()} ({b})"
        })

    except Exception as e:
        app_logger.error(f"Web [switch_api_slot]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/disable_api_key', methods=['POST'])
def disable_api_key():
    """Disables API credentials for a specific slot ('live', 'demo', 'active', or 'all')."""
    try:
        body = request.get_json(silent=True) or {}
        target_slot = body.get('slot', 'active')

        import db_manager
        db_manager.disable_api_slot(target_slot)

        current_active = db_manager.get_active_api_slot()
        if target_slot in ('all', 'active') or target_slot == current_active:
            if bot_engine:
                bot_engine.execution.mode = 'PAPER'
                config.BOT_MODE = 'PAPER'
                if bot_engine.api_client:
                    bot_engine.api_client.api_key = ""
                    bot_engine.api_client.api_secret = ""

            config.DELTA_API_KEY = ""
            config.DELTA_API_SECRET = ""
            os.environ['DELTA_API_KEY'] = ""
            os.environ['DELTA_API_SECRET'] = ""

        if os.path.exists(LOT_SIZE_FILE):
            try:
                with open(LOT_SIZE_FILE, 'r') as f:
                    data = json.load(f)
                data['live_mode'] = False
                with open(LOT_SIZE_FILE, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception:
                pass

        app_logger.warning(f"Web [disable_api_key]: Delta Exchange API key disabled for slot '{target_slot}'.")
        return jsonify({
            'success': True,
            'message': f"API Key disconnected and disabled for {target_slot.upper()} slot. Bot is safe."
        })

    except Exception as e:
        app_logger.error(f"Web [disable_api_key]: Error – {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/server_ip')
def get_server_ip():
    """Returns outbound IPv4 and IPv6 of the server (Render / Local)."""
    import urllib.request
    ipv4, ipv6 = "", ""
    try:
        ipv4 = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode().strip()
    except Exception:
        pass
    try:
        ipv6 = urllib.request.urlopen('https://api64.ipify.org', timeout=3).read().decode().strip()
    except Exception:
        pass
    return jsonify({'ipv4': ipv4, 'ipv6': ipv6})


# ─── Tomorrow's Trade Probability ─────────────────────────────────────────────


@app.route('/api/trade_probability')
def trade_probability():
    """
    Calculates probability of taking a trade tomorrow.
    Weighted scoring across 4 factors (total = 100 pts):
      1. Day / Schedule check   → 0 or 35 pts
      2. IV Filter condition    → 0–25 pts
      3. Market Regime (ADX)    → 0–20 pts
      4. High-Impact News (24h) → 0–20 pts
    """
    import requests as req
    from datetime import datetime, timezone, timedelta

    try:
        from utils import get_ist_now
        now_ist = get_ist_now()
    except Exception:
        now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

    tomorrow_ist     = now_ist + timedelta(days=1)
    tomorrow_weekday = tomorrow_ist.weekday()   # 0=Mon … 6=Sun
    day_names        = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    tomorrow_name    = day_names[tomorrow_weekday]
    skip_days        = []   # Fri / Sat / Sun - Disabled (Trade all 7 days)

    factors = []
    score   = 0

    # ── 1. Day / Schedule (35 pts) ───────────────────────────────────────────
    if tomorrow_weekday in skip_days:
        day_score, day_label, day_status = 0, f"Skip day ({tomorrow_name})", "bad"
    else:
        day_score, day_label, day_status = 35, f"Trading day ({tomorrow_name})", "good"
    score += day_score
    factors.append({'name': 'Schedule', 'score': day_score, 'max': 35,
                    'label': day_label, 'status': day_status})

    # ── 2. IV Filter (25 pts) ────────────────────────────────────────────────
    current_iv = getattr(bot_engine, 'current_iv', 0.0)  if bot_engine else 0.0
    avg_5d_iv  = getattr(bot_engine, 'avg_7d_iv',  0.0)  if bot_engine else 0.0
    iv_lower   = current_iv > 0.35
    iv_upper   = avg_5d_iv > 0 and current_iv < 0.92 * avg_5d_iv

    if iv_lower and iv_upper:
        iv_score, iv_label, iv_status = 25, f"IV {current_iv:.1f}% — Filter PASS", "good"
    elif iv_lower:
        iv_score, iv_label, iv_status = 10, f"IV {current_iv:.1f}% — High vs 5d avg", "neutral"
    else:
        iv_score, iv_label, iv_status = 0,  f"IV {current_iv:.1f}% — Too low (<0.35)", "bad"
    score += iv_score
    factors.append({'name': 'IV Environment', 'score': iv_score, 'max': 25,
                    'label': iv_label, 'status': iv_status})

    # ── 3. Market Regime / ADX (20 pts) ─────────────────────────────────────
    adx = getattr(bot_engine, 'current_adx_value', 0.0) if bot_engine else 0.0
    if adx == 0:
        adx_score, adx_label, adx_status = 10, "Regime unknown (ADX=0)", "neutral"
    elif adx < 20:
        adx_score, adx_label, adx_status = 20, f"Ranging strongly (ADX={adx:.1f})", "good"
    elif adx < 25:
        adx_score, adx_label, adx_status = 15, f"Mildly ranging (ADX={adx:.1f})", "good"
    elif adx < 35:
        adx_score, adx_label, adx_status = 5,  f"Trending (ADX={adx:.1f})", "neutral"
    else:
        adx_score, adx_label, adx_status = 0,  f"Strong trend (ADX={adx:.1f})", "bad"
    score += adx_score
    factors.append({'name': 'Market Regime (ADX)', 'score': adx_score, 'max': 20,
                    'label': adx_label, 'status': adx_status})

    # ── 4. High-Impact News in next 24h (20 pts) ─────────────────────────────
    news_score, news_label, news_status, news_events = 20, "No high-impact news in 24h", "good", []
    try:
        r = req.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
        if r.status_code == 200:
            now_utc = datetime.now(timezone.utc)
            cutoff  = now_utc + timedelta(hours=24)
            for e in r.json():
                if e.get('impact') != 'High':
                    continue
                if e.get('country') not in ('USD', 'EUR', 'GBP', 'JPY', 'CNY'):
                    continue
                try:
                    dt = datetime.fromisoformat(e.get('date','').replace('Z','+00:00'))
                    if now_utc <= dt <= cutoff:
                        news_events.append(e.get('title','Unknown'))
                except Exception:
                    pass
            if news_events:
                news_score, news_label, news_status = 0, f"{len(news_events)} high-impact event(s) in 24h", "bad"
    except Exception:
        news_score, news_label, news_status = 10, "News feed unavailable", "neutral"
    score += news_score
    factors.append({'name': 'High-Impact News (24h)', 'score': news_score, 'max': 20,
                    'label': news_label, 'status': news_status})

    # ── Final score ───────────────────────────────────────────────────────────
    prob = 0 if tomorrow_weekday in skip_days else max(0, min(100, score))

    if prob >= 80:
        verdict, verdict_level = "High chance — Conditions look excellent", "high"
    elif prob >= 55:
        verdict, verdict_level = "Moderate chance — Bot may trade tomorrow", "medium"
    elif prob >= 25:
        verdict, verdict_level = "Low chance — Unfavorable conditions", "low"
    else:
        verdict, verdict_level = "Very unlikely — Trade will almost certainly be skipped", "none"

    return jsonify({
        'probability':   prob,
        'verdict':       verdict,
        'verdict_level': verdict_level,
        'tomorrow_day':  tomorrow_name,
        'factors':       factors,
        'news_events':   news_events[:5],
        'calculated_at': now_ist.strftime('%H:%M IST')
    })

@app.route('/api/journal')
def get_journal():
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    journal_file = os.path.join(base_dir, "scratch", "pro_trader_journal.md")
    if os.path.exists(journal_file):
        try:
            with open(journal_file, 'r') as f:
                content = f.read()
            return jsonify({'success': True, 'content': content})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True, 'content': '📓 *No diary entries recorded yet. The first entry will appear automatically once a trade completes!*'})
@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/api/history')
def get_trade_history():
    mode = request.args.get('mode', 'PAPER').upper()
    if bot_engine and getattr(bot_engine, 'performance_tracker', None):
        pt = bot_engine.performance_tracker
        if mode == 'LIVE':
            return jsonify({"trades": pt.live_trades, "max_equity": pt.live_max_equity})
        else:
            return jsonify({"trades": pt.trades, "max_equity": pt.max_equity})

    import db_manager
    if db_manager.is_connected():
        data = db_manager.load_all_data()
        if data:
            if "bot_state" in data:
                state = data["bot_state"]
            else:
                state = data
                
            if mode == 'LIVE':
                return jsonify({"trades": state.get("live_trades", []), "max_equity": state.get("live_max_equity", 0.0)})
            else:
                return jsonify({"trades": state.get("trades", []), "max_equity": state.get("max_equity", 0.0)})
            
    # Fallback to local JSON if cloud fails
    import os, json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    filename = 'live_trade_history.json' if mode == 'LIVE' else 'trade_history.json'
    history_file = os.path.join(base_dir, filename)
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return jsonify(data)
        except Exception as e:
            app_logger.error(f"Failed to read {filename}: {e}")
    return jsonify({"max_equity": 0.0, "trades": []})

@app.route('/api/last_backup_time')
def last_backup_time():
    import db_manager
    return jsonify({"time": db_manager.get_last_backup_time()})

@app.route('/api/backup_history', methods=['POST'])
def backup_history():
    """Manually trigger a backup to the Secondary Cloud Backup."""
    try:
        import db_manager
        
        # Load from the primary database
        primary_data = db_manager.load_all_data()
        
        if not primary_data or not primary_data.get('trades'):
            return jsonify({"success": False, "message": "Primary database is empty. Nothing to backup."}), 400
            
        # Overwrite the secondary database with the primary
        success = db_manager.save_backup_data(primary_data)
        if success:
            return jsonify({"success": True, "message": f"Successfully backed up {len(primary_data['trades'])} trades to Secondary Cloud DB."})
        else:
            return jsonify({"success": False, "message": "Failed to save to Secondary Cloud DB."}), 500
    except Exception as e:
        app_logger.error(f"Error backing up history: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/restore_history', methods=['POST'])
def restore_history():
    """Restores the cloud trade history from the Secondary Cloud Backup or Local File."""
    try:
        import db_manager
        import os, json
        
        # Load from the indestructible secondary backup
        backup_data = db_manager.load_backup_data()
        
        if not backup_data or not backup_data.get('trades'):
            app_logger.warning("Secondary backup empty. Attempting local restore...")
            local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
            if os.path.exists(local_file):
                with open(local_file, 'r') as f:
                    backup_data = json.load(f)
                    
        if not backup_data or not backup_data.get('trades'):
            return jsonify({"success": False, "message": "Secondary backup and local backup are both empty or could not be loaded."}), 400
            
        # Overwrite the primary database with the backup
        success = db_manager.save_all_data(backup_data)
        if success:
            return jsonify({"success": True, "message": f"Successfully restored {len(backup_data.get('trades', []))} trades to Primary Cloud DB."})
        else:
            return jsonify({"success": False, "message": "Failed to overwrite Primary Cloud DB."}), 500
    except Exception as e:
        app_logger.error(f"Error restoring history: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/pnl_chart')
def get_pnl_chart():
    """Returns engine-isolated P&L chart data for the current active trade.
    Query parameter: ?engine=live or ?engine=paper (defaults to current execution mode).
    Stores 1 point per minute so a full 9AM-5PM day = max ~480 pts.
    """
    if not bot_engine:
        return jsonify({"points": [], "active": False})

    req_engine = request.args.get('engine', '').strip().upper()
    current_mode = getattr(bot_engine.execution, 'mode', 'PAPER')
    engine_mode = req_engine if req_engine in ('LIVE', 'PAPER') else current_mode

    if engine_mode == 'LIVE':
        live_positions = getattr(bot_engine.execution, 'live_active_positions', {})
        real_positions = {k: v for k, v in live_positions.items() if not k.startswith('__')}
        has_trade = bool(real_positions)

        chart_data = list(getattr(bot_engine, 'live_pnl_chart_data', []))
        if current_mode == 'LIVE' and len(chart_data) == 0:
            chart_data = list(getattr(bot_engine, 'pnl_chart_data', []))
            
        trail_state = bot_engine.risk_manager.get_live_trailing_state()
        
        # Calculate live entry premium
        total_entry_premium = 0.0
        for sym, d in real_positions.items():
            lots = d.get('entry_size', d.get('size', 0))
            ep = d.get('entry_price', 0)
            total_entry_premium += ep * lots * LOT_TO_BTC

        if not has_trade and len(chart_data) == 0:
            return jsonify({
                "active": False,
                "engine": "LIVE",
                "points": [],
                "message": "Zero active live positions on Delta Exchange.",
                "trail_state": trail_state,
                "total_entry_premium": 0.0
            })

        return jsonify({
            "active": has_trade or len(chart_data) > 0,
            "engine": "LIVE",
            "points": chart_data,
            "total_points": len(chart_data),
            "trail_state": trail_state,
            "total_entry_premium": round(total_entry_premium, 6)
        })

    else:
        # PAPER engine
        paper_positions = getattr(bot_engine.execution, 'paper_active_positions', {})
        real_positions = {k: v for k, v in paper_positions.items() if not k.startswith('__')}
        has_trade = bool(real_positions)

        chart_data = list(getattr(bot_engine, 'paper_pnl_chart_data', []))
        if len(chart_data) == 0 and current_mode == 'PAPER':
            chart_data = list(getattr(bot_engine, 'pnl_chart_data', []))

        total_entry_premium = getattr(bot_engine, 'total_entry_premium', 0)
        trail_state = bot_engine.risk_manager.get_paper_trailing_state()

        if len(chart_data) == 0 and not has_trade:
            return jsonify({
                "active": False,
                "engine": "PAPER",
                "points": [],
                "message": "Waiting for paper trade data...",
                "trail_state": trail_state,
                "total_entry_premium": 0.0
            })

        # Fallback if chart_data empty but trade active
        if len(chart_data) == 0 and has_trade:
            try:
                from utils import get_ist_now
                collected_premium = 0.0
                current_option_value = 0.0
                for sym, data in real_positions.items():
                    lots = data.get('entry_size', data.get('size', 0))
                    ep = data.get('entry_price', 0)
                    cp = data.get('last_good_price', ep)
                    collected_premium += ep * lots * LOT_TO_BTC
                    current_option_value += cp * lots * LOT_TO_BTC
                opt_profit = collected_premium - current_option_value
                if total_entry_premium <= 0:
                    total_entry_premium = collected_premium
                chart_data.append({
                    "t": get_ist_now().strftime("%H:%M"),
                    "pnl": round(opt_profit, 4),
                    "hedge": 0.0,
                    "total": round(opt_profit, 4)
                })
            except Exception as e:
                app_logger.error(f"Error creating synthetic chart point: {e}")

        return jsonify({
            "active": has_trade or len(chart_data) > 0,
            "engine": "PAPER",
            "points": chart_data,
            "total_points": len(chart_data),
            "trail_state": trail_state,
            "total_entry_premium": round(total_entry_premium, 6)
        })

@app.route('/api/runtime_state')
def get_runtime_state():
    """Single Source of Truth endpoint. All dashboard widgets should read from here."""
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
    rs = getattr(bot_engine, 'runtime_state', None)
    if not rs:
        return jsonify({'error': 'Runtime state not initialized'}), 500
    return jsonify(rs.to_dict())

@app.route('/api/live_equity')
def get_live_equity_api():
    try:
        if bot_engine and bot_engine.api_client:
            res = bot_engine.api_client.get_balances()
            if res and res.get('success'):
                equity_val = 0.0
                for b in res.get('result', []):
                    try:
                        # Grab equity, fallback to balance or available_balance
                        raw_val = str(b.get('equity', b.get('balance', b.get('available_balance', 0))))
                        val = float(raw_val.replace(',', ''))
                        if val > equity_val:
                            equity_val = val
                    except:
                        pass
                return jsonify({"equity": equity_val})
            else:
                app_logger.error(f"API request for live equity failed or returned false success: {res}")
    except Exception as e:
        app_logger.error(f"Failed to fetch live equity for history tab: {e}")
    return jsonify({"equity": 0.0})

@app.route('/api/system_health')
def get_system_health():
    """Permanent diagnostics panel endpoint for dashboard health monitoring."""
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
    
    health = {
        'delta_api': 'ONLINE' if getattr(bot_engine.api_client, 'ws_connected', False) else 'OFFLINE',
        'websocket': 'CONNECTED' if getattr(bot_engine.api_client, 'ws_connected', False) else 'DISCONNECTED',
        'position_sync': 'SYNCED' if bot_engine.execution.active_positions is not None else 'ERROR',
        'iv_feed': 'ONLINE' if getattr(bot_engine, 'current_iv', 0) > 0 else 'OFFLINE',
        'premium_feed': 'ONLINE' if bot_engine.api_client.last_price_update_time > 0 else 'OFFLINE',
        'hedge_engine': 'ONLINE' if getattr(bot_engine, 'smart_hedging', None) else 'OFFLINE',
        'graph_feed': 'ACTIVE' if len(getattr(bot_engine, 'pnl_chart_data', [])) > 0 else 'WAITING',
        'audit_system': 'ONLINE',
        'database_sync': 'ONLINE',
        'hot_recovery': 'READY',
        'last_heartbeat': round(time.time()),
        'last_price_update': round(bot_engine.api_client.last_price_update_time, 0),
        'data_age_seconds': round(time.time() - bot_engine.api_client.last_price_update_time) if bot_engine.api_client.last_price_update_time > 0 else 999,
        'last_error': getattr(bot_engine.runtime_state, 'last_error', '') if hasattr(bot_engine, 'runtime_state') else '',
        'backend_version': '2.0.0',
        'engine_uptime_seconds': round(time.time() - getattr(bot_engine, '_engine_start_ts', time.time())),
    }
    
    # DVOL Provider
    if getattr(bot_engine, 'dvol_provider', None):
        health['dvol_feed'] = 'ONLINE' if bot_engine.dvol_provider.current_dvol > 0 else 'OFFLINE'
        health['dvol_value'] = round(bot_engine.dvol_provider.current_dvol, 2)
    
    # ARES
    if ares_runner:
        try:
            health['ares_status'] = 'ACTIVE' if getattr(ares_runner.orchestrator, 'latest_tick_result', None) else 'STANDBY'
        except:
            health['ares_status'] = 'ERROR'
    else:
        health['ares_status'] = 'NOT_INITIALIZED'
    
    return jsonify(health)

@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    """Runs the advanced strangle backtest and returns metrics and curve data."""
    try:
        from backtester import AdvancedBacktester
        
        data = request.get_json(force=True) or {}
        starting_capital = float(data.get('starting_capital', 50000.0))
        start_str = data.get('start_date')
        end_str = data.get('end_date')
        
        days = 90
        if start_str and end_str:
            from datetime import date
            try:
                s_dt = date.fromisoformat(start_str)
                e_dt = date.fromisoformat(end_str)
                days = (e_dt - s_dt).days
                if days <= 0:
                    days = 90
            except Exception:
                pass
                
        app_logger.info(f"Web: Running backtest for {days} days, capital: ${starting_capital}...")
        backtester = AdvancedBacktester(starting_capital=starting_capital)
        results = backtester.run(days=days, start_date=start_str, end_date=end_str)
        
        return jsonify({
            'success': True,
            'metrics': results.get('metrics', {}),
            'trades': results.get('trades', [])[:100],  # Limit trade logs to avoid overloading
            'equity_curve': results.get('equity_curve', [])
        }), 200
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app_logger.error(f"Web [backtest]: Backtester error: {e}\n{tb}")
        return jsonify({'success': False, 'error': str(e)}), 500



# ====================================================
# ARES INTEGRATION ROUTES (SAFE MODE)
# ====================================================

@app.route('/ares/dashboard')
def ares_dashboard():
    if not ares_runner:
        return render_template('ares_disabled.html')
    return render_template('ares_dashboard.html')

@app.route('/ares/health')
def ares_health():
    if not ares_runner:
        return jsonify({'status': 'DISABLED', 'ares_enabled': False})
    return jsonify({'status': 'UP', 'ares_enabled': True, 'mode': ares_runner.config.mode})

@app.route('/ares/status')
def ares_status():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    
    # Use get_live_stats() — the actual method on ShadowAnalytics
    try:
        analytics = ares_runner.analytics.get_live_stats()
    except Exception:
        analytics = {}
        
    # Use get_system_health() — the actual method on deployment HealthMonitor
    try:
        health_data = ares_runner.health_monitor.get_system_health()
        health = health_data.get('status', 'UNKNOWN')
    except Exception:
        health = 'UNKNOWN'
        health_data = {}
        
    try:
        portfolio_hash = ares_runner.pipeline_validator.validator.analytics.metrics.get('portfolio_hash', 'N/A')
    except:
        portfolio_hash = 'N/A'
    
    # Extract latest tick result for richer data
    tick_result = getattr(ares_runner.orchestrator, 'latest_tick_result', None)
    
    # Build risk info from tick result
    risk_level = 'LOW'
    hedge_active = False
    # Build complete decision telemetry from tick result
    trend_strength = 0.0
    market_regime = 'WAITING'
    recovery_prob = 0.0
    confidence = 0.0
    risk_score = 0.0
    expected_loss = 0.0
    recommended_size = 0.0
    decision_reason = 'Initializing'
    decision_action = 'WAITING'
    clusters = {
        'directional': 0.0,
        'volatility': 0.0,
        'financial': 0.0,
        'context': 0.0,
        'final_stress': 0.0
    }

    if tick_result:
        trend_res = getattr(tick_result, 'trend_result', None)
        if trend_res:
            trend_strength = getattr(trend_res, 'trend_strength', 0.0)
            
        regime_res = getattr(tick_result, 'regime_result', None)
        if regime_res and hasattr(regime_res, 'current_regime'):
            market_regime = regime_res.current_regime.name
            
        risk_result = getattr(tick_result, 'risk_result', None)
        
        if risk_result:
            risk_level = getattr(risk_result, 'risk_level', 'LOW')
            if hasattr(risk_level, 'name'):
                risk_level = risk_level.name
            risk_score = getattr(risk_result, 'overall_risk_score', 0.0)
            recovery_prob = getattr(risk_result, 'recovery_probability', 0.0)
            expected_loss = getattr(risk_result, 'call_stress', 0.0) + getattr(risk_result, 'put_stress', 0.0)
            
            # Extract cluster math for UI
            try:
                # Find the leg with the highest stress to show its clusters
                breakdown = getattr(risk_result, 'call_breakdown', None)
                if not breakdown or getattr(risk_result, 'put_stress', 0.0) > getattr(risk_result, 'call_stress', 0.0):
                    breakdown = getattr(risk_result, 'put_breakdown', None)
                    
                if breakdown and hasattr(breakdown, 'fusion_breakdown') and breakdown.fusion_breakdown:
                    fb = breakdown.fusion_breakdown
                    # Normalize to 0.0-1.0 scale (scores are 0-100 internally, JS multiplies by 100)
                    clusters['directional'] = min(1.0, max(0.0, getattr(fb.directional_cluster, 'score', 0.0) / 100.0))
                    clusters['volatility'] = min(1.0, max(0.0, getattr(fb.volatility_cluster, 'score', 0.0) / 100.0))
                    clusters['financial'] = min(1.0, max(0.0, getattr(fb.financial_cluster, 'score', 0.0) / 100.0))
                    clusters['context'] = min(1.0, max(0.0, getattr(fb.context_cluster, 'score', 0.0) / 100.0))
                    clusters['final_stress'] = min(1.0, max(0.0, getattr(fb, 'fused_score', 0.0) / 100.0))
            except Exception as e:
                pass
            
        hedge_decision = getattr(tick_result, 'hedge_decision', None)
        if hedge_decision:
            action = getattr(hedge_decision, 'action', None)
            if action:
                decision_action = action.name if hasattr(action, 'name') else str(action)
                if decision_action != 'HOLD':
                    hedge_active = True
            decision_reason = getattr(hedge_decision, 'reason', 'No Reason')
            confidence = getattr(hedge_decision, 'confidence', 0.0)
            
        sizing_res = getattr(tick_result, 'hedge_sizing', None)
        if sizing_res:
            recommended_size = getattr(sizing_res, 'target_delta', 0.0)

    # --- Module 49: Live Protection Efficiency KPIs ---
    option_mtm = 0.0
    hedge_mtm = 0.0
    combined_mtm = 0.0
    protection_pct = 0.0
    
    actual_hedge_size = 0.0
    options_delta = analytics.get('current_portfolio_delta', 0.0)
    delta_coverage_pct = 0.0
    
    if bot_engine and getattr(bot_engine, 'execution', None):
        # 1. Option MTM
        for sym, data in bot_engine.execution.active_positions.items():
            entry_p = data.get('entry_price', 0)
            size = data.get('entry_size', data.get('size', 0))
            
            # Find current price
            current_p = entry_p
            try:
                ws_data = bot_engine.api_client.get_realtime_ticker(sym)
                if ws_data:
                    current_p = float(ws_data.get('mark_price') or entry_p)
            except:
                pass
                
            btc_qty = size * LOT_TO_BTC
            # Option is sold, so profit = entry - current
            option_mtm += (entry_p - current_p) * btc_qty
            
        # 2. Hedge MTM and Delta Coverage
        actual_hedge_size = bot_engine.execution.hedge_size_btc
        if abs(actual_hedge_size) > 0:
            hedge_entry = bot_engine.execution.hedge_entry_price
            current_btc = ares_runner.orchestrator.market_data_provider.get_latest_data().get('spot_price', 0)
            # GUARD: Only calculate hedge MTM if entry price is valid and reasonable
            if current_btc > 0 and hedge_entry > 0 and abs(current_btc - hedge_entry) / hedge_entry < 0.5:
                if actual_hedge_size > 0: # Long hedge
                    hedge_mtm = (current_btc - hedge_entry) * actual_hedge_size
                else: # Short hedge
                    hedge_mtm = (hedge_entry - current_btc) * abs(actual_hedge_size)
            elif hedge_entry <= 0:
                hedge_mtm = 0.0  # Entry price not set yet, skip
                    
            if abs(options_delta) > 0.0001:
                delta_coverage_pct = round((abs(actual_hedge_size) / abs(options_delta)) * 100, 2)
            else:
                delta_coverage_pct = 100.0
                    
        # 3. Combined MTM & Protection
        combined_mtm = option_mtm + hedge_mtm
        
        if option_mtm < 0 and hedge_mtm > 0:
            protection_pct = round((abs(hedge_mtm) / abs(option_mtm)) * 100, 2)
            if protection_pct > 100.0: protection_pct = 100.0

    # --- INTRA-DAY TREND OVERRIDE ---
    # The UI wants the trend since trade entry, not the 24h moving average.
    intraday_trend = "WAITING"
    
    if bot_engine and bot_engine.current_trade_info.get("calls"):
        btc_entry = bot_engine.current_trade_info.get("btc_entry_price", 0.0)
        current_btc = analytics.get('btc_price', 0.0)
        if current_btc == 0.0 and getattr(ares_runner.orchestrator, 'market_data_provider', None):
            current_btc = ares_runner.orchestrator.market_data_provider.get_latest_data().get('spot_price', 0.0)
            
        if btc_entry > 0 and current_btc > 0:
            pct_change = ((current_btc - btc_entry) / btc_entry) * 100.0
            
        # Get the highly accurate ADX + RSI + BB Multi-Indicator signal from the Filter
        try:
            detailed_signal = getattr(bot_engine.filters, 'last_detailed_signal', 'WAITING')
            market_regime = detailed_signal
            trend_strength = getattr(bot_engine, 'current_adx_value', trend_strength)
        except Exception:
            pass
        
    res = {
        'bot_mode': ares_runner.config.mode,
        'exchange_status': 'CONNECTED' if getattr(ares_runner.orchestrator.execution_provider, 'is_connected', False) else 'DISCONNECTED',
        'btc_price': ares_runner.orchestrator.market_data_provider.get_latest_data().get('spot_price', 0),
        'portfolio_value': analytics.get('daily_pnl', 0) + 10000,
        'pnl': analytics.get('daily_pnl', 0),
        'total_delta': analytics.get('current_portfolio_delta', 0),
        'current_risk': risk_level,
        'active_hedge': 'ACTIVE' if hedge_active else 'NONE',
        'margin_used': analytics.get('margin_utilization', 0),
        'cpu': health_data.get('cpu_percent', 0),
        'ram': health_data.get('ram_percent', 0),
        'event_bus': 'ONLINE',
        'health_status': health,
        'portfolio_hash': portfolio_hash,
        'total_ticks': analytics.get('total_ticks', 0),
        'avg_latency': analytics.get('average_latency_ms', 0),
        'max_drawdown': analytics.get('max_drawdown', 0),
        'pipeline_latency': getattr(tick_result, 'pipeline_latency', 0) if tick_result else 0,
        'provider_health': getattr(tick_result, 'provider_health', 'N/A') if tick_result else 'N/A',
        'option_mtm': round(option_mtm, 2),
        'hedge_mtm': round(hedge_mtm, 2),
        'combined_mtm': round(combined_mtm, 2),
        'protection_pct': protection_pct,
        'trend_strength': trend_strength,
        'market_regime': market_regime,
        'intraday_trend': intraday_trend,
        'recovery_probability': recovery_prob,
        'confidence': confidence,
        'risk_score': risk_score,
        'expected_future_loss': expected_loss,
        'recommended_hedge_size': recommended_size,
        'decision_reason': decision_reason,
        'decision_action': decision_action,
        'actual_hedge_size': actual_hedge_size,
        'options_delta': options_delta,
        'delta_coverage_pct': delta_coverage_pct,
        'clusters': clusters
    }
    return jsonify(res)

@app.route('/ares/orders')
def ares_orders():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    if not ares_runner.store:
        return jsonify({'error': 'Store not initialized'}), 500
        
    orders = getattr(ares_runner.store, 'get_execution_orders', lambda: [])()
    # Also check state machine for live orders
    if not orders:
        try:
            orders = ares_runner.orchestrator.state_machine.get_all_orders()
        except Exception:
            orders = []
    res = []
    for order in orders:
        res.append({
            'client_order_id': getattr(order, 'client_order_id', ''),
            'timestamp': str(getattr(order, 'timestamp', '')),
            'symbol': getattr(order, 'symbol', ''),
            'side': order.side.name if hasattr(order, 'side') else '',
            'quantity': getattr(order, 'quantity', 0),
            'price': getattr(order, 'price', 0),
            'average_fill_price': getattr(order, 'average_fill_price', getattr(order, 'price', 0)),
            'state': order.state.name if hasattr(order, 'state') else ''
        })
    return jsonify(res)

@app.route('/ares/risk')
def ares_risk():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    metrics = getattr(ares_runner.orchestrator.risk_engine, 'last_risk_evaluation', {})
    return jsonify(metrics)

@app.route('/ares/portfolio')
def ares_portfolio():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    # PaperExecutionProvider uses fetch_position() not get_positions()
    positions = []
    try:
        pos = ares_runner.orchestrator.execution_provider.fetch_position()
        if pos:
            positions = [pos] if isinstance(pos, dict) else [pos]
    except Exception:
        pass
    
    # Also get portfolio snapshot from orchestrator
    snapshot = getattr(ares_runner.orchestrator.portfolio_sync, 'latest_snapshot', None)
    
    res = []
    for pos in positions:
        if isinstance(pos, dict):
            res.append(pos)
        else:
            res.append({
                'symbol': getattr(pos, 'symbol', 'BTCUSD'),
                'quantity': getattr(pos, 'quantity', 0),
                'average_entry_price': getattr(pos, 'average_entry_price', 0),
                'unrealized_pnl': getattr(pos, 'unrealized_pnl', 0)
            })
    
    # Add snapshot data if available
    if snapshot:
        res_data = {'positions': res}
        for attr in ['net_delta', 'net_gamma', 'net_vega', 'net_theta', 'margin_used', 'available_margin', 'portfolio_value']:
            res_data[attr] = getattr(snapshot, attr, None)
        return jsonify(res_data)
    
    return jsonify(res)

@app.route('/ares/analytics')
def ares_analytics():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    # ShadowAnalytics uses get_live_stats() not get_summary()
    metrics = ares_runner.analytics.get_live_stats()
    return jsonify(metrics)

@app.route('/ares/system')
def ares_system():
    import threading
    res = {'active_threads': threading.active_count()}
    try:
        import psutil
        res['cpu_percent'] = psutil.cpu_percent()
        res['memory_percent'] = psutil.virtual_memory().percent
    except ImportError:
        res['cpu_percent'] = 0.0
        res['memory_percent'] = 0.0
    return jsonify(res)

@app.route('/ares/provider')
def ares_provider():
    if not ares_runner:
        return jsonify({'error': 'ARES not initialized'}), 500
    prov = ares_runner.orchestrator.execution_provider
    res = {
        'connected': getattr(prov, 'is_connected', False),
        'type': prov.__class__.__name__
    }
    return jsonify(res)

@app.route('/ares/logs')
def ares_logs():
    import os
    # Read the last 50 lines from the system log (trading_bot.log) and ares log
    logs = []
    try:
        with open('trading_bot.log', 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            logs.extend([line.strip() for line in lines[-50:]])
    except Exception as e:
        logs.append(f"Error reading trading_bot.log: {e}")

    try:
        ares_log_path = os.path.join("logs", "system.log")
        if os.path.exists(ares_log_path):
            with open(ares_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                if lines:
                    logs.append("--- ARES SYSTEM LOGS ---")
                    logs.extend([line.strip() for line in lines[-30:]])
    except Exception as e:
        pass

    if not logs:
        logs = ['No logs found.']
    return jsonify({'logs': logs})

