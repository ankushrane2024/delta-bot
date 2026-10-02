import os
import json
import time
import math
import threading
from datetime import datetime, timedelta, timezone
from api_client import DeltaIndiaClient
from logger import app_logger, error_logger
from utils import get_ist_now
from config import LOT_TO_BTC

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "btst_config.json")
POSITIONS_FILE = os.path.join(BASE_DIR, "btst_positions.json")
TRADES_FILE = os.path.join(BASE_DIR, "btst_trade_history.json")

DEFAULT_CONFIG = {
    "capital_inr": 1000000,
    "lots": 500,
    "sl_pct": 100.0,
    "straddle_multiplier": 1.8,
    "entry_time_ist": "22:30",
    "exit_time_ist": "17:28",
    "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "is_active": True,
    "mode": "PAPER",      # "PAPER" for forward-testing, "LIVE" for real execution
    "usd_to_inr": 85.0
}

class BTSTStrangleEngine:
    """
    Independent BTST 44-Hour Bitcoin Short Strangle Forward-Test & Live Strategy Engine.
    
    Strategy Rules (Replicated from AlgoTest Strangle BTC Backtest):
    - Entry Time: 10:30 PM IST (22:30 IST).
    - Expiry Selection: Next day expiry target (D+2, ~43-44 hours holding time).
    - ATM Straddle Width:
        1. Find ATM Strike closest to current BTC spot price.
        2. ATM Straddle Price = ATM CE Premium + ATM PE Premium.
        3. Offset = round(Straddle Multiplier x ATM Straddle Price) [Default 1.8x].
        4. Target Call Strike = ATM + Offset (nearest available in chain).
        5. Target Put Strike = ATM - Offset (nearest available in chain).
    - Stop Loss:
        Individual leg stop loss at SL% (Default 100% = 2x entry price).
        PARTIAL STOP LOSS: If Leg 1 hits SL, Leg 1 exits, Leg 2 CONTINUES RUNNING until expiry.
    - Exit Time:
        05:28 PM IST (17:28 IST) on the expiry date (approx 43-44h total duration).
    """

    def __init__(self, api_client=None):
        self.api_client = api_client or DeltaIndiaClient()
        self.lock = threading.Lock()
        self.config = self._load_config()
        self.active_trade = self._load_positions()
        self.trade_history = self._load_trade_history()
        self.last_evaluated_entry_date = None
        self.last_entry_trigger_key = None
        self.is_running = False
        self.worker_thread = None

    # ── CONFIG & PERSISTENCE ──────────────────────────────────────────────────
    def _load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    merged = {**DEFAULT_CONFIG, **cfg}
                    return merged
        except Exception as e:
            app_logger.error(f"[BTST] Error loading config: {e}")
        return dict(DEFAULT_CONFIG)

    def save_config(self, new_cfg):
        with self.lock:
            try:
                time_changed = False
                exit_time_changed = False
                for k, v in new_cfg.items():
                    if k in self.config:
                        # Type-cast safely
                        if k in ["capital_inr", "lots"]:
                            self.config[k] = int(v)
                        elif k in ["sl_pct", "straddle_multiplier", "usd_to_inr"]:
                            self.config[k] = float(v)
                        elif k == "is_active":
                            self.config[k] = bool(v)
                        elif k == "entry_time_ist":
                            val_str = str(v).strip()
                            if val_str != self.config.get("entry_time_ist"):
                                time_changed = True
                            self.config[k] = val_str
                        elif k == "exit_time_ist":
                            val_str = str(v).strip()
                            if val_str != self.config.get("exit_time_ist"):
                                exit_time_changed = True
                            self.config[k] = val_str
                        elif k == "mode":
                            self.config[k] = str(v).strip()
                        elif k == "weekdays" and isinstance(v, list):
                            self.config[k] = v

                # If entry time changed, re-arm scheduler immediately
                if time_changed:
                    self.last_entry_trigger_key = None
                    self.last_evaluated_entry_date = None
                    app_logger.info(f"[BTST] Entry time updated to {self.config.get('entry_time_ist')}. Scheduler immediately re-armed.")

                # If exit time changed and trade is open, update active trade target exit time
                if exit_time_changed and self.active_trade and self.active_trade.get("target_expiry_date"):
                    exp_date = self.active_trade["target_expiry_date"]
                    self.active_trade["target_exit_time"] = f"{exp_date} {self.config.get('exit_time_ist')}:00"
                    self._save_positions()
                    app_logger.info(f"[BTST] Active trade target exit time updated to {self.active_trade['target_exit_time']}.")

                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4)
                app_logger.info(f"[BTST] Configuration successfully saved: {self.config}")
                return True, "Configuration updated successfully."
            except Exception as e:
                app_logger.error(f"[BTST] Failed to save config: {e}")
                return False, str(e)

    def _load_positions(self):
        try:
            if os.path.exists(POSITIONS_FILE):
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data and isinstance(data, dict) and data.get("status") in ["OPEN", "PARTIALLY_CLOSED"]:
                        return data
        except Exception as e:
            app_logger.error(f"[BTST] Error loading positions: {e}")
        return None

    def _save_positions(self):
        try:
            with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.active_trade, f, indent=4)
        except Exception as e:
            app_logger.error(f"[BTST] Error saving positions: {e}")

    def _load_trade_history(self):
        try:
            if os.path.exists(TRADES_FILE):
                with open(TRADES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            app_logger.error(f"[BTST] Error loading trade history: {e}")
        return []

    def _save_trade_history(self):
        try:
            with open(TRADES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.trade_history, f, indent=4)
        except Exception as e:
            app_logger.error(f"[BTST] Error saving trade history: {e}")

    # ── MARKET DATA & STRIKE CALCULATION ──────────────────────────────────────
    def get_btc_spot_price(self):
        try:
            res = self.api_client.get_tickers({'symbol': 'BTCUSD'})
            if res.get('success') and res.get('result'):
                for item in res['result']:
                    if item.get('symbol') == 'BTCUSD':
                        price = float(item.get('mark_price') or item.get('close') or item.get('last_price') or 0)
                        if price > 0:
                            return price
        except Exception as e:
            app_logger.warning(f"[BTST] Error fetching BTCUSD spot from Delta: {e}")

        # Fallback to general tickers
        try:
            res = self.api_client.get_tickers({'contract_types': 'call_options', 'underlying_asset_symbol': 'BTC'})
            for t in res.get('result', []):
                spot = float(t.get('spot_price') or t.get('greeks', {}).get('spot') or 0)
                if spot > 0:
                    return spot
        except Exception:
            pass
        return 0.0

    def find_target_expiry_and_tickers(self, entry_dt=None):
        """
        Finds the D+2 expiry (or nearest expiry between 36h and 60h from entry).
        Returns: (target_exp_str, target_expiry_date_str, expiry_tickers, all_tickers)
        """
        if not entry_dt:
            entry_dt = get_ist_now()

        res = self.api_client.get_tickers({
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        })
        if not res or not res.get('success'):
            app_logger.error("[BTST] Failed to fetch tickers from Delta Exchange.")
            return None, None, [], []

        tickers = [t for t in res.get('result', []) if '-BTC-' in t.get('symbol', '')]
        if not tickers:
            return None, None, [], []

        # Target date is D+2 from entry_dt
        d2_target = entry_dt + timedelta(days=2)
        d2_str = d2_target.strftime('%d%m%y')
        
        # Check if D+2 is present
        exp_tickers = [t for t in tickers if t.get('symbol', '').endswith(d2_str)]
        if exp_tickers:
            return d2_str, d2_target.strftime('%Y-%m-%d'), exp_tickers, tickers

        # If D+2 not strictly found, find available expiries and pick the closest between 36h and 60h
        all_expiries = set()
        for t in tickers:
            sym = t.get('symbol', '')
            parts = sym.split('-')
            if len(parts) >= 4 and len(parts[-1]) == 6 and parts[-1].isdigit():
                all_expiries.add(parts[-1])

        parsed_expiries = []
        for exp_s in all_expiries:
            try:
                # Delta options expire at 12:00 UTC = 17:30 IST
                exp_dt = datetime.strptime(exp_s, '%d%m%y').replace(hour=17, minute=30, tzinfo=entry_dt.tzinfo)
                hours_diff = (exp_dt - entry_dt).total_seconds() / 3600.0
                parsed_expiries.append((exp_dt, exp_s, hours_diff))
            except Exception:
                pass

        # Sort by distance from 43 hours
        parsed_expiries.sort(key=lambda x: abs(x[2] - 43.0))
        for exp_dt, exp_s, hours_diff in parsed_expiries:
            if hours_diff > 20: # At least next day
                exp_tickers = [t for t in tickers if t.get('symbol', '').endswith(exp_s)]
                return exp_s, exp_dt.strftime('%Y-%m-%d'), exp_tickers, tickers

        return None, None, [], tickers

    def calculate_strangle_strikes(self, entry_dt=None):
        """
        Calculates ATM Strike, Straddle Price, 1.8x Straddle Width Offset,
        and selects nearest available OTM Call and Put strikes.
        """
        if not entry_dt:
            entry_dt = get_ist_now()

        spot_price = self.get_btc_spot_price()
        if spot_price <= 0:
            return False, "Could not resolve live BTC spot price.", None

        exp_str, exp_date_str, exp_tickers, all_tickers = self.find_target_expiry_and_tickers(entry_dt)
        if not exp_str or not exp_tickers:
            return False, "No valid options found for target D+2 expiry.", None

        strikes = sorted(list(set(float(t['strike_price']) for t in exp_tickers if t.get('strike_price'))))
        if len(strikes) < 5:
            return False, f"Insufficient strikes ({len(strikes)}) in target expiry {exp_str}.", None

        # ATM Strike
        atm_strike = min(strikes, key=lambda s: abs(s - spot_price))
        atm_ce_sym = f"C-BTC-{int(atm_strike)}-{exp_str}"
        atm_pe_sym = f"P-BTC-{int(atm_strike)}-{exp_str}"

        atm_ce = next((t for t in exp_tickers if t.get('symbol') == atm_ce_sym), None)
        atm_pe = next((t for t in exp_tickers if t.get('symbol') == atm_pe_sym), None)

        ce_premium = float(atm_ce.get('mark_price') or atm_ce.get('close') or atm_ce.get('last_price') or 0) if atm_ce else 0.0
        pe_premium = float(atm_pe.get('mark_price') or atm_pe.get('close') or atm_pe.get('last_price') or 0) if atm_pe else 0.0

        # Targeted fallback query if bulk ticker mark_price is empty
        if ce_premium <= 0:
            try:
                t_ce = self.api_client.get_realtime_ticker(atm_ce_sym)
                if t_ce:
                    ce_premium = float(t_ce.get('mark_price') or t_ce.get('close') or t_ce.get('last_price') or 0)
            except Exception:
                pass

        if pe_premium <= 0:
            try:
                t_pe = self.api_client.get_realtime_ticker(atm_pe_sym)
                if t_pe:
                    pe_premium = float(t_pe.get('mark_price') or t_pe.get('close') or t_pe.get('last_price') or 0)
            except Exception:
                pass

        if ce_premium <= 0 or pe_premium <= 0:
            return False, f"Could not fetch ATM premiums (CE: {ce_premium}, PE: {pe_premium}) for strike {atm_strike}.", None

        straddle_price = ce_premium + pe_premium
        multiplier = float(self.config.get("straddle_multiplier", 1.8))
        offset = round(multiplier * straddle_price)

        target_call_strike = atm_strike + offset
        target_put_strike = atm_strike - offset

        # Select nearest available strikes in option chain
        selected_ce_strike = min(strikes, key=lambda s: abs(s - target_call_strike))
        selected_pe_strike = min(strikes, key=lambda s: abs(s - target_put_strike))

        call_sym = f"C-BTC-{int(selected_ce_strike)}-{exp_str}"
        put_sym = f"P-BTC-{int(selected_pe_strike)}-{exp_str}"

        call_ticker = next((t for t in exp_tickers if t.get('symbol') == call_sym), None)
        put_ticker = next((t for t in exp_tickers if t.get('symbol') == put_sym), None)

        if not call_ticker or not put_ticker:
            return False, f"Selected strikes {call_sym} or {put_sym} not active in Delta ticker data.", None

        call_entry_price = float(call_ticker.get('mark_price') or call_ticker.get('close') or call_ticker.get('last_price') or 0)
        put_entry_price = float(put_ticker.get('mark_price') or put_ticker.get('close') or put_ticker.get('last_price') or 0)

        # Targeted fallback query if bulk selected mark_price is empty
        if call_entry_price <= 0:
            try:
                t_c = self.api_client.get_realtime_ticker(call_sym)
                if t_c:
                    call_entry_price = float(t_c.get('mark_price') or t_c.get('close') or t_c.get('last_price') or 0)
            except Exception:
                pass

        if put_entry_price <= 0:
            try:
                t_p = self.api_client.get_realtime_ticker(put_sym)
                if t_p:
                    put_entry_price = float(t_p.get('mark_price') or t_p.get('close') or t_p.get('last_price') or 0)
            except Exception:
                pass

        if call_entry_price <= 0 or put_entry_price <= 0:
            return False, f"Selected strikes {call_sym} (${call_entry_price}) or {put_sym} (${put_entry_price}) have no active quotes.", None

        sl_multiplier = 1.0 + (float(self.config.get("sl_pct", 100.0)) / 100.0)
        call_sl_price = round(call_entry_price * sl_multiplier, 4)
        put_sl_price = round(put_entry_price * sl_multiplier, 4)

        result = {
            "entry_dt": entry_dt,
            "spot_price": spot_price,
            "expiry_str": exp_str,
            "expiry_date_str": exp_date_str,
            "target_exit_time_str": f"{exp_date_str} {self.config.get('exit_time_ist', '17:28')}:00",
            "atm_strike": atm_strike,
            "atm_ce_premium": ce_premium,
            "atm_pe_premium": pe_premium,
            "straddle_price": straddle_price,
            "multiplier": multiplier,
            "offset": offset,
            "target_call_strike": target_call_strike,
            "target_put_strike": target_put_strike,
            "selected_ce_strike": selected_ce_strike,
            "selected_pe_strike": selected_pe_strike,
            "call_symbol": call_sym,
            "put_symbol": put_sym,
            "call_product_id": call_ticker.get('product_id'),
            "put_product_id": put_ticker.get('product_id'),
            "call_entry_price": call_entry_price,
            "put_entry_price": put_entry_price,
            "call_sl_price": call_sl_price,
            "put_sl_price": put_sl_price,
        }
        return True, "Strike calculation successful.", result

    # ── TRADE ENTRY TRIGGER ───────────────────────────────────────────────────
    def trigger_entry(self, force=False):
        """
        Executes trade entry for the BTST Strangle strategy.
        Supports both PAPER (forward test) and LIVE modes.
        """
        with self.lock:
            if self.active_trade and self.active_trade.get("status") in ["OPEN", "PARTIALLY_CLOSED"]:
                return False, "A BTST position is already currently open. Cannot open multiple simultaneous trades."

            now_ist = get_ist_now()
            weekday_str = now_ist.strftime('%a')
            if not force and weekday_str not in self.config.get("weekdays", []):
                return False, f"Today ({weekday_str}) is not in active trading weekdays: {self.config.get('weekdays')}"

            success, msg, math_res = self.calculate_strangle_strikes(now_ist)
            if not success or not math_res:
                return False, f"Strike selection failed: {msg}"

            trade_id = f"BTST-{now_ist.strftime('%Y%m%d-%H%M%S')}"
            lots = int(self.config.get("lots", 500))
            qty_btc = round(lots * LOT_TO_BTC, 4)
            mode = self.config.get("mode", "PAPER")

            app_logger.info(
                f"[BTST] Opening {mode} Strangle Trade {trade_id} | ATM={math_res['atm_strike']} | "
                f"Offset={math_res['offset']} ({math_res['multiplier']}x) | "
                f"CE={math_res['call_symbol']} @ ${math_res['call_entry_price']} (SL ${math_res['call_sl_price']}) | "
                f"PE={math_res['put_symbol']} @ ${math_res['put_entry_price']} (SL ${math_res['put_sl_price']})"
            )

            # Live execution order dispatch (if mode is LIVE)
            call_live_order_id = None
            put_live_order_id = None
            if mode == "LIVE":
                try:
                    c_res = self.api_client.place_order(
                        product_id=math_res['call_product_id'],
                        side='sell',
                        size=lots,
                        order_type='market_order'
                    )
                    if not c_res.get('success'):
                        return False, f"Live CE leg order failed: {c_res.get('error')}"
                    call_live_order_id = c_res.get('result', {}).get('id')

                    p_res = self.api_client.place_order(
                        product_id=math_res['put_product_id'],
                        side='sell',
                        size=lots,
                        order_type='market_order'
                    )
                    if not p_res.get('success'):
                        # Safe rollback if PE fails
                        self.api_client.place_order(product_id=math_res['call_product_id'], side='buy', size=lots, order_type='market_order', reduce_only=True)
                        return False, f"Live PE leg order failed: {p_res.get('error')}"
                    put_live_order_id = p_res.get('result', {}).get('id')
                except Exception as e:
                    return False, f"Error placing live orders: {e}"

            # Create position object
            self.active_trade = {
                "trade_id": trade_id,
                "entry_time": now_ist.strftime('%Y-%m-%d %H:%M:%S'),
                "entry_date": now_ist.strftime('%Y-%m-%d'),
                "target_expiry_date": math_res['expiry_date_str'],
                "target_expiry_str": math_res['expiry_str'],
                "target_exit_time": math_res['target_exit_time_str'],
                "btc_spot_at_entry": math_res['spot_price'],
                "atm_strike": math_res['atm_strike'],
                "atm_ce_premium": math_res['atm_ce_premium'],
                "atm_pe_premium": math_res['atm_pe_premium'],
                "straddle_price": math_res['straddle_price'],
                "straddle_multiplier": math_res['multiplier'],
                "offset_points": math_res['offset'],
                "status": "OPEN",
                "mode": mode,
                "lots": lots,
                "qty_btc": qty_btc,
                "sl_pct": self.config.get("sl_pct", 100.0),
                "ce_leg": {
                    "symbol": math_res['call_symbol'],
                    "product_id": math_res['call_product_id'],
                    "strike": math_res['selected_ce_strike'],
                    "side": "sell",
                    "lots": lots,
                    "entry_price": math_res['call_entry_price'],
                    "sl_price": math_res['call_sl_price'],
                    "current_price": math_res['call_entry_price'],
                    "status": "OPEN",
                    "order_id": call_live_order_id,
                    "exit_price": None,
                    "exit_time": None,
                    "exit_reason": None,
                    "pnl_usd": 0.0,
                    "pnl_inr": 0.0
                },
                "pe_leg": {
                    "symbol": math_res['put_symbol'],
                    "product_id": math_res['put_product_id'],
                    "strike": math_res['selected_pe_strike'],
                    "side": "sell",
                    "lots": lots,
                    "entry_price": math_res['put_entry_price'],
                    "sl_price": math_res['put_sl_price'],
                    "current_price": math_res['put_entry_price'],
                    "status": "OPEN",
                    "order_id": put_live_order_id,
                    "exit_price": None,
                    "exit_time": None,
                    "exit_reason": None,
                    "pnl_usd": 0.0,
                    "pnl_inr": 0.0
                },
                "total_pnl_usd": 0.0,
                "total_pnl_inr": 0.0,
                "last_update_time": now_ist.strftime('%Y-%m-%d %H:%M:%S')
            }
            self._save_positions()
            return True, f"BTST Strangle trade {trade_id} successfully entered."

    # ── LIVE MONITORING & PARTIAL SL EVALUATION ───────────────────────────────
    def evaluate_open_positions(self, custom_quotes=None):
        """
        Periodically called by worker thread:
        1. Updates current prices and PnL for open legs.
        2. Evaluates individual Leg Stop Loss (PARTIAL SL).
        3. Evaluates 17:28 IST Expiry Exit time.
        """
        with self.lock:
            if not self.active_trade or self.active_trade.get("status") not in ["OPEN", "PARTIALLY_CLOSED"]:
                return

            trade = self.active_trade
            now_ist = get_ist_now()
            rate = float(self.config.get("usd_to_inr", 85.0))
            lots = int(trade.get("lots", 500))
            qty_btc = float(trade.get("qty_btc", lots * LOT_TO_BTC))

            # Fetch fresh quotes for both legs
            call_sym = trade['ce_leg']['symbol']
            put_sym = trade['pe_leg']['symbol']

            ce_ticker = None
            pe_ticker = None

            if custom_quotes:
                if call_sym in custom_quotes:
                    ce_ticker = {'mark_price': custom_quotes[call_sym]}
                if put_sym in custom_quotes:
                    pe_ticker = {'mark_price': custom_quotes[put_sym]}
            else:
                ce_ticker = self.api_client.get_realtime_ticker(call_sym)
                pe_ticker = self.api_client.get_realtime_ticker(put_sym)

                # REST fallback if WS cache empty
                if not ce_ticker or not pe_ticker:
                    try:
                        res_quotes = self.api_client.get_tickers({'contract_types': 'call_options,put_options', 'underlying_asset_symbol': 'BTC'})
                        for t in res_quotes.get('result', []):
                            if t.get('symbol') == call_sym and not ce_ticker:
                                ce_ticker = t
                            elif t.get('symbol') == put_sym and not pe_ticker:
                                pe_ticker = t
                    except Exception as e:
                        app_logger.warning(f"[BTST] Error refreshing ticker quotes: {e}")

            # Update Call Leg
            ce = trade['ce_leg']
            if ce['status'] == 'OPEN' and ce_ticker:
                curr_ce = float(ce_ticker.get('mark_price') or ce_ticker.get('close') or ce.get('current_price') or 0)
                if curr_ce > 0:
                    ce['current_price'] = curr_ce
                    ce_pnl_usd = (ce['entry_price'] - curr_ce) * qty_btc
                    ce['pnl_usd'] = round(ce_pnl_usd, 2)
                    ce['pnl_inr'] = round(ce_pnl_usd * rate, 2)

            # Update Put Leg
            pe = trade['pe_leg']
            if pe['status'] == 'OPEN' and pe_ticker:
                curr_pe = float(pe_ticker.get('mark_price') or pe_ticker.get('close') or pe.get('current_price') or 0)
                if curr_pe > 0:
                    pe['current_price'] = curr_pe
                    pe_pnl_usd = (pe['entry_price'] - curr_pe) * qty_btc
                    pe['pnl_usd'] = round(pe_pnl_usd, 2)
                    pe['pnl_inr'] = round(pe_pnl_usd * rate, 2)

            trade['total_pnl_usd'] = round(ce['pnl_usd'] + pe['pnl_usd'], 2)
            trade['total_pnl_inr'] = round(ce['pnl_inr'] + pe['pnl_inr'], 2)
            trade['last_update_time'] = now_ist.strftime('%Y-%m-%d %H:%M:%S')

            # ── PARTIAL STOP LOSS EVALUATION ──────────────────────────────────
            # If Call hits SL -> square off Call. Put continues running!
            if ce['status'] == 'OPEN' and ce['current_price'] >= ce['sl_price']:
                app_logger.warning(f"[BTST] Call Leg SL HIT! Current: ${ce['current_price']} >= SL: ${ce['sl_price']}. Squaring off Call leg...")
                self._square_off_leg('ce_leg', exit_reason='SL_HIT')

            # If Put hits SL -> square off Put. Call continues running!
            if pe['status'] == 'OPEN' and pe['current_price'] >= pe['sl_price']:
                app_logger.warning(f"[BTST] Put Leg SL HIT! Current: ${pe['current_price']} >= SL: ${pe['sl_price']}. Squaring off Put leg...")
                self._square_off_leg('pe_leg', exit_reason='SL_HIT')

            # ── EXPIRY EXIT TIME CHECK (exit_time_ist on Expiry Date) ─────────────
            try:
                exit_cfg = str(self.config.get("exit_time_ist", "17:28")).strip()
                exit_parts = exit_cfg.split(':')
                exit_h = int(exit_parts[0])
                exit_m = int(exit_parts[1]) if len(exit_parts) > 1 else 0

                exp_date_str = trade.get('target_expiry_date')
                if exp_date_str:
                    target_exit_dt = datetime.strptime(exp_date_str, '%Y-%m-%d').replace(
                        hour=exit_h, minute=exit_m, second=0, microsecond=0, tzinfo=now_ist.tzinfo
                    )
                elif trade.get('target_exit_time'):
                    target_exit_dt = datetime.strptime(trade['target_exit_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=now_ist.tzinfo)
                else:
                    target_exit_dt = None

                if target_exit_dt and now_ist >= target_exit_dt:
                    app_logger.info(f"[BTST] Expiry exit time ({target_exit_dt.strftime('%Y-%m-%d %H:%M:%S')} IST) reached! Closing all remaining open legs...")
                    if ce['status'] == 'OPEN':
                        self._square_off_leg('ce_leg', exit_reason='EXPIRED_EXIT')
                    if pe['status'] == 'OPEN':
                        self._square_off_leg('pe_leg', exit_reason='EXPIRED_EXIT')
            except Exception as e:
                app_logger.warning(f"[BTST] Error evaluating expiry exit timestamp: {e}")

            # Check overall status
            if ce['status'] != 'OPEN' and pe['status'] != 'OPEN':
                trade['status'] = 'CLOSED'
                app_logger.info(f"[BTST] Trade {trade['trade_id']} fully finalized! Total PnL: ${trade['total_pnl_usd']} (INR {trade['total_pnl_inr']})")
                self._archive_trade_to_history(trade)
                self.active_trade = None
            elif ce['status'] != 'OPEN' or pe['status'] != 'OPEN':
                trade['status'] = 'PARTIALLY_CLOSED'

            self._save_positions()

    def _square_off_leg(self, leg_key, exit_reason='MANUAL_EXIT'):
        """Squares off an individual leg while allowing the other leg to keep running."""
        leg = self.active_trade[leg_key]
        if leg['status'] != 'OPEN':
            return

        now_ist = get_ist_now()
        rate = float(self.config.get("usd_to_inr", 85.0))
        qty_btc = float(self.active_trade.get("qty_btc", 0.5))

        # Real order square off in LIVE mode
        if self.active_trade.get("mode") == "LIVE":
            try:
                self.api_client.place_order(
                    product_id=leg['product_id'],
                    side='buy',
                    size=leg['lots'],
                    order_type='market_order',
                    reduce_only=True
                )
            except Exception as e:
                app_logger.error(f"[BTST] Error placing live buy order for {leg['symbol']}: {e}")

        # In AlgoTest, expired OTM options exit at 0.10
        exit_price = leg['current_price']
        if exit_reason == 'EXPIRED_EXIT' and exit_price <= 1.0:
            exit_price = 0.10

        pnl_usd = (leg['entry_price'] - exit_price) * qty_btc
        pnl_inr = pnl_usd * rate

        leg['status'] = exit_reason
        leg['exit_price'] = round(exit_price, 2)
        leg['exit_time'] = now_ist.strftime('%Y-%m-%d %H:%M:%S')
        leg['exit_reason'] = exit_reason
        leg['pnl_usd'] = round(pnl_usd, 2)
        leg['pnl_inr'] = round(pnl_inr, 2)

    def square_off_all(self, reason='MANUAL_SQUARE_OFF'):
        """Manually squares off any currently open BTST trade immediately."""
        with self.lock:
            if not self.active_trade or self.active_trade.get("status") not in ["OPEN", "PARTIALLY_CLOSED"]:
                return False, "No active BTST position to square off."

            if self.active_trade['ce_leg']['status'] == 'OPEN':
                self._square_off_leg('ce_leg', exit_reason=reason)
            if self.active_trade['pe_leg']['status'] == 'OPEN':
                self._square_off_leg('pe_leg', exit_reason=reason)

            self.active_trade['total_pnl_usd'] = round(self.active_trade['ce_leg']['pnl_usd'] + self.active_trade['pe_leg']['pnl_usd'], 2)
            self.active_trade['total_pnl_inr'] = round(self.active_trade['ce_leg']['pnl_inr'] + self.active_trade['pe_leg']['pnl_inr'], 2)
            self.active_trade['status'] = 'CLOSED'

            self._archive_trade_to_history(self.active_trade)
            self.active_trade = None
            self._save_positions()
            return True, "All BTST positions have been squared off."

    def _archive_trade_to_history(self, trade):
        """Archives completed trade into the AlgoTest-formatted trade history ledger."""
        trade_id = trade['trade_id']
        ce = trade['ce_leg']
        pe = trade['pe_leg']

        # Determine next index number
        base_idx = len(self.trade_history) // 2 + 1

        ce_entry = {
            "index": f"{base_idx}.1",
            "trade_id": trade_id,
            "entry_date": trade['entry_date'],
            "entry_time": trade['entry_time'].split(' ')[1] if ' ' in trade['entry_time'] else trade['entry_time'],
            "exit_date": ce['exit_time'].split(' ')[0] if ce.get('exit_time') else trade['target_expiry_date'],
            "exit_time": ce['exit_time'].split(' ')[1] if ce.get('exit_time') else "17:28:00",
            "type": "CE",
            "strike": ce['strike'],
            "side": "Sell",
            "lots": ce['lots'],
            "qty_btc": trade['qty_btc'],
            "entry_price": ce['entry_price'],
            "exit_price": ce['exit_price'],
            "pnl_usd": ce['pnl_usd'],
            "pnl_inr": ce['pnl_inr'],
            "exit_reason": ce['exit_reason'],
            "mode": trade['mode']
        }

        pe_entry = {
            "index": f"{base_idx}.2",
            "trade_id": trade_id,
            "entry_date": trade['entry_date'],
            "entry_time": trade['entry_time'].split(' ')[1] if ' ' in trade['entry_time'] else trade['entry_time'],
            "exit_date": pe['exit_time'].split(' ')[0] if pe.get('exit_time') else trade['target_expiry_date'],
            "exit_time": pe['exit_time'].split(' ')[1] if pe.get('exit_time') else "17:28:00",
            "type": "PE",
            "strike": pe['strike'],
            "side": "Sell",
            "lots": pe['lots'],
            "qty_btc": trade['qty_btc'],
            "entry_price": pe['entry_price'],
            "exit_price": pe['exit_price'],
            "pnl_usd": pe['pnl_usd'],
            "pnl_inr": pe['pnl_inr'],
            "exit_reason": pe['exit_reason'],
            "mode": trade['mode']
        }

        self.trade_history.insert(0, pe_entry)
        self.trade_history.insert(0, ce_entry)
        self._save_trade_history()

    # ── METRICS & STATS ───────────────────────────────────────────────────────
    def get_summary_metrics(self):
        """Calculates backtest/forward-test performance metrics matching AlgoTest report."""
        if not self.trade_history:
            return {
                "overall_profit_inr": 0.0,
                "overall_profit_usd": 0.0,
                "total_trades": 0,
                "avg_profit_per_trade_inr": 0.0,
                "win_pct": 0.0,
                "loss_pct": 0.0,
                "avg_win_inr": 0.0,
                "avg_loss_inr": 0.0,
                "max_profit_inr": 0.0,
                "max_loss_inr": 0.0,
                "max_drawdown_inr": 0.0,
                "return_to_mdd": 0.0,
                "reward_to_risk": 0.0
            }

        total_pnl = sum(t.get('pnl_inr', 0) for t in self.trade_history)
        total_pnl_usd = sum(t.get('pnl_usd', 0) for t in self.trade_history)
        total_legs = len(self.trade_history)
        
        wins = [t.get('pnl_inr', 0) for t in self.trade_history if t.get('pnl_inr', 0) > 0]
        losses = [t.get('pnl_inr', 0) for t in self.trade_history if t.get('pnl_inr', 0) < 0]

        win_pct = round((len(wins) / total_legs * 100), 2) if total_legs > 0 else 0.0
        loss_pct = round((len(losses) / total_legs * 100), 2) if total_legs > 0 else 0.0
        avg_profit = round(total_pnl / (total_legs / 2.0), 2) if total_legs > 0 else 0.0
        avg_win = round(sum(wins) / len(wins), 2) if wins else 0.0
        avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0
        max_win = round(max(wins), 2) if wins else 0.0
        max_loss = round(min(losses), 2) if losses else 0.0

        # Calculate max drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in reversed(self.trade_history):
            cumulative += t.get('pnl_inr', 0)
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        return {
            "overall_profit_inr": round(total_pnl, 2),
            "overall_profit_usd": round(total_pnl_usd, 2),
            "total_trades": total_legs // 2,
            "avg_profit_per_trade_inr": avg_profit,
            "win_pct": win_pct,
            "loss_pct": loss_pct,
            "avg_win_inr": avg_win,
            "avg_loss_inr": avg_loss,
            "max_profit_inr": max_win,
            "max_loss_inr": max_loss,
            "max_drawdown_inr": round(-max_dd, 2),
            "return_to_mdd": round(total_pnl / max_dd, 2) if max_dd > 0 else 0.0,
            "reward_to_risk": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0.0
        }

    def get_status_payload(self):
        """Complete status payload consumed by the dashboard frontend."""
        spot = self.get_btc_spot_price()
        metrics = self.get_summary_metrics()

        # Calculate live time remaining if position open
        time_remaining_str = "--"
        if self.active_trade and self.active_trade.get("target_exit_time"):
            try:
                now_ist = get_ist_now()
                target_dt = datetime.strptime(self.active_trade["target_exit_time"], '%Y-%m-%d %H:%M:%S').replace(tzinfo=now_ist.tzinfo)
                diff = target_dt - now_ist
                if diff.total_seconds() > 0:
                    hrs = int(diff.total_seconds() // 3600)
                    mins = int((diff.total_seconds() % 3600) // 60)
                    time_remaining_str = f"{hrs}h {mins}m"
                else:
                    time_remaining_str = "Expiring Now"
            except Exception:
                pass

        return {
            "config": self.config,
            "active_trade": self.active_trade,
            "trade_history": self.trade_history[:50],  # Latest 50 trade entries
            "metrics": metrics,
            "btc_spot_price": spot,
            "time_remaining": time_remaining_str,
            "server_time_ist": get_ist_now().strftime('%Y-%m-%d %H:%M:%S')
        }

    # ── AUTOMATED BACKGROUND RUNNER ───────────────────────────────────────────
    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="BTSTStrategyWorker")
        self.worker_thread.start()
        app_logger.info("[BTST] Background strategy runner started.")

    def _run_loop(self):
        while self.is_running:
            try:
                now_ist = get_ist_now()
                now_date = now_ist.strftime('%Y-%m-%d')

                # 1. Evaluate open positions if any
                if self.active_trade:
                    self.evaluate_open_positions()

                # 2. Check automated scheduled entry at user-given time (default 22:30 IST)
                elif self.config.get("is_active", True):
                    entry_cfg_time = str(self.config.get("entry_time_ist", "22:30")).strip()
                    try:
                        parts = entry_cfg_time.split(':')
                        cfg_h = int(parts[0])
                        cfg_m = int(parts[1]) if len(parts) > 1 else 0
                        target_entry_dt = now_ist.replace(hour=cfg_h, minute=cfg_m, second=0, microsecond=0)
                        diff_secs = (now_ist - target_entry_dt).total_seconds()

                        # Active entry window: within 5 minutes after scheduled time (0 to 300 seconds)
                        entry_key = f"{now_date}_{cfg_h:02d}:{cfg_m:02d}"

                        if 0 <= diff_secs <= 300 and getattr(self, 'last_entry_trigger_key', None) != entry_key:
                            allowed_weekdays = self.config.get("weekdays", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
                            weekday_str = now_ist.strftime('%a')
                            if not allowed_weekdays or weekday_str in allowed_weekdays:
                                app_logger.info(f"[BTST] Evaluating scheduled entry at {now_ist.strftime('%H:%M:%S')} IST for scheduled time {cfg_h:02d}:{cfg_m:02d} (Key: {entry_key})...")
                                ok, msg = self.trigger_entry(force=False)
                                if ok:
                                    app_logger.info(f"[BTST] Scheduled trade successfully opened: {msg}")
                                    self.last_entry_trigger_key = entry_key
                                    self.last_evaluated_entry_date = now_date
                                else:
                                    app_logger.warning(f"[BTST] Scheduled trade entry attempt returned: {msg}. Will retry on next loop within window.")
                    except Exception as ex:
                        app_logger.error(f"[BTST] Error in scheduled entry evaluation: {ex}")
            except Exception as e:
                app_logger.error(f"[BTST] Exception in runner loop: {e}")

            time.sleep(10)

# Global Singleton Instance
btst_engine = BTSTStrangleEngine()
