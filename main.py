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
    24/7 Persistent Cloud Keep-Alive Pinger.
    Guarantees that the bot NEVER sleeps or hibernates on Render (24*7, 365 days a year).
    Pings https://delta-btc-options-bot.onrender.com/ping every 240 seconds (4 minutes)
    so Render's 15-minute inactivity counter NEVER expires.
    Supports both:
    1. Morning Intraday Strategy (09:00 - 17:00 IST)
    2. Night BTST 44H Strategy (22:30 IST entry - 44h hold to D+2 17:28 IST)
    """
    time.sleep(30)
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if (not url or url == 'http://localhost:5000') and os.environ.get('RENDER') == 'true':
        url = 'https://delta-btc-options-bot.onrender.com'
    if not url:
        url = 'https://delta-btc-options-bot.onrender.com'
        
    app_logger.info(f"[24/7 KEEPALIVE] Persistent keep-alive pinger started. Target URL: {url}")
    
    while True:
        try:
            from utils import get_ist_now
            now_ist = get_ist_now()
            
            # Check BTST and Intraday position status
            has_btst_pos = False
            try:
                from btst_strategy import btst_engine
                has_btst_pos = bool(btst_engine.active_trade and btst_engine.active_trade.get('status') in ['OPEN', 'PARTIALLY_CLOSED'])
            except Exception:
                pass
                
            has_intraday_pos = False
            exec_module = getattr(engine, 'execution', None)
            if exec_module:
                has_intraday_pos = bool(
                    getattr(exec_module, 'active_positions', None) or
                    getattr(exec_module, 'live_positions', None) or
                    getattr(exec_module, 'paper_positions', None)
                )

            # Send HTTP keep-alive ping to Render
            try:
                res = requests.get(f"{url}/ping", timeout=15)
                app_logger.info(
                    f"[24/7 KEEPALIVE] Ping sent at {now_ist.strftime('%H:%M:%S')} IST (HTTP {res.status_code}). "
                    f"Intraday Pos: {has_intraday_pos}, BTST Pos: {has_btst_pos}. Container active 24/7."
                )
            except Exception as ping_err:
                app_logger.warning(f"[24/7 KEEPALIVE] Ping network notice: {ping_err}")
                
            # Sleep 240 seconds (4 minutes) — well below Render's 15-minute hibernation timeout
            time.sleep(240)
        except Exception as e:
            app_logger.warning(f"[24/7 KEEPALIVE] Error in keepalive loop: {e}")
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
