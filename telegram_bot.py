"""
telegram_bot.py — Two-Way Telegram Mobile Control
==================================================
Uses long-polling (manual requests loop) instead of python-telegram-bot's
Application.run_polling() to avoid asyncio event loop conflicts with Flask
and the main trading thread.

Commands supported:
  /status      – Live equity, mode, trade status, open positions
  /pause       – Stop bot from entering new trades
  /resume      – Resume normal trading
  /close_all   – Emergency: square off ALL positions at market immediately
  /force_trade – Manually trigger an entry cycle right now
"""

import time
import threading
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from logger import app_logger

# Global engine reference
_engine = None
_last_update_id = None
_running = False

def _send(chat_id, text):
    """Send a reply to Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        app_logger.error(f"Telegram send error: {e}")

def _handle_command(chat_id, text):
    """Dispatch a command to the right handler."""
    cmd = text.strip().lower().split()[0]

    if cmd == "/status":
        _cmd_status(chat_id)
    elif cmd == "/pause":
        _cmd_pause(chat_id)
    elif cmd == "/resume":
        _cmd_resume(chat_id)
    elif cmd == "/close_all":
        _cmd_close_all(chat_id)
    elif cmd == "/force_trade":
        _cmd_force_trade(chat_id)
    else:
        _send(chat_id, 
              "❓ Unknown command. Available commands:\n"
              "/status - Live bot status\n"
              "/pause - Pause new trades\n"
              "/resume - Resume trading\n"
              "/close_all - Emergency exit all positions\n"
              "/force_trade - Force an entry now")

def _cmd_status(chat_id):
    if not _engine:
        _send(chat_id, "⚠️ Engine not initialized.")
        return

    mode = getattr(_engine.execution, 'mode', 'UNKNOWN')
    equity = _engine.risk_manager.current_equity
    is_running = _engine.is_running
    trade_status = getattr(_engine, 'today_trade_status', 'Pending')
    manual_pause = getattr(_engine, 'manual_pause', False)
    positions = _engine.execution.active_positions
    
    pos_lines = []
    for sym, d in positions.items():
        pos_lines.append(f"  • {sym}: {d['size']} lots")
    pos_text = "\n".join(pos_lines) if pos_lines else "  None"

    premium = getattr(_engine, 'total_entry_premium', 0.0)
    skip_reason = getattr(_engine, 'today_skip_reason', None) or "—"

    msg = (
        f"📊 <b>Delta Bot Status</b>\n\n"
        f"Mode: <b>{mode}</b>\n"
        f"Engine: {'✅ Running' if is_running else '⛔ Stopped'}\n"
        f"Manual Pause: {'⏸ YES' if manual_pause else '▶ NO'}\n"
        f"Equity: <b>${equity:,.2f}</b>\n"
        f"Today Status: {trade_status}\n"
        f"Skip Reason: {skip_reason}\n\n"
        f"Open Positions:\n{pos_text}\n"
        f"Premium Collected: ${premium:.4f}"
    )
    _send(chat_id, msg)

def _cmd_pause(chat_id):
    if not _engine:
        _send(chat_id, "⚠️ Engine not initialized.")
        return
    _engine.manual_pause = True
    _send(chat_id, 
          "⏸️ <b>Trading Paused.</b>\n\n"
          "The bot will block all scheduled entries until you send /resume.\n"
          "Any currently active trade is NOT affected — it continues normally.")

def _cmd_resume(chat_id):
    if not _engine:
        _send(chat_id, "⚠️ Engine not initialized.")
        return
    _engine.manual_pause = False
    _send(chat_id, "▶️ <b>Trading Resumed.</b>\nBot will enter trades at the next scheduled window.")

def _cmd_close_all(chat_id):
    if not _engine:
        _send(chat_id, "⚠️ Engine not initialized.")
        return

    _send(chat_id, "🚨 <b>EMERGENCY CLOSE TRIGGERED</b>\nSquaring off all positions at market price...")
    try:
        _engine.execution.close_all(reason="Telegram Emergency Square-Off")
        _engine.smart_hedging.close_hedge()
        _engine.reset_daily_state()
        _engine.today_trade_status = "Emergency Manual Closed"
        _engine.today_skip_reason = "Telegram Emergency"
        _send(chat_id, "✅ <b>All positions closed successfully.</b>\nAccount is secured.")
    except Exception as e:
        app_logger.error(f"Telegram /close_all error: {e}")
        _send(chat_id, f"⚠️ Error during close: {e}")

def _cmd_force_trade(chat_id):
    if not _engine:
        _send(chat_id, "⚠️ Engine not initialized.")
        return
    _engine.trades_taken_today = 0
    threading.Thread(target=_engine.run_entry_cycle, kwargs={'force': True}, daemon=True).start()
    _send(chat_id, "⚡ <b>Force Trade Triggered.</b>\nEntry cycle running in background. Check dashboard in 30 seconds.")

def _polling_loop():
    """Simple long-polling loop. Runs forever in a daemon thread."""
    global _last_update_id, _running
    app_logger.info("Telegram polling loop started.")

    # Get the latest update_id so we skip old messages from before startup
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 1, "limit": 100},
            timeout=15
        )
        updates = r.json().get("result", [])
        if updates:
            _last_update_id = updates[-1]["update_id"]
        app_logger.info(f"Telegram: Skipped {len(updates)} old messages. Waiting for new commands.")
    except Exception as e:
        app_logger.error(f"Telegram startup skip error: {e}")

    while _running:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if _last_update_id is not None:
                params["offset"] = _last_update_id + 1

            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params=params,
                timeout=40
            )

            if resp.status_code != 200:
                time.sleep(5)
                continue

            updates = resp.json().get("result", [])
            for update in updates:
                _last_update_id = update["update_id"]
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")

                # Security: only respond to your personal chat
                if str(chat_id) != str(TELEGRAM_CHAT_ID):
                    app_logger.warning(f"Telegram: Ignoring message from unauthorized chat {chat_id}")
                    continue

                if text.startswith("/"):
                    app_logger.info(f"Telegram: Received command: {text}")
                    _handle_command(chat_id, text)

        except requests.exceptions.ReadTimeout:
            # Normal — long poll expired with no messages
            continue
        except Exception as e:
            app_logger.error(f"Telegram polling error: {e}")
            time.sleep(5)

def start_interactive_bot(engine):
    """Initializes and starts the two-way Telegram bot in a daemon thread."""
    global _engine, _running

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        app_logger.warning("Telegram token or chat_id missing. Interactive bot disabled.")
        return

    _engine = engine
    _running = True

    bot_thread = threading.Thread(target=_polling_loop, daemon=True, name="TelegramPoller")
    bot_thread.start()
    app_logger.info("Telegram interactive bot thread started.")
