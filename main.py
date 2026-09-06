import sys
import os
import threading
import time
import requests
from bot_engine import DeltaTradingEngine
from web_server import app, init_web_server
from logger import app_logger

def run_bot_engine(engine):
    try:
        engine.start()
    except Exception as e:
        app_logger.critical(f"Critical error in engine thread: {e}")

def keep_alive_pinger(engine):
    """
    Smart Background Keep-Alive Pinger
    Maintains active cloud execution during the trading session (08:30 AM to 05:30 PM IST)
    AND anytime an active position is open (day or night).
    
    Outside the trading window (17:30 to 08:30 IST) when there are 0 open positions,
    the pinger sleeps, allowing Render to automatically hibernate and consume 0 bandwidth.
    """
    time.sleep(60)
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if (not url or url == 'http://localhost:5000') and os.environ.get('RENDER') == 'true':
        url = 'https://delta-btc-options-bot.onrender.com'
    if not url:
        url = 'http://localhost:5000'
    app_logger.info(f"Smart Keep-alive pinger started. Target URL: {url}")
    
    last_log_dormant_ts = 0.0
    while True:
        try:
            # 1. Check if any positions are active in paper or live mode
            exec_module = getattr(engine, 'execution', None)
            has_active_pos = False
            if exec_module:
                has_active_pos = bool(
                    getattr(exec_module, 'active_positions', None) or
                    getattr(exec_module, 'live_positions', None) or
                    getattr(exec_module, 'paper_positions', None)
                )

            # 2. Check current time in IST (08:30 to 17:30 IST is active daytime window)
            from utils import get_ist_now
            now_ist = get_ist_now()
            current_mins = now_ist.hour * 60 + now_ist.minute
            # 08:30 IST is 510 minutes. 17:30 IST is 1050 minutes.
            is_active_window = 510 <= current_mins <= 1050

            # 3. Decision: Ping if within trading hours OR if ANY position is open
            if is_active_window or has_active_pos:
                requests.get(f"{url}/ping", timeout=15)
                mode = getattr(getattr(engine, 'execution', None), 'mode', 'PAPER')
                reason = "ACTIVE_WINDOW" if is_active_window else "OPEN_POSITIONS_OVERRIDE"
                app_logger.info(f"[KEEPALIVE] Ping sent ({reason}). Engine={'ON' if getattr(engine, 'is_running', True) else 'OFF'} (Mode: {mode}, Pos: {has_active_pos})")
                time.sleep(240)  # Ping every 4 minutes while active
            else:
                # Outside window & 0 open positions -> Sleep and allow Render to hibernate
                if time.time() - last_log_dormant_ts > 1800:
                    last_log_dormant_ts = time.time()
                    app_logger.info(f"[KEEPALIVE] Standby period ({now_ist.strftime('%H:%M')} IST). No open trades. Pinger dormant to allow Render hibernation.")
                time.sleep(120)  # Check every 2 minutes for new trade entries
        except Exception as e:
            app_logger.warning(f"[KEEPALIVE] Keep-alive ping check error: {e}")
            time.sleep(60)

def main():
    try:
        # 1. Initialize Engine
        engine = DeltaTradingEngine()
        
        # 2. Pass to Web Server
        init_web_server(engine)
        
        # 3. Start Engine in a background thread
        engine_thread = threading.Thread(target=run_bot_engine, args=(engine,), daemon=True)
        engine_thread.start()
        
        # 3.5 Start Two-Way Telegram Mobile Command Listener
        try:
            from telegram_bot import start_interactive_bot
            start_interactive_bot(engine)
        except Exception as tg_err:
            app_logger.error(f"Failed to start telegram listener: {tg_err}")
        
        # 4. Start keep-alive pinger in a background thread
        pinger_thread = threading.Thread(target=keep_alive_pinger, args=(engine,), daemon=True)
        pinger_thread.start()
        

        
        # 7. Start Flask server on the main thread
        port = int(os.environ.get('PORT', 5000))
        app_logger.info(f"Starting Web Dashboard on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
        
    except KeyboardInterrupt:
        app_logger.info("Bot stopped by user.")
        sys.exit(0)
    except Exception as e:
        app_logger.critical(f"Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
