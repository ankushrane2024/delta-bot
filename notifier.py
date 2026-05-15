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

notifier = TelegramNotifier()
