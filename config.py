import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- API Settings ---
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")
DELTA_INDIA_BASE_URL = "https://api.india.delta.exchange"
DELTA_INDIA_WS_URL = "wss://socket.india.delta.exchange"

# --- Bot Mode ---
# Set BOT_MODE to "PAPER" for simulation or "LIVE" for real trading.
BOT_MODE = os.getenv("BOT_MODE", "PAPER").upper()

# --- Capital & Risk ---
# STARTING_CAPITAL is used only for paper-mode equity simulation and reporting.
# Example: STARTING_CAPITAL = 50000 means bot starts with a $50,000 paper balance.
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", 50000))

# Maximum allowed daily loss as a percentage of starting equity.
# Bot stops trading for the day if floating loss >= 3%.
MAX_DAILY_LOSS_PCT = 0.03

# --- Manual Lot Sizing ---
# MANUAL_TOTAL_LOTS is the total number of lots for a strangle trade.
# This value is overridden by the dashboard "Manual Lot Size Settings" panel
# which writes to lot_size.json. On bot startup, lot_size.json is checked first.
# If lot_size.json is absent, this value is used as the default.
# Example: 200 = 100 lots per leg (call side + put side).
MANUAL_TOTAL_LOTS = int(os.getenv("MANUAL_TOTAL_LOTS", 200))

# --- Entry/Exit Times (IST) ---
ENTRY_TIMES = ["08:30", "09:00", "09:30"]
EXIT_TIME_START = "17:00"
EXIT_TIME_END = "17:20"

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Strategy Parameters ---
# Target delta for strike selection (approximate 0.22 delta OTM strikes).
DELTA_TARGET = 0.22
DELTA_TOLERANCE = 0.03

# --- Stop Loss & Profit Booking ---
SL_PERCENT = 1.50              # 150% of collected premium → triggers full exit
PARTIAL_PROFIT_TRIGGER = 0.50  # 50% profit reached → trigger partial close
PARTIAL_PROFIT_SIZE = 0.50     # Close 50% of position size on partial profit
TRAILING_SL_TRIGGER = 0.40    # After 40% profit → activate trailing SL to breakeven
TRAILING_SL_LEVEL = 0.0       # Trailing SL level: breakeven (0% profit)
EXIT_PROFIT_TARGET = 0.70     # 70% total profit → full exit

# --- Hedging Parameters ---
# When net Delta or Gamma exceed these thresholds, the bot hedges using BTC futures.
HEDGE_SYMBOL = "BTCUSD"           # BTC Perpetual futures contract symbol
HEDGE_DELTA_THRESHOLD = 0.20      # Net delta above 0.20 triggers hedging
HEDGE_GAMMA_THRESHOLD = 0.02      # Net gamma above 0.02 triggers hedging
