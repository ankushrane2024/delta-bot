import json
import os
import time
import requests
import datetime
from utils import get_ist_now
from logger import app_logger, error_logger

class TradingFilters:
    def __init__(self, api_client):
        self.api_client = api_client
        self.iv_file = 'iv_history.json'

    def check_day_filter(self):
        """Skip Friday, Saturday, and Sunday."""
        now = get_ist_now()
        day_name = now.strftime('%A')
        if day_name in ['Friday', 'Saturday', 'Sunday']:
            app_logger.info(f"Filter: Skipping trade as today is {day_name}")
            return False
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
                ivs = [float(t.get('mark_iv', 0)) for t in tickers if t.get('mark_iv')]
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

        # Calculate 7-day average
        past_7_days_ivs = []
        for i in range(1, 8):
            d_str = (get_ist_now() - datetime.timedelta(days=i)).strftime('%Y-%m-%d')
            if d_str in history:
                past_7_days_ivs.append(history[d_str])

        seven_day_avg = 0
        if past_7_days_ivs:
            seven_day_avg = sum(past_7_days_ivs) / len(past_7_days_ivs)
        else:
            # If no history, assume 7-day avg is slightly below current to allow trading,
            # or just return current_avg_iv as the baseline.
            seven_day_avg = current_avg_iv * 0.99 

        return current_avg_iv, seven_day_avg

    def check_iv_filter(self):
        """Check if current IV > 7-day average IV."""
        current_iv, avg_7d_iv = self._update_and_get_iv()
        
        if current_iv == 0:
            app_logger.warning("Filter: Could not determine IV. Skipping trade to be safe.")
            return False

        if current_iv > avg_7d_iv:
            app_logger.info(f"Filter: IV check passed. Current: {current_iv:.4f} > 7d Avg: {avg_7d_iv:.4f}")
            return True
        else:
            app_logger.info(f"Filter: IV check failed. Current: {current_iv:.4f} <= 7d Avg: {avg_7d_iv:.4f}")
            return False

    def check_news_filter(self):
        """Skip major news days using live API."""
        try:
            # ForexFactory or similar open API for calendar
            # Using a public free economic calendar endpoint if available, 
            # otherwise fallback to checking a predefined critical list if API is unreachable.
            
            # Since ForexFactory blocks automated simple requests often, we use an open aggregator
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                events = response.json()
                today_str = get_ist_now().strftime('%Y-%m-%d')
                
                for event in events:
                    # Check if event is High impact, for USD (which drives BTC), and occurs today
                    if event.get('impact') == 'High' and event.get('country') == 'USD':
                        event_date = event.get('date', '')[:10]
                        if event_date == today_str:
                            app_logger.info(f"Filter: Skipping trade due to HIGH impact USD news today: {event.get('title')}")
                            return False
                
                app_logger.info("Filter: News check passed. No High impact USD news today.")
                return True
            else:
                app_logger.warning(f"Filter: News API returned {response.status_code}. Proceeding with caution.")
                return True
        except Exception as e:
            app_logger.warning(f"Filter: News check error, proceeding anyway. {e}")
            return True

    def all_passed(self):
        today = get_ist_now()
        if today.weekday() >= 4:  # Friday=4, Sat=5, Sun=6
            app_logger.info("Filter: Skipping trade - Today is Friday/Weekend")
            return False
            
        return (self.check_day_filter() and 
                self.check_iv_filter() and 
                self.check_news_filter())

    def get_filter_status(self):
        """Returns (passed: bool, reason: str) prioritized by Weekend > News > IV"""
        if not self.check_day_filter():
            return False, "Weekend (Fri/Sat/Sun)"
        if not self.check_news_filter():
            return False, "High Impact USD News"
        if not self.check_iv_filter():
            return False, "Low IV (Current IV <= 7d Avg)"
        return True, "All Filters Passed"

    def get_schedule(self, days=7):
        """Calculates skip status for the next 'days' days."""
        schedule = []
        today = get_ist_now().date()
        
        # Pre-fetch news for the week
        news_events = []
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                news_events = response.json()
        except Exception:
            pass

        for i in range(days):
            target_date = today + datetime.timedelta(days=i)
            target_date_str = target_date.strftime('%Y-%m-%d')
            day_name = target_date.strftime('%A')
            
            skip = False
            reason = None
            skip_type = 'normal' # normal or severe (for styling)
            
            # 1. Weekend Check
            if day_name in ['Friday', 'Saturday', 'Sunday']:
                skip = True
                reason = f"Weekend ({day_name})"
                skip_type = 'severe'
            
            # 2. News Check
            if not skip:
                for event in news_events:
                    if event.get('impact') == 'High' and event.get('country') == 'USD':
                        event_date = event.get('date', '')[:10]
                        if event_date == target_date_str:
                            skip = True
                            reason = f"High Impact News"
                            skip_type = 'severe'
                            break
            
            schedule.append({
                'date': target_date.strftime('%b %d'),
                'day': day_name,
                'skip': skip,
                'reason': reason,
                'skip_type': skip_type
            })
            
        return schedule

    def get_market_regime(self):
        """Calculates 14-period ADX on 4H BTC perp candles. Returns (regime, adx_value)."""
        import pandas as pd
        import pandas_ta as ta
        
        try:
            # Fetch 4H candles for BTCUSD perp for the last few days (enough for 14-period ADX calculation)
            # 14 periods of 4H = 56 hours. We fetch last 7 days to be safe.
            end_time = int(time.time())
            start_time = end_time - (7 * 24 * 3600)
            
            res = self.api_client.get_candles("BTCUSD", "4h", start=start_time, end=end_time)
            
            if res and res.get('success'):
                candles = res.get('result', [])
                if not candles or len(candles) < 15:
                    app_logger.warning("Filter: Not enough candle data to calculate ADX.")
                    return "Unknown", 0.0
                    
                df = pd.DataFrame(candles)
                # Ensure correct types
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['close'] = df['close'].astype(float)
                
                # Sort chronologically just in case
                if 'time' in df.columns:
                    df = df.sort_values(by='time')
                    
                # Calculate ADX (default is 14 period)
                adx_df = df.ta.adx(length=14)
                if adx_df is not None and not adx_df.empty:
                    # Get the most recent ADX value (typically column name is 'ADX_14')
                    adx_col = [c for c in adx_df.columns if 'ADX' in c][0]
                    current_adx = float(adx_df.iloc[-1][adx_col])
                    
                    regime = "Trending" if current_adx > 25 else "Ranging"
                    app_logger.info(f"Filter: Market Regime is {regime} (ADX: {current_adx:.2f})")
                    return regime, current_adx
                else:
                    app_logger.warning("Filter: Failed to compute ADX.")
                    return "Unknown", 0.0
            else:
                app_logger.warning("Filter: Failed to fetch candles for ADX.")
                return "Unknown", 0.0
        except Exception as e:
            app_logger.error(f"Filter: Error calculating ADX: {e}")
            return "Unknown", 0.0
