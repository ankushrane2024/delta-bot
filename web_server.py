from flask import Flask, render_template, jsonify, request
from logger import app_logger
from config import LOT_TO_BTC
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

    # Format active positions with rich real-time data
    from datetime import datetime, timezone, timedelta
    positions = []
    
    # Get trade status from engine for position cards
    partial_profit_hit = getattr(bot_engine, 'partial_profit_hit', False)
    trailing_sl_active = getattr(bot_engine, 'trailing_sl_active', False)
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
    
    for sym, data in bot_engine.execution.active_positions.items():
        entry_price = data.get('entry_price', 0)
        size = data.get('size', 0)
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
                # Reject any live price that is unrealistically far from entry.
                # A BTC option premium cannot move >95% in one monitor cycle.
                # This is the root cause of "1.31 USDT" appearing when WS sends
                # stale/garbage data after reconnect.
                # Also reject if price is zero or negative (invalid API response).
                price_is_valid = (
                    candidate_price > 0.01 and               # must be positive
                    entry_price > 0 and                       # need entry to compare
                    abs(candidate_price - entry_price) / entry_price < 0.99  # max 99% move
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
        leg_pnl_inr = leg_pnl_usd * 84.0  # approx INR conversion
        
        # P&L Percentage
        leg_entry_premium_total = entry_price * btc_quantity
        leg_pnl_pct = (leg_pnl_usd / leg_entry_premium_total * 100) if leg_entry_premium_total > 0 else 0.0
        
        # Trade status label
        if trailing_sl_active:
            trade_status = "Trailing SL Active"
        elif partial_profit_hit:
            trade_status = "Partial Profit Booked"
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
            'leg_pnl_pct': round(leg_pnl_pct, 2),
            'delta': round(delta_val, 4),
            'gamma': round(gamma_val, 5),
            'entry_time': entry_time_str,
            'mins_to_squareoff': mins_remaining,
            'current_iv_pct': current_iv_pct,
            'trade_status': trade_status,
        })
    
    # Total P&L across all legs
    total_pnl_usd = round(sum(pos['leg_pnl_usd'] for pos in positions), 2) if positions else 0.0
    total_pnl_inr = round(total_pnl_usd * 84.0, 2)
    total_pnl_pct = (total_pnl_usd / total_entry_premium * 100) if total_entry_premium > 0 else 0.0
    
    dvol_status = bot_engine.dvol_provider.get_status() if getattr(bot_engine, 'dvol_provider', None) else {}
    hedge_status = bot_engine.smart_hedging.get_status() if getattr(bot_engine, 'smart_hedging', None) else {}
    
    return jsonify({
        'is_running': bot_engine.is_running,
        'mode': getattr(bot_engine.execution, 'mode', 'UNKNOWN'),
        'equity': round(bot_engine.risk_manager.current_equity, 2),
        'daily_loss_hits': bot_engine.daily_loss_hits,
        'positions': positions,
        'total_entry_premium': round(total_entry_premium, 4),
        'total_pnl_usd': total_pnl_usd,
        'total_pnl_inr': total_pnl_inr,
        'total_pnl_pct': round(total_pnl_pct, 2),
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
        'today_skip_reason': getattr(bot_engine, 'today_skip_reason', None),
        # New advanced metrics
        'dvol_status': dvol_status,
        'hedge_status': hedge_status,
        'size_multiplier': round(getattr(bot_engine, 'size_multiplier', 1.0), 2),
        'consecutive_loss_count': getattr(bot_engine, 'consecutive_loss_count', 0),
        'next_day_paused': getattr(bot_engine, 'next_day_paused', False),
        'reduced_size_trades_remaining': getattr(bot_engine, 'reduced_size_trades_remaining', 0)
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
        
    # Calculate closed P&L and log it to performance tracker and diary before wiping positions
    if bot_engine.execution.active_positions and bot_engine.total_entry_premium > 0:
        current_total_value = 0
        for sym, data in bot_engine.execution.active_positions.items():
            ws_data = bot_engine.api_client.get_realtime_ticker(sym)
            if ws_data and 'mark_price' in ws_data:
                # BTC_Quantity = Lots * LOT_TO_BTC (0.001 per lot)
                btc_qty = data['size'] * LOT_TO_BTC
                current_total_value += float(ws_data['mark_price']) * btc_qty
        
        # Fallback to entry prices if live ticker not received yet
        if current_total_value == 0:
            current_total_value = sum(
                data['entry_price'] * data['size'] * LOT_TO_BTC
                for data in bot_engine.execution.active_positions.values()
            )
            
        profit = bot_engine.total_entry_premium - current_total_value
        bot_engine._log_and_reset_trade(profit, "Emergency Manual Closed")
        from notifier import notifier
        notifier.notify_full_exit("Emergency Manual Closed", profit)
        
    bot_engine.execution.close_all(reason="Emergency Manual Square-Off")
    bot_engine.smart_hedging.close_hedge()
    bot_engine.reset_daily_state()
    
    bot_engine.today_trade_status = "Emergency Manual Closed"
    bot_engine.today_skip_reason = "User Triggered Emergency"
    
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

