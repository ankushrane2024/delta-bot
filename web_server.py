from flask import Flask, render_template, jsonify, request
from logger import app_logger
from config import LOT_TO_BTC
import os

app = Flask(__name__, template_folder='templates')

# Global reference to the engine
bot_engine = None
ares_runner = None

def init_web_server(engine):
    global bot_engine
    bot_engine = engine

def set_ares_runner(runner):
    global ares_runner
    ares_runner = runner

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/ping')
def ping():
    # Lightweight endpoint for Keep-Alive pinger and UptimeRobot
    return "OK", 200

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

@app.route('/api/status')
def get_status():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
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
    from datetime import datetime, timezone, timedelta
    positions = []
    
    # Get trade status from engine for position cards
    trail_state = bot_engine.risk_manager.get_trailing_state()
    total_entry_premium = getattr(bot_engine, 'total_entry_premium', 0)
    
    # Compute time remaining to 17:00 IST
    try:
        from utils import get_ist_now
        now_ist = get_ist_now()
        target_ist = now_ist.replace(hour=17, minute=0, second=0, microsecond=0)
        if now_ist >= target_ist:
            mins_remaining = 0
        else:
            mins_remaining = int((target_ist - now_ist).total_seconds() / 60)
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
        # Fallback 2: fetch from API tickers
        try:
            res_btc = bot_engine.api_client.get_tickers({'symbol': 'BTCUSD'})
            if res_btc.get('success') and res_btc.get('result'):
                for ticker in res_btc['result']:
                    if ticker.get('symbol') == 'BTCUSD':
                        btc_price = float(ticker.get('mark_price') or ticker.get('close') or ticker.get('last_price') or 0)
                        break
        except Exception as btc_err:
            app_logger.debug(f"Web status: Failed to get BTC price from REST fallback: {btc_err}")
            
    if not btc_price or btc_price <= 0:
        # Fallback 3: check if bot_engine has cached btc price in btc_price_history
        if getattr(bot_engine, 'btc_price_history', None) and len(bot_engine.btc_price_history) > 0:
            btc_price = bot_engine.btc_price_history[-1][1]
            
    if not btc_price or btc_price <= 0:
        # Fallback 4: Binance public API
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                if 'price' in data:
                    btc_price = float(data['price'])
        except Exception:
            pass
            
    # Absolute fallback (e.g. 70000) so we never crash/divide by zero
    if not btc_price or btc_price <= 0:
        btc_price = 70000.0

    for sym, data in bot_engine.execution.active_positions.items():
        entry_price = data.get('entry_price', 0)
        # Use entry_size if available to prevent inflated PnL calculations on re-entries, just like bot_engine.py
        size = data.get('entry_size', data.get('size', 0))
        leg_type = data.get('leg_type', 'unknown')
        entry_time_str = data.get('entry_time', '')
        strike = data.get('strike', 0)
        
        # Live price from WebSocket / HTTP cache
        current_price = entry_price  # fallback to entry_price if no live data
        delta_val = 0.0
        gamma_val = 0.0
        try:
            ws_data = bot_engine.api_client.get_realtime_ticker(sym)
            if ws_data and 'mark_price' in ws_data:
                candidate_price = float(ws_data['mark_price'])
                
                # ── Price Sanity Guard ──────────────────────────────────────────
                # Reject garbage data (e.g. $0.01 after WS reconnect) but ALLOW
                # legitimate violent moves. Options CAN double/triple during a
                # flash crash (200-300% premium spike is real). Using 10x (1000%)
                # threshold so the dashboard never hides real market damage.
                price_is_valid = (
                    candidate_price > 0.01 and               # must be positive
                    entry_price > 0 and                       # need entry to compare
                    abs(candidate_price - entry_price) / entry_price < 10.0  # max 1000% move
                )
                
                if price_is_valid:
                    current_price = candidate_price
                    # Update last-known-good price in the position store
                    data['last_good_price'] = candidate_price
                    greeks = ws_data.get('greeks') or {}
                    delta_val = float(greeks.get('delta', 0))
                    gamma_val = float(greeks.get('gamma', 0))
                else:
                    # Use last known-good price if available, otherwise entry price
                    lgp = data.get('last_good_price')
                    if lgp and lgp > 0.01:
                        current_price = lgp
                        app_logger.debug(
                            f"Status: Rejected bad live price {candidate_price:.4f} for {sym} "
                            f"(entry={entry_price:.4f}). Using last_good_price={lgp:.4f}"
                        )
                    else:
                        current_price = entry_price  # absolute fallback
                        app_logger.debug(
                            f"Status: Rejected bad live price {candidate_price:.4f} for {sym}. "
                            f"Falling back to entry_price={entry_price:.4f}"
                        )
                
        except Exception as ex:
            app_logger.debug(f"Status: Price fetch error for {sym}: {ex}")
        
        # P&L for this leg (short position: profit = entry - current)
        # Formula: PnL = (Entry_Premium - Current_Premium) * BTC_Quantity
        # where BTC_Quantity = Number_of_Lots * LOT_TO_BTC (0.001 BTC per lot)
        btc_quantity = size * LOT_TO_BTC
        leg_pnl_usd = (entry_price - current_price) * btc_quantity
        leg_pnl_inr = leg_pnl_usd * 95.5  # Updated July 2026 INR rate
        
        # P&L Percentage (1 lot = 0.001 BTC)
        leg_entry_premium_total = entry_price * btc_quantity
        leg_pnl_pct_premium = (leg_pnl_usd / leg_entry_premium_total * 100) if leg_entry_premium_total > 0 else 0.0
        
        leg_capital_used = size * LOT_TO_BTC * btc_price
        leg_pnl_pct_capital = (leg_pnl_usd / leg_capital_used * 100) if leg_capital_used > 0 else 0.0
        
        # Trade status label
        if trail_state['trailing_confirmed'] and trail_state['current_trailing_sl'] is not None:
            trade_status = f"Locked +{trail_state['current_trailing_sl']}% SL"
        elif len(bot_engine.execution.active_positions) > 0:
            trade_status = "Running"
        else:
            trade_status = "Unknown"
        
        positions.append({
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
    
    # Hedge Status (ARES Engine Integration)
    hedge_status = {}
    hedge_pnl_usd = 0.0
    
    if getattr(bot_engine, 'ares_runner', None) and getattr(bot_engine.ares_runner, 'orchestrator', None):
        ares_orch = bot_engine.ares_runner.orchestrator
        tick_result = getattr(ares_orch, 'latest_tick_result', None)
        decision_engine = getattr(ares_orch, 'decision_engine', None)
        
        hedge_percentage = 0.0
        hedge_type = "Standby"
        hedge_active = False
        
        if tick_result and getattr(tick_result, 'hedge_decision', None):
            action_name = tick_result.hedge_decision.action.name
            if action_name == "PARTIAL_HEDGE": 
                hedge_percentage = 50.0
                hedge_type = "Partial (Tier 1)"
                hedge_active = True
            elif action_name in ["FULL_HEDGE", "EMERGENCY_HEDGE"]:
                hedge_percentage = 100.0
                hedge_type = "Full (Emergency)"
                hedge_active = True
            elif action_name == "DEHEDGE":
                hedge_percentage = 0.0
                hedge_type = "Dehedged"
                
        actual_hedge_size = bot_engine.execution.hedge_size_btc
        hedge_entry = bot_engine.execution.hedge_entry_price
        current_btc = (ares_orch.market_data_provider.get_latest_data() or {}).get('spot_price', 0)
        
        if current_btc > 0 and hedge_entry > 0 and abs(actual_hedge_size) > 0:
            direction_mult = 1 if actual_hedge_size > 0 else -1
            hedge_pnl_usd = (current_btc - hedge_entry) * abs(actual_hedge_size) * direction_mult
            
        max_hedge_pnl = getattr(decision_engine, '_max_hedge_pnl', 0.0) if decision_engine else 0.0
        
        # Calculate bleeding leg details for dashboard
        start_pnl = getattr(decision_engine, '_hedge_start_bleeding_pnl', None) if decision_engine else None
        bleeding_leg_val = "None"
        bleeding_leg_loss_pct = 0.0
        remaining_sl_pct = 100.0
        options_pnl_live = 0.0
        combined_pnl_live = 0.0
        
        call_pnl = sum(p['leg_pnl_usd'] for p in positions if p['leg_type'] == 'call') if positions else 0.0
        put_pnl = sum(p['leg_pnl_usd'] for p in positions if p['leg_type'] == 'put') if positions else 0.0
        options_pnl_live = call_pnl + put_pnl
        combined_pnl_live = options_pnl_live + hedge_pnl_usd
        
        # Calculate individual leg loss percentages
        call_premium = 0.0
        put_premium = 0.0
        if tick_result and getattr(tick_result, 'portfolio_snapshot', None):
            snap_meta = tick_result.portfolio_snapshot.metadata
            call_leg = snap_meta.get('call_leg', {})
            put_leg = snap_meta.get('put_leg', {})
            call_premium = call_leg.get('entry_premium_usd', 0.0)
            put_premium = put_leg.get('entry_premium_usd', 0.0)
        
        if put_pnl < call_pnl and put_pnl < 0:
            bleeding_leg_loss_pct = (abs(put_pnl) / put_premium * 100.0) if put_premium > 0 else 0.0
            remaining_sl_pct = max(0.0, 100.0 - bleeding_leg_loss_pct)
            bleeding_leg_val = f"PUT (-{bleeding_leg_loss_pct:.1f}%)"
        elif call_pnl < put_pnl and call_pnl < 0:
            bleeding_leg_loss_pct = (abs(call_pnl) / call_premium * 100.0) if call_premium > 0 else 0.0
            remaining_sl_pct = max(0.0, 100.0 - bleeding_leg_loss_pct)
            bleeding_leg_val = f"CALL (-{bleeding_leg_loss_pct:.1f}%)"
        else:
            bleeding_leg_val = "None"
        
        # Get the decision reason for display
        decision_reason = ""
        if tick_result and getattr(tick_result, 'hedge_decision', None):
            decision_reason = tick_result.hedge_decision.reason or ""
        
        hedge_status = {
            'hedge_active': hedge_active,
            'hedge_percentage': hedge_percentage,
            'hedge_type': hedge_type,
            'hedge_size_btc': abs(actual_hedge_size),
            'hedge_pnl_usd': hedge_pnl_usd,
            'hedge_peak_pnl': max_hedge_pnl,
            'bleeding_leg': bleeding_leg_val,
            'bleeding_leg_loss_pct': bleeding_leg_loss_pct,
            'remaining_sl_pct': remaining_sl_pct,
            'options_pnl_live': options_pnl_live,
            'combined_pnl_live': combined_pnl_live,
            'decision_reason': decision_reason,
            'sl_tightened': False
        }
    else:
        hedge_status = bot_engine.smart_hedging.get_status() if getattr(bot_engine, 'smart_hedging', None) else {}
        hedge_pnl_usd = hedge_status.get('hedge_pnl_usd', 0.0)

    # Total P&L and Capital Used across all legs + Hedge
    options_pnl_usd = sum(pos['leg_pnl_usd'] for pos in positions) if positions else 0.0
    total_pnl_usd = round(options_pnl_usd + hedge_pnl_usd, 2)
    total_pnl_inr = round(total_pnl_usd * 95.5, 2)
    
    total_pnl_pct_premium = (total_pnl_usd / total_entry_premium * 100) if total_entry_premium > 0 else 0.0
    total_capital_used = round(sum(pos['leg_capital_used'] for pos in positions), 2) if positions else 0.0
    total_pnl_pct_capital = (total_pnl_usd / total_capital_used * 100) if total_capital_used > 0 else 0.0
    
    dvol_status = bot_engine.dvol_provider.get_status() if getattr(bot_engine, 'dvol_provider', None) else {}
    
    return jsonify({
        'is_running': bot_engine.is_running,
        'mode': getattr(bot_engine.execution, 'mode', 'UNKNOWN'),
        'equity': round(bot_engine.risk_manager.current_equity, 2),
        'daily_loss_hits': bot_engine.daily_loss_hits,
        'positions': positions,
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
        'performance': bot_engine.performance_tracker.get_metrics(bot_engine.risk_manager.current_equity),
        'rule_report': bot_engine.latest_rule_report,
        'schedule_info': bot_engine.get_schedule_info(),
        'regime_filter_enabled': bot_engine.market_regime_filter_enabled,
        'smart_hedging_enabled': getattr(bot_engine, 'smart_hedging_enabled', True),
        'current_market_regime': bot_engine.current_market_regime,
        'current_adx_value': bot_engine.current_adx_value,
        'adx_history': getattr(bot_engine, 'adx_history', []),
        'paper_lot_multiplier': getattr(bot_engine, 'paper_lot_multiplier', 1.0),
        'api_connected': bot_engine.api_client.ws_connected if bot_engine.api_client else False,
        'current_iv': getattr(bot_engine, 'current_iv', 0.0),
        'avg_7d_iv': getattr(bot_engine, 'avg_7d_iv', 0.0),
        'iv_status': getattr(bot_engine, 'iv_status', 'Normal'),
        'today_skip_reason': getattr(bot_engine, 'today_skip_reason', None),
        # New advanced metrics
        'dvol_status': dvol_status,
        'hedge_status': hedge_status,
        'size_multiplier': round(getattr(bot_engine, 'size_multiplier', 1.0), 2),
        'consecutive_loss_count': getattr(bot_engine, 'consecutive_loss_count', 0),
        'next_day_paused': getattr(bot_engine, 'next_day_paused', False),
        'reduced_size_trades_remaining': getattr(bot_engine, 'reduced_size_trades_remaining', 0),
        'trail_state': trail_state
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
    if bot_engine.execution.active_positions and bot_engine.total_entry_premium > 0:
        current_total_value = 0
        for sym, data in bot_engine.execution.active_positions.items():
            ws_data = bot_engine.api_client.get_realtime_ticker(sym)
            if ws_data and 'mark_price' in ws_data:
                btc_qty = data['size'] * LOT_TO_BTC
                current_total_value += float(ws_data['mark_price']) * btc_qty

        # Fallback to entry prices if live ticker not received
        if current_total_value == 0:
            current_total_value = sum(
                data['entry_price'] * data['size'] * LOT_TO_BTC
                for data in bot_engine.execution.active_positions.values()
            )

        profit = bot_engine.total_entry_premium - current_total_value

        # ── CRITICAL FIX ──────────────────────────────────────────────────
        # _log_and_reset_trade checks current_trade_info["calls"] to decide
        # whether to save the trade. During manual close, the bot loop may
        # not have populated this yet → the trade gets silently skipped.
        # We force-populate it here from active_positions so it is ALWAYS saved.
        if not bot_engine.current_trade_info.get("calls"):
            from utils import get_ist_now
            calls = [sym for sym, d in bot_engine.execution.active_positions.items() if d.get('side') == 'sell' and ('-C' in sym or 'C-' in sym)]
            puts  = [sym for sym, d in bot_engine.execution.active_positions.items() if d.get('side') == 'sell' and ('-P' in sym or 'P-' in sym)]
            # Fallback: split all symbols into calls/puts if side not tagged
            if not calls and not puts:
                for sym in bot_engine.execution.active_positions:
                    if '-C' in sym or 'C-' in sym:
                        calls.append(sym)
                    elif '-P' in sym or 'P-' in sym:
                        puts.append(sym)
            bot_engine.current_trade_info["calls"] = calls
            bot_engine.current_trade_info["puts"]  = puts
            if not bot_engine.current_trade_info.get("entry_time"):
                bot_engine.current_trade_info["entry_time"] = get_ist_now().isoformat()
            app_logger.info(f"Emergency Close: Force-populated current_trade_info → calls={calls}, puts={puts}")
        # ─────────────────────────────────────────────────────────────────

        bot_engine._log_and_reset_trade(profit, "Manual Square-Off")
        from notifier import notifier
        notifier.notify_full_exit("Manual Square-Off", profit)

    bot_engine.execution.close_all(reason="Emergency Manual Square-Off")
    bot_engine.smart_hedging.close_hedge()
    bot_engine.reset_daily_state()

    bot_engine.today_trade_status = "Emergency Manual Closed"
    bot_engine.today_skip_reason  = "User Triggered Emergency"

    from notifier import notifier
    notifier.notify_error("🚨 USER EMERGENCY 🚨\nAll positions squared off manually via Dashboard.")

    return jsonify({'status': 'success'})

@app.route('/api/toggle_regime', methods=['POST'])
def toggle_regime():
    if not bot_engine:
        return jsonify({'error': 'Engine not initialized'}), 500
        
    bot_engine.market_regime_filter_enabled = not bot_engine.market_regime_filter_enabled
    state = "ENABLED" if bot_engine.market_regime_filter_enabled else "DISABLED"
    app_logger.info(f"Web: Market Regime Filter {state}")
    
    return jsonify({'status': 'success', 'enabled': bot_engine.market_regime_filter_enabled})

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
def manual_order():
    try:
        if not bot_engine:
            app_logger.error("Web [manual_order]: Engine not initialized")
            return jsonify({'success': False, 'error': 'Engine not initialized'}), 200

        app_logger.info("Web [manual_order]: Manual strangle entry cycle triggered via dashboard.")
        
        # Temporarily bypass the "1 trade per day limit" just for manual force execution
        bot_engine.trades_taken_today = 0
        
        # Trigger the entry cycle asynchronously in a background thread with force=True
        import threading
        threading.Thread(target=bot_engine.run_entry_cycle, kwargs={'force': True}, daemon=True).start()
        
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
    import db_manager
    if db_manager.is_connected():
        data = db_manager.load_all_data()
        if data and "trades" in data:
            return jsonify(data)
            
    # Fallback to local JSON if cloud fails
    import os, json
    base_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(base_dir, 'trade_history.json')
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return jsonify(data)
        except Exception as e:
            app_logger.error(f"Failed to read trade_history.json: {e}")
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
    """Returns live P&L chart data for the current active trade.
    Stores 1 point per minute so a full 9AM-5PM day = max ~480 pts.
    All points are sent directly — no downsampling needed.
    Old data is NEVER deleted, so full trade history is always visible.
    """
    if not bot_engine:
        return jsonify({"points": [], "active": False})

    chart_data = getattr(bot_engine, 'pnl_chart_data', [])
    has_trade = bool(bot_engine.execution.active_positions)

    if not has_trade or len(chart_data) == 0:
        return jsonify({"active": False, "points": []})

    trail_state = bot_engine.risk_manager.get_trailing_state()
    total_entry_premium = getattr(bot_engine, 'total_entry_premium', 0)

    return jsonify({
        "active": True,
        "points": chart_data,
        "total_points": len(chart_data),
        "trail_state": trail_state,
        "total_entry_premium": round(total_entry_premium, 6)
    })

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
            size = data.get('size', 0)
            
            # Find current price
            current_p = entry_p
            try:
                ws_data = bot_engine.api_client.get_realtime_ticker(sym)
                if ws_data:
                    current_p = float(ws_data.get('mark_price') or entry_p)
            except:
                pass
                
            btc_qty = size * 0.001
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

