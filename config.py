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
BOT_MODE = os.getenv("BOT_MODE", "PAPER").upper()

# --- Capital & Risk ---
# User can change this (e.g., 2000, 10000, 50000). Lot sizes scale dynamically based on this.
# Example: 
# STARTING_CAPITAL = 50000 -> 500 lots total (approx 166 per entry)
# STARTING_CAPITAL = 10000 -> 100 lots total (approx 33 per entry)
# STARTING_CAPITAL = 2000  -> 20 lots total (approx 6 per entry)
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL", 50000))
# Exactly 1.5% max loss of CURRENT account equity on 150% SL hit
RISK_PERCENT = 0.015 
# The base logic: 50,000 capital = 500 lots total (split across 3 entries)
BASE_CAPITAL_FOR_SCALING = 50000.0
BASE_LOTS_TARGET = 500
MAX_DAILY_LOSS_PCT = 0.03 # Stop trading if -3% account loss

# --- Entry/Exit Times (IST) ---
ENTRY_TIMES = ["08:30", "09:00", "09:30"]
EXIT_TIME_START = "17:00"
EXIT_TIME_END = "17:20"

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Strategy Parameters ---
# Delta
DELTA_TARGET = 0.22
DELTA_TOLERANCE = 0.03

# Premium (₹70-100 equivalent in USDT, assuming ~83 INR/USD -> ~0.85 to 1.20 USDT)
PREMIUM_MIN_USDT = 0.80
PREMIUM_MAX_USDT = 1.25

# Stop Loss & Profit Booking
SL_PERCENT = 1.50         # 150% of premium
PARTIAL_PROFIT_TRIGGER = 0.50 # 50% profit
PARTIAL_PROFIT_SIZE = 0.50    # Close 50% of legs
TRAILING_SL_TRIGGER = 0.40    # Trail after 40% profit
TRAILING_SL_LEVEL = 0.0       # Move to breakeven
EXIT_PROFIT_TARGET = 0.70     # 70% overall profit

# RECOST Rules (1-time same-day re-entry after SL)
RECOST_DELTA_MIN = 0.18
RECOST_DELTA_MAX = 0.20

# --- Hedging Parameters ---
HEDGE_SYMBOL = "BTCUSD" # Perpetual futures contract
HEDGE_DELTA_THRESHOLD = 0.20
HEDGE_GAMMA_THRESHOLD = 0.02
