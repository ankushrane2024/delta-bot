import asyncio
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from logger import app_logger

# Global reference to the bot engine
_engine = None

async def _verify_user(update: Update) -> bool:
    """Ensure the sender is the authorized user."""
    if str(update.effective_chat.id) != str(TELEGRAM_CHAT_ID):
        app_logger.warning(f"Unauthorized access attempt from chat ID {update.effective_chat.id}")
        return False
    return True

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status command"""
    if not await _verify_user(update): return
    
    if not _engine:
        await update.message.reply_text("Engine is not initialized.")
        return

    # Gather status information
    mode = getattr(_engine.execution, 'mode', 'UNKNOWN')
    equity = _engine.risk_manager.current_equity
    is_running = _engine.is_running
    trade_status = getattr(_engine, 'today_trade_status', 'Pending')
    
    active_positions = _engine.execution.active_positions
    pos_details = []
    if active_positions:
        for sym, data in active_positions.items():
            pos_details.append(f"- {sym}: {data['size']} lots @ {data['avg_price']:.2f}")
        pos_str = "\n".join(pos_details)
        
        # Try to calculate floating profit roughly
        # Note: accurate profit requires fetching ws data, so we just state positions
        profit_str = f"Open Positions:\n{pos_str}"
    else:
        profit_str = "No active positions."

    msg = (
        f"📊 <b>Bot Status</b>\n\n"
        f"Mode: {mode}\n"
        f"State: {'Running' if is_running else 'Stopped'}\n"
        f"Equity: ${equity:.2f}\n"
        f"Today's Status: {trade_status}\n\n"
        f"{profit_str}"
    )
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /pause command"""
    if not await _verify_user(update): return
    
    if _engine:
        _engine.manual_pause = True
        await update.message.reply_text("⏸️ <b>Trading Paused.</b> The bot will ignore scheduled entries until /resume is sent.", parse_mode='HTML')

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /resume command"""
    if not await _verify_user(update): return
    
    if _engine:
        _engine.manual_pause = False
        await update.message.reply_text("▶️ <b>Trading Resumed.</b> The bot will resume normal scheduled entries.", parse_mode='HTML')

async def cmd_close_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /close_all command"""
    if not await _verify_user(update): return
    
    if not _engine:
        await update.message.reply_text("Engine is not initialized.")
        return

    await update.message.reply_text("🚨 <b>EMERGENCY TRIGGERED</b>\nSquaring off all positions at market price...", parse_mode='HTML')
    
    try:
        # We must call engine functions thread-safely or assume they are thread-safe.
        # close_all triggers API calls which are generally safe
        _engine.execution.close_all(reason="Emergency Telegram Square-Off")
        _engine.smart_hedging.close_hedge()
        _engine.reset_daily_state()
        
        _engine.today_trade_status = "Emergency Manual Closed"
        _engine.today_skip_reason = "Telegram Emergency"
        
        from notifier import notifier
        notifier.notify_full_exit("Emergency Telegram Square-Off", 0) # Approx PnL not calculated here for speed
        
        await update.message.reply_text("✅ All positions squared off successfully.")
    except Exception as e:
        app_logger.error(f"Telegram /close_all failed: {e}")
        await update.message.reply_text(f"⚠️ Error during square-off: {e}")

async def cmd_force_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /force_trade command"""
    if not await _verify_user(update): return
    
    if not _engine:
        return

    await update.message.reply_text("⚡ Triggering manual entry cycle...", parse_mode='HTML')
    
    _engine.trades_taken_today = 0
    # Run entry cycle in background so it doesn't block telegram async loop
    threading.Thread(target=_engine.run_entry_cycle, kwargs={'force': True}, daemon=True).start()
    
    await update.message.reply_text("Entry cycle initiated in background.")


def _run_asyncio_loop(token):
    """Creates a new event loop and runs the Telegram bot Application."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))
    application.add_handler(CommandHandler("close_all", cmd_close_all))
    application.add_handler(CommandHandler("force_trade", cmd_force_trade))

    app_logger.info("Telegram interactive bot started.")
    
    # Run the application (this blocks the thread)
    application.run_polling(drop_pending_updates=True)

def start_interactive_bot(engine):
    """
    Initializes and starts the two-way Telegram bot in a daemon thread.
    """
    global _engine
    _engine = engine

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        app_logger.warning("Telegram token or chat_id missing. Interactive bot disabled.")
        return

    bot_thread = threading.Thread(target=_run_asyncio_loop, args=(TELEGRAM_BOT_TOKEN,), daemon=True)
    bot_thread.start()
