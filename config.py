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

# --- Stop Loss & Dynamic Profit Lock (Section 6) ---
SL_PERCENT = 1.00              # 100% of collected premium → triggers full exit
MIN_ENTRY_PREMIUM = 100.0      # Minimum required premium for entry
MIN_HOLD_SECONDS = 30          # Minimum seconds to hold before any exit is allowed

# --- ARES Dynamic Profit Lock ---
# Trailing confirmation: lock SL at +5% as soon as 19% profit is confirmed
TRAILING_CONFIRM_THRESHOLD = 0.15    # 15%: Begin tracking (confirmation window opens)
TRAILING_CONFIRM_TARGET = 0.19       # 19%: Confirm and lock SL at +5% (was incorrectly 0.15)
CAPITAL_PROTECTION_SL = 0.05         # Lock SL at +5% once 19% is confirmed

# Progressive profit lock tiers: (profit_threshold, sl_level)
PROFIT_LOCK_TIERS = [
    (0.20, 0.12),  # 20% profit → SL = 12%
    (0.25, 0.17),  # 25% profit → SL = 17%
    (0.28, 0.23),  # 28% profit → SL = 23%
]

# Dynamic trailing after 28%: SL = Peak Profit - 5%
DYNAMIC_TRAIL_THRESHOLD = 0.28
DYNAMIC_TRAIL_GAP = 0.05

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
# Daily Loss Limit (2%) removed per user request
# Max consecutive losses and Next day pause rules REMOVED as per user request
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

# --- Premium Growth Factor Parameters (Module 22) ---
PREMIUM_GROWTH_REFERENCE_K = float(os.getenv("PREMIUM_GROWTH_REFERENCE_K", 1.0)) # 1.0 = 100% premium growth -> 50 stress
PREMIUM_GROWTH_STEEPNESS_N = float(os.getenv("PREMIUM_GROWTH_STEEPNESS_N", 3.0)) # Hill coefficient for acceleration

# --- IV Expansion Factor Parameters (Module 23) ---
IV_EXPANSION_REFERENCE = float(os.getenv("IV_EXPANSION_REFERENCE", 1.0)) # 1.0 = 100% IV increase -> 50 stress
IV_EXPANSION_SHAPE_N = float(os.getenv("IV_EXPANSION_SHAPE_N", 3.0)) # Weibull shape parameter (Cubed Exponential)

# --- Trend Factor Parameters (Module 24) ---
TREND_SIGMOID_CENTER = float(os.getenv("TREND_SIGMOID_CENTER", 60.0))
TREND_SIGMOID_STEEPNESS = float(os.getenv("TREND_SIGMOID_STEEPNESS", 0.1))

# --- Market Regime Factor Parameters (Module 25) ---
REGIME_BASE_SCORE_SAFE_RANGE = float(os.getenv("REGIME_BASE_SCORE_SAFE_RANGE", 0.0))
REGIME_BASE_SCORE_WEAK_RANGE = float(os.getenv("REGIME_BASE_SCORE_WEAK_RANGE", 10.0))
REGIME_BASE_SCORE_TRANSITION = float(os.getenv("REGIME_BASE_SCORE_TRANSITION", 30.0))
REGIME_BASE_SCORE_EARLY_TREND = float(os.getenv("REGIME_BASE_SCORE_EARLY_TREND", 60.0))
REGIME_BASE_SCORE_CONFIRMED_TREND = float(os.getenv("REGIME_BASE_SCORE_CONFIRMED_TREND", 85.0))
REGIME_BASE_SCORE_ACCELERATION = float(os.getenv("REGIME_BASE_SCORE_ACCELERATION", 100.0))
REGIME_BASE_SCORE_TREND_EXHAUSTION = float(os.getenv("REGIME_BASE_SCORE_TREND_EXHAUSTION", 40.0))

# --- Time-to-Expiry Factor Parameters (Module 26) ---
TIME_EXPIRY_REFERENCE_DAYS = float(os.getenv("TIME_EXPIRY_REFERENCE_DAYS", 10.0))

# --- P&L Factor Parameters (Module 27) ---
PNL_STRESS_REFERENCE_LOSS = float(os.getenv("PNL_STRESS_REFERENCE_LOSS", 500.0))

# --- Stress Fusion Parameters (Module 29) ---
FUSION_SOFTMAX_K = float(os.getenv("FUSION_SOFTMAX_K", 0.05)) # Determines how aggressively the dominant factor takes over
CONFIDENCE_PENALTY_POWER = float(os.getenv("CONFIDENCE_PENALTY_POWER", 2.0)) # How aggressively low confidence penalizes medium risks

# --- Decision Engine Parameters (Module 30) ---
DECISION_EMA_ALPHA = float(os.getenv("DECISION_EMA_ALPHA", 0.3)) # Smoothing factor for fused stress

HEDGE_THRESHOLD_PREPARE = float(os.getenv("HEDGE_THRESHOLD_PREPARE", 50.0))
HEDGE_THRESHOLD_PARTIAL = float(os.getenv("HEDGE_THRESHOLD_PARTIAL", 65.0))
HEDGE_THRESHOLD_FULL = float(os.getenv("HEDGE_THRESHOLD_FULL", 80.0))
HEDGE_THRESHOLD_EMERGENCY = float(os.getenv("HEDGE_THRESHOLD_EMERGENCY", 95.0))

UNHEDGE_THRESHOLD_BUFFER = float(os.getenv("UNHEDGE_THRESHOLD_BUFFER", 10.0)) # Needs to drop 10 points below threshold to dehedge

PARTIAL_HEDGE_RATIO = float(os.getenv("PARTIAL_HEDGE_RATIO", 0.5))
FULL_HEDGE_RATIO = float(os.getenv("FULL_HEDGE_RATIO", 1.0))

# --- Hedge Sizing Engine Parameters (Module 31) ---
FUTURES_CONTRACT_SIZE_BTC = float(os.getenv("FUTURES_CONTRACT_SIZE_BTC", 0.001)) # 1 contract = 0.001 BTC
MIN_ORDER_QTY = float(os.getenv("MIN_ORDER_QTY", 1.0))
QTY_STEP_SIZE = float(os.getenv("QTY_STEP_SIZE", 1.0))
MAX_ORDER_QTY = float(os.getenv("MAX_ORDER_QTY", 10000.0))


# --- Hedge Provider Override ---
SMART_HEDGE_PROVIDER = os.getenv('SMART_HEDGE_PROVIDER', 'ARES')
