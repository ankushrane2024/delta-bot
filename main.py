import sys
import os
from pathlib import Path
from datetime import datetime
import threading
import time
import requests
import pytz
from dotenv import load_dotenv

# Ensure .env is loaded before reading any environment variables
_env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=_env_path)

from config import BOT_MODE, ENABLE_TELEGRAM_HEARTBEAT, HEARTBEAT_INTERVAL_MINS
from bot_engine import DeltaTradingEngine
from web_server import app, init_web_server
from logger import app_logger
from notifier import notifier

def run_bot_engine(engine):
    try:
        engine.start()
    except Exception as e:
        app_logger.critical(f"Critical error in engine thread: {e}")
        try:
            notifier.send_message(f"🚨 <b>Critical Error in Engine Thread:</b>\n<code>{e}</code>")
        except Exception:
            pass

def keep_alive_pinger(engine):
    """
    Local Loopback Health Pinger.
    Pings the local /ping endpoint every 4 minutes to verify server responsiveness
    and log an ongoing health heartbeat to journalctl.
    """
    time.sleep(15)
    port = os.environ.get('PORT', '5000')
    url = os.environ.get('APP_URL', f'http://127.0.0.1:{port}').rstrip('/')
    app_logger.info(f"Health pinger started. Target URL: {url}/ping")
    while True:
        try:
            res = requests.get(f"{url}/ping", timeout=10)
            mode = getattr(engine, 'mode', BOT_MODE)
            engine_running = getattr(engine, 'is_running', True)
            app_logger.info(f"[HEALTH PING] HTTP {res.status_code}, engine={'ON' if engine_running else 'OFF'} (Mode: {mode})")
        except Exception as e:
            app_logger.warning(f"[HEALTH PING] Local health ping failed: {e}")
        time.sleep(240)  # Ping every 4 minutes

def telegram_heartbeat_worker(engine):
    """
    Periodic Telegram Heartbeat Monitor.
    Sends a concise status summary to Telegram at configured intervals
    so the operator knows the VM and bot are alive and healthy.
    """
    if not ENABLE_TELEGRAM_HEARTBEAT:
        app_logger.info("Telegram heartbeat is disabled in config.")
        return

    interval_seconds = max(300, HEARTBEAT_INTERVAL_MINS * 60)
    app_logger.info(f"Telegram heartbeat worker started (Interval: {HEARTBEAT_INTERVAL_MINS}m).")

    # Initial settling delay
    time.sleep(120)
    start_time = time.time()

    while True:
        try:
            now_ist = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M IST')
            uptime_hours = (time.time() - start_time) / 3600.0

            # Virtual memory usage
            mem_pct = 0.0
            try:
                import psutil
                mem_pct = psutil.virtual_memory().percent
            except Exception:
                pass

            mode = getattr(getattr(engine, 'execution', None), 'mode', BOT_MODE)
            equity = getattr(getattr(engine, 'risk_manager', None), 'current_equity', 0.0)
            is_running = getattr(engine, 'is_running', False)
            today_status = getattr(engine, 'today_trade_status', 'Idle')
            active_positions = getattr(getattr(engine, 'execution', None), 'active_positions', {})
            open_pos_count = len(active_positions)

            status_icon = "🟢" if is_running else "🟡"
            msg = (
                f"💓 <b>Delta Bot Heartbeat</b> [{now_ist}]\n"
                f"Status: {status_icon} {'Running' if is_running else 'Idle/Paused'}\n"
                f"Mode: <b>{mode}</b> | Today: {today_status}\n"
                f"Open Positions: {open_pos_count}\n"
                f"Sim Equity: ${equity:,.2f}\n"
                f"VM RAM: {mem_pct:.1f}% | Uptime: {uptime_hours:.1f}h"
            )
            notifier.send_message(msg)
        except Exception as e:
            app_logger.error(f"Telegram heartbeat error: {e}")

        time.sleep(interval_seconds)

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
        
        # 4. Start local health pinger in a background thread
        pinger_thread = threading.Thread(target=keep_alive_pinger, args=(engine,), daemon=True)
        pinger_thread.start()

        # 5. Start periodic Telegram heartbeat monitor in a background thread
        heartbeat_thread = threading.Thread(target=telegram_heartbeat_worker, args=(engine,), daemon=True)
        heartbeat_thread.start()
        
        # 6. Start Flask server on the main thread
        port = int(os.environ.get('PORT', 5000))
        app_logger.info(f"Starting Web Dashboard on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        app_logger.info("Bot stopped by user (graceful exit).")
        sys.exit(0)
    except Exception as e:
        app_logger.critical(f"Critical error in main process: {e}")
        try:
            notifier.send_message(f"🚨 <b>CRITICAL: Delta Bot Terminated with Exception!</b>\n<code>{e}</code>\n<i>systemd will auto-restart in 5s.</i>")
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()
