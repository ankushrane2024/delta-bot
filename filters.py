import json
import os
import time
import requests
import datetime
from utils import get_ist_now
from logger import app_logger, error_logger

class TradingFilters:
    def __init__(self, api_client, dvol_provider=None):
        self.api_client = api_client
        self.dvol_provider = dvol_provider
        self.iv_file = 'iv_history.json'
        self.cached_news = []
        self.last_news_fetch_time = 0.0

    def check_dvol_percentile_filter(self):
        """DVOL Percentile Filter - COMPLETELY DISABLED FOR TESTING (as requested)."""
        return True, "DVOL Percentile Filter (Completely Disabled for Testing)"

    def check_day_filter(self):
        """Allow trading on all 7 days."""
        return True

    def _update_and_get_iv(self):
        """Stores daily IV and calculates 7-day average."""
        history = {}
        if os.path.exists(self.iv_file):
            try:
                with open(self.iv_file, 'r') as f:
                    history = json.load(f)
            except Exception:
                pass

        today_str = get_ist_now().strftime('%Y-%m-%d')
        
        # Get current IV from Delta API
        current_avg_iv = 0
        try:
            res = self.api_client.get_tickers({'contract_types': 'call_options,put_options', 'underlying_asset_symbol': 'BTC'})
            if res.get('success'):
                tickers = res.get('result', [])
                # mark_iv is nested inside t['quotes'] in Delta Exchange API
                ivs = []
                for t in tickers:
                    quotes = t.get('quotes') or {}
                    iv_val = float(quotes.get('mark_iv', 0) or t.get('mark_vol', 0) or 0)
                    if iv_val > 0:
                        ivs.append(iv_val)
                if ivs:
                    current_avg_iv = sum(ivs) / len(ivs)
                    # Update today's record
                    history[today_str] = current_avg_iv
                    
                    # Save back
                    with open(self.iv_file, 'w') as f:
                        json.dump(history, f)
        except Exception as e:
            error_logger.error(f"Filter: Failed to fetch current IV: {e}")
            return 0, 0

        # Calculate 5-day average
        past_5_days_ivs = []
        for i in range(1, 6):
            d_str = (get_ist_now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
            if d_str in history:
                past_5_days_ivs.append(history[d_str])

        five_day_avg = 0
        if past_5_days_ivs:
            five_day_avg = sum(past_5_days_ivs) / len(past_5_days_ivs)
        else:
            # If no history, assume 5-day avg is slightly below current to allow trading,
            # or just return current_avg_iv as the baseline.
            five_day_avg = current_avg_iv * 0.99 

        return current_avg_iv, five_day_avg

    def check_iv_filter(self):
        """Check if current IV > 0.35 AND current IV < 0.92 * 5-day average IV."""
        # TEMPORARILY DISABLED FOR TESTING (as requested)
        app_logger.info("Filter: IV check TEMPORARILY DISABLED FOR TESTING. Allowing trade.")
        return True

    def _update_news_cache(self):
        """Helper to fetch and cache news calendar from ForexFactory every 6 hours."""
        current_time = time.time()
        # If cache is fresh (less than 6 hours old), do not fetch
        if self.cached_news and (current_time - self.last_news_fetch_time < 21600):
            return
            
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                self.cached_news = response.json()
                self.last_news_fetch_time = current_time
                app_logger.info("Filters: ForexFactory calendar cache updated.")
        except Exception as e:
            app_logger.warning(f"Filters: Failed to fetch ForexFactory calendar: {e}")

    def check_news_filter(self):
        """Skip major news days using cached calendar API. TEMPORARILY DISABLED."""
        app_logger.info("Filter: News check TEMPORARILY DISABLED FOR TESTING. Allowing trade.")
        return True

    def all_passed(self):
        return (self.check_day_filter() and 
                self.check_dvol_percentile_filter()[0] and 
                self.check_news_filter())

    def get_filter_status(self):
        """Returns (passed: bool, reason: str) prioritized by News > DVOL Percentile"""
        if not self.check_news_filter():
            return False, "High Impact USD News"
        
        dvol_ok, dvol_reason = self.check_dvol_percentile_filter()
        if not dvol_ok:
            return False, f"DVOL Percentile Filter: {dvol_reason}"
            
        return True, "All Filters Passed"

    def get_schedule(self, days=7):
        """Calculates skip status for the next 'days' days using cached news."""
        schedule = []
        today = get_ist_now().date()
        
        self._update_news_cache()
        news_events = self.cached_news

        for i in range(days):
            target_date = today + datetime.timedelta(days=i)
            target_date_str = target_date.strftime('%Y-%m-%d')
            day_name = target_date.strftime('%A')
            
            skip = False
            reason = None
            skip_type = 'normal' # normal or severe (for styling)
            
            # 1. Weekend Check - Disabled (Trade 7 days a week)
            
            # 2. News Check
            # TEMPORARILY DISABLED FOR TESTING
            # if not skip and news_events:
            #     for event in news_events:
            #         if event.get('impact') == 'High' and event.get('country') == 'USD':
            #             event_date = event.get('date', '')[:10]
            #             if event_date == target_date_str:
            #                 skip = True
            #                 reason = f"High Impact News"
            #                 skip_type = 'severe'
            #                 break
            
            schedule.append({
                'date': target_date.strftime('%b %d'),
                'day': day_name,
                'skip': skip,
                'reason': reason,
                'skip_type': skip_type
            })
            
        return schedule

    def get_market_regime(self):
        """Calculates 14-period ADX on 4H BTC perp candles using pure pandas/numpy.
        Returns (regime, adx_value). No external TA libraries needed."""
        import pandas as pd
        import numpy as np
        
        try:
            # Fetch 7 days of 4H candles to ensure enough data for a stable 14-period ADX
            end_time = int(time.time())
            start_time = end_time - (7 * 24 * 3600)
            
            res = self.api_client.get_candles("BTCUSD", "4h", start=start_time, end=end_time)
            
            if not (res and res.get('success')):
                app_logger.warning("Filter: Failed to fetch candles for ADX.")
                return "Unknown", 0.0
                
            candles = res.get('result', [])
            if not candles or len(candles) < 28:  # need ~2x period for stable Wilder's smoothing
                app_logger.warning(f"Filter: Not enough candle data ({len(candles) if candles else 0} bars) to calculate ADX.")
                return "Unknown", 0.0
                
            df = pd.DataFrame(candles)
            df['high']  = df['high'].astype(float)
            df['low']   = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            if 'time' in df.columns:
                df = df.sort_values(by='time').reset_index(drop=True)
            
            period = 14
            
            # --- True Range ---
            df['prev_close'] = df['close'].shift(1)
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    (df['high'] - df['prev_close']).abs(),
                    (df['low']  - df['prev_close']).abs()
                )
            )
            
            # --- Directional Movement ---
            df['prev_high'] = df['high'].shift(1)
            df['prev_low']  = df['low'].shift(1)
            df['up_move']   = df['high'] - df['prev_high']
            df['down_move'] = df['prev_low'] - df['low']
            
            df['plus_dm']  = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
            df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
            
            # --- Wilder's Smoothing (RMA) ---
            def wilders(series, n):
                result = [np.nan] * len(series)
                # Seed with simple average of first n values
                seed_start = series.first_valid_index()
                vals = series.dropna().values
                if len(vals) < n:
                    return pd.Series(result, index=series.index)
                result_arr = np.full(len(series), np.nan)
                # Find first non-nan position
                first_idx = series.first_valid_index()
                pos = series.index.get_loc(first_idx)
                result_arr[pos + n - 1] = vals[:n].mean()
                for i in range(n, len(vals)):
                    result_arr[pos + i] = (result_arr[pos + i - 1] * (n - 1) + vals[i]) / n
                return pd.Series(result_arr, index=series.index)
            
            df = df.dropna(subset=['tr', 'plus_dm', 'minus_dm']).reset_index(drop=True)
            
            smoothed_tr       = wilders(df['tr'],       period)
            smoothed_plus_dm  = wilders(df['plus_dm'],  period)
            smoothed_minus_dm = wilders(df['minus_dm'], period)
            
            plus_di  = 100 * smoothed_plus_dm  / smoothed_tr.replace(0, np.nan)
            minus_di = 100 * smoothed_minus_dm / smoothed_tr.replace(0, np.nan)
            
            di_sum  = (plus_di + minus_di).replace(0, np.nan)
            dx      = 100 * (plus_di - minus_di).abs() / di_sum
            
            adx_series = wilders(dx.dropna().reset_index(drop=True), period)
            
            current_adx = float(adx_series.dropna().iloc[-1])
            
            regime = "Trending" if current_adx > 25 else "Ranging"
            app_logger.info(f"Filter: Market Regime is {regime} (ADX: {current_adx:.2f})")
            return regime, round(current_adx, 2)
            
        except Exception as e:
            app_logger.error(f"Filter: Error calculating ADX: {e}")
            return "Unknown", 0.0
