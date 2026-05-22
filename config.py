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
# Remote Render bot is forced to "PAPER" mode for safety and simulation, local uses .env.
if os.getenv("RENDER") == "true":
    BOT_MODE = "PAPER"
else:
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
EXIT_PREPARE_TIME = "16:55"   # Start preparing forced exit at 16:55 IST
EXIT_TIME_HARD = "17:00"      # Hard square off at 17:00 IST
EXIT_TIME_START = "17:00"     # Kept for backward compatibility
EXIT_TIME_END = "17:20"       # Kept for backward compatibility

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Strategy Parameters ---
# Target delta for strike selection (approximate 0.22 delta OTM strikes).
DELTA_TARGET = 0.22
DELTA_TOLERANCE = 0.03

# --- DVOL-Based Strike Selection (Section 1) ---
# Minimum number of strikes OTM from ATM for both call and put legs.
MIN_OTM_STRIKES = 4
# Put premium must not exceed this multiple of call premium.
PUT_SKEW_CAP = 1.35
# Maximum allowed absolute net delta at entry. Triggers 1-strike OTM shift if exceeded.
NET_DELTA_ENTRY_LIMIT = 0.15
# DVOL-based premium target ranges: {tier: {threshold, min_premium, max_premium}}
DVOL_PREMIUM_RANGES = {
    "low":  {"threshold": 40,  "min": 140, "max": 300},   # DVOL < 40%
    "mid":  {"threshold": 55,  "min": 120, "max": 260},   # DVOL 40–55%
    "high": {"threshold": 999, "min": 110, "max": 240},   # DVOL > 55%
}

# --- Stop Loss & Profit Booking (Section 6) ---
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
HEDGE_MONITOR_INTERVAL = 30       # Smart hedge monitoring interval in seconds
HEDGE_RETRY_COUNT = 3             # Number of retries for hedge order placement
HEDGE_RETRY_DELAY = 2             # Seconds between hedge order retries
HEDGE_LIMIT_ORDER_SPREAD = 0.001  # 0.1% spread for limit hedge orders
HEDGE_EMERGENCY_SL_TIGHTEN = 1.05 # Tighten SL to 105% during emergency hedge

# --- Smart Hedging Pipeline (Section 3) ---
HEDGE_WAIT_AFTER_ENTRY = 5        # Seconds to wait after order fill before first hedge check
HEDGE_RECHECK_INTERVAL = 30       # Seconds between continuous hedge management checks
# IV-based hedging decision thresholds (Step 2)
HEDGE_IV_THRESHOLDS = {
    "low":  {"iv_max": 45, "delta_trigger": 0.20, "action": "full"},
    "mid":  {"iv_min": 45, "iv_max": 55, "delta_trigger": 0.17, "action": "full"},
    "high": {"iv_min": 55, "delta_trigger": 0.12, "action": "partial"},
}
HEDGE_PARTIAL_INITIAL_PCT = 0.50      # Start partial hedge at 50% of required size
HEDGE_PARTIAL_ESCALATE_PCT = 0.80     # Escalate partial hedge to 80–100%
HEDGE_PARTIAL_ESCALATE_DELTA = 0.10   # Re-check threshold after partial hedge
HEDGE_PARTIAL_WAIT = 10               # Seconds to wait between partial hedge steps
HEDGE_EMERGENCY_LOSS_PCT = 0.60       # 60% unrealized loss → force full hedge
HEDGE_RETRY_COUNT = 2                 # Number of retries on hedge order failure
HEDGE_RETRY_DELAY = 5                 # Seconds between retries
HEDGE_LIMIT_ORDER_SPREAD = 0.001      # 0.1% from mark price for limit orders in volatile markets

# --- Dynamic Position Sizing (Section 4) ---
DVOL_MID_SIZE_BOOST = 0.20            # 20% lot increase when DVOL is 40–55%
CONSECUTIVE_LOSS_REDUCE_PCT = 0.20    # 20% reduction after 2 consecutive losses
CONSECUTIVE_LOSS_THRESHOLD = 2        # Consecutive losses to trigger size reduction
CONSECUTIVE_LOSS_COOLDOWN_TRADES = 3  # Reduced-size trades before resetting
DAILY_LOSS_REDUCE_THRESHOLD = 0.02    # 2% daily loss triggers 30% lot reduction
DAILY_LOSS_REDUCE_PCT = 0.30          # Reduction percentage on 2% daily loss

# --- Money Management & Capital Protection (Section 5) ---
MAX_RISK_PER_TRADE_PCT = 0.015        # 1.5% of equity max risk per trade
DAILY_LOSS_LIMIT_PCT = 0.03           # 3% daily loss → immediate square off + stop
MAX_CONSECUTIVE_LOSSES_DAY = 3        # 3 consecutive losses in a day → stop trading
DAILY_LOSS_PAUSE_THRESHOLD = 0.025    # 2.5% loss → pause next trading day
# Never increase position size after a big loss day (enforced in bot_engine.py)

# --- DVOL Percentile Boundaries (Section 2) ---
DVOL_PERCENTILE_MIN = 10              # Minimum DVOL percentile to trade
DVOL_PERCENTILE_MAX = 90              # Maximum DVOL percentile to trade
