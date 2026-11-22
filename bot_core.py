import os
import time
import datetime
import threading
import hmac
import hashlib
import json
import schedule
import requests as _requests
import logging

# Configure logging for 24/7 monitor
logging.basicConfig(
    filename='bot_system.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

DELTA_INDIA_BASE = "https://api.india.delta.exchange"
ENTRY_TIME_UTC = "02:30"   # 08:00 AM IST


# ─── DELTA INDIA DIRECT CLIENT ────────────────────────────────────────────────
class DeltaIndiaClient:
    """Direct HTTP client for Delta Exchange India — HMAC-SHA256 signed."""

    def __init__(self, api_key="", api_secret=""):
        self.api_key    = api_key
        self.api_secret = api_secret
        self.base       = DELTA_INDIA_BASE
        self.time_offset = 0
        self.session    = _requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        if api_key and api_secret:
            self.sync_time()

    def sync_time(self):
        """Fetch server time and calculate offset to prevent 'expired_signature'."""
        try:
            # We use tickers as a lightweight public endpoint to get server time if needed, 
            # but usually Delta's response headers or a specific time endpoint works.
            # Delta India doesn't always have a clear /time endpoint in v2, 
            # but we can infer it from the 'Date' header of any request.
            r = _requests.get(f"{self.base}/v2/tickers", timeout=10)
            server_date = r.headers.get('Date')
            if server_date:
                import email.utils
                server_ts = email.utils.mktime_tz(email.utils.parsedate_tz(server_date))
                self.time_offset = int(server_ts - time.time())
                print(f"[TIME] Synced. Offset: {self.time_offset}s")
        except Exception as e:
            print(f"[TIME] Sync failed: {e}")

    def _sign(self, method, path_with_qs, body=""):
        """Delta India signature: method + timestamp(s) + path_with_querystring + body"""
        ts  = str(int(time.time() + self.time_offset))
        msg = method + ts + path_with_qs + body
        sig = hmac.new(
            self.api_secret.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()
        return ts, sig

    def _headers(self, method, path_with_qs, body=""):
        h = {
            'Content-Type': 'application/json',
            'Accept':       'application/json',
            'User-Agent':   'DeltaBotv2/1.0',
        }
        if self.api_key and self.api_secret:
            ts, sig = self._sign(method, path_with_qs, body)
            h.update({'api-key': self.api_key, 'timestamp': ts, 'signature': sig})
        return h

    def get(self, path, params=None):
        if params:
            qs = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
            path_with_qs = f"{path}?{qs}"
        else:
            path_with_qs = path
        url = self.base + path_with_qs
        try:
            r = self.session.get(url, headers=self._headers('GET', path_with_qs), timeout=15)
            if r.status_code == 403:
                print(f"[API] 403 Forbidden on {path} - WAF block?")
            if r.status_code == 429:
                print(f"[API] 429 Rate Limited on {path}")
            return r.json()
        except Exception as e:
            return {'success': False, 'error': {'code': 'request_error', 'message': str(e)}}

    def post(self, path, data=None):
        body = json.dumps(data or {}, separators=(',', ':'))
        url  = self.base + path
        try:
            r = _requests.post(url, data=body, headers=self._headers('POST', path, body), timeout=15)
            return r.json()
        except Exception as e:
            return {'success': False, 'error': {'code': 'request_error', 'message': str(e)}}

    # ── Public helpers ────────────────────────────────────────────────────────
    def test_connection(self):
        r = self.get('/v2/profile')
        if r.get('success'):
            return True, r.get('result', {})
        err  = r.get('error', {})
        code = err.get('code', 'unknown')
        ctx  = err.get('context', {})
        if code == 'ip_not_whitelisted_for_api_key':
            ip = ctx.get('client_ip', 'unknown')
            return False, f"IP not whitelisted: {ip}. Add this IP in Delta API key settings."
        if code == 'invalid_api_key':
            return False, "Invalid API key or secret."
        return False, f"Connection error: {code}"

    def get_balance(self):
        r = self.get('/v2/wallet/balances')
        if not r.get('success'):
            return 0.0
        for b in r.get('result', []):
            if b.get('asset_symbol') == 'USDT':
                return float(b.get('available_balance', 0))
        return 0.0

    def get_btc_price(self):
        """Try Delta India first, then Binance/CoinGecko, finally fallback to History API."""
        # 1. Delta India Tickers
        try:
            r = self.get('/v2/tickers', {'contract_types': 'perpetual_futures', 'underlying_asset_symbol': 'BTC'})
            if r.get('success') and r.get('result'):
                for t in r['result']:
                    if t.get('symbol') == 'BTCUSD':
                        price = float(t.get('mark_price') or t.get('close') or 0)
                        if price > 0: return price
        except: pass

        # 2. Delta India History (Request 4h to be safe)
        try:
            hist = self.get_history('BTCUSD', '1h', 4)
            if hist:
                price = float(hist[-1].get('close', 0))
                if price > 0: 
                    print(f"[PRICE] Using History API Fallback: {price}")
                    return price
        except: pass

        # 3. Binance Public API
        try:
            b = _requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', timeout=5).json()
            if 'price' in b: 
                price = float(b['price'])
                print(f"[PRICE] Using Binance Fallback: {price}")
                return price
        except: pass

        # 4. CoinGecko Fallback
        try:
            cg = _requests.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', timeout=5).json()
            if 'bitcoin' in cg:
                price = float(cg['bitcoin']['usd'])
                print(f"[PRICE] Using CoinGecko Fallback: {price}")
                return price
        except: pass
        return 0.0

    def get_option_chain(self):
        # Use direct requests for public data to avoid any header/signature issues
        url = f"{DELTA_INDIA_BASE}/v2/tickers"
        params = {
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        }
        try:
            r = _requests.get(url, params=params, timeout=15).json()
            if r.get('success'):
                res = r.get('result', [])
                # Robust filter: check underlying symbol OR 'BTC' in symbol string
                filtered = [t for t in res if 
                            t.get('underlying_asset_symbol') in ['BTC', 'BTCUSD'] or 
                            'BTC' in t.get('symbol', '').split('-')]
                
                if not filtered and res:
                    filtered = [t for t in res if 'BTC' in t.get('symbol', '')]
                
                # Normalize results
                for t in filtered:
                    if 'contract_type' in t:
                        if 'call' in t['contract_type']: t['option_type'] = 'call'
                        elif 'put' in t['contract_type']: t['option_type'] = 'put'
                    if 'mark_vol' in t and t.get('mark_iv') is None:
                        t['mark_iv'] = t['mark_vol']
                
                print(f"[CHAIN] Fetched {len(res)} tickers, filtered to {len(filtered)} BTC options")
                return filtered
        except Exception as e:
            print(f"[CHAIN] Fetch failed: {e}")
        
        # Emergency Fallback
        try:
            r2 = _requests.get(f"{DELTA_INDIA_BASE}/v2/products", params={'contract_types': 'call_options,put_options'}, timeout=15).json()
            if r2.get('success'):
                res2 = r2.get('result', [])
                filtered2 = [t for t in res2 if 'BTC' in t.get('symbol', '')]
                for t in filtered2:
                    if 'contract_type' in t:
                        if 'call' in t['contract_type']: t['option_type'] = 'call'
                        elif 'put' in t['contract_type']: t['option_type'] = 'put'
                return filtered2
        except: pass
        
        return []

    def set_leverage(self, product_id, leverage):
        return self.post('/v2/orders/leverage', {'product_id': product_id, 'leverage': str(leverage)})

    def set_margin_mode(self, product_id, mode='isolated'):
        return self.post('/v2/orders/margin_mode', {'product_id': product_id, 'margin_mode': mode})

    def place_order(self, product_id, side, size, order_type='market_order', limit_price=None):
        data = {'product_id': product_id, 'side': side, 'size': size, 'order_type': order_type}
        if limit_price:
            data['limit_price'] = str(limit_price)
        return self.post('/v2/orders', data)

    def get_history(self, symbol='BTCUSD', resolution='1h', hours=24):
# ... existing get_history code ...

        """Fetch OHLCV candles — symbol must NOT include 'MARK:' prefix."""
        symbol = symbol.replace('MARK:', '')  # sanitize
        now   = int(time.time())
        start = now - (hours * 3600)
        r = self.get('/v2/history/candles', {
            'symbol': symbol, 'resolution': resolution,
            'start': start, 'end': now
        })
        return r.get('result', []) if r.get('success') else []

    def get_ticker_stats(self, symbol='BTCUSD'):
        r = self.get('/v2/tickers', {'symbol': symbol})
        if r.get('success') and r.get('result'):
            return r['result'][0]
        return {}


# ─── BOT ──────────────────────────────────────────────────────────────────────
class DeltaOptionsBot:
    def __init__(self):
        # Persistent threads/state
        self.market_thread  = None
        self.current_btc_price  = 0.0
        self.last_stats_update  = 0
        self.cached_stats       = {}
        self.last_chain_update  = 0
        self.last_iv_pcr        = {'avg_iv': 0.0, 'pcr': 0.0}
        
        # Persistence files
        self.creds_file = "credentials.json"
        self.state_file = "bot_state.json"
        self.reconnect_delay = 5 # Initial retry delay in seconds
        self.is_connected = False
        self.last_heartbeat = 0

        # Per-mode state
        self.state = {
            'PAPER': {
                'running': False,
                'logs': [], 'balance': 10000.0,
                'starting_balance': 10000.0,
                'positions': {'call': None, 'put': None},
                'reentry_watch': {'call': None, 'put': None},
                'config': {}
            },
            'LIVE': {
                'running': False,
                'logs': [], 'balance': 0.0,
                'starting_balance': 0.0,
                'positions': {'call': None, 'put': None},
                'reentry_watch': {'call': None, 'put': None},
                'config': {},
                'client': None
            }
        }

        self.india_client = DeltaIndiaClient() # Public client for stats
        try:
            init_btc = self.india_client.get_btc_price()
            if init_btc > 0:
                self.current_btc_price = init_btc
        except Exception:
            pass
        
        # Add SYSTEM log mode
        self.state['SYSTEM'] = {'logs': []}
        
        # Load saved data
        self._load_creds()
        self._load_state()
        
        # Start background threads
        threading.Thread(target=self._market_data_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        threading.Thread(target=self._connection_monitor_loop, daemon=True).start()

    @property
    def running(self):
        return self.state['PAPER']['running'] or self.state['LIVE']['running']

    @property
    def active_mode(self):
        if self.state['LIVE']['running']: return 'LIVE'
        if self.state['PAPER']['running']: return 'PAPER'
        return None

    # ── Logging ───────────────────────────────────────────────────────────────
    def log(self, mode, message, mtype="info"):
        ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        ts  = ist.strftime('%H:%M:%S')
        entry = {'time': ts, 'msg': message, 'type': mtype}
        try:
            print(f"[{mode}][{ts} IST] {message}")
        except UnicodeEncodeError:
            print(f"[{mode}][{ts} IST] {message.encode('ascii','replace').decode()}")
        
        # Ensure mode exists in state
        if mode not in self.state:
            # Fallback for SYSTEM or other tags
            target = 'PAPER' if mode != 'LIVE' else 'LIVE'
            logs = self.state[target]['logs']
        else:
            logs = self.state[mode]['logs']
            
        logs.append(entry)
        if len(logs) > 500: logs.pop(0)

    def test_live_connection(self, key, secret):
        """Used by UI to verify keys before starting."""
        try:
            print(f"[START] Testing live connection for key ending in ...{key[-4:] if key else 'None'}")
            client = DeltaIndiaClient(key, secret)
            # Short timeout for testing
            r = client.get('/v2/wallet/balances')
            if r.get('success'):
                print("[START] Connection successful.")
                return True, "Connected successfully."
            else:
                err = r.get('error', {}).get('message', 'Unknown API Error')
                print(f"[START] Connection failed: {err}")
                return False, f"API Error: {err}"
        except Exception as e:
            print(f"[START] Exception during test: {e}")
            return False, str(e)

    def start(self, config):
        mode = config.get('mode', 'PAPER').upper()
        print(f"[START] Request received for {mode} mode.")
        
        # Save config
        s = self.state[mode]
        s['config'] = {
            'target_premium': float(config.get('target_premium', 100)),
            'allocation_pct': float(config.get('allocation_pct', 50)) / 100.0,
            'call_sl_mult':   1.0 + float(config.get('call_stop_loss', 100)) / 100.0,
            'call_sl_on':     bool(config.get('call_stop_loss_on', True)),
            'call_tp_mult':   1.0 - float(config.get('call_take_profit', 95)) / 100.0,
            'call_tp_on':     bool(config.get('call_take_profit_on', True)),
            'put_sl_mult':    1.0 + float(config.get('put_stop_loss', 100)) / 100.0,
            'put_sl_on':      bool(config.get('put_stop_loss_on', True)),
            'put_tp_mult':    1.0 - float(config.get('put_take_profit', 95)) / 100.0,
            'put_tp_on':      bool(config.get('put_take_profit_on', True)),
        }
        self._save_state()

        if mode == 'LIVE':
            env_key = config.get('api_key') or os.environ.get('DELTA_API_KEY')
            env_sec = config.get('api_secret') or os.environ.get('DELTA_API_SECRET')
            
            if not env_key or not env_sec:
                print("[START] Missing API credentials.")
                return False, "API Key/Secret required for LIVE mode."
            
            print("[START] Verifying credentials...")
            self.state['LIVE']['client'] = DeltaIndiaClient(env_key, env_sec)
            ok, msg = self.test_live_connection(env_key, env_sec)
            if not ok: 
                print(f"[START] LIVE Verification failed: {msg}")
                return False, msg
            self.log('LIVE', "✅ LIVE ENGINE STARTED.", "success")
        else:
            self.log('PAPER', "✅ PAPER ENGINE STARTED.", "success")

        s['running'] = True
        self.active_mode = mode
        self.last_stats_update = 0 # Force immediate update
        return True, f"{mode} engine started successfully."

    def get_logs(self, mode):
        if mode == 'CHAIN': return self.state['SYSTEM']['logs'] # Reuse system logs for chain tab if needed
        return self.state.get(mode, self.state['PAPER'])['logs']

    # ── Persistence ───────────────────────────────────────────────────────────
    def _load_creds(self):
        # 1. Check for Environment Variables (Render/Production)
        env_key = os.environ.get('DELTA_API_KEY')
        env_sec = os.environ.get('DELTA_API_SECRET')
        if env_key and env_sec:
            self.state['LIVE']['client'] = DeltaIndiaClient(env_key, env_sec)
            self.log('SYSTEM', "🔑 Credentials loaded from environment variables.")
            return

        # 2. Check for local file (Development)
        if os.path.exists(self.creds_file):
            try:
                with open(self.creds_file, 'r') as f:
                    creds = json.load(f)
                    if creds.get('api_key') and creds.get('api_secret'):
                        self.state['LIVE']['client'] = DeltaIndiaClient(creds['api_key'], creds['api_secret'])
                        self.log('SYSTEM', "🔑 Credentials loaded from storage.")
            except Exception as e:
                self.log('SYSTEM', f"⚠️ Failed to load credentials: {e}", "error")

    def _save_creds(self, api_key, api_secret):
        try:
            with open(self.creds_file, 'w') as f:
                json.dump({'api_key': api_key, 'api_secret': api_secret}, f)
        except Exception as e:
            self.log('SYSTEM', f"⚠️ Failed to save credentials: {e}", "error")

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    for mode in ['PAPER', 'LIVE']:
                        if mode in data:
                            self.state[mode]['running'] = data[mode].get('running', False)
                            self.state[mode]['config']  = data[mode].get('config', {})
                            self.state[mode]['positions'] = data[mode].get('positions', {'call': None, 'put': None})
                            self.state[mode]['reentry_watch'] = data[mode].get('reentry_watch', {'call': None, 'put': None})
                            self.state[mode]['balance'] = data[mode].get('balance', 10000.0)
                    self.log('SYSTEM', "💾 Previous bot state restored.")
            except Exception as e:
                self.log('SYSTEM', f"⚠️ Failed to load state: {e}", "error")

    def _save_state(self):
        try:
            data = {}
            for mode in ['PAPER', 'LIVE']:
                data[mode] = {
                    'running':   self.state[mode]['running'],
                    'config':    self.state[mode]['config'],
                    'positions': self.state[mode]['positions'],
                    'balance':   self.state[mode]['balance']
                }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=4)
                
            import db_manager
            db_manager.trigger_cloud_sync()
        except Exception as e:
            logging.error(f"Failed to save state: {e}")

    # ── State ─────────────────────────────────────────────────────────────────
    def get_state(self, mode):
        if mode not in self.state:
            mode = 'PAPER'
        s        = self.state[mode]
        pos      = s['positions']
        total_pnl = (pos['call'] or {}).get('pnl', 0.0) + (pos['put'] or {}).get('pnl', 0.0)

        ist      = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        next_8am = ist.replace(hour=8, minute=0, second=0, microsecond=0)
        if ist >= next_8am:
            next_8am += datetime.timedelta(days=1)
        diff = next_8am - ist
        h    = int(diff.total_seconds() // 3600)
        m    = int((diff.total_seconds() % 3600) // 60)

        return {
            'running':           s['running'],
            'btc_price':         self.current_btc_price,
            'balance':           s['balance'] + total_pnl,
            'starting_balance':  s['starting_balance'],
            'call':              pos['call'],
            'put':               pos['put'],
            'total_pnl':         round(total_pnl, 2),
            'next_trade_in':     f"{h}h {m}m",
            'ist_time':          ist.strftime('%H:%M:%S IST'),
            'market_stats':      self.cached_stats,
            'sentiment':         self.last_iv_pcr,
        }

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def test_live_connection(self, api_key, api_secret):
        if not api_key or not api_secret:
            return False, "API Key and Secret required."
        client = DeltaIndiaClient(api_key.strip(), api_secret.strip())
        ok, info = client.test_connection()
        if ok:
            self.state['LIVE']['client'] = client
            self.is_connected = True
            self._save_creds(api_key.strip(), api_secret.strip())
            self.log('SYSTEM', "✅ API Connection manually verified and saved.")
            return True, "✅ Connection Successful!"
        return False, f"❌ Connection Failed: {info}"

    def start(self, config):
        mode = config.get('mode', 'PAPER').upper()
        s    = self.state[mode]
        
        # Save config
        s['config'] = {
            'target_premium': float(config.get('target_premium', 100)),
            'allocation_pct': float(config.get('allocation_pct', 50)) / 100.0,
            'call_sl_mult':   1.0 + float(config.get('call_stop_loss', 100)) / 100.0,
            'call_sl_on':     bool(config.get('call_stop_loss_on', True)),
            'call_tp_mult':   1.0 - float(config.get('call_take_profit', 95)) / 100.0,
            'call_tp_on':     bool(config.get('call_take_profit_on', True)),
            'put_sl_mult':    1.0 + float(config.get('put_stop_loss', 100)) / 100.0,
            'put_sl_on':      bool(config.get('put_stop_loss_on', True)),
            'put_tp_mult':    1.0 - float(config.get('put_take_profit', 95)) / 100.0,
            'put_tp_on':      bool(config.get('put_take_profit_on', True)),
        }
        self._save_state()

        if mode == 'LIVE':
            key = config.get('api_key', '').strip()
            sec = config.get('api_secret', '').strip()
            if not key or not sec:
                return False, "LIVE mode requires API Key and Secret."
            
            # Re-test/Initialize client
            ok, msg = self.test_live_connection(key, sec)
            if not ok: return False, msg
            self.log('LIVE', "✅ LIVE ENGINE STARTED.", "success")
        else:
            self.log('PAPER', "✅ PAPER ENGINE STARTED.", "success")

        s['running'] = True
        return True, f"{mode} engine started successfully."

    def stop(self, mode):
        if mode in self.state:
            self.state[mode]['running'] = False
            self.log(mode, "🛑 ENGINE STOPPED.", "error")
            self._save_state()

    def trigger_execution(self, mode=None):
        if not mode:
            mode = self.active_mode or 'PAPER'
        self.log(mode, "⚡ MANUAL EXECUTION TRIGGERED...", "info")
        threading.Thread(target=self.execute_strategy, args=(mode,), daemon=True).start()

    def clear_positions(self, mode):
        if mode in self.state:
            self.state[mode]['positions'] = {'call': None, 'put': None}
            self.log(mode, "Positions cleared.", "warn")
            self._save_state()

    # ── Loops ─────────────────────────────────────────────────────────────────
    def _scheduler_loop(self):
        schedule.every().day.at("08:00", "Asia/Kolkata").do(self.execute_strategy, mode='PAPER')
        schedule.every().day.at("08:00", "Asia/Kolkata").do(self.execute_strategy, mode='LIVE')
        while True:
            schedule.run_pending()
            time.sleep(1)

    def _connection_monitor_loop(self):
        """24/7 Monitor to keep API connection alive and handle auto-reconnect."""
        self.log('SYSTEM', "🚀 24/7 Connection Monitor Active.")
        while True:
            try:
                client = self.state['LIVE'].get('client')
                if client and client.api_key:
                    # Heartbeat check
                    ok, info = client.test_connection()
                    if ok:
                        if not self.is_connected:
                            self.log('SYSTEM', "📡 Connection RESTORED.", "success")
                        self.is_connected = True
                        self.last_heartbeat = time.time()
                        self.reconnect_delay = 5 # Reset backoff
                    else:
                        self.is_connected = False
                        self.log('SYSTEM', f"⚡ Connection DROPPED: {info}. Retrying in {self.reconnect_delay}s...", "error")
                        # Exponential backoff
                        time.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(self.reconnect_delay * 2, 300) # Max 5 mins
                        
                        # Re-sync time and retry
                        client.sync_time()
                else:
                    # No credentials yet
                    self.is_connected = False
            except Exception as e:
                logging.error(f"Monitor loop error: {e}")
            
            time.sleep(60) # Standard heartbeat interval

    def _market_data_loop(self):
        self.log('SYSTEM', "📡 Market data feed active.")
        while True:
            try:
                # 1. Update BTC Price & Stats
                now_ts = time.time()
                if now_ts - self.last_stats_update > 60:
                    price = self.india_client.get_btc_price()
                    if price > 0:
                        if self.current_btc_price == 0:
                            self.log('SYSTEM', f"✅ BTC Price Feed Connected: ${price}", "success")
                        self.current_btc_price = price
                    elif self.current_btc_price == 0:
                        # Only log once if we are totally disconnected
                        self.log('SYSTEM', "⚠️ Price feed unavailable. Check connection.", "warn")
                    
                    r = self.india_client.get('/v2/tickers', {'contract_types': 'perpetual_futures', 'underlying_asset_symbol': 'BTC'})
                    if r.get('success') and r.get('result'):
                        for t in r['result']:
                            if t.get('symbol') == 'BTCUSD':
                                self.cached_stats = {'high': float(t.get('high', 0)), 'low': float(t.get('low', 0)), 'volume': float(t.get('volume', 0)), 'oi': float(t.get('open_interest', 0))}
                                break
                    self.last_stats_update = now_ts

                # 2. Update IV/PCR
                if now_ts - self.last_chain_update > 120:
                    chain = self.india_client.get_option_chain()
                    if chain:
                        call_oi, put_oi, ivs = 0, 0, []
                        for opt in chain:
                            oi = float(opt.get('open_interest', 0) or 0)
                            iv = float(opt.get('mark_iv') or opt.get('implied_volatility') or 0)
                            if opt.get('option_type') == 'call': call_oi += oi
                            else: put_oi += oi
                            if iv > 0: ivs.append(iv)
                        self.last_iv_pcr = {'pcr': round(put_oi/call_oi, 2) if call_oi > 0 else 0.0, 'avg_iv': round(sum(ivs)/len(ivs), 2) if ivs else 0.0}
                    self.last_chain_update = now_ts

                # 3. Update PnL & Enforce AlgoTest SL/TP/Trailing/Re-entry with Live Delta Option Data
                now_ts = time.time()
                for mode in ['PAPER', 'LIVE']:
                    if self.state[mode]['running']:
                        s   = self.state[mode]
                        cfg = s['config']
                        pos = s['positions']
                        
                        # Fetch live option prices for active symbols from Delta India
                        active_syms = [pos[leg]['symbol'] for leg in ['call', 'put'] if pos.get(leg) and pos[leg].get('symbol')]
                        if active_syms and (now_ts - getattr(self, 'last_pos_price_update', 0) > 8):
                            try:
                                for sym in active_syms:
                                    r_tick = self.india_client.get(f'/v2/tickers/{sym}')
                                    if r_tick.get('success') and r_tick.get('result'):
                                        mp = float(r_tick['result'].get('mark_price') or r_tick['result'].get('close') or 0)
                                        if mp > 0:
                                            for leg in ['call', 'put']:
                                                if pos.get(leg) and pos[leg].get('symbol') == sym:
                                                    pos[leg]['current_price'] = round(mp, 2)
                                self.last_pos_price_update = now_ts
                            except Exception as _tick_err:
                                pass

                        # Check PnL and Leg SL/TP
                        for leg in ['call', 'put']:
                            if pos.get(leg):
                                p = pos[leg]
                                p['pnl'] = round((p['entry_price'] - p['current_price']) * p['size'] * 0.001, 2)

                                # Enforce SL/TP
                                is_call = (leg == 'call')
                                sl_on = cfg.get('call_sl_on', True) if is_call else cfg.get('put_sl_on', True)
                                tp_on = cfg.get('call_tp_on', False) if is_call else cfg.get('put_tp_on', False)

                                reason = None
                                if sl_on and p['current_price'] >= p['sl']:
                                    reason = "STOP LOSS"
                                elif tp_on and p['current_price'] <= p['tp']:
                                    reason = "TAKE PROFIT"

                                if reason:
                                    self.log(mode, f"📢 {mode}: {reason} HIT for {leg.upper()} ({p['symbol']}) @ ${p['current_price']:.2f} (SL: ${p['sl']:.2f})", "warn")
                                    s['balance'] += p['pnl']
                                    curr_reentry = p.get('reentry_count', 0)
                                    sl_leg_copy = dict(p)
                                    pos[leg] = None
                                    self.log(mode, f"✅ {leg.upper()} Closed. Current Balance: ${s['balance']:.2f}", "success")

                                    # AlgoTest: Re-entry on SL (RE MOMENTUM 1x: Delta Match & Wait for BTC Move to Finish)
                                    import config as _c
                                    reentry_on = getattr(_c, 'SL_REENTRY_ENABLED', True)
                                    max_reentry = getattr(_c, 'SL_REENTRY_MAX_COUNT', 1)
                                    if reason == "STOP LOSS" and reentry_on and curr_reentry < max_reentry:
                                        self.log(mode, f"🔄 RE MOMENTUM: Initiating momentum peak watch {curr_reentry+1}/{max_reentry} for {leg.upper()}", "info")
                                        self.initiate_reentry_watch(mode, leg, curr_reentry + 1, sl_leg_copy)

                        # Check Lock & Trail Trailing Strategy
                        import config as _c
                        if getattr(_c, 'TRAILING_ENABLED', False) and (pos.get('call') or pos.get('put')):
                            total_profit = sum(pos[l]['pnl'] for l in ['call', 'put'] if pos.get(l))
                            trail_state = getattr(self, f'{mode.lower()}_trail_state', {'peak': 0.0, 'locked_sl': None})
                            if total_profit > trail_state['peak']:
                                trail_state['peak'] = total_profit

                            start_trig = getattr(_c, 'TRAIL_IF_PROFIT', 11.0)
                            lock_amt   = getattr(_c, 'TRAIL_LOCK_PROFIT', 1.0)
                            step_amt   = getattr(_c, 'TRAIL_INCREASE_BY', 5.0)
                            step_trail = getattr(_c, 'TRAIL_PROFIT_BY', 5.0)

                            if trail_state['peak'] >= start_trig:
                                if trail_state['locked_sl'] is None:
                                    trail_state['locked_sl'] = lock_amt
                                    self.log(mode, f"🔒 LOCK & TRAIL ACTIVATED: Profit hit ${trail_state['peak']:.2f} -> Locked floor at ${lock_amt:.2f}", "success")
                                else:
                                    excess = trail_state['peak'] - start_trig
                                    steps = int(excess // step_amt)
                                    new_floor = lock_amt + steps * step_trail
                                    if new_floor > trail_state['locked_sl']:
                                        trail_state['locked_sl'] = new_floor
                                        self.log(mode, f"📈 TRAILING STEP: Profit peaked ${trail_state['peak']:.2f} -> Trail floor moved to ${new_floor:.2f}", "info")

                            setattr(self, f'{mode.lower()}_trail_state', trail_state)

                            # If profit drops below locked trailing SL
                            if trail_state['locked_sl'] is not None and total_profit < trail_state['locked_sl']:
                                self.log(mode, f"🚨 TRAILING STOP LOSS TRIGGERED: Profit dropped to ${total_profit:.2f} (Floor: ${trail_state['locked_sl']:.2f}). Squaring off.", "warn")
                                for l in ['call', 'put']:
                                    if pos.get(l):
                                        s['balance'] += pos[l]['pnl']
                                        pos[l] = None
                                setattr(self, f'{mode.lower()}_trail_state', {'peak': 0.0, 'locked_sl': None})
                                self.log(mode, f"✅ All positions squared off by Lock & Trail. Balance: ${s['balance']:.2f}", "success")

                        # Check active RE-ENTRY WATCH (Momentum exhaustion & Delta matching)
                        self._check_reentry_watch(mode)
            except Exception as e:
                print(f"[MARKET_LOOP ERROR] {e}")
            time.sleep(5)


    # ── Options chain helpers ─────────────────────────────────────────────────
    def get_valid_expiries(self, options):
        expiries = set()
        for o in options:
            sym = o.get('symbol', '').upper()
            parts = sym.split('-')
            if len(parts) >= 4:
                # Format is usually [Side]-[Asset]-[Strike]-[Date]
                expiries.add(parts[3])
        
        def _parse_exp(e):
            try:
                if len(e) == 6 and e.isdigit():
                    return datetime.datetime.strptime(e, '%d%m%y')
                elif len(e) == 7:
                    return datetime.datetime.strptime(e, '%d%b%y')
            except Exception:
                pass
            return datetime.datetime.max

        return sorted(list(expiries), key=_parse_exp)

    def find_best_strike(self, options, option_type, target_premium, target_dates):
        """
        Finds the strike that has premium >= target_premium and is closest to it.
        target_dates: list of valid date strings (e.g. ['120526', '12MAY26'])
        """
        valid = []
        for o in options:
            if o.get('option_type') != option_type: continue
            
            sym = o.get('symbol', '').upper()
            found_date = False
            for d in target_dates:
                if d.upper() in sym:
                    found_date = True
                    break
            
            if not found_date: continue
            
            # Premium discovery: Mark -> Theoretical -> Bid
            prem = float(o.get('mark_price') or o.get('theoretical_price') or 
                         (o.get('quotes', {}).get('best_bid') if o.get('quotes') else 0) or 0)
            
            if prem >= target_premium:
                valid.append((o, prem))
        
        if not valid: return None, target_premium, None
        
        # Sort by premium (ascending) to get the one closest to target but >= target
        valid.sort(key=lambda x: x[1])
        best_opt, best_prem = valid[0]
        return best_opt.get('symbol'), best_prem, best_opt.get('id')

    def find_straddle_width_strikes(self, options, btc_price, target_dates, call_mult=1.6, put_mult=2.3):
        """
        Balance BTC Midnight Strangle (Straddle Width Strike Selection):
        Call Strike = ATM + call_mult * ATM_Straddle_Price
        Put  Strike = ATM - put_mult  * ATM_Straddle_Price
        """
        expiry_opts = []
        for o in options:
            sym = o.get('symbol', '').upper()
            if any(d.upper() in sym for d in target_dates):
                expiry_opts.append(o)

        if not expiry_opts:
            return None, None

        all_strikes = sorted(set(float(o.get('strike_price', 0)) for o in expiry_opts if o.get('strike_price')))
        if not all_strikes:
            return None, None

        atm_strike = min(all_strikes, key=lambda s: abs(s - btc_price))
        atm_ce = 0.0
        atm_pe = 0.0
        for o in expiry_opts:
            if float(o.get('strike_price', 0)) == atm_strike:
                prem = float(o.get('mark_price') or o.get('close') or 0)
                if o.get('option_type') == 'call':
                    atm_ce = prem
                elif o.get('option_type') == 'put':
                    atm_pe = prem

        straddle_price = atm_ce + atm_pe
        if straddle_price <= 0:
            straddle_price = btc_price * 0.01

        target_call_k = atm_strike + call_mult * straddle_price
        target_put_k  = atm_strike - put_mult  * straddle_price

        best_call, best_call_dist = None, float('inf')
        best_put,  best_put_dist  = None, float('inf')

        for o in expiry_opts:
            k = float(o.get('strike_price', 0))
            prem = float(o.get('mark_price') or o.get('close') or 0)
            if prem <= 0: continue
            if o.get('option_type') == 'call' and k >= atm_strike:
                d = abs(k - target_call_k)
                if d < best_call_dist:
                    best_call_dist = d
                    best_call = (o.get('symbol'), prem, o.get('product_id') or o.get('id'))
            elif o.get('option_type') == 'put' and k <= atm_strike:
                d = abs(k - target_put_k)
                if d < best_put_dist:
                    best_put_dist = d
                    best_put = (o.get('symbol'), prem, o.get('product_id') or o.get('id'))

        return best_call, best_put

    # ── Strategy execution ────────────────────────────────────────────────────
    def execute_strategy(self, mode='PAPER'):
        s = self.state[mode]
        if not s['running']: return

        # GUARD: STRIKE LOCK ENFORCEMENT
        # Once strikes are selected, they MUST NOT change or get updated/overwritten!
        pos = s.get('positions', {})
        if pos.get('call') or pos.get('put'):
            self.log(mode, "🔒 STRIKE LOCKED: Position already open. Strikes are locked and will not be changed while trade is running.", "warn")
            return

        self.log(mode, "=" * 45, "info")
        self.log(mode, f"🚀 EXECUTING {mode} STRATEGY", "success")
        self.log(mode, "=" * 45, "info")

        try:
            # Get Options first to discover available expiries
            options = self.india_client.get_option_chain()
            if not options:
                self.log(mode, "❌ Could not fetch option chain. Aborting.", "error")
                return

            # Discover expiries
            all_expiries = self.get_valid_expiries(options)
            self.log(mode, f"Available Expiries: {all_expiries}", "info")

            # Target is tomorrow (08:00 AM trade -> Next day 05:30 PM expiry)
            now_dt = datetime.datetime.now()
            target_dt = now_dt + datetime.timedelta(days=1)
            target_d1 = target_dt.strftime('%d%m%y')
            target_d2 = target_dt.strftime('%d%b%y').upper()
            
            # Find the first available expiry that is today or later
            target_dates = []
            for exp in all_expiries:
                # Simple check: if expiry matches our target strings
                if target_d1 in exp or target_d2 in exp:
                    target_dates = [exp]
                    break
            
            if not target_dates and all_expiries:
                # Fallback: pick the first one that is at least 24h away if possible
                target_dates = [all_expiries[0]]
            
            if not target_dates:
                self.log(mode, "❌ No valid expiries found. Aborting.", "error")
                return

            self.log(mode, f"Target Expiry Selected: {target_dates}", "info")

            if mode == 'LIVE': s['client'].sync_time()

            if self.current_btc_price <= 0:
                self.current_btc_price = self.india_client.get_btc_price()
            if self.current_btc_price <= 0:
                self.log(mode, "❌ Cannot get BTC price. Aborting.", "error")
                return

            btc = self.current_btc_price
            cfg = s['config']

            # Get Options and find strikes using Balance BTC Straddle Width formula
            options = self.india_client.get_option_chain()
            import config as _cfg
            call_mult = getattr(_cfg, 'CALL_STRADDLE_MULT', 1.6)
            put_mult  = getattr(_cfg, 'PUT_STRADDLE_MULT',  2.3)

            sw_ce, sw_pe = self.find_straddle_width_strikes(options, btc, target_dates, call_mult, put_mult)
            if sw_ce and sw_pe:
                call_sym, call_prem, call_id = sw_ce
                put_sym,  put_prem,  put_id  = sw_pe
                self.log(mode, f"🎯 BALANCE BTC STRADDLE WIDTH: CE +{call_mult}x, PE -{put_mult}x", "info")
            else:
                target_prem = 100.0
                call_sym, call_prem, call_id = self.find_best_strike(options, 'call', target_prem, target_dates)
                put_sym,  put_prem,  put_id  = self.find_best_strike(options, 'put',  target_prem, target_dates)

            if not call_sym or not put_sym:
                self.log(mode, f"❌ Could not find strikes for {target_dates}", "error")
                return

            self.log(mode, f"SELECTED CE: {call_sym} @ ${call_prem:.2f}", "success")
            self.log(mode, f"SELECTED PE: {put_sym} @ ${put_prem:.2f}", "success")

            # ── PAPER ──
            if mode == 'PAPER':
                bal  = s['balance']
                pos  = s['positions']
                
                # Check configured lot size (default 500 lots per leg as per AlgoTest config)
                configured_lots = 500
                try:
                    import json
                    with open('strategy_config.json', 'r') as _scf:
                        _scfg = json.load(_scf)
                        configured_lots = int(_scfg.get('total_lots', 1000) // 2)
                except Exception:
                    pass
                c_sz = configured_lots if configured_lots > 0 else max(1, int((bal * cfg['allocation_pct'] * 200) / (call_prem + 1)))
                p_sz = configured_lots if configured_lots > 0 else max(1, int((bal * cfg['allocation_pct'] * 200) / (put_prem + 1)))

                pos['call'] = {
                    'symbol': call_sym, 'strike': 0, 'side': 'SELL CALL',
                    'entry_price': call_prem, 'current_price': call_prem,
                    'size': c_sz, 'pnl': 0.0,
                    'sl': round(call_prem * cfg['call_sl_mult'], 2),
                    'sl_on': cfg['call_sl_on'],
                    'tp': round(call_prem * cfg['call_tp_mult'], 2),
                    'tp_on': cfg['call_tp_on'],
                    'reentry_count': 0
                }
                pos['put'] = {
                    'symbol': put_sym, 'strike': 0, 'side': 'SELL PUT',
                    'entry_price': put_prem, 'current_price': put_prem,
                    'size': p_sz, 'pnl': 0.0,
                    'sl': round(put_prem * cfg['put_sl_mult'], 2),
                    'sl_on': cfg['put_sl_on'],
                    'tp': round(put_prem * cfg['put_tp_mult'], 2),
                    'tp_on': cfg['put_tp_on'],
                    'reentry_count': 0
                }
                self.log(mode, f"✅ PAPER EXECUTION COMPLETE. x{c_sz} CE, x{p_sz} PE", "success")
                return

            # ── LIVE ──
            if mode == 'LIVE':
                client = s['client']
                live_bal = client.get_balance()
                if live_bal <= 0:
                    self.log(mode, "❌ Zero USDT balance. Cannot trade.", "error")
                    return
                s['balance'] = live_bal
                
                configured_lots = 500
                try:
                    import json
                    with open('strategy_config.json', 'r') as _scf:
                        _scfg = json.load(_scf)
                        configured_lots = int(_scfg.get('total_lots', 1000) // 2)
                except Exception:
                    pass
                c_sz = configured_lots if configured_lots > 0 else max(1, int((live_bal * cfg['allocation_pct'] * 200) / (call_prem + 1)))
                p_sz = configured_lots if configured_lots > 0 else max(1, int((live_bal * cfg['allocation_pct'] * 200) / (put_prem + 1)))
                pos  = s['positions']

                for pid, sym, sz, prem, sl_m, tp_m, sl_on, tp_on, leg in [
                    (call_id, call_sym, c_sz, call_prem, cfg['call_sl_mult'], cfg['call_tp_mult'], cfg['call_sl_on'], cfg['call_tp_on'], 'CALL'),
                    (put_id,  put_sym,  p_sz, put_prem,  cfg['put_sl_mult'],  cfg['put_tp_mult'],  cfg['put_sl_on'],  cfg['put_tp_on'],  'PUT'),
                ]:
                    # 1. Set Isolated Mode & 200X Leverage
                    self.log(mode, f"Setting Isolated 200X for {sym}...", "info")
                    client.set_margin_mode(pid, 'isolated')
                    client.set_leverage(pid, 200)
                    
                    # 2. Place Order
                    self.log(mode, f"Placing {leg} order: {sym} x{sz}...", "info")
                    res = client.place_order(pid, 'sell', sz, 'limit_order', prem)
                    
                    if res.get('success'):
                        pos[leg.lower()] = {
                            'symbol': sym, 'strike': 0, 'side': f'SELL {leg}',
                            'entry_price': prem, 'current_price': prem,
                            'size': sz, 'pnl': 0.0,
                            'sl': round(prem * sl_m, 2),
                            'sl_on': sl_on,
                            'tp': round(prem * tp_m, 2),
                            'tp_on': tp_on,
                            'reentry_count': 0
                        }
                        self.log(mode, f"✅ {leg} Filled: {sym}", "success")
                    else:
                        err = res.get('error', {})
                        self.log(mode, f"❌ {leg} Failed: {err.get('message', 'Unknown error')}", "error")

                self.log(mode, "✅ LIVE EXECUTION COMPLETE.", "success")

        except Exception as e:
            self.log(mode, f"❌ Strategy error: {e}", "error")
            import traceback
            traceback.print_exc()

    def initiate_reentry_watch(self, mode, leg, count, prev_leg_data):
        """
        AlgoTest RE MOMENTUM 1x:
        When a leg hits Stop Loss, monitor candidate replacement leg until the BTC move finishes.
        Matches delta of the surviving other leg.
        Enters ONLY when the candidate leg's premium stops rising and begins falling!
        """
        try:
            s = self.state[mode]
            pos = s['positions']
            btc = self.current_btc_price
            if btc <= 0:
                btc = self.india_client.get_btc_price()

            options = self.india_client.get_option_chain()
            if not options:
                self.log(mode, "❌ Re-entry watch failed: could not fetch option chain", "error")
                return

            expiries = self.get_valid_expiries(options)
            if not expiries:
                return
            target_expiry = expiries[0]

            # 1. Identify surviving other leg and determine target Delta
            other_leg = 'put' if leg == 'call' else 'call'
            surviving_delta = 0.10  # default baseline
            surviving_pos = pos.get(other_leg)
            
            if surviving_pos and surviving_pos.get('symbol'):
                surv_sym = surviving_pos['symbol']
                matching_ticker = next((o for o in options if o.get('symbol') == surv_sym), None)
                if matching_ticker and matching_ticker.get('greeks') and matching_ticker['greeks'].get('delta'):
                    try:
                        surviving_delta = abs(float(matching_ticker['greeks']['delta']))
                    except Exception:
                        pass

            # 2. Filter candidate options for the stopped leg's side
            target_contract_type = 'call_options' if leg == 'call' else 'put_options'
            candidates = []
            for o in options:
                sym = o.get('symbol', '')
                if not sym.endswith(target_expiry):
                    continue
                if o.get('contract_type') != target_contract_type:
                    continue
                try:
                    k = float(o.get('strike_price', 0))
                    # OTM condition: Calls >= BTC, Puts <= BTC
                    if leg == 'call' and k < btc:
                        continue
                    if leg == 'put' and k > btc:
                        continue
                    mp = float(o.get('mark_price', 0))
                    if mp <= 0:
                        continue
                    candidates.append(o)
                except Exception:
                    continue

            if not candidates:
                self.log(mode, f"❌ No valid OTM replacement candidates found for {leg.upper()}", "warn")
                return

            # 3. Match Delta of other leg
            def _delta_diff(cand):
                try:
                    g = cand.get('greeks') or {}
                    if g.get('delta'):
                        return abs(abs(float(g['delta'])) - surviving_delta)
                except Exception:
                    pass
                return 999.0

            cand_with_greeks = [c for c in candidates if c.get('greeks') and c['greeks'].get('delta')]
            if cand_with_greeks:
                best_cand = min(cand_with_greeks, key=_delta_diff)
            else:
                import config as _cfg
                call_mult = getattr(_cfg, 'CALL_STRADDLE_MULT', 1.6)
                put_mult  = getattr(_cfg, 'PUT_STRADDLE_MULT',  2.3)
                sw_ce, sw_pe = self.find_straddle_width_strikes(options, btc, [target_expiry], call_mult, put_mult)
                chosen = sw_ce if leg == 'call' else sw_pe
                if chosen:
                    best_cand = next((o for o in candidates if o.get('symbol') == chosen[0]), candidates[0])
                else:
                    best_cand = candidates[len(candidates)//2]

            cand_sym  = best_cand['symbol']
            cand_pid  = best_cand.get('product_id')
            cand_prem = float(best_cand.get('mark_price', 0))
            cand_k    = float(best_cand.get('strike_price', 0))
            cand_d    = abs(float(best_cand.get('greeks', {}).get('delta', 0))) if best_cand.get('greeks') and best_cand['greeks'].get('delta') else 0.0

            if 'reentry_watch' not in s:
                s['reentry_watch'] = {'call': None, 'put': None}

            s['reentry_watch'][leg] = {
                'leg': leg,
                'count': count,
                'prev_leg': prev_leg_data,
                'other_leg': other_leg,
                'target_delta': surviving_delta,
                'candidate_symbol': cand_sym,
                'candidate_product_id': cand_pid,
                'candidate_strike': cand_k,
                'candidate_delta': cand_d,
                'peak_premium': cand_prem,
                'last_premium': cand_prem,
                'falling_count': 0,
                'status': 'MONITORING_MOMENTUM',
                'activated_at': time.time(),
                'last_log_ts': 0
            }

            self.log(mode, f"👁️ RE-ENTRY WATCH ACTIVATED [{leg.upper()}]: Matched {cand_sym} (Delta {cand_d:.4f} ~ {other_leg.upper()} Delta {surviving_delta:.4f}) @ ${cand_prem:.2f}. Monitoring BTC move: will enter ONLY when premium stops rising and begins falling!", "warn")

        except Exception as e:
            self.log(mode, f"❌ initiate_reentry_watch error: {e}", "error")
            import traceback
            traceback.print_exc()

    def _check_reentry_watch(self, mode):
        """
        Periodically inspects active re-entry watches.
        If premium keeps rising -> No entry (BTC move continuing).
        If premium starts falling (exhaustion confirmed) -> Executes re-entry immediately!
        """
        try:
            s = self.state[mode]
            watches = s.get('reentry_watch', {})
            for leg in ['call', 'put']:
                w = watches.get(leg)
                if not w:
                    continue

                sym = w['candidate_symbol']
                chain = self.india_client.get_option_chain()
                ticker = next((o for o in chain if o.get('symbol') == sym), None) if chain else None
                if not ticker or float(ticker.get('mark_price', 0)) <= 0:
                    continue

                curr_prem = float(ticker['mark_price'])
                peak = w['peak_premium']
                now = time.time()

                if curr_prem > peak:
                    # BTC move still continuing! Premium making new highs!
                    w['peak_premium'] = curr_prem
                    w['falling_count'] = 0
                    if now - w.get('last_log_ts', 0) > 12:
                        self.log(mode, f"⏳ RE-ENTRY PAUSED [{leg.upper()}]: BTC move continuing. {sym} premium rising (${curr_prem:.2f} > peak ${peak:.2f}). Holding off entry...", "info")
                        w['last_log_ts'] = now
                elif curr_prem < peak:
                    # Premium has started falling!
                    drop_amt = peak - curr_prem
                    drop_pct = drop_amt / peak if peak > 0 else 0
                    w['falling_count'] += 1
                    
                    if now - w.get('last_log_ts', 0) > 12:
                        self.log(mode, f"📉 RE-ENTRY WATCH [{leg.upper()}]: Premium retreating from peak ${peak:.2f} to ${curr_prem:.2f} (-{drop_pct*100:.1f}%, ticks={w['falling_count']}). Checking exhaustion...", "info")
                        w['last_log_ts'] = now

                    # Exhaustion confirmation: dropped >= 2.0% from peak OR 2 consecutive falling cycles
                    if drop_pct >= 0.020 or w['falling_count'] >= 2:
                        self.log(mode, f"🎯 RE-ENTRY TRIGGERED [{leg.upper()}]: BTC move finished! {sym} peaked at ${peak:.2f} and started falling to ${curr_prem:.2f} (-{drop_pct*100:.1f}%). Delta matched to {w['other_leg'].upper()} ({w['target_delta']:.4f}). Entering leg now!", "success")
                        self._execute_reentry(
                            mode=mode,
                            leg=leg,
                            count=w['count'],
                            prev_leg_data=w['prev_leg'],
                            symbol=sym,
                            prem=curr_prem,
                            product_id=w['candidate_product_id'],
                            strike=w['candidate_strike']
                        )
                        s['reentry_watch'][leg] = None

        except Exception as e:
            print(f"[_check_reentry_watch ERROR] {e}")

    def _execute_reentry(self, mode, leg, count, prev_leg_data, symbol, prem, product_id, strike=0):
        try:
            s = self.state[mode]
            cfg = s['config']
            pos = s['positions']
            size = prev_leg_data.get('size', 500)
            sl_mult = cfg.get(f'{leg}_sl_mult', 2.0)
            sl_on = cfg.get(f'{leg}_sl_on', True)
            tp_mult = cfg.get(f'{leg}_tp_mult', 0.05)
            tp_on = cfg.get(f'{leg}_tp_on', False)

            if mode == 'PAPER':
                pos[leg] = {
                    'symbol': symbol, 'strike': strike, 'side': f'SELL {leg.upper()}',
                    'entry_price': prem, 'current_price': prem,
                    'size': size, 'pnl': 0.0,
                    'sl': round(prem * sl_mult, 2),
                    'sl_on': sl_on,
                    'tp': round(prem * tp_mult, 2),
                    'tp_on': tp_on,
                    'reentry_count': count
                }
                self.log(mode, f"🎯 RE-ENTERED {symbol} @ ${prem:.2f} (SL: ${prem*sl_mult:.2f}) x{size} lots", "success")
            elif mode == 'LIVE':
                client = s['client']
                client.set_margin_mode(product_id, 'isolated')
                client.set_leverage(product_id, 200)
                res = client.place_order(product_id, 'sell', size, 'limit_order', prem)
                if res.get('success'):
                    pos[leg] = {
                        'symbol': symbol, 'strike': strike, 'side': f'SELL {leg.upper()}',
                        'entry_price': prem, 'current_price': prem,
                        'size': size, 'pnl': 0.0,
                        'sl': round(prem * sl_mult, 2),
                        'sl_on': sl_on,
                        'tp': round(prem * tp_mult, 2),
                        'tp_on': tp_on,
                        'reentry_count': count
                    }
                    self.log(mode, f"🎯 LIVE RE-ENTERED {symbol} @ ${prem:.2f}", "success")
                else:
                    self.log(mode, f"❌ Live Re-entry Failed: {res.get('error')}", "error")
        except Exception as e:
            self.log(mode, f"❌ _execute_reentry error: {e}", "error")

    def _reenter_leg(self, mode, leg, count, prev_leg_data):
        """Wrapper maintaining interface compatibility"""
        self.initiate_reentry_watch(mode, leg, count, prev_leg_data)

bot_instance = DeltaOptionsBot()

