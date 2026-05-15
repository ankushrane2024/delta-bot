import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from logger import error_logger, app_logger

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
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if not response.json().get("ok"):
                error_logger.error(f"Telegram failed: {response.text}")
        except Exception as e:
            error_logger.error(f"Telegram notification error: {e}")

    def notify_entry(self, mode, strategy, call_sym, put_sym, lots):
        msg = (
            f"🚀 *{mode} Entry: {strategy}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 Time: IST Morning\n"
            f"📞 CE: `{call_sym}`\n"
            f"📥 PE: `{put_sym}`\n"
            f"📦 Lots: `{lots}` per leg\n"
        )
        self.send_message(msg)

    def notify_exit(self, mode, reason, pnl, total_pnl):
        msg = (
            f"🏁 *{mode} Exit*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"❓ Reason: `{reason}`\n"
            f"💵 PnL: `{pnl:.2f}`\n"
            f"📈 Total PnL: `{total_pnl:.2f}`\n"
        )
        self.send_message(msg)

    def notify_hedge(self, mode, delta, gamma, action):
        msg = (
            f"🛡️ *{mode} Hedging*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📊 Net Delta: `{delta:.4f}`\n"
            f"📈 Gamma: `{gamma:.4f}`\n"
            f"⚡ Action: `{action}`\n"
        )
        self.send_message(msg)

    def notify_error(self, error_msg):
        msg = f"⚠️ *ERROR ALERT*\n`{error_msg}`"
        self.send_message(msg)

notifier = TelegramNotifier()
