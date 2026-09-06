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
        """Helper to fetch and cache news calendar from ForexFactory every 6 hours with disk persistence."""
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_calendar_cache.json')
        current_time = time.time()
        
        # 1. Load from disk cache if memory cache is empty
        if not self.cached_news and os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if isinstance(cache_data, dict):
                        self.cached_news = cache_data.get('events', [])
                        self.last_news_fetch_time = float(cache_data.get('timestamp', 0.0))
                    elif isinstance(cache_data, list):
                        self.cached_news = cache_data
                        self.last_news_fetch_time = os.path.getmtime(cache_file)
            except Exception as e:
                app_logger.warning(f"Filters: Error reading news cache from disk: {e}")

        # If cache is fresh (less than 6 hours old), do not fetch
        if self.cached_news and (current_time - self.last_news_fetch_time < 21600):
            return
            
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json'
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                self.cached_news = response.json()
                self.last_news_fetch_time = current_time
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump({'timestamp': current_time, 'events': self.cached_news}, f, indent=2)
                except Exception as e:
                    app_logger.warning(f"Filters: Failed to write news cache to disk: {e}")
                app_logger.info("Filters: ForexFactory calendar cache updated.")
            elif response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '300')
                app_logger.warning(f"Filters: ForexFactory rate-limited (HTTP 429). Retrying after {retry_after}s. Using cached events.")
                self.last_news_fetch_time = current_time - 21600 + (int(retry_after) if retry_after.isdigit() else 300)
            else:
                app_logger.warning(f"Filters: ForexFactory calendar fetch returned status {response.status_code}")
        except Exception as e:
            app_logger.warning(f"Filters: Failed to fetch ForexFactory calendar: {e}")

    def check_news_filter(self):
        """Skip major economic news / calendar alert days using cached ForexFactory calendar."""
        self._update_news_cache()
        if not self.cached_news:
            return True, "No news data"
            
        today_str = get_ist_now().strftime('%Y-%m-%d')
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        keywords = ['cpi', 'fomc', 'nfp', 'non-farm', 'fed', 'powell', 'etf', 'ism', 'pmi', 'unemployment', 'gdp', 'pce', 'rate decision']
        
        for event in self.cached_news:
            country = event.get('country', '')
            impact = event.get('impact', '')
            if country in ['USD', 'BTC']:
                raw_date = event.get('date', '')
                if not raw_date:
                    continue
                try:
                    dt = datetime.datetime.fromisoformat(raw_date).astimezone(ist_tz)
                    event_date = dt.strftime('%Y-%m-%d')
                    event_time_str = dt.strftime('%H:%M')
                except Exception:
                    dt = None
                    event_date = raw_date[:10]
                    event_time_str = ""
                
                if event_date == today_str:
                    title = event.get('title', '').strip()
                    title_lower = title.lower()
                    is_high_risk = (impact == 'High') or (impact == 'Medium' and any(k in title_lower for k in keywords))
                    if is_high_risk:
                        # If the event is at or after 17:00 IST (after bot exit), positions close before the event hits
                        if dt and dt.time() >= datetime.time(17, 0):
                            app_logger.info(
                                f"Filter: Event '{title}' scheduled at {event_time_str} IST (after 17:00 IST exit). "
                                f"Allowing daytime trade session as bot exits prior to event."
                            )
                            continue

                        msg = f"Calendar Alert: {title} at {event_time_str} IST ({impact} Impact, {country})"
                        app_logger.warning(f"Filter: Skipping automatic trade due to calendar alert: {msg}")
                        return False, msg

        return True, "Calendar Clean: No high-risk events during trade hours"

    def all_passed(self):
        return (self.check_day_filter() and 
                self.check_dvol_percentile_filter()[0] and 
                self.check_news_filter()[0])

    def get_filter_status(self):
        """Returns (passed: bool, reason: str) prioritized by News > DVOL Percentile"""
        news_ok, news_reason = self.check_news_filter()
        if not news_ok:
            return False, news_reason
        
        dvol_ok, dvol_reason = self.check_dvol_percentile_filter()
        if not dvol_ok:
            return False, f"DVOL Percentile Filter: {dvol_reason}"
            
        return True, "All Filters Passed"

    def get_schedule(self, days=7):
        """Calculates skip status for the next 'days' days using cached news."""
        schedule = []
        today = get_ist_now().date()
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        keywords = ['cpi', 'fomc', 'nfp', 'non-farm', 'fed', 'powell', 'etf', 'ism', 'pmi', 'unemployment', 'gdp', 'pce', 'rate decision']
        
        self._update_news_cache()
        news_events = self.cached_news

        for i in range(days):
            target_date = today + datetime.timedelta(days=i)
            target_date_str = target_date.strftime('%Y-%m-%d')
            day_name = target_date.strftime('%A')
            
            skip = False
            reason = None
            skip_type = 'normal' # normal or severe (for styling)
            
            # News Check for USD & BTC
            if news_events:
                for event in news_events:
                    country = event.get('country', '')
                    impact = event.get('impact', '')
                    if country in ['USD', 'BTC']:
                        raw_date = event.get('date', '')
                        if not raw_date:
                            continue
                        try:
                            dt = datetime.datetime.fromisoformat(raw_date).astimezone(ist_tz)
                            event_date = dt.strftime('%Y-%m-%d')
                            event_time_str = dt.strftime('%H:%M')
                        except Exception:
                            dt = None
                            event_date = raw_date[:10]
                            event_time_str = ""
                        
                        if event_date == target_date_str:
                            title = event.get('title', '').strip()
                            title_lower = title.lower()
                            is_high_risk = (impact == 'High') or (impact == 'Medium' and any(k in title_lower for k in keywords))
                            if is_high_risk:
                                if dt and dt.time() >= datetime.time(17, 0):
                                    reason = f"Evening Event (After 17:00 IST): {title}"
                                    skip = False
                                    skip_type = 'normal'
                                else:
                                    skip = True
                                    reason = f"High Risk: {title} ({event_time_str} IST)"
                                    skip_type = 'severe' if impact == 'High' else 'normal'
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
        """Calculates ADX, Bollinger Bands, and RSI on 15m BTC perp candles.
        Returns (regime, adx_value, adx_history)."""
        now_ts = time.time()
        if now_ts - getattr(self, 'last_regime_fetch_time', 0.0) < 60.0 and getattr(self, 'cached_regime', None) and self.cached_regime[0] != "Unknown":
            return self.cached_regime

        import pandas as pd
        import numpy as np
        import pytz
        from datetime import datetime
        
        try:
            # Fetch 720 candles (15m) from Kraken (Binance/Bybit block Render cloud IPs with 403/451)
            import requests
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get('https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=15', headers=headers, timeout=5)
            
            if res.status_code != 200:
                app_logger.warning(f"Filter: Failed to fetch candles for Market Regime from Kraken. Status code: {res.status_code}")
                return "Unknown", 0.0, []
                
            data = res.json()
            if not data or 'error' in data and data['error'] or 'result' not in data:
                app_logger.warning("Filter: Not enough candle data from Kraken.")
                return "Unknown", 0.0, []
                
            # Kraken returns a dict with the pair name as key (usually 'XXBTZUSD' for XBTUSD)
            pair_key = list(data['result'].keys())[0]
            if pair_key == 'last': pair_key = list(data['result'].keys())[1]
            candles = data['result'][pair_key]
            
            # Kraken format: [time(sec), open, high, low, close, vwap, volume, count]
            df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            df['time']  = pd.to_datetime(df['time'].astype(float), unit='s')
            df = df.sort_values(by='time').reset_index(drop=True)
            
            # --- ADX + DI (Native Pandas to avoid numba/llvmlite build failures) ---
            def calc_adx(high, low, close, length=14):
                tr1 = high - low
                tr2 = (high - close.shift()).abs()
                tr3 = (low - close.shift()).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                
                up = high - high.shift()
                down = low.shift() - low
                
                pos_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
                neg_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
                
                # Smoothed Moving Average (Wilder's)
                atr = tr.ewm(alpha=1/length, adjust=False).mean()
                pos_di = 100 * (pos_dm.ewm(alpha=1/length, adjust=False).mean() / atr)
                neg_di = 100 * (neg_dm.ewm(alpha=1/length, adjust=False).mean() / atr)
                
                dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, 1)
                adx = dx.ewm(alpha=1/length, adjust=False).mean()
                return adx, pos_di, neg_di

            adx, pos_di, neg_di = calc_adx(df['high'], df['low'], df['close'])
            df['ADX'] = adx
            df['+DI'] = pos_di
            df['-DI'] = neg_di
            
            # --- Bollinger Bands ---
            df['BB_mid'] = df['close'].rolling(20).mean()
            df['BB_upper'] = df['BB_mid'] + 2 * df['close'].rolling(20).std()
            df['BB_lower'] = df['BB_mid'] - 2 * df['close'].rolling(20).std()
            df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_mid']
            
            # --- RSI ---
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = -delta.where(delta < 0, 0).rolling(14).mean()
            df['RSI'] = 100 - (100 / (1 + gain / loss))
            
            df = df.dropna()
            if df.empty:
                return "Unknown", 0.0, []
                
            # Filter for IST Session (09:00 - 17:00)
            ist_tz = pytz.timezone('Asia/Kolkata')
            df['ist_time'] = df['time'].dt.tz_localize('UTC').dt.tz_convert(ist_tz).dt.strftime('%H:%M')
            session_df = df[(df['ist_time'] >= '09:00') & (df['ist_time'] <= '17:00')]
            
            if session_df.empty:
                # Outside session hours, evaluate on latest overall candle for fallback
                session_df = df
                
            latest = session_df.iloc[-1]
            prev = session_df.iloc[-2] if len(session_df) > 1 else latest
            
            adx_val = latest['ADX']
            adx_history = session_df['ADX'].tail(6).tolist()
            
            # Default backward-compatible regime
            regime = "Transition"
            detailed_signal = "WAITING"
            
            # ARES Multi-Indicator Signal Logic
            if latest['ADX'] < 23 and latest['BB_width'] < 0.025 and 40 <= latest['RSI'] <= 60:
                detailed_signal = "SIDEWAYS"
                regime = "Sideways"
                
            # Uptrend Start
            elif (prev['ADX'] <= 25 and latest['ADX'] > 25) and latest['+DI'] > latest['-DI'] and latest['RSI'] > 52 and latest['close'] > latest['BB_mid']:
                detailed_signal = "UPTREND START"
                regime = "Trending"
                
            # Downtrend Start
            elif (prev['ADX'] <= 25 and latest['ADX'] > 25) and latest['-DI'] > latest['+DI'] and latest['RSI'] < 48 and latest['close'] < latest['BB_mid']:
                detailed_signal = "DOWNTREND START"
                regime = "Trending"
                
            # Trend Strengthening
            elif latest['ADX'] > 28 and latest['ADX'] > prev['ADX']:
                dir_str = "UP" if latest['+DI'] > latest['-DI'] else "DOWN"
                detailed_signal = f"STRENGTHENING {dir_str}"
                regime = "Trending"
                
            # Trend Weakening
            elif latest['ADX'] < 25 and prev['ADX'] >= 25:
                detailed_signal = "WEAKENING"
                regime = "Sideways"
                
            elif latest['ADX'] > 25:
                 regime = "Trending"
                 detailed_signal = "TRENDING"
            else:
                 regime = "Sideways"
                 detailed_signal = "SIDEWAYS"
            
            self.last_detailed_signal = detailed_signal
            app_logger.info(f"Filter: Market is {detailed_signal} / {regime} (ADX: {adx_val:.2f}, RSI: {latest['RSI']:.1f})")
            
            result = (regime, round(adx_val, 2), [round(float(x), 2) for x in adx_history])
            self.cached_regime = result
            self.last_regime_fetch_time = time.time()
            return result
            
        except Exception as e:
            app_logger.error(f"Filter: Error calculating Regime: {e}")
            if getattr(self, 'cached_regime', None) and self.cached_regime[0] != "Unknown":
                return self.cached_regime
            return "Unknown", 0.0, []

    def get_price_rejection_signal(self):
        """Analyzes the latest closed 15m candle for extreme V-shape wick rejection piercing Bollinger Bands."""
        import pandas as pd
        import time
        import requests
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get('https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=15', headers=headers, timeout=5)
            if res.status_code != 200:
                return "SAFE"
                
            data = res.json()
            if not data or 'error' in data and data['error'] or 'result' not in data:
                return "SAFE"
                
            pair_key = list(data['result'].keys())[0]
            if pair_key == 'last': pair_key = list(data['result'].keys())[1]
            candles = data['result'][pair_key][-30:] # Take last 30
            
            df = pd.DataFrame(candles, columns=['time', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
                
            # Calculate 20-period Bollinger Bands
            df['BB_mid'] = df['close'].rolling(20).mean()
            df['BB_std'] = df['close'].rolling(20).std()
            df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
            df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
            
            df = df.dropna()
            if df.empty: return "SAFE"
            
            # Look at the latest completely formed candle (or the currently forming one if we want instant reaction)
            # Let's look at the current forming candle since we want early detection.
            latest = df.iloc[-1]
            
            c_open = latest['open']
            c_close = latest['close']
            c_high = latest['high']
            c_low = latest['low']
            bb_lower = latest['BB_lower']
            bb_upper = latest['BB_upper']
            
            candle_range = c_high - c_low
            if candle_range == 0: return "SAFE"
            
            body_top = max(c_open, c_close)
            body_bottom = min(c_open, c_close)
            
            lower_wick = body_bottom - c_low
            upper_wick = c_high - body_top
            
            # BULLISH REJECTION: Dump that pierced lower BB but formed a massive lower wick (Hammer)
            # Wick is > 60% of total candle, AND low is below lower BB
            if c_low < bb_lower and (lower_wick / candle_range) > 0.55:
                return "BULLISH_REJECTION"
                
            # BEARISH REJECTION: Pump that pierced upper BB but formed massive upper wick (Shooting Star)
            if c_high > bb_upper and (upper_wick / candle_range) > 0.55:
                return "BEARISH_REJECTION"
                
            return "SAFE"
            
        except Exception as e:
            app_logger.error(f"Filter: Rejection Error: {e}")
            return "SAFE"

    def get_btc_atr(self, period=14, resolution="15m"):
        """Calculates the Average True Range (ATR) of BTCUSDT over the specified resolution."""
        try:
            import time
            end_time = int(time.time())
            # Fetch period+1 candles to get prev_close for TR calculation
            seconds_per_candle = int(resolution.replace('m','')) * 60 if 'm' in resolution else 3600
            start_time = end_time - ((period + 2) * seconds_per_candle)
            
            res = requests.get(f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT&resolution={resolution}&start={start_time}&end={end_time}', timeout=10)
            if res.status_code == 200:
                data = res.json()
                candles = data.get('result', [])
                if len(candles) < period:
                    return 100.0 # fallback
                
                # Sort chronologically
                candles.sort(key=lambda x: x['time'])
                
                true_ranges = []
                for i in range(1, len(candles)):
                    high = float(candles[i]['high'])
                    low = float(candles[i]['low'])
                    prev_close = float(candles[i-1]['close'])
                    
                    tr = max(
                        high - low,
                        abs(high - prev_close),
                        abs(low - prev_close)
                    )
                    true_ranges.append(tr)
                
                recent_trs = true_ranges[-period:]
                atr = sum(recent_trs) / len(recent_trs)
                app_logger.info(f"Filter: Calculated {period}-period {resolution} BTC ATR: ${atr:.2f}")
                return atr
        except Exception as e:
            app_logger.error(f"Filter: Error calculating ATR: {e}")
        return 100.0 # Safe fallback

    def get_pivot_points(self):
        """
        Returns two types of structural levels:

        1. SWING_HIGH / SWING_LOW (strongest signals — from 15m candles):
           These represent the pre-trade consolidation range (the 'green box'
           you see on the chart before the current move started).
           - Fetches last 52 x 15m candles.
           - Skips the last 4 candles (current forming move).
           - SWING_HIGH = max(high) of candles [-52:-4] = 12h pre-move high
           - SWING_LOW  = min(low)  of candles [-52:-4] = 12h pre-move low
           A 15m candle CLOSE BELOW SWING_LOW = confirmed downtrend structural break.
           A 15m candle CLOSE ABOVE SWING_HIGH = confirmed uptrend structural break.

        2. P, R1, R2, R3, S1, S2, S3 (standard pivot math from previous daily candle):
           Classic pivot levels traders watch on intraday charts.
        """
        import time
        import requests
        try:
            end_time = int(time.time())

            # ── SWING LEVELS: 15m candles (recent pre-trade consolidation) ──
            swing_start = end_time - (52 * 15 * 60)   # 52 candles back
            res_15m = requests.get(
                f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT'
                f'&resolution=15m&start={swing_start}&end={end_time}',
                timeout=10
            )
            swing_high = None
            swing_low  = None
            if res_15m.status_code == 200:
                data_15m = res_15m.json()
                if data_15m.get('success'):
                    candles_15m = sorted(data_15m.get('result', []), key=lambda x: x['time'])
                    # Skip last 4 candles (current move); use the 48 before that
                    consolidation = candles_15m[:-4] if len(candles_15m) > 4 else candles_15m
                    if consolidation:
                        swing_high = max(float(c['high']) for c in consolidation)
                        swing_low  = min(float(c['low'])  for c in consolidation)
                        app_logger.debug(
                            f"Pivot: SWING_HIGH=${swing_high:.0f}, SWING_LOW=${swing_low:.0f} "
                            f"(from {len(consolidation)} x 15m pre-move candles)"
                        )

            # ── DAILY PIVOT MATH: previous day's candle ──
            daily_start = end_time - (3 * 86400)
            res_1d = requests.get(
                f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT'
                f'&resolution=1d&start={daily_start}&end={end_time}',
                timeout=10
            )
            if res_1d.status_code == 200:
                data_1d = res_1d.json()
                if data_1d.get('success'):
                    candles_1d = sorted(data_1d.get('result', []), key=lambda x: x['time'])
                    if len(candles_1d) >= 2:
                        prev_day = candles_1d[-2]
                        H = float(prev_day['high'])
                        L = float(prev_day['low'])
                        C = float(prev_day['close'])
                        P  = (H + L + C) / 3
                        R1 = P + 0.382 * (H - L)
                        R2 = P + 0.618 * (H - L)
                        R3 = P + 1.000 * (H - L)
                        S1 = P - 0.382 * (H - L)
                        S2 = P - 0.618 * (H - L)
                        S3 = P - 1.000 * (H - L)
                        result = {
                            # ── Structural swing levels (15m, strongest signals) ──
                            'SWING_HIGH': swing_high,  # Pre-move high — close above = uptrend break
                            'SWING_LOW':  swing_low,   # Pre-move low  — close below = downtrend break
                            # ── Classic daily pivot math ──
                            'P':  P,
                            'R1': R1, 'R2': R2, 'R3': R3,
                            'S1': S1, 'S2': S2, 'S3': S3,
                        }
                        return result

        except Exception as e:
            app_logger.error(f"Filter: Error calculating Pivot Points: {e}")
        return None



    def get_supertrend(self, period=10, multiplier=3):
        """Calculates 5m Supertrend."""
        import time
        import requests
        import pandas as pd
        import numpy as np
        try:
            end_time = int(time.time())
            start_time = end_time - (100 * 5 * 60)
            res = requests.get(f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT&resolution=5m&start={start_time}&end={end_time}', timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('success'):
                    candles = data.get('result', [])
                    if len(candles) < period * 2:
                        return None
                    
                    df = pd.DataFrame(candles)
                    df['open'] = df['open'].astype(float)
                    df['high'] = df['high'].astype(float)
                    df['low'] = df['low'].astype(float)
                    df['close'] = df['close'].astype(float)
                    df = df.sort_values(by='time').reset_index(drop=True)
                    
                    df['tr0'] = abs(df['high'] - df['low'])
                    df['tr1'] = abs(df['high'] - df['close'].shift())
                    df['tr2'] = abs(df['low'] - df['close'].shift())
                    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
                    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
                    
                    hl2 = (df['high'] + df['low']) / 2
                    df['basic_ub'] = hl2 + (multiplier * df['atr'])
                    df['basic_lb'] = hl2 - (multiplier * df['atr'])
                    
                    df['final_ub'] = 0.0
                    df['final_lb'] = 0.0
                    for i in range(period, len(df)):
                        if df['basic_ub'].iloc[i] < df['final_ub'].iloc[i-1] or df['close'].iloc[i-1] > df['final_ub'].iloc[i-1]:
                            df.loc[df.index[i], 'final_ub'] = df['basic_ub'].iloc[i]
                        else:
                            df.loc[df.index[i], 'final_ub'] = df['final_ub'].iloc[i-1]
                        
                        if df['basic_lb'].iloc[i] > df['final_lb'].iloc[i-1] or df['close'].iloc[i-1] < df['final_lb'].iloc[i-1]:
                            df.loc[df.index[i], 'final_lb'] = df['basic_lb'].iloc[i]
                        else:
                            df.loc[df.index[i], 'final_lb'] = df['final_lb'].iloc[i-1]

                    df['supertrend'] = 0.0
                    for i in range(period, len(df)):
                        if df['supertrend'].iloc[i-1] == df['final_ub'].iloc[i-1] and df['close'].iloc[i] < df['final_ub'].iloc[i]:
                            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i]
                        elif df['supertrend'].iloc[i-1] == df['final_ub'].iloc[i-1] and df['close'].iloc[i] > df['final_ub'].iloc[i]:
                            df.loc[df.index[i], 'supertrend'] = df['final_lb'].iloc[i]
                        elif df['supertrend'].iloc[i-1] == df['final_lb'].iloc[i-1] and df['close'].iloc[i] > df['final_lb'].iloc[i]:
                            df.loc[df.index[i], 'supertrend'] = df['final_lb'].iloc[i]
                        elif df['supertrend'].iloc[i-1] == df['final_lb'].iloc[i-1] and df['close'].iloc[i] < df['final_lb'].iloc[i]:
                            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i]
                        else:
                            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i] if df['close'].iloc[i] < df['final_ub'].iloc[i] else df['final_lb'].iloc[i]

                    df['trend'] = np.where(df['close'] > df['supertrend'], 'BUY', 'SELL')
                    
                    if len(df) >= 2:
                        latest_closed = df.iloc[-2]
                    else:
                        latest_closed = df.iloc[-1]
                    
                    return {
                        'trend': latest_closed['trend'], 
                        'value': float(latest_closed['supertrend']), 
                        'close': float(latest_closed['close']),
                        'open': float(latest_closed['open']),
                        'high': float(latest_closed['high']),
                        'low': float(latest_closed['low'])
                    }
        except Exception as e:
            app_logger.error(f"Filter: Error calculating Supertrend: {e}")
        return None
