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

    def _calculate_rv_5d(self) -> float:
        try:
            history = self.api_client.get_history("BTCUSD", "1h")
            if not history or len(history) < 24 * 5: return 40.0
            closes = [c['close'] for c in history[-120:]]
            if len(closes) < 2: return 40.0
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0 and closes[i] > 0:
                    returns.append(math.log(closes[i] / closes[i-1]))
            if not returns: return 40.0
            variance = statistics.variance(returns)
            return math.sqrt(variance * 8760) * 100
        except Exception:
            return 40.0

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
            iv_percentile = self.dvol_provider.dvol_percentile
            iv_rank = 50.0
            if dvol_history and len(dvol_history) > 1:
                min_iv, max_iv = min(dvol_history), max(dvol_history)
                if max_iv > min_iv:
                    iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100
                    
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
                # ALLOW: IV is acceptable
                zone = "HEALTHY"
                decision = "SELL STRADDLE"
                trade_allowed = True
                decision_reason = f"IV {formatted_iv}% is above {min_iv:.0f}% threshold — trade conditions are favorable."
                reasons.append(decision_reason)
                # Edge score: map IV range. 20% = 50, 40% = 75, 60%+ = 90+
                edge_score = min(100.0, 50.0 + ((current_iv - min_iv) / 40.0) * 50.0)
            
            edge_score = max(0.0, min(100.0, round(edge_score, 1)))
            
            payload["zone"] = zone
            payload["decision"] = decision
            payload["edge_score"] = edge_score
            payload["trade_allowed"] = trade_allowed
            payload["premium_state"] = premium_state
            payload["reasons"] = reasons
            payload["final_decision"] = "ALLOW" if trade_allowed else "BLOCK"
            payload["decision_reason"] = decision_reason
            
            sign = "+" if iv_change_1h_pct > 0 else ""
            payload["metrics"] = {
                "btc_price": btc_price,
                "atm_iv": current_iv,
                "iv_percentile": iv_percentile,
                "iv_rank": iv_rank,
                "iv_trend_5d": trend_str,
                "iv_change_1h": f"{sign}{iv_change_1h_pct:.2f}%",
                "iv_stability": stability_status
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
