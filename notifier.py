import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from logger import error_logger

class TelegramNotifier:
    def __init__(self, token=None, chat_id=None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, message):
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if not response.json().get("ok"):
                error_logger.error(f"Telegram failed: {response.text}")
        except Exception as e:
            error_logger.error(f"Telegram notification error: {e}")

    def send_document(self, file_path, caption=""):
        if not self.enabled:
            return
            
        url = f"https://api.telegram.org/bot{self.token}/sendDocument"
        payload = {
            "chat_id": self.chat_id,
            "caption": caption,
            "parse_mode": "HTML"
        }
        
        try:
            with open(file_path, 'rb') as doc:
                files = {'document': doc}
                response = requests.post(url, data=payload, files=files, timeout=20)
                if not response.json().get("ok"):
                    error_logger.error(f"Telegram document upload failed: {response.text}")
        except Exception as e:
            error_logger.error(f"Telegram document send error: {e}")

    def notify_startup(self, mode, capital):
        self.send_message(f"🚀 <b>Bot Started in {mode} mode | Capital: ${capital}</b>")

    def notify_entry(self, call_sym, put_sym, lots, premium):
        self.send_message(f"🟢 <b>New Short Strangle Entered</b>\nSize: {lots} lots | Premium: ${premium:.2f}\nStrikes: {call_sym} & {put_sym}")

    def notify_partial_profit(self, pnl):
        self.send_message(f"💰 <b>Partial Profit Booked (50%)</b> | P&L: ${pnl:.2f}")

    def notify_trailing_sl(self):
        self.send_message("📈 <b>Trailing SL moved to Breakeven</b>")

    def notify_stop_loss(self, loss, recost_triggered):
        msg = f"🔴 <b>Stop Loss Hit (150%)</b> | Loss: ${loss:.2f}"
        if recost_triggered:
            msg += " | RECOST triggered"
        self.send_message(msg)

    def notify_full_exit(self, reason, pnl):
        self.send_message(f"🟡 <b>Position Closed</b> | Reason: {reason} | P&L: ${pnl:.2f}")

    def notify_recost(self):
        self.send_message("🔄 <b>RECOST Re-entry executed with wider strikes</b>")

    def notify_compliance_report(self, win_rate, pnl, drawdown):
        msg = (
            f"📊 <b>Daily Rule Compliance Report</b>\n"
            f"Win Rate: {win_rate}%\n"
            f"Net P&L: ${pnl:.2f}\n"
            f"Current Drawdown: {drawdown}%"
        )
        self.send_message(msg)

    def notify_error(self, error_msg):
        self.send_message(f"⚠️ <b>Warning: {error_msg}</b>")

    def notify_hedge_executed(self, timestamp, iv, net_delta, hedge_type, size_btc, order_id):
        """Hedge executed notification with full details."""
        msg = (
            f"🛡️ <b>HEDGE EXECUTED</b>\n"
            f"Time: {timestamp}\n"
            f"IV: {iv:.1f}%\n"
            f"Net Delta: {net_delta:.4f}\n"
            f"Hedge Type: {hedge_type}\n"
            f"Size: {size_btc:.6f} BTC\n"
            f"Order ID: {order_id}"
        )
        self.send_message(msg)

    def notify_hedge_escalated(self, timestamp, from_pct, to_pct, loss_pct):
        """Hedge escalated due to increasing loss."""
        msg = (
            f"⚠️ <b>EMERGENCY HEDGE INCREASED</b>\n"
            f"Time: {timestamp}\n"
            f"From: {from_pct:.0f}% → To: {to_pct:.0f}%\n"
            f"Unrealized Loss: {loss_pct:.1f}%"
        )
        self.send_message(msg)

    def notify_hedge_failed(self):
        """Critical alert when hedging fails after retries."""
        self.send_message("🚨 <b>HEDGING FAILED - Manual intervention needed!</b>\nAll retry attempts exhausted. Check positions immediately.")

    def notify_dvol_skip(self, dvol, percentile, reason):
        """Trade skipped due to DVOL percentile filter."""
        self.send_message(
            f"📊 <b>Trade Skipped (DVOL Filter)</b>\n"
            f"Current DVOL: {dvol:.2f}%\n"
            f"DVOL Percentile: {percentile:.1f}%\n"
            f"Reason: {reason}"
        )

    def notify_size_adjusted(self, base_lots, adjusted_lots, multiplier, reason):
        """Position size dynamically adjusted."""
        self.send_message(
            f"📐 <b>Position Size Adjusted</b>\n"
            f"Base: {base_lots} lots → Adjusted: {adjusted_lots} lots\n"
            f"Multiplier: {multiplier:.2f}x\n"
            f"Reason: {reason}"
        )

    def notify_daily_loss_limit(self, loss_pct, equity):
        """Daily loss limit hit - trading stopped."""
        self.send_message(
            f"🛑 <b>DAILY LOSS LIMIT HIT</b>\n"
            f"Daily Loss: {loss_pct:.2f}%\n"
            f"Current Equity: ${equity:.2f}\n"
            f"Trading stopped for the day. All positions squared off."
        )

    def notify_next_day_paused(self, loss_pct):
        """Tomorrow paused due to today's heavy loss."""
        self.send_message(
            f"⏸️ <b>Tomorrow Trading PAUSED</b>\n"
            f"Today's Loss: {loss_pct:.2f}%\n"
            f"Exceeds 2.5% threshold. Next trading day will be skipped."
        )

notifier = TelegramNotifier()
