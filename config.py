import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- API Settings ---
DELTA_API_KEY = os.getenv("DELTA_API_KEY", "")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET", "")
DELTA_INDIA_BASE_URL = "https://api.india.delta.exchange"
DELTA_INDIA_WS_URL = "wss://socket.india.delta.exchange"
DELTA_GLOBAL_LIVE_BASE_URL = "https://api.delta.exchange"
DELTA_GLOBAL_LIVE_WS_URL = "wss://socket.delta.exchange"
DELTA_GLOBAL_DEMO_BASE_URL = "https://testnet-api.delta.exchange"
DELTA_GLOBAL_DEMO_WS_URL = "wss://testnet-api.delta.exchange"
DELTA_INDIA_DEMO_BASE_URL = "https://cdn-ind.testnet.deltaex.org"
DELTA_INDIA_DEMO_WS_URL = "wss://socket-ind.testnet.deltaex.org"
DELTA_BASE_URL = os.getenv("DELTA_BASE_URL", DELTA_INDIA_BASE_URL)

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
# Bot stops trading for the day if floating loss >= 3% (DISABLED PER USER REQUEST).
MAX_DAILY_LOSS_PCT = 1.00

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
_env_entry_times = os.getenv("ENTRY_TIMES")
if _env_entry_times:
    ENTRY_TIMES = [t.strip() for t in _env_entry_times.split(",") if t.strip()]
else:
    ENTRY_TIMES = ["22:30"]  # 10:30 PM IST — Midnight BTC Strangle overnight session

EXIT_PREPARE_TIME = os.getenv("EXIT_PREPARE_TIME", "16:55")   # Start preparing forced exit at 16:55 IST
EXIT_TIME_HARD = os.getenv("EXIT_TIME_HARD", "17:00")         # Hard square off at 17:00 IST
EXIT_TIME_START = os.getenv("EXIT_TIME_START", "17:00")       # Kept for backward compatibility
EXIT_TIME_END = os.getenv("EXIT_TIME_END", "17:20")           # Kept for backward compatibility

# --- Telegram Settings ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# --- Strategy Parameters ---

# ─── BALANCE BTC MIDNIGHT STRANGLE (Straddle Width Strike Selection) ───────
# Strategy: Sell OTM Call + Sell OTM Put using ATM Straddle Price as width multiplier
# Leg 1 (Call): Strike = ATM + CALL_STRADDLE_MULT × ATM_Straddle_Price
# Leg 2 (Put):  Strike = ATM - PUT_STRADDLE_MULT  × ATM_Straddle_Price

CALL_STRADDLE_MULT   = float(os.getenv("CALL_STRADDLE_MULT", 1.6))   # Call leg: 1.6x straddle width OTM
PUT_STRADDLE_MULT    = float(os.getenv("PUT_STRADDLE_MULT",  2.3))   # Put leg:  2.3x straddle width OTM
LEG_SL_PCT           = float(os.getenv("LEG_SL_PCT", 100.0))         # Per-leg SL: 100% of leg premium
SL_REENTRY_ENABLED   = True                                           # Re-entry on SL hit
SL_REENTRY_MAX_COUNT = int(os.getenv("SL_REENTRY_MAX_COUNT", 1))     # Max 1 re-entry per leg
SL_REENTRY_LEG_SL_PCT = float(os.getenv("SL_REENTRY_LEG_SL_PCT", 100.0))  # 100% SL to trigger re-entry
SL_REENTRY_DELTA_TOLERANCE = 0.05

# --- Overall Strategy Settings ---
OVERALL_SL_ENABLED   = False
OVERALL_SL_TYPE      = "Total Premium %"
OVERALL_SL_VALUE     = 10.0
OVERALL_TARGET_ENABLED = False
OVERALL_TARGET_TYPE  = "Max Profit"
OVERALL_TARGET_VALUE = 0.0

# --- Trailing / Lock and Trail ---
TRAILING_ENABLED     = False
TRAILING_MODE        = "Lock and Trail"
TRAIL_IF_PROFIT      = float(os.getenv("TRAIL_IF_PROFIT", 11.0))     # Lock when profit reaches 11%
TRAIL_LOCK_PROFIT    = float(os.getenv("TRAIL_LOCK_PROFIT", 1.0))    # Lock 1%
TRAIL_INCREASE_BY    = float(os.getenv("TRAIL_INCREASE_BY", 5.0))    # For every 5% more profit
TRAIL_PROFIT_BY      = float(os.getenv("TRAIL_PROFIT_BY", 5.0))      # Trail by 5%

# --- ARES Dynamic Profit Lock (kept for compatibility) ---
TRAILING_CONFIRM_THRESHOLD = TRAIL_IF_PROFIT / 100.0
TRAILING_CONFIRM_TARGET    = TRAIL_IF_PROFIT / 100.0
CAPITAL_PROTECTION_SL      = TRAIL_LOCK_PROFIT / 100.0
PROFIT_LOCK_TIERS          = []     # Replaced by Lock-and-Trail above
DYNAMIC_TRAIL_THRESHOLD    = (TRAIL_IF_PROFIT + TRAIL_INCREASE_BY) / 100.0
DYNAMIC_TRAIL_GAP          = TRAIL_PROFIT_BY / 100.0

# --- Stop Loss ---
SL_PERCENT           = LEG_SL_PCT / 100.0   # e.g. 1.00 = 100% of premium
MIN_ENTRY_PREMIUM    = float(os.getenv("MIN_ENTRY_PREMIUM", 1.0))
MIN_HOLD_SECONDS     = 30

# --- Legacy strike params (kept for imports that reference them) ---
MIN_OTM_STRIKES      = 5
PUT_SKEW_CAP         = 1.35
NET_DELTA_ENTRY_LIMIT = 0.15
DVOL_PREMIUM_RANGES  = {
    "low":  {"threshold": 40,  "min": 100, "max": 300},
    "mid":  {"threshold": 55,  "min": 100, "max": 260},
    "high": {"threshold": 999, "min": 100, "max": 240},
}

# --- Expiry Cutoff ---
EXPIRY_CUTOFF_HOUR   = 17
EXPIRY_CUTOFF_MINUTE = 28

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
