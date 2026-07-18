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
            "weights": {
                "stability": 40.0,
                "percentile": 20.0,
                "rank": 15.0,
                "trend_5d": 15.0,
                "change_1h": 10.0
            },
            "thresholds": {
                "score_excellent": 70.0,
                "score_good": 40.0,
                "score_poor": 30.0,
                "iv_stale_seconds": 300,
                "rv_premium_excellent": 10.0,
                "rv_premium_good": 0.0,
                "rv_premium_poor": -5.0
            },
            "stability": {
                "rapid_rise_slope": 1.0,
                "slow_rise_slope": 0.2,
                "rapid_fall_slope": -1.0,
                "slow_fall_slope": -0.2
            }
        }
        try:
            if os.path.exists('psce_config.json'):
                with open('psce_config.json', 'r') as f:
                    cfg = json.load(f)
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

    def evaluate_conditions(self, mode="ENTRY") -> dict:
        """
        Master method to evaluate all metrics and return absolute permission.
        mode can be "ENTRY" or "MONITOR".
        """
        payload = {
            "status": "success",
            "trade_allowed": False,
            "zone": "RED",
            "edge_score": 0.0,
            "decision": "SKIP TRADE",
            "premium_state": "Premium Selling Environment: Unknown",
            "reasons": [],
            "metrics": {},
            "health": {
                "btc_feed": "OFFLINE",
                "iv_feed": "OFFLINE",
                "db_status": "ONLINE",
                "engine_status": "ONLINE"
            },
            "last_update": get_ist_now().strftime("%Y-%m-%dT%H:%M:%S")
        }
        
        try:
            self.config = self._load_config() # hot reload config
            
            # --- 1. Data Feed Validation ---
            btc_price = 0.0
            if hasattr(self.api_client, 'last_price_update_time') and self.api_client.last_price_update_time > 0:
                ticker = self.api_client.get_realtime_ticker("BTCUSD")
                if ticker:
                    btc_price = float(ticker.get('spot_price', ticker.get('mark_price', 0.0)))
            
            if btc_price <= 0:
                payload["reasons"].append("BTC Price feed is offline or invalid.")
                payload["decision"] = "DATA UNAVAILABLE"
                return payload
            payload["health"]["btc_feed"] = "ONLINE"

            if time.time() - self.dvol_provider.last_update_time > self.config['thresholds']['iv_stale_seconds']:
                payload["reasons"].append(f"IV Feed is stale (>{self.config['thresholds']['iv_stale_seconds']}s).")
                payload["decision"] = "DATA UNAVAILABLE"
                return payload
                
            current_iv = self.dvol_provider.current_dvol
            if current_iv <= 0:
                payload["reasons"].append("IV value is 0 or negative.")
                payload["decision"] = "DATA UNAVAILABLE"
                return payload
            payload["health"]["iv_feed"] = "ONLINE"
            
            # --- 2. Metric Computation ---
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
            s_cfg = self.config['stability']
            stability_status = "Stable"
            stability_score_mult = 1.0
            
            if slope_intraday >= s_cfg['rapid_rise_slope']:
                stability_status = "Rapidly Rising"
                stability_score_mult = 0.0 # Extreme penalty
            elif slope_intraday >= s_cfg['slow_rise_slope']:
                stability_status = "Slowly Rising"
                stability_score_mult = 0.5
            elif slope_intraday <= s_cfg['rapid_fall_slope']:
                stability_status = "Rapidly Falling"
                stability_score_mult = 0.3 # Falling very fast implies panic
            elif slope_intraday <= s_cfg['slow_fall_slope']:
                stability_status = "Slowly Falling"
                stability_score_mult = 1.0 # Good for selling
            else:
                stability_status = "Stable"
                stability_score_mult = 1.0
                
            # 1-Hour IV Expansion
            iv_change_1h_pct = 0.0
            if len(intraday_candles) >= 60:
                iv_1h_ago = intraday_candles[-60]
                iv_change_1h_pct = ((current_iv - iv_1h_ago) / iv_1h_ago) * 100
                
            # Premium State
            rv_5d = self._calculate_rv_5d()
            iv_premium = current_iv - rv_5d
            t_cfg = self.config['thresholds']
            if iv_premium >= t_cfg['rv_premium_excellent']:
                premium_state = "Premium Selling Environment: Excellent"
                prem_mult = 1.0
            elif iv_premium >= t_cfg['rv_premium_good']:
                premium_state = "Premium Selling Environment: Good"
                prem_mult = 0.8
            elif iv_premium >= t_cfg['rv_premium_poor']:
                premium_state = "Premium Selling Environment: Average"
                prem_mult = 0.5
            else:
                premium_state = "Premium Selling Environment: Poor"
                prem_mult = 0.1
                
            # --- 3. Edge Score Calculation ---
            w_cfg = self.config['weights']
            
            # Max base score is 100 before multipliers
            # Stability uses its multiplier against the total score at the end
            score_percentile = (iv_percentile / 100.0) * w_cfg['percentile']
            score_rank = (iv_rank / 100.0) * w_cfg['rank']
            
            # Trend: Falling or Stable is better for sellers
            score_trend = w_cfg['trend_5d'] if trend_str in ["STABLE", "FALLING"] else (w_cfg['trend_5d'] * 0.5)
            
            # 1H Expansion: Big positive change is bad
            if iv_change_1h_pct > 2.0: score_exp = 0
            elif iv_change_1h_pct > 1.0: score_exp = w_cfg['change_1h'] * 0.5
            else: score_exp = w_cfg['change_1h']
            
            # Base score combined with Premium multiplier and Stability multiplier
            base_components = score_percentile + score_rank + score_trend + score_exp
            
            # To give stability its weight directly as points vs multiplier:
            # Let's map stability string to point value out of w_cfg['stability']
            stab_points = w_cfg['stability'] * stability_score_mult
            
            raw_score = stab_points + base_components
            edge_score = raw_score * prem_mult # Apply premium environment overall multiplier
            
            edge_score = max(0.0, min(100.0, round(edge_score, 1)))
            
            # --- 4. Decision Boundaries ---
            reasons = []
            reasons.append(f"IV is {stability_status} today.")
            reasons.append(premium_state)
            
            if edge_score >= t_cfg['score_excellent']:
                zone = "HEALTHY"
                decision = "SELL STRADDLE"
                trade_allowed = True
                reasons.append("Optimal edge for premium selling.")
            elif edge_score >= t_cfg['score_good']:
                zone = "CAUTION"
                decision = "REDUCE SIZE"
                trade_allowed = True
                reasons.append("Medium edge. Watch for IV expansion.")
            else:
                zone = "LOW EDGE"
                decision = "SKIP TRADE"
                trade_allowed = False
                reasons.append("Unfavorable risk/reward. Theta advantage is weak.")
                
            payload["zone"] = zone
            payload["decision"] = decision
            payload["edge_score"] = edge_score
            payload["trade_allowed"] = trade_allowed
            payload["premium_state"] = premium_state
            payload["reasons"] = reasons
            
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
                "iv_rank": iv_rank,
                "iv_percentile": iv_percentile,
                "premium_state": premium_state,
                "edge_score": edge_score,
                "decision": decision,
                "trade_allowed": trade_allowed
            }
            self._save_historical_snapshot(snapshot)
            
            return payload
            
        except Exception as e:
            error_logger.error(f"PSCE: Critical failure during evaluation: {e}", exc_info=True)
            payload["reasons"].append(f"Engine Exception: {str(e)}")
            payload["health"]["engine_status"] = "ERROR"
            payload["decision"] = "ENGINE ERROR"
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
