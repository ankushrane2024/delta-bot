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
MANUAL_TOTAL_LOTS = int(os.getenv("MANUAL_TOTAL_LOTS", 1000))

# --- Contract Size (Delta Exchange BTC Options) ---
# Each BTC options contract on Delta Exchange represents 0.001 BTC.
# P&L Formula: Total_PnL = (Entry_Premium - Current_Premium) * Lots * LOT_TO_BTC
# Example: 105 lots * 0.001 = 0.105 BTC exposure per leg
LOT_TO_BTC = 0.001  # 1 lot = 0.001 BTC (Delta Exchange BTC Options contract size)

# --- Entry/Exit Times (IST) ---
ENTRY_TIMES = ["09:00", "09:30"]
EXIT_PREPARE_TIME = "16:55"   # Start preparing forced exit at 16:55 IST
EXIT_TIME_HARD = "17:00"      # Hard square off at 17:00 IST
EXIT_TIME_START = "17:00"     # Kept for backward compatibility
EXIT_TIME_END = "17:20"       # Kept for backward compatibility

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Strategy Parameters ---

# --- DVOL-Based Strike Selection (Section 1) ---
# Minimum number of strikes OTM from ATM for both call and put legs.
MIN_OTM_STRIKES = 5
# Put premium must not exceed this multiple of call premium.
PUT_SKEW_CAP = 1.30
# Maximum allowed absolute net delta at entry. Triggers 1-strike OTM shift if exceeded.
NET_DELTA_ENTRY_LIMIT = 0.10
# DVOL-based premium target ranges: {tier: {threshold, min_premium, max_premium}}
DVOL_PREMIUM_RANGES = {
    "low":  {"threshold": 40,  "min": 140, "max": 300},   # DVOL < 40%
    "mid":  {"threshold": 55,  "min": 120, "max": 260},   # DVOL 40–55%
    "high": {"threshold": 999, "min": 110, "max": 240},   # DVOL > 55%
}

# --- Stop Loss & Profit Booking (Section 6) ---
SL_PERCENT = 1.30              # 130% of collected premium → triggers full exit (tighter)
PARTIAL_PROFIT_TRIGGER = 0.20  # 20% profit reached -> trigger partial close
PARTIAL_PROFIT_SIZE = 0.50     # Close 50% of position size on partial profit
TRAILING_SL_TRIGGER = 0.15    # After 15% profit -> activate trailing SL to breakeven
TRAILING_SL_LEVEL = 0.0       # Trailing SL level: breakeven (0% profit)
EXIT_PROFIT_TARGET = 0.30     # 30% total profit -> full exit
MIN_HOLD_SECONDS = 30         # Minimum seconds to hold before any profit target exit is allowed

# --- Hedging Parameters ---
HEDGE_SYMBOL = "BTCUSD"           # BTC Perpetual futures contract symbol
HEDGE_MONITOR_INTERVAL = 15       # Smart hedge monitoring interval in seconds (Tighter)
HEDGE_RETRY_COUNT = 3             # Number of retries for hedge order placement
HEDGE_RETRY_DELAY = 2             # Seconds between hedge order retries
HEDGE_LIMIT_ORDER_SPREAD = 0.001  # 0.1% spread for limit hedge orders

# --- Smart Hedging Pipeline (Section 3) ---
HEDGE_WAIT_AFTER_ENTRY = 5        # Seconds to wait after order fill before first hedge check
HEDGE_RECHECK_INTERVAL = 15       # Seconds between continuous hedge management checks

# --- Dynamic Position Sizing (Section 4) ---
DVOL_MID_SIZE_BOOST = 0.20            # 20% lot increase when DVOL is 40–55%
CONSECUTIVE_LOSS_REDUCE_PCT = 0.20    # 20% reduction after 2 consecutive losses
CONSECUTIVE_LOSS_THRESHOLD = 2        # Consecutive losses to trigger size reduction
CONSECUTIVE_LOSS_COOLDOWN_TRADES = 3  # Reduced-size trades before resetting
DAILY_LOSS_REDUCE_THRESHOLD = 0.02    # 2% daily loss triggers 30% lot reduction
DAILY_LOSS_REDUCE_PCT = 0.30          # Reduction percentage on 2% daily loss

# --- Money Management & Capital Protection (Section 5) ---
MAX_RISK_PER_TRADE_PCT = 0.010        # 1.0% of equity max risk per trade
DAILY_LOSS_LIMIT_PCT = 0.02           # 2% daily loss → immediate square off + stop
MAX_CONSECUTIVE_LOSSES_DAY = 3        # 3 consecutive losses in a day → stop trading
DAILY_LOSS_PAUSE_THRESHOLD = 0.025    # 2.5% loss → pause next trading day
# Never increase position size after a big loss day (enforced in bot_engine.py)

# --- DVOL Percentile Boundaries (Section 2) ---
DVOL_PERCENTILE_MIN = 10              # Minimum DVOL percentile to trade
DVOL_PERCENTILE_MAX = 90              # Maximum DVOL percentile to trade

# --- Delta Factor Parameters (Module 19) ---
DELTA_SIGMOID_CENTER = float(os.getenv("DELTA_SIGMOID_CENTER", 0.5))
DELTA_SIGMOID_STEEPNESS = float(os.getenv("DELTA_SIGMOID_STEEPNESS", 10.0))

# --- Gamma Factor Parameters (Module 20) ---
GAMMA_SENSITIVITY_K = float(os.getenv("GAMMA_SENSITIVITY_K", 0.05))

# --- Vega Factor Parameters (Module 21) ---
VEGA_REFERENCE = float(os.getenv("VEGA_REFERENCE", 10.0))  # Vega value at which stress reaches 50%
