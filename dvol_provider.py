import requests
import time
import json
import os
import threading
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger("trading_bot")

class DVOLProvider:
    def __init__(self, cache_file: str = "dvol_history.json", update_interval: int = 60):
        self.cache_file = cache_file
        self.update_interval = update_interval
        self.lock = threading.RLock()
        
        # State variables
        self.current_dvol = 40.0  # Default fallback
        self.dvol_history = []
        self.dvol_percentile = 50.0  # Default fallback
        self.last_update_time = 0.0
        self.is_running = False
        self.thread = None
        
        # Load from cache on startup
        self._load_cache()

    def start(self):
        """Start the background thread to refresh DVOL data."""
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
            self.thread = threading.Thread(target=self._update_loop, daemon=True)
            self.thread.start()
            logger.info("DVOLProvider background thread started.")

    def stop(self):
        """Stop the background thread."""
        with self.lock:
            self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            logger.info("DVOLProvider background thread stopped.")

    def _update_loop(self):
        while True:
            with self.lock:
                if not self.is_running:
                    break
            try:
                self.refresh_data()
            except Exception as e:
                logger.error(f"Error in DVOL update loop: {e}", exc_info=True)
            time.sleep(self.update_interval)

    def refresh_data(self) -> bool:
        """Fetch current DVOL and history, calculate percentile, and cache."""
        try:
            # 1. Fetch current DVOL (1-minute level for high precision or 1-hour resolution)
            curr_dvol = self.fetch_current_dvol()
            
            # 2. Fetch 30 days of history
            history = self.fetch_dvol_history(days=30)
            
            with self.lock:
                if curr_dvol is not None:
                    self.current_dvol = curr_dvol
                if history:
                    self.dvol_history = history
                
                # 3. Calculate percentile
                if self.dvol_history:
                    # If we don't have current_dvol in the history or if we want to include it,
                    # calculate where the current dvol sits
                    count = sum(1 for val in self.dvol_history if val <= self.current_dvol)
                    self.dvol_percentile = (count / len(self.dvol_history)) * 100.0
                else:
                    self.dvol_percentile = 50.0
                
                self.last_update_time = time.time()
                
            # 4. Save cache
            self._save_cache()
            return True
        except Exception as e:
            logger.error(f"Failed to refresh DVOL data: {e}")
            return False

    def fetch_current_dvol(self) -> float:
        """Call Deribit public API for current BTC DVOL."""
        url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
        end_ts = int(time.time() * 1000)
        # Fetch last 2 hours at 60-minute resolution
        start_ts = end_ts - 2 * 60 * 60 * 1000
        params = {
            "currency": "BTC",
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "resolution": "60"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "data" in data["result"]:
                    points = data["result"]["data"]
                    if points:
                        # Return close price of the latest point (index 4)
                        return float(points[-1][4])
            logger.warning(f"Deribit API for current DVOL returned status {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching current DVOL from Deribit: {e}")
        return self.current_dvol  # Return last known state on failure

    def fetch_dvol_history(self, days: int = 30) -> List[float]:
        """Fetch historical daily DVOL values for percentile calculation."""
        url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
        end_ts = int(time.time() * 1000)
        start_ts = end_ts - (days + 10) * 24 * 60 * 60 * 1000  # Fetch extra days to ensure we have enough daily candles
        params = {
            "currency": "BTC",
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "resolution": "1D"  # Capital D!
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "data" in data["result"]:
                    points = data["result"]["data"]
                    # Extract close values (index 4) and take the last 'days' items
                    closes = [float(p[4]) for p in points]
                    return closes[-days:]
            logger.warning(f"Deribit API for historical DVOL returned status {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching historical DVOL from Deribit: {e}")
        return self.dvol_history  # Return cached/historical list on failure

    def get_dvol_percentile(self) -> float:
        """Returns the current percentile (0-100) based on 30-day data."""
        with self.lock:
            return self.dvol_percentile

    def get_current_dvol(self) -> float:
        """Returns current DVOL value."""
        with self.lock:
            return self.current_dvol

    def get_premium_range(self) -> Tuple[float, float]:
        """Returns target premium range (min, max) based on current DVOL."""
        dvol = self.get_current_dvol()
        if dvol < 40.0:
            return (140.0, 300.0)
        elif 40.0 <= dvol <= 55.0:
            return (120.0, 260.0)
        else:
            return (110.0, 240.0)

    def should_trade(self) -> Tuple[bool, str]:
        """Check if percentile is between 20% and 80% to trade."""
        pct = self.get_dvol_percentile()
        dvol = self.get_current_dvol()
        
        # Safe zone check
        if 20.0 <= pct <= 80.0:
            return True, f"DVOL Percentile {pct:.1f}% (DVOL {dvol:.2f}) is in the safe zone [20-80]."
        else:
            return False, f"DVOL Percentile {pct:.1f}% (DVOL {dvol:.2f}) is outside the safe zone [20-80]. Skipping trade."

    def get_status(self) -> Dict[str, Any]:
        """Get status dictionary for web server status endpoint."""
        with self.lock:
            return {
                "current_dvol": round(self.current_dvol, 2),
                "dvol_percentile": round(self.dvol_percentile, 1),
                "eligible_to_trade": 20.0 <= self.dvol_percentile <= 80.0,
                "premium_range": self.get_premium_range(),
                "last_update": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_update_time))
            }

    def _save_cache(self):
        try:
            with self.lock:
                cache_data = {
                    "current_dvol": self.current_dvol,
                    "dvol_history": self.dvol_history,
                    "dvol_percentile": self.dvol_percentile,
                    "last_update_time": self.last_update_time
                }
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving DVOL cache: {e}")

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                with self.lock:
                    self.current_dvol = cache_data.get("current_dvol", 40.0)
                    self.dvol_history = cache_data.get("dvol_history", [])
                    self.dvol_percentile = cache_data.get("dvol_percentile", 50.0)
                    self.last_update_time = cache_data.get("last_update_time", 0.0)
                logger.info(f"Loaded DVOL cache from {self.cache_file}.")
            except Exception as e:
                logger.error(f"Error loading DVOL cache: {e}")
