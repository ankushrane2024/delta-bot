import sys
import threading
from bot_engine import DeltaTradingEngine
from web_server import app, init_web_server
from logger import app_logger

def run_bot_engine(engine):
    try:
        engine.start()
    except Exception as e:
        app_logger.critical(f"Critical error in engine thread: {e}")

def main():
    try:
        # 1. Initialize Engine
        engine = DeltaTradingEngine()
        
        # 2. Pass to Web Server
        init_web_server(engine)
        
        # 3. Start Engine in a background thread
        engine_thread = threading.Thread(target=run_bot_engine, args=(engine,), daemon=True)
        engine_thread.start()
        
        # 4. Start Flask server on the main thread
        app_logger.info("Starting Web Dashboard on http://127.0.0.1:5000")
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        app_logger.info("Bot stopped by user.")
        sys.exit(0)
    except Exception as e:
        app_logger.critical(f"Critical error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
