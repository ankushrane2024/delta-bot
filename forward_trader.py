"""
╔══════════════════════════════════════════════════════════════════════════╗
║          BALANCE BTC MIDNIGHT - FORWARD TEST AUTO TRADER                 ║
║   Auto Daily Paper Trade: Mon-Fri Only, Full INR Lock & Trail            ║
║                                                                          ║
║  Lock & Trail (INR):                                                     ║
║    If Total Profit >= ₹1500  →  Lock ₹500 as floor                      ║
║    Every ₹500 more profit    →  Trail floor up by ₹200                   ║
║                                                                          ║
║  Schedule: Entry at 10:30 PM IST, Square-off at 5:00 PM next day        ║
║  Trade Days: Monday – Friday (Saturday & Sunday are skipped)             ║
║  Records: All trades logged in forward_test_log.json                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import threading
import datetime
import time
import json
import os
import logging
import sys

# ─── Lock & Trail Configuration (INR-based as per user spec) ───────────────
FT_LOCK_TRIGGER_INR   = 1500.0   # Activate Lock when profit reaches ₹1500
FT_LOCK_AMOUNT_INR    = 500.0    # Initial locked floor: ₹500
FT_TRAIL_STEP_INR     = 500.0    # For every ₹500 more profit...
FT_TRAIL_BY_INR       = 200.0    # ...trail the floor up by ₹200
INR_PER_USD           = 85.0     # 1 USD = 85 INR (configurable)
LOTS_PER_LEG          = 500      # 500 lots per leg
LOT_TO_BTC            = 0.001    # 1 lot = 0.001 BTC
DEFAULT_SLIPPAGE_PCT  = 5.0      # 5% default execution slippage per user requirement

# ─── Time Settings (IST) ────────────────────────────────────────────────────
ENTRY_HOUR, ENTRY_MIN    = 22, 30   # 10:30 PM IST  
SQUAREOFF_HOUR, SQUAREOFF_MIN = 17, 0  # 5:00 PM IST next day

# ─── Paths ───────────────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'forward_test_log.json')

logging.basicConfig(level=logging.INFO, format='[FT][%(asctime)s] %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger('ForwardTrader')


class LockTrailEngine:
    """
    INR-based Lock and Trail profit protection engine.
    Dynamically configurable from strategy_config.json.
    """
    def __init__(self, trigger_inr=FT_LOCK_TRIGGER_INR, lock_inr=FT_LOCK_AMOUNT_INR, step_inr=FT_TRAIL_STEP_INR, trail_inr=FT_TRAIL_BY_INR):
        self.trigger_inr = float(trigger_inr)
        self.lock_inr    = float(lock_inr)
        self.step_inr    = float(step_inr)
        self.trail_inr   = float(trail_inr)
        self.reset()

    def configure(self, trigger_inr, lock_inr, step_inr, trail_inr):
        self.trigger_inr = float(trigger_inr)
        self.lock_inr    = float(lock_inr)
        self.step_inr    = float(step_inr)
        self.trail_inr   = float(trail_inr)

    def reset(self):
        self.peak_inr     = 0.0
        self.locked_inr   = None   # None = not activated yet
        self.lock_active  = False
        self.last_log_ts  = 0

    def update(self, total_pnl_inr: float) -> dict:
        result = {'locked': self.lock_active, 'locked_floor': self.locked_inr, 'exit_now': False, 'exit_reason': ''}

        # Update peak
        if total_pnl_inr > self.peak_inr:
            self.peak_inr = total_pnl_inr

        # --- PHASE 1: Activate lock when profit first hits trigger ---
        if not self.lock_active and self.peak_inr >= self.trigger_inr:
            self.locked_inr  = self.lock_inr
            self.lock_active = True
            logger.info(f"🔒 LOCK ACTIVATED: Profit peak ₹{self.peak_inr:.0f} >= ₹{self.trigger_inr:.0f} → Floor locked at ₹{self.locked_inr:.0f}")

        # --- PHASE 2: Ratchet trail when lock is active ---
        if self.lock_active:
            excess = self.peak_inr - self.trigger_inr
            steps  = int(excess // self.step_inr) if self.step_inr > 0 else 0
            new_floor = self.lock_inr + steps * self.trail_inr

            if new_floor > self.locked_inr:
                logger.info(f"📈 TRAIL RATCHET: Peak ₹{self.peak_inr:.0f} → Floor raised from ₹{self.locked_inr:.0f} to ₹{new_floor:.0f}")
                self.locked_inr = new_floor

            result['locked']       = True
            result['locked_floor'] = self.locked_inr

            # --- PHASE 3: Exit if profit drops below floor ---
            if total_pnl_inr < self.locked_inr:
                result['exit_now']    = True
                result['exit_reason'] = f'LOCK_TRAIL_EXIT (PnL ₹{total_pnl_inr:.0f} < Floor ₹{self.locked_inr:.0f})'
                logger.info(f"🚨 LOCK & TRAIL TRIGGERED: Profit ₹{total_pnl_inr:.0f} dropped below floor ₹{self.locked_inr:.0f}")

        return result


class ForwardTestRecorder:
    """Maintains persistent JSON log of all forward test trades."""

    def __init__(self, log_file=LOG_FILE):
        self.log_file = log_file
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                json.dump({'trades': [], 'summary': {'total_trades': 0, 'wins': 0, 'losses': 0,
                           'total_pnl_usd': 0.0, 'total_pnl_inr': 0.0}}, f, indent=2)

    def save_trade(self, trade: dict):
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
        except Exception:
            data = {'trades': [], 'summary': {'total_trades': 0, 'wins': 0, 'losses': 0,
                    'total_pnl_usd': 0.0, 'total_pnl_inr': 0.0}}

        data['trades'].append(trade)
        s = data['summary']
        s['total_trades'] += 1
        pnl_inr = trade.get('pnl_inr', 0.0)
        s['total_pnl_usd'] = round(s.get('total_pnl_usd', 0.0) + trade.get('pnl_usd', 0.0), 2)
        s['total_pnl_inr'] = round(s.get('total_pnl_inr', 0.0) + pnl_inr, 2)
        if pnl_inr >= 0:
            s['wins'] = s.get('wins', 0) + 1
        else:
            s['losses'] = s.get('losses', 0) + 1
        s['win_rate_pct'] = round(s['wins'] / s['total_trades'] * 100, 2) if s['total_trades'] > 0 else 0.0

        with open(self.log_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"💾 Trade saved to {self.log_file}. Total trades: {s['total_trades']}, Win Rate: {s['win_rate_pct']}%")

    def get_summary(self) -> dict:
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            return data.get('summary', {})
        except Exception:
            return {}

    def get_all_trades(self) -> list:
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            return data.get('trades', [])
        except Exception:
            return []


class ForwardTrader:
    """
    Daily auto-trader that:
    - Skips Saturday and Sunday
    - Enters Straddle Width strangle at 10:30 PM IST
    - Monitors with Lock & Trail (INR) every 5 seconds
    - Squares off at 5:00 PM IST or on Lock & Trail exit
    - Records every trade with full details
    """

    def __init__(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bot_core import bot_instance
        self.bot         = bot_instance
        self.recorder    = ForwardTestRecorder()
        self.lock_trail  = LockTrailEngine()
        self.mode        = 'PAPER'
        self.running     = False
        self._thread     = None

        # Per-trade state
        self.trade_active     = False
        self.trade_date       = None
        self.entry_time       = None
        self.entry_btc        = 0.0
        self.call_sym         = ''
        self.put_sym          = ''
        self.call_entry       = 0.0
        self.put_entry        = 0.0
        self.call_exit        = None
        self.put_exit         = None
        self.call_sl          = 0.0
        self.put_sl           = 0.0
        self.lots             = LOTS_PER_LEG
        self.call_sl_hits     = 0
        self.put_sl_hits      = 0
        self.realized_pnl_usd = 0.0
        self.pnl_snapshots    = []   # [{time, pnl_inr, locked_floor, btc}]

        # Configurable rules (loaded dynamically from strategy_config.json)
        self.call_mult        = 1.6
        self.put_mult         = 2.3
        self.leg_sl_pct       = 100.0
        self.reentry_enabled  = True
        self.reentry_max      = 1
        self.slippage_pct     = DEFAULT_SLIPPAGE_PCT
        self.entry_hour       = ENTRY_HOUR
        self.entry_min        = ENTRY_MIN
        self.squareoff_hour   = SQUAREOFF_HOUR
        self.squareoff_min    = SQUAREOFF_MIN

        self.reload_config()

        logger.info("✅ ForwardTrader initialized. Use start() to begin.")

    def reload_config(self):
        """Dynamically reload strategy rules from strategy_config.json."""
        cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategy_config.json')
        cfg = {}
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, 'r') as f:
                    cfg = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load strategy_config.json: {e}")

        leg1    = cfg.get('leg1', {})
        leg2    = cfg.get('leg2', {})
        overall = cfg.get('overall', {})

        # Multipliers (prefer nested leg1/leg2 from UI if present)
        if 'strike_multiplier' in leg1 and leg1['strike_multiplier']:
            self.call_mult = float(leg1['strike_multiplier'])
        elif 'call_straddle_mult' in cfg and cfg['call_straddle_mult']:
            self.call_mult = float(cfg['call_straddle_mult'])
        else:
            self.call_mult = 1.6

        if 'strike_multiplier' in leg2 and leg2['strike_multiplier']:
            self.put_mult = float(leg2['strike_multiplier'])
        elif 'put_straddle_mult' in cfg and cfg['put_straddle_mult']:
            self.put_mult = float(cfg['put_straddle_mult'])
        else:
            self.put_mult = 2.3

        # Stop Loss & Lots
        if 'stop_loss_value' in leg1 and leg1['stop_loss_value'] is not None:
            self.leg_sl_pct = float(leg1['stop_loss_value'])
        elif 'leg_sl_pct' in cfg and cfg['leg_sl_pct'] is not None:
            self.leg_sl_pct = float(cfg['leg_sl_pct'])
        else:
            self.leg_sl_pct = 100.0

        if 'lots' in leg1 and leg1['lots']:
            self.lots = int(leg1['lots'])
        elif 'total_lots' in cfg and cfg['total_lots']:
            self.lots = int(cfg['total_lots']) // 2
        else:
            self.lots = LOTS_PER_LEG

        # Re-entry
        if 'reentry_sl_on' in leg1:
            self.reentry_enabled = bool(leg1['reentry_sl_on'])
        else:
            self.reentry_enabled = bool(cfg.get('sl_reentry_enabled', True))

        if 'reentry_sl_count' in leg1:
            self.reentry_max = int(leg1['reentry_sl_count'])
        else:
            self.reentry_max = int(cfg.get('sl_reentry_max', 1))

        # Slippage
        self.slippage_pct = float(cfg.get('slippage_pct', DEFAULT_SLIPPAGE_PCT))

        # Times
        entry_str = cfg.get('entry_time', '22:30')
        try:
            eh, em = entry_str.split(':')
            self.entry_hour, self.entry_min = int(eh), int(em)
        except Exception:
            self.entry_hour, self.entry_min = ENTRY_HOUR, ENTRY_MIN

        exit_str = cfg.get('exit_time', '17:00')
        try:
            xh, xm = exit_str.split(':')
            self.squareoff_hour, self.squareoff_min = int(xh), int(xm)
        except Exception:
            self.squareoff_hour, self.squareoff_min = SQUAREOFF_HOUR, SQUAREOFF_MIN

        # Lock & Trail values:
        trig  = FT_LOCK_TRIGGER_INR
        lock  = FT_LOCK_AMOUNT_INR
        step  = FT_TRAIL_STEP_INR
        trail = FT_TRAIL_BY_INR

        if 'lock_trail_trigger_inr' in cfg:
            trig = float(cfg['lock_trail_trigger_inr'])
        elif 'trail_if_profit_inr' in overall:
            trig = float(overall['trail_if_profit_inr'])
        elif 'trail_if_profit' in overall and float(overall['trail_if_profit']) > 100:
            trig = float(overall['trail_if_profit'])
        elif 'trail_if_profit' in cfg and float(cfg['trail_if_profit']) > 100:
            trig = float(cfg['trail_if_profit'])

        if 'lock_trail_lock_inr' in cfg:
            lock = float(cfg['lock_trail_lock_inr'])
        elif 'trail_lock_profit_inr' in overall:
            lock = float(overall['trail_lock_profit_inr'])
        elif 'trail_lock_profit' in overall and float(overall['trail_lock_profit']) >= 50:
            lock = float(overall['trail_lock_profit'])
        elif 'trail_lock_profit' in cfg and float(cfg['trail_lock_profit']) >= 50:
            lock = float(cfg['trail_lock_profit'])

        if 'lock_trail_step_inr' in cfg:
            step = float(cfg['lock_trail_step_inr'])
        elif 'trail_increase_by_inr' in overall:
            step = float(overall['trail_increase_by_inr'])
        elif 'trail_increase_by' in overall and float(overall['trail_increase_by']) >= 50:
            step = float(overall['trail_increase_by'])
        elif 'trail_increase_by' in cfg and float(cfg['trail_increase_by']) >= 50:
            step = float(cfg['trail_increase_by'])

        if 'lock_trail_trail_inr' in cfg:
            trail = float(cfg['lock_trail_trail_inr'])
        elif 'trail_profit_by_inr' in overall:
            trail = float(overall['trail_profit_by_inr'])
        elif 'trail_profit_by' in overall and float(overall['trail_profit_by']) >= 50:
            trail = float(overall['trail_profit_by'])
        elif 'trail_profit_by' in cfg and float(cfg['trail_profit_by']) >= 50:
            trail = float(cfg['trail_profit_by'])

        self.lock_trail.configure(trig, lock, step, trail)
        logger.info(f"🔄 Config reloaded: CE +{self.call_mult}x | PE -{self.put_mult}x | SL {self.leg_sl_pct}% | Lots {self.lots} | Slip {self.slippage_pct}%")
        logger.info(f"   Lock & Trail: Trigger ₹{trig:.0f} → Lock ₹{lock:.0f} | Step ₹{step:.0f} → Trail ₹{trail:.0f}")

    def _ist_now(self) -> datetime.datetime:
        return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)

    def _is_weekday(self, dt: datetime.datetime) -> bool:
        return dt.weekday() < 5   # 0=Mon ... 4=Fri; 5=Sat, 6=Sun

    def _get_pnl_inr(self) -> float:
        """Calculate current total (realized + unrealized) PnL in INR with 5% slippage."""
        return round(self._get_pnl_usd() * INR_PER_USD, 2)

    def _get_pnl_usd(self) -> float:
        """Calculate current total (realized + unrealized) PnL in USD including 5% exit slippage."""
        pos = self.bot.state[self.mode]['positions']
        unrealized = 0.0
        slip_exit_mult = 1.0 + (DEFAULT_SLIPPAGE_PCT / 100.0)
        for leg in ['call', 'put']:
            if pos.get(leg):
                p = pos[leg]
                cur = p.get('current_price', p['entry_price'])
                cur_with_slip = cur * slip_exit_mult
                unrealized += (p['entry_price'] - cur_with_slip) * p['size'] * LOT_TO_BTC
        return round(self.realized_pnl_usd + unrealized, 4)

    def _enter_trade(self):
        """Enter the daily paper strangle trade with 5% slippage and strike lock."""
        # GUARD: STRIKE LOCK ENFORCEMENT
        # Once strikes are selected, they MUST NOT change or get updated/overwritten!
        if self.trade_active:
            logger.warning(f"🔒 STRIKES LOCKED: Trade is already active (CE: {self.call_sym}, PE: {self.put_sym}). Strikes cannot change until SL or exit.")
            return False

        ist = self._ist_now()
        logger.info("=" * 60)
        logger.info(f"🚀 FORWARD TEST ENTRY: {ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
        logger.info(f"   Default Slippage: {DEFAULT_SLIPPAGE_PCT}% applied on entry and exit")
        logger.info("=" * 60)

        # Reset positions
        self.bot.state[self.mode]['positions'] = {'call': None, 'put': None}
        self.bot.state[self.mode]['reentry_watch'] = {'call': None, 'put': None}
        self.bot.state[self.mode]['running'] = True

        # Reset lock & trail state
        self.lock_trail.reset()
        setattr(self.bot, f'{self.mode.lower()}_trail_state', {'peak': 0.0, 'locked_sl': None})

        btc = self.bot.current_btc_price
        if btc <= 0:
            btc = self.bot.india_client.get_btc_price()
        if btc <= 0:
            logger.error("❌ Cannot get BTC price. Trade aborted.")
            return False

        # Fetch option chain and pick strikes
        import config as _cfg
        options = self.bot.india_client.get_option_chain()
        if not options:
            logger.error("❌ Could not fetch option chain. Trade aborted.")
            return False

        expiries = self.bot.get_valid_expiries(options)
        if not expiries:
            logger.error("❌ No valid expiries found. Trade aborted.")
            return False

        # At 10:30 PM IST we target next day expiry (or closest available)
        ist_tomorrow = (ist + datetime.timedelta(days=1)).strftime('%d%m%y')
        target_dates = [exp for exp in expiries if ist_tomorrow in exp]
        if not target_dates:
            target_dates = [expiries[0]]

        logger.info(f"  BTC Spot: ${btc:.2f} | Target Expiry: {target_dates}")

        # Dynamically reload latest settings
        self.reload_config()
        call_mult = self.call_mult
        put_mult  = self.put_mult
        sw_ce, sw_pe = self.bot.find_straddle_width_strikes(options, btc, target_dates, call_mult, put_mult)

        if not sw_ce or not sw_pe:
            logger.error("❌ Could not find Straddle Width strikes. Trade aborted.")
            return False

        call_sym, call_prem, call_id = sw_ce
        put_sym,  put_prem,  put_id  = sw_pe

        # Slippage on Sell Entry: filled at slippage_pct lower premium
        slip_entry_mult = 1.0 - (self.slippage_pct / 100.0)
        call_entry_eff  = round(call_prem * slip_entry_mult, 2)
        put_entry_eff   = round(put_prem  * slip_entry_mult, 2)

        # SL Level based on self.leg_sl_pct
        call_sl = round(call_prem * (1.0 + self.leg_sl_pct / 100.0), 2)
        put_sl  = round(put_prem  * (1.0 + self.leg_sl_pct / 100.0), 2)

        logger.info(f"  CE: {call_sym} @ raw ${call_prem:.2f} → effective ${call_entry_eff:.2f} ({self.slippage_pct}% slippage) | SL ({self.leg_sl_pct}%): ${call_sl:.2f}")
        logger.info(f"  PE: {put_sym} @ raw ${put_prem:.2f} → effective ${put_entry_eff:.2f} ({self.slippage_pct}% slippage) | SL ({self.leg_sl_pct}%): ${put_sl:.2f}")

        # Set paper positions
        pos = self.bot.state[self.mode]['positions']
        pos['call'] = {
            'symbol': call_sym, 'strike': 0, 'side': 'SELL CALL',
            'raw_entry': call_prem,
            'entry_price': call_entry_eff, 'current_price': call_prem,
            'size': self.lots, 'pnl': 0.0,
            'sl': call_sl,
            'sl_on': True, 'tp_on': False, 'reentry_count': 0
        }
        pos['put'] = {
            'symbol': put_sym, 'strike': 0, 'side': 'SELL PUT',
            'raw_entry': put_prem,
            'entry_price': put_entry_eff, 'current_price': put_prem,
            'size': self.lots, 'pnl': 0.0,
            'sl': put_sl,
            'sl_on': True, 'tp_on': False, 'reentry_count': 0
        }

        # Store trade metadata
        self.trade_active     = True
        self.trade_date       = ist.strftime('%Y-%m-%d')
        self.entry_time       = ist.isoformat()
        self.entry_btc        = btc
        self.call_sym         = call_sym
        self.put_sym          = put_sym
        self.call_raw_entry   = call_prem
        self.put_raw_entry    = put_prem
        self.call_entry       = call_entry_eff
        self.put_entry        = put_entry_eff
        self.call_exit        = None
        self.put_exit         = None
        self.realized_pnl_usd = 0.0
        self.call_sl          = call_sl
        self.put_sl           = put_sl
        self.call_sl_hits     = 0
        self.put_sl_hits      = 0
        self.pnl_snapshots    = []

        logger.info(f"  🔒 STRIKES LOCKED: CE {call_sym} & PE {put_sym} are locked in and will NOT change.")
        logger.info(f"  Lock & Trail: Trigger ₹{FT_LOCK_TRIGGER_INR:.0f} → Lock ₹{FT_LOCK_AMOUNT_INR:.0f} | Per ₹{FT_TRAIL_STEP_INR:.0f} → Trail ₹{FT_TRAIL_BY_INR:.0f}")
        logger.info("  ✅ Paper positions entered. Monitoring begins now.")
        return True

    def manual_squareoff(self):
        """Manually turn off/exit the active forward test trade right now."""
        if not self.trade_active:
            return False, "No active forward test trade to turn off."
        logger.info("🛑 MANUAL OFF TRIGGERED: Squaring off all positions immediately.")
        pnl_inr = self._squareoff(reason='MANUAL_OFF')
        return True, f"Active trade successfully squared off manually. PnL: ₹{pnl_inr:.2f}"

    def _squareoff(self, reason: str = 'SCHEDULED_SQUAREOFF'):
        """Square off all positions and record the trade."""
        ist = self._ist_now()
        pos = self.bot.state[self.mode]['positions']

        # Close any surviving legs with dynamic exit buyback slippage
        slip_exit_mult = 1.0 + (self.slippage_pct / 100.0)
        for leg in ['call', 'put']:
            if pos.get(leg):
                p   = pos[leg]
                cur = p.get('current_price', p['entry_price'])
                cur_with_slip = round(cur * slip_exit_mult, 2)
                leg_realized = (p['entry_price'] - cur_with_slip) * p['size'] * LOT_TO_BTC
                self.realized_pnl_usd += leg_realized
                if leg == 'call':
                    self.call_exit = cur_with_slip
                else:
                    self.put_exit  = cur_with_slip

        pnl_usd = round(self.realized_pnl_usd, 4)
        pnl_inr = round(pnl_usd * INR_PER_USD, 2)
        call_exit_px = self.call_exit if self.call_exit is not None else self.call_entry
        put_exit_px  = self.put_exit if self.put_exit is not None else self.put_entry

        logger.info("=" * 60)
        logger.info(f"📤 SQUARE OFF: {ist.strftime('%H:%M:%S IST')} | Reason: {reason}")
        logger.info(f"   PnL: ${pnl_usd:.4f} USD | ₹{pnl_inr:.2f} INR (with {self.slippage_pct}% slippage)")
        logger.info(f"   Lock & Trail Floor: ₹{self.lock_trail.locked_inr or 0:.0f}")
        logger.info("=" * 60)

        # Clear positions
        self.bot.state[self.mode]['positions'] = {'call': None, 'put': None}
        self.bot.state[self.mode]['reentry_watch'] = {'call': None, 'put': None}
        self.bot.state[self.mode]['running'] = False

        # Determine leg exit status (AlgoTest style: SL 100% vs OTM Expired)
        ce_status = "SL 100%" if self.call_sl_hits > 0 else "OTM Expired"
        pe_status = "SL 100%" if self.put_sl_hits > 0 else "OTM Expired"

        # Build complete trade record
        trade_record = {
            'trade_date':     self.trade_date,
            'entry_time':     self.entry_time,
            'exit_time':      ist.isoformat(),
            'exit_reason':    reason,
            'ce_exit_status': ce_status,
            'pe_exit_status': pe_status,
            'slippage_pct':   self.slippage_pct,
            'btc_spot_entry': round(self.entry_btc, 2),
            'btc_spot_exit':  round(self.bot.current_btc_price, 2),
            'call_symbol':    self.call_sym,
            'put_symbol':     self.put_sym,
            'call_raw_entry': round(getattr(self, 'call_raw_entry', self.call_entry), 2),
            'put_raw_entry':  round(getattr(self, 'put_raw_entry', self.put_entry), 2),
            'call_entry':     round(self.call_entry, 2),
            'put_entry':      round(self.put_entry, 2),
            'call_exit':      round(call_exit_px, 2),
            'put_exit':       round(put_exit_px, 2),
            'call_sl_level':  self.call_sl,
            'put_sl_level':   self.put_sl,
            'call_sl_hits':   self.call_sl_hits,
            'put_sl_hits':    self.put_sl_hits,
            'lots_per_leg':   self.lots,
            'pnl_usd':        pnl_usd,
            'pnl_inr':        pnl_inr,
            'peak_pnl_inr':   round(self.lock_trail.peak_inr, 2),
            'lock_activated': self.lock_trail.lock_active,
            'lock_floor_inr': round(self.lock_trail.locked_inr or 0, 2),
            'pnl_snapshots':  self.pnl_snapshots[-30:],  # Last 30 snapshot points
            'strategy':       'Balance BTC midnight - lock profit',
            'multipliers':    f'CE +{self.call_mult}x | PE -{self.put_mult}x',
            'lock_trail_cfg': {
                'trigger_inr': self.lock_trail.trigger_inr,
                'lock_inr':    self.lock_trail.lock_inr,
                'step_inr':    self.lock_trail.step_inr,
                'trail_inr':   self.lock_trail.trail_inr,
            }
        }

        self.recorder.save_trade(trade_record)

        self.trade_active = False
        self.lock_trail.reset()

        return pnl_inr

    def _monitor_loop(self):
        """
        Core monitoring thread: runs every 5 seconds while trade is active.
        Checks PnL, updates Lock & Trail, watches for SL hits and squaroff time.
        """
        logger.info("🎯 Monitor loop started.")
        snapshot_interval = 60  # Save a PnL snapshot every 60s
        last_snapshot_ts  = 0

        while self.running:
            try:
                ist = self._ist_now()

                if self.trade_active:
                    # 1. Refresh option prices
                    pos = self.bot.state[self.mode]['positions']
                    for leg in ['call', 'put']:
                        if pos.get(leg) and pos[leg].get('symbol'):
                            sym = pos[leg]['symbol']
                            try:
                                r = self.bot.india_client.get(f'/v2/tickers/{sym}')
                                if r.get('success') and r.get('result'):
                                    mp = float(r['result'].get('mark_price') or r['result'].get('close') or 0)
                                    if mp > 0:
                                        pos[leg]['current_price'] = round(mp, 2)
                            except Exception:
                                pass

                    # 2. Calculate PnL
                    pnl_inr = self._get_pnl_inr()
                    pnl_usd = self._get_pnl_usd()
                    btc     = self.bot.current_btc_price

                    # 3. Check Leg Stop Losses
                    for leg in ['call', 'put']:
                        if pos.get(leg):
                            p   = pos[leg]
                            cur = p.get('current_price', p['entry_price'])
                            sl  = p['sl']
                            if cur >= sl:
                                logger.warning(f"🔴 LEG SL HIT: {leg.upper()} {p['symbol']} @ ${cur:.2f} (SL: ${sl:.2f})")
                                # Dynamic exit buyback slippage
                                cur_with_slip = round(cur * (1.0 + self.slippage_pct / 100.0), 2)
                                leg_loss = (p['entry_price'] - cur_with_slip) * p['size'] * LOT_TO_BTC
                                self.realized_pnl_usd += leg_loss
                                if leg == 'call':
                                    self.call_sl_hits += 1
                                    self.call_exit = cur_with_slip
                                else:
                                    self.put_sl_hits += 1
                                    self.put_exit  = cur_with_slip
                                # Trigger RE MOMENTUM watch
                                sl_copy = dict(p)
                                pos[leg] = None
                                reentry_ok = self.reentry_enabled and (p.get('reentry_count', 0) < self.reentry_max)
                                if reentry_ok:
                                    logger.info(f"🔄 Initiating RE MOMENTUM watch for {leg.upper()}...")
                                    self.bot.initiate_reentry_watch(self.mode, leg, 1, sl_copy)
                                # Recalculate PnL after close
                                pnl_inr = self._get_pnl_inr()
                                pnl_usd = self._get_pnl_usd()

                    # Check re-entry watches
                    self.bot._check_reentry_watch(self.mode)

                    # 4. Lock & Trail check (INR)
                    lt_result = self.lock_trail.update(pnl_inr)
                    if lt_result['exit_now']:
                        self._squareoff(reason=lt_result['exit_reason'])
                        continue

                    # 5. PnL snapshot
                    now_ts = time.time()
                    if now_ts - last_snapshot_ts >= snapshot_interval:
                        self.pnl_snapshots.append({
                            'time':         ist.strftime('%H:%M'),
                            'pnl_inr':      pnl_inr,
                            'pnl_usd':      pnl_usd,
                            'btc':          round(btc, 0),
                            'locked_floor': lt_result.get('locked_floor'),
                        })
                        last_snapshot_ts = now_ts
                        logger.info(f"📊 PnL: ₹{pnl_inr:.0f} | Floor: ₹{lt_result.get('locked_floor') or '—'} | BTC: ${btc:.0f}")

                    # 6. Hard squareoff time check
                    if ist.hour == self.squareoff_hour and ist.minute >= self.squareoff_min:
                        any_active = any(pos.get(leg) for leg in ['call', 'put'])
                        if any_active or self.trade_active:
                            self._squareoff(reason=f"{self.squareoff_hour:02d}:{self.squareoff_min:02d}_HARD_SQUAREOFF")

                else:
                    # Not in trade — check if it's time to enter
                    is_weekday = self._is_weekday(ist)
                    is_entry_time = (ist.hour == self.entry_hour and ist.minute >= self.entry_min and ist.minute < self.entry_min + 5)

                    if is_weekday and is_entry_time:
                        # Avoid duplicate entry in the same minute
                        entry_key = ist.strftime('%Y-%m-%d-%H%M')
                        if entry_key != getattr(self, '_last_entry_key', ''):
                            logger.info(f"⏰ Entry time reached: {ist.strftime('%H:%M IST')} | Today is {ist.strftime('%A')}")
                            ok = self._enter_trade()
                            if ok:
                                self._last_entry_key = entry_key
                    elif not is_weekday:
                        if not getattr(self, '_weekend_logged', False):
                            logger.info(f"🗓️ Today is {ist.strftime('%A')} - Weekend. No trade.")
                            self._weekend_logged = True
                    else:
                        self._weekend_logged = False

            except Exception as e:
                logger.error(f"[MONITOR ERROR] {e}", exc_info=True)

            time.sleep(5)

        logger.info("🛑 Monitor loop stopped.")

    def start(self):
        if self.running:
            logger.info("ForwardTrader already running.")
            return
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name='FT-Monitor')
        self._thread.start()
        logger.info(f"✅ ForwardTrader started. Will trade Mon-Fri at {self.entry_hour:02d}:{self.entry_min:02d} IST.")
        logger.info(f"📌 Lock & Trail Rule: Trigger ₹{self.lock_trail.trigger_inr:.0f} → Lock ₹{self.lock_trail.lock_inr:.0f} | Per ₹{self.lock_trail.step_inr:.0f} more → Trail ₹{self.lock_trail.trail_inr:.0f}")

    def stop(self):
        self.running = False
        logger.info("🛑 ForwardTrader stopping...")

    def force_enter_now(self):
        """Force enter a trade immediately for testing purposes."""
        if self.trade_active:
            logger.warning("🔒 STRIKES LOCKED: Trade already active! Strikes cannot be changed while trade is running. Use 'Manual Off' first.")
            return False
        logger.info("🔧 FORCE ENTRY triggered for immediate testing...")
        self.bot.state[self.mode]['running'] = True
        ok = self._enter_trade()
        if ok:
            logger.info("✅ Force entry successful! Monitoring active.")
        else:
            logger.error("❌ Force entry failed.")
        return ok

    def status(self) -> dict:
        if not self.trade_active:
            self.reload_config()
        ist = self._ist_now()
        pnl_inr = self._get_pnl_inr() if self.trade_active else 0.0
        pnl_usd = self._get_pnl_usd() if self.trade_active else 0.0
        pos = self.bot.state[self.mode]['positions']
        return {
            'running':          self.running,
            'trade_active':     self.trade_active,
            'trade_date':       self.trade_date,
            'ist_time':         ist.strftime('%Y-%m-%d %H:%M:%S IST'),
            'today_weekday':    ist.strftime('%A'),
            'will_trade_today': self._is_weekday(ist),
            'slippage_pct':     self.slippage_pct,
            'pnl_usd':          pnl_usd,
            'pnl_inr':          pnl_inr,
            'lock_active':      self.lock_trail.lock_active,
            'lock_floor_inr':   self.lock_trail.locked_inr,
            'peak_pnl_inr':     self.lock_trail.peak_inr,
            'call_symbol':      self.call_sym,
            'put_symbol':       self.put_sym,
            'call_raw_entry':   getattr(self, 'call_raw_entry', self.call_entry),
            'put_raw_entry':    getattr(self, 'put_raw_entry', self.put_entry),
            'call_sl_hits':     self.call_sl_hits,
            'put_sl_hits':      self.put_sl_hits,
            'call_pos':         pos.get('call'),
            'put_pos':          pos.get('put'),
            'next_entry':       f"Today at {self.entry_hour:02d}:{self.entry_min:02d} IST" if self._is_weekday(ist) else f"Monday at {self.entry_hour:02d}:{self.entry_min:02d} IST",
            'records_file':     LOG_FILE,
            'total_trades_logged': len(self.recorder.get_all_trades()),
            'summary':          self.recorder.get_summary(),
            'rules': {
                'call_mult':            self.call_mult,
                'put_mult':             self.put_mult,
                'leg_sl_pct':           self.leg_sl_pct,
                'lots':                 self.lots,
                'reentry_enabled':      self.reentry_enabled,
                'reentry_max':          self.reentry_max,
                'slippage_pct':         self.slippage_pct,
                'entry_time':           f"{self.entry_hour:02d}:{self.entry_min:02d}",
                'squareoff_time':       f"{self.squareoff_hour:02d}:{self.squareoff_min:02d}",
                'lock_trigger_inr':     self.lock_trail.trigger_inr,
                'lock_amount_inr':      self.lock_trail.lock_inr,
                'trail_step_inr':       self.lock_trail.step_inr,
                'trail_by_inr':         self.lock_trail.trail_inr,
            }
        }


# ─── Singleton instance ──────────────────────────────────────────────────────
forward_trader = ForwardTrader()
