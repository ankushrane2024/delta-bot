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
    Background Keep-Alive Pinger
    This prevents the Render.com free tier from putting the web service to sleep.
    Render sleeps apps after 15 minutes of inactivity. By pinging our own /ping 
    endpoint every 4 minutes, the instance registers activity and stays awake 24/7.
    """
    time.sleep(60)
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if (not url or url == 'http://localhost:5000') and os.environ.get('RENDER') == 'true':
        url = 'https://delta-btc-options-bot.onrender.com'
    if not url:
        url = 'http://localhost:5000'
    app_logger.info(f"Keep-alive pinger started. Target URL: {url}")
    while True:
        try:
            requests.get(f"{url}/ping", timeout=15)
            mode = getattr(engine, 'mode', 'OFF')
            app_logger.info(f"[KEEPALIVE] alive, engine={'ON' if mode != 'OFF' else 'OFF'} (Mode: {mode})")
        except Exception as e:
            app_logger.warning(f"[KEEPALIVE] Keep-alive ping failed: {e}")
        time.sleep(240)  # Ping every 4 minutes

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
        
        # 5. Initialize ARES ServiceRunner
        if os.environ.get('ENABLE_ARES', 'true').lower() == 'true':
            try:
                from hedge.deployment.service_runner import ServiceRunner
                from hedge.engines.adapters.option_bridge import OptionBridge
                
                bridge = OptionBridge(engine)
                ares_runner = ServiceRunner(mode_override='PAPER', option_bridge=bridge)
                ares_thread = threading.Thread(target=ares_runner.run, daemon=True)
                ares_thread.start()
                app_logger.info("ARES ServiceRunner initialized in background thread in PAPER mode with OptionBridge.")
            except Exception as e:
                app_logger.error(f"Failed to initialize ARES ServiceRunner: {e}")
                ares_runner = None
        else:
            app_logger.info("ARES is disabled via ENABLE_ARES flag.")
            ares_runner = None
            
        # 6. Pass ARES Runner to Web Server
        import web_server
        web_server.ares_runner = ares_runner
        
        # 7. Start Flask server on the main thread
        port = int(os.environ.get('PORT', 5000))
        app_logger.info(f"Starting Web Dashboard on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        app_logger.info("Bot stopped by user.")
        sys.exit(0)
    except Exception as e:
        app_logger.critical(f"Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
