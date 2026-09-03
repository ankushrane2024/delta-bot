import time
import math
import logging
import statistics
import requests
import json
import os
import numpy as np
from datetime import datetime, timezone, timedelta

from logger import app_logger, error_logger
from utils import get_ist_now
import db_manager

class PremiumSellingConditionsEngine:
    def __init__(self, api_client, dvol_provider):
        self.api_client = api_client
        self.dvol_provider = dvol_provider
        self.config = self._load_config()
        
    def _load_config(self):
        default_config = {
            "min_iv_threshold": 20.0,
            "min_premium_threshold": 100.0,
            "iv_refresh_interval_seconds": 60,
            "iv_data_freshness_timeout_seconds": 300,
            "iv_status_boundaries": {
                "low_max": 30.0,
                "medium_max": 50.0
            }
        }
        try:
            if os.path.exists('psce_config.json'):
                with open('psce_config.json', 'r') as f:
                    cfg = json.load(f)
                    # Merge with defaults so missing keys don't crash
                    for key, val in default_config.items():
                        if key not in cfg:
                            cfg[key] = val
                    if "iv_status_boundaries" not in cfg:
                        cfg["iv_status_boundaries"] = default_config["iv_status_boundaries"]
                    return cfg
        except Exception as e:
            error_logger.error(f"PSCE: Failed to load config: {e}")
        return default_config

    def _get_current_session_dvol_slope(self):
        """Calculates IV slope only over the current trading session (since 00:00 UTC)."""
        try:
            # Current UTC midnight timestamp
            now = datetime.now(timezone.utc)
            midnight = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            start_ts = int(midnight.timestamp() * 1000)
            end_ts = int(now.timestamp() * 1000)
            
            # If session just started, look back at least 2 hours to avoid extreme noise
            if end_ts - start_ts < 2 * 3600 * 1000:
                start_ts = end_ts - 2 * 3600 * 1000
                
            url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            params = {
                "currency": "BTC",
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "resolution": "60" # 1 min candles for intraday
            }
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data and "data" in data["result"]:
                    points = data["result"]["data"]
                    if len(points) > 2:
                        closes = [float(p[4]) for p in points]
                        # Calculate slope per hour
                        x = np.arange(len(closes)) / 60.0 # x in hours
                        slope = np.polyfit(x, closes, 1)[0]
                        return slope, closes
            return 0.0, []
        except Exception as e:
            error_logger.warning(f"PSCE: Failed intraday DVOL slope: {e}")
            return 0.0, []

    # ── Realized-Volatility helpers ────────────────────────────────────────
    # NOTE: api_client (DeltaIndiaClient) has NO get_history() method.
    # All RV calculations use the Deribit public candle API directly,
    # the same source already used by dvol_provider for DVOL history.
    # ────────────────────────────────────────────────────────────────────────

    def _fetch_deribit_btc_candles(self, resolution_seconds: int, days: int) -> list:
        """Fetch BTC spot/perp hourly closes from Deribit public API.
        resolution_seconds: 3600 for 1h candles, 86400 for 1D candles.
        Returns list of close prices (floats), newest last.
        Falls back to [] on any error.
        Data source: Deribit BTC DVOL index (same as dvol_provider).
        For RV calculation we use the DVOL index itself as a proxy because:
          - api_client has no historical OHLC method
          - Deribit DVOL data is reliably available for 60+ days
          - RV vs DVOL comparison is internally consistent using the same exchange
        """
        try:
            url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            end_ts = int(time.time() * 1000)
            start_ts = end_ts - int(days * 24 * 3600 * 1000 * 1.1)  # +10% buffer
            res_str = str(int(resolution_seconds // 60)) if resolution_seconds < 86400 else "1D"
            params = {
                "currency": "BTC",
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "resolution": res_str
            }
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data and "data" in data["result"]:
                    return [float(p[4]) for p in data["result"]["data"]]
        except Exception as e:
            error_logger.warning(f"PSCE: Deribit candle fetch failed ({resolution_seconds}s, {days}d): {e}")
        return []

    def _calculate_rv_5d(self) -> float:
        """5-day realized volatility using Deribit hourly DVOL data. Annualized %."""
        try:
            closes = self._fetch_deribit_btc_candles(resolution_seconds=3600, days=6)
            if len(closes) < 24 * 5:
                return 40.0  # Insufficient data fallback
            closes = closes[-120:]  # last 5 days of hourly candles
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0 and closes[i] > 0:
                    returns.append(math.log(closes[i] / closes[i-1]))
            if len(returns) < 2:
                return 40.0
            variance = statistics.variance(returns)
            return math.sqrt(variance * 8760) * 100
        except Exception as e:
            error_logger.warning(f"PSCE: _calculate_rv_5d failed: {e}")
            return 40.0

    def _calculate_rv_24h(self) -> float:
        """24-hour realized volatility using Deribit 1-hour DVOL data. Annualized %.
        Data source: Deribit public DVOL index (same as dvol_provider).
        """
        try:
            closes = self._fetch_deribit_btc_candles(resolution_seconds=3600, days=2)
            if len(closes) < 24:
                return 40.0  # Insufficient data fallback
            closes = closes[-24:]  # last 24 hourly candles
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0 and closes[i] > 0:
                    returns.append(math.log(closes[i] / closes[i-1]))
            if len(returns) < 2:
                return 40.0
            variance = statistics.variance(returns)
            return math.sqrt(variance * 8760) * 100
        except Exception as e:
            error_logger.warning(f"PSCE: _calculate_rv_24h failed: {e}")
            return 40.0

    def _calculate_rv24_avg_60day(self) -> float:
        """Rolling 60-day average of daily-close RV using Deribit 1D DVOL data.
        Each daily close is treated as the daily RV proxy; we compute a log-return
        series and return the mean of rolling 1-day annualized variance, averaged
        over 60 days.
        Data source: Deribit public DVOL index daily closes (same as dvol_provider).
        """
        try:
            closes = self._fetch_deribit_btc_candles(resolution_seconds=86400, days=65)
            if len(closes) < 5:
                return 40.0  # Insufficient data fallback
            closes = closes[-61:]  # last 60 daily candles + 1 for log-returns
            # Compute annualized RV for each day (log-return squared * sqrt(365))
            daily_rvs = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0 and closes[i] > 0:
                    r = math.log(closes[i] / closes[i-1])
                    # Annualize: daily vol = |r|, annualized = |r| * sqrt(252) * 100
                    daily_rvs.append(abs(r) * math.sqrt(252) * 100)
            if not daily_rvs:
                return 40.0
            return statistics.mean(daily_rvs)
        except Exception as e:
            error_logger.warning(f"PSCE: _calculate_rv24_avg_60day failed: {e}")
            return 40.0

    def _check_rv24_filter(self, current_iv: float) -> tuple:
        """B1 Pre-trade RV24 entry filter.

        Blocks entry if:
          RV24 > 1.3 * RV24_avg_60day  (realized vol is spiking above its 60-day average)
          OR
          RV24 > 0.85 * current_ATM_IV  (realized vol is eating into the IV premium)

        Returns (blocked: bool, reason: str).
        This method is ONLY called at entry evaluation time.
        It has ZERO interaction with the SL monitor loop or the trailing-SL logic
        (those run after a position is already open).
        Data source: Deribit public API (same as dvol_provider). See _fetch_deribit_btc_candles.
        """
        try:
            rv24 = self._calculate_rv_24h()
            rv24_avg_60d = self._calculate_rv24_avg_60day()

            spike_threshold = 1.3 * rv24_avg_60d
            iv_eat_threshold = 0.85 * current_iv

            if rv24 > spike_threshold:
                reason = (
                    f"B1 RV24 Spike Filter: RV24={rv24:.1f}% > 1.3x 60d-avg "
                    f"({rv24_avg_60d:.1f}% * 1.3 = {spike_threshold:.1f}%). "
                    f"Realized vol is spiking. No same-day retry."
                )
                error_logger.warning(f"PSCE: {reason}")
                return True, reason

            if rv24 > iv_eat_threshold:
                reason = (
                    f"B1 RV24 vs IV Filter: RV24={rv24:.1f}% > 0.85x ATM IV "
                    f"({current_iv:.1f}% * 0.85 = {iv_eat_threshold:.1f}%). "
                    f"Premium edge is too thin. No same-day retry."
                )
                error_logger.warning(f"PSCE: {reason}")
                return True, reason

            return False, f"RV24={rv24:.1f}% passes both thresholds (60d-avg={rv24_avg_60d:.1f}%, 0.85xIV={iv_eat_threshold:.1f}%)"
        except Exception as e:
            error_logger.error(f"PSCE: _check_rv24_filter exception: {e}")
            # On error, do NOT block — fail open to avoid spurious blocks
            return False, f"RV24 filter error (non-blocking): {e}"

    def _ensure_fresh_iv(self):
        """Force-refresh IV data if it is stale beyond the configured timeout."""
        freshness_timeout = self.config.get('iv_data_freshness_timeout_seconds', 300)
        data_age = time.time() - self.dvol_provider.last_update_time
        
        if data_age > freshness_timeout:
            app_logger.info(f"PSCE: IV data is {data_age:.0f}s old (limit: {freshness_timeout}s). Force-refreshing...")
            try:
                self.dvol_provider.refresh_data()
                app_logger.info(f"PSCE: IV data refreshed. New DVOL: {self.dvol_provider.current_dvol:.2f}")
            except Exception as e:
                error_logger.error(f"PSCE: Failed to force-refresh IV data: {e}")

    def _get_iv_status(self, iv_value):
        """Returns IV status label based on config boundaries (display only, never blocks)."""
        boundaries = self.config.get('iv_status_boundaries', {"low_max": 30.0, "medium_max": 50.0})
        if iv_value < boundaries.get('low_max', 30.0):
            return "Low"
        elif iv_value < boundaries.get('medium_max', 50.0):
            return "Medium"
        else:
            return "Healthy"

    def evaluate_conditions(self, mode="ENTRY") -> dict:
        """
        Simplified IV Trade Readiness Master Gate.
        
        Decision Logic:
        1. IV < min_iv_threshold (default 20%) → BLOCK
        2. Otherwise → ALLOW
        
        Premium validation is handled separately in run_entry_cycle().
        """
        payload = {
            "status": "success",
            "trade_allowed": False,
            "zone": "RED",
            "edge_score": 0.0,
            "decision": "SKIP TRADE",
            "premium_state": "Unknown",
            "reasons": [],
            "metrics": {},
            "health": {
                "btc_feed": "OFFLINE",
                "iv_feed": "OFFLINE",
                "db_status": "ONLINE",
                "engine_status": "ONLINE"
            },
            "last_update": get_ist_now().strftime("%Y-%m-%dT%H:%M:%S"),
            # New transparency fields
            "live_iv": 0.0,
            "iv_status": "Unknown",
            "min_iv_threshold": self.config.get('min_iv_threshold', 20.0),
            "iv_data_timestamp": "",
            "data_age_seconds": 0,
            "final_decision": "BLOCK",
            "decision_reason": "Evaluation not started"
        }
        
        try:
            self.config = self._load_config()  # hot reload config
            
            # --- 1. Data Feed Validation ---
            btc_price = 0.0
            if hasattr(self.api_client, 'last_price_update_time') and self.api_client.last_price_update_time > 0:
                ticker = self.api_client.get_realtime_ticker("BTCUSD")
                if ticker:
                    btc_price = float(ticker.get('spot_price', ticker.get('mark_price', 0.0)))
            
            # Fallback to REST ticker if WS price is not yet available
            if btc_price <= 0:
                try:
                    res = self.api_client.get_tickers({'contract_types': 'perpetual_futures'})
                    if res.get('success'):
                        for t in res.get('result', []):
                            if t.get('symbol') == 'BTCUSD':
                                btc_price = float(t.get('spot_price') or t.get('mark_price') or 0.0)
                                break
                except Exception as btc_err:
                    error_logger.warning(f"PSCE: REST BTC ticker fallback failed: {btc_err}")
            
            if btc_price <= 0:
                payload["reasons"].append("BTC Price feed is offline or invalid.")
                payload["decision"] = "DATA UNAVAILABLE"
                payload["decision_reason"] = "BTC Price feed is offline or invalid."
                payload["final_decision"] = "BLOCK"
                return payload
            payload["health"]["btc_feed"] = "ONLINE"

            # --- 2. Ensure Fresh IV Data ---
            self._ensure_fresh_iv()
            
            data_age = time.time() - self.dvol_provider.last_update_time
            freshness_timeout = self.config.get('iv_data_freshness_timeout_seconds', 300)
            
            if data_age > freshness_timeout:
                payload["reasons"].append(f"IV Feed is stale (>{freshness_timeout}s old even after refresh attempt).")
                payload["decision"] = "DATA UNAVAILABLE"
                payload["decision_reason"] = f"IV data is {data_age:.0f}s old — stale beyond {freshness_timeout}s limit."
                payload["final_decision"] = "BLOCK"
                payload["data_age_seconds"] = round(data_age)
                return payload
                
            current_iv = self.dvol_provider.current_dvol
            if current_iv <= 0:
                payload["reasons"].append("IV value is 0 or negative.")
                payload["decision"] = "DATA UNAVAILABLE"
                payload["decision_reason"] = "IV value is 0 or negative."
                payload["final_decision"] = "BLOCK"
                return payload
            payload["health"]["iv_feed"] = "ONLINE"
            
            # --- 3. Populate Transparency Fields ---
            iv_status = self._get_iv_status(current_iv)
            iv_timestamp = datetime.fromtimestamp(
                self.dvol_provider.last_update_time, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S UTC")
            
            payload["live_iv"] = round(current_iv, 2)
            payload["iv_status"] = iv_status
            payload["iv_data_timestamp"] = iv_timestamp
            payload["data_age_seconds"] = round(data_age)
            payload["min_iv_threshold"] = self.config.get('min_iv_threshold', 20.0)
            
            # --- 4. Compute Display Metrics (informational only) ---
            dvol_history = self.dvol_provider.dvol_history
            # iv_percentile: None sentinel when history is too thin to be meaningful.
            # The default dvol_percentile=50.0 is a fallback, not real data.
            iv_percentile = self.dvol_provider.dvol_percentile if len(dvol_history) >= 5 else None
            iv_rank = None  # None = "Insufficient data" sentinel
            if dvol_history and len(dvol_history) >= 5:
                min_iv, max_iv = min(dvol_history), max(dvol_history)
                if max_iv > min_iv:
                    # Clamp to [0, 100]: negative rank means current IV is below the 30d min,
                    # which would display as "-0" in JS toFixed(0) — clamp prevents this.
                    iv_rank = max(0.0, min(100.0, ((current_iv - min_iv) / (max_iv - min_iv)) * 100))
                    
            # 5-Day Trend
            trend_str = "STABLE"
            if len(dvol_history) >= 5:
                recent_5d = dvol_history[-5:]
                slope_5d = np.polyfit(range(5), recent_5d, 1)[0]
                if slope_5d > 0.5: trend_str = "RISING"
                elif slope_5d < -0.5: trend_str = "FALLING"
                
            # IV Stability Today (Current Session)
            slope_intraday, intraday_candles = self._get_current_session_dvol_slope()
            stability_status = "Stable"
            if slope_intraday >= 1.0:
                stability_status = "Rapidly Rising"
            elif slope_intraday >= 0.2:
                stability_status = "Slowly Rising"
            elif slope_intraday <= -1.0:
                stability_status = "Rapidly Falling"
            elif slope_intraday <= -0.2:
                stability_status = "Slowly Falling"
                
            # 1-Hour IV Expansion
            iv_change_1h_pct = 0.0
            if len(intraday_candles) >= 60:
                iv_1h_ago = intraday_candles[-60]
                if iv_1h_ago > 0:
                    iv_change_1h_pct = ((current_iv - iv_1h_ago) / iv_1h_ago) * 100
                    
            # Premium State (display only)
            rv_5d = self._calculate_rv_5d()
            iv_premium = current_iv - rv_5d
            if iv_premium >= 10.0:
                premium_state = "Premium Selling Environment: Excellent"
            elif iv_premium >= 0.0:
                premium_state = "Premium Selling Environment: Good"
            elif iv_premium >= -5.0:
                premium_state = "Premium Selling Environment: Average"
            else:
                premium_state = "Premium Selling Environment: Poor"
            
            # --- 5. SIMPLE DECISION LOGIC ---
            min_iv = self.config.get('min_iv_threshold', 20.0)
            healthy_iv_threshold = self.config.get('iv_status_boundaries', {}).get('medium_max', 50.0)
            reasons = []
            formatted_iv = f"{current_iv + 1e-9:.1f}"
            reasons.append(f"Live IV: {formatted_iv}% ({iv_status})")
            reasons.append(f"IV is {stability_status} today.")
            reasons.append(premium_state)

            if current_iv < min_iv:
                # BLOCK: Extremely Low IV
                zone = "RED"
                decision = "SKIP TRADE"
                trade_allowed = False
                decision_reason = f"Extremely Low IV — {formatted_iv}% is below {min_iv:.0f}% minimum. Premiums are too compressed."
                reasons.append(decision_reason)
                # Edge score: map IV to 0-100 scale where min_iv = 0
                edge_score = max(0.0, (current_iv / min_iv) * 25.0)  # Below threshold = low score
            else:
                # ALLOW: IV is at least above the minimum.
                # A1 FIX: Zone correctly reflects the three-tier threshold scale:
                #   RED:    IV < min_iv (20%)
                #   MEDIUM: min_iv <= IV < healthy_iv_threshold (50%)
                #   HEALTHY: IV >= healthy_iv_threshold (50%)
                # This matches the IV Zone Meter displayed at the bottom of the panel.
                if current_iv >= healthy_iv_threshold:
                    zone = "HEALTHY"
                else:
                    zone = "MEDIUM"
                decision = "SELL STRADDLE"
                trade_allowed = True
                decision_reason = f"IV {formatted_iv}% is above {min_iv:.0f}% threshold — trade conditions are favorable."
                reasons.append(decision_reason)
                # Edge score: map IV range. 20% = 50, 40% = 75, 60%+ = 90+
                edge_score = min(100.0, 50.0 + ((current_iv - min_iv) / 40.0) * 50.0)
            
            edge_score = max(0.0, min(100.0, round(edge_score, 1)))

            # --- 6. B1: RV24 Pre-Trade Entry Filter ---
            # Only checked at ENTRY time (mode=ENTRY). During MONITOR mode,
            # skip to avoid interfering with in-trade monitoring.
            # This filter has ZERO interaction with the SL/trailing-SL monitor loop.
            if mode == "ENTRY" and trade_allowed:
                rv24_blocked, rv24_reason = self._check_rv24_filter(current_iv)
                if rv24_blocked:
                    trade_allowed = False
                    zone = "RED"
                    decision = "SKIP TRADE"
                    decision_reason = rv24_reason
                    reasons.append(rv24_reason)
                    edge_score = max(0.0, edge_score * 0.5)  # Penalise score when RV blocks
                else:
                    reasons.append(rv24_reason)  # Log passing reason for transparency

            # --- 7. Market Condition (A3 Fix) ---
            # Derived from real trend+edge data, not from premium_state string matching.
            # DIRECTIONAL: IV is trending upward (rising) OR edge score is weak (<55)
            # RANGE: IV is stable/falling AND edge score is adequate
            if trend_str == "RISING" or edge_score < 55:
                market_condition = "DIRECTIONAL"
            else:
                market_condition = "RANGE"

            payload["zone"] = zone
            payload["decision"] = decision
            payload["edge_score"] = edge_score
            payload["trade_allowed"] = trade_allowed
            payload["premium_state"] = premium_state
            payload["market_condition"] = market_condition
            payload["reasons"] = reasons
            payload["final_decision"] = "ALLOW" if trade_allowed else "BLOCK"
            payload["decision_reason"] = decision_reason
            
            sign = "+" if iv_change_1h_pct > 0 else ""
            # A2 FIX: iv_percentile and iv_rank are None when dvol_history has < 5 entries.
            # The JS will show "Insufficient data" instead of 0% / -0.
            # iv_rank is clamped to [0, 100] — negative values (current IV below 30d min)
            # previously rendered as "-0" via toFixed(0).
            payload["metrics"] = {
                "btc_price": btc_price,
                "atm_iv": current_iv,
                "iv_percentile": round(iv_percentile, 1) if iv_percentile is not None else None,
                "iv_rank": round(iv_rank, 1) if iv_rank is not None else None,
                "iv_trend_5d": trend_str,
                "iv_change_1h": f"{sign}{iv_change_1h_pct:.2f}%",
                "iv_stability": stability_status,
                "iv_history_ready": len(dvol_history) >= 5
            }
            
            # Log snapshot to Historical DB
            snapshot = {
                "timestamp": int(time.time()),
                "mode": mode,
                "atm_iv": current_iv,
                "iv_status": iv_status,
                "iv_rank": iv_rank,
                "iv_percentile": iv_percentile,
                "premium_state": premium_state,
                "edge_score": edge_score,
                "decision": decision,
                "trade_allowed": trade_allowed,
                "decision_reason": decision_reason,
                "data_age_seconds": round(data_age)
            }
            self._save_historical_snapshot(snapshot)
            
            return payload
            
        except Exception as e:
            error_logger.error(f"PSCE: Critical failure during evaluation: {e}", exc_info=True)
            payload["reasons"].append(f"Engine Exception: {str(e)}")
            payload["health"]["engine_status"] = "ERROR"
            payload["decision"] = "ENGINE ERROR"
            payload["decision_reason"] = f"Engine Exception: {str(e)}"
            payload["final_decision"] = "BLOCK"
            return payload

    def _save_historical_snapshot(self, snapshot: dict):
        try:
            # We save snapshots into a separate file directly via db_manager
            # In a real system, this would append to Cloud DB
            import json, os
            filepath = "psce_history.json"
            history = []
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        history = json.load(f)
                except:
                    pass
            history.append(snapshot)
            # Keep only last 1000
            history = history[-1000:]
            with open(filepath, 'w') as f:
                json.dump(history, f)
        except Exception as e:
            error_logger.warning(f"PSCE: Failed to save historical snapshot: {e}")
