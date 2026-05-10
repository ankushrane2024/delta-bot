import os
import time
import datetime
import threading
import hmac
import hashlib
import json
import schedule
import requests as _requests

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
            r = _requests.get(url, headers=self._headers('GET', path_with_qs), timeout=15)
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
        """Try Delta India first, fallback to CoinGecko if unreachable."""
        try:
            r = self.get('/v2/tickers', {
                'contract_types': 'perpetual_futures',
                'underlying_asset_symbol': 'BTC'
            })
            if r.get('success') and r.get('result'):
                for t in r['result']:
                    if t.get('symbol') == 'BTCUSD':
                        price = float(t.get('mark_price') or t.get('close') or 0)
                        if price > 0:
                            return price
        except Exception:
            pass
        # Fallback: CoinGecko public API (no auth needed)
        try:
            cg = _requests.get(
                'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
                timeout=10
            ).json()
            return float(cg['bitcoin']['usd'])
        except Exception:
            return 0.0

    def get_option_chain(self):
        # Delta India often works better with tickers endpoint for full chain data
        params = {
            'contract_types': 'call_options,put_options',
            'underlying_asset_id': '13', # BTC
            'underlying_asset_symbol': 'BTC'
        }
        r = self.get('/v2/tickers', params)
        if r.get('success'):
            results = r.get('result', [])
            # Robust filter: check underlying symbol or symbol prefix
            return [t for t in results if 
                    t.get('underlying_asset_symbol') in ['BTC', 'BTCUSD'] or 
                    t.get('symbol', '').startswith(('C-BTC', 'P-BTC', 'BTC-'))]
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

        # Per-mode state
        self.state = {
            'PAPER': {
                'running': False,
                'logs': [], 'balance': 10000.0,
                'starting_balance': 10000.0,
                'positions': {'call': None, 'put': None},
                'config': {}
            },
            'LIVE': {
                'running': False,
                'logs': [], 'balance': 0.0,
                'starting_balance': 0.0,
                'positions': {'call': None, 'put': None},
                'config': {},
                'client': None
            }
        }

        self.india_client = DeltaIndiaClient() # Public client for stats
        threading.Thread(target=self._market_data_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    # ── Logging ───────────────────────────────────────────────────────────────
    def log(self, mode, message, mtype="info"):
        ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        ts  = ist.strftime('%H:%M:%S')
        entry = {'time': ts, 'msg': message, 'type': mtype}
        try:
            print(f"[{mode}][{ts} IST] {message}")
        except UnicodeEncodeError:
            print(f"[{mode}][{ts} IST] {message.encode('ascii','replace').decode()}")
        logs = self.state[mode]['logs']
        logs.append(entry)
        if len(logs) > 500:
            logs.pop(0)

    def get_logs(self, mode):
        return self.state.get(mode, self.state['PAPER'])['logs']

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
        client = DeltaIndiaClient(api_key.strip(), api_secret.strip())
        ok, info = client.test_connection()
        if ok:
            self.state['LIVE']['client'] = client
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
            'call_tp_mult':   1.0 - float(config.get('call_take_profit', 95)) / 100.0,
            'put_sl_mult':    1.0 + float(config.get('put_stop_loss', 100)) / 100.0,
            'put_tp_mult':    1.0 - float(config.get('put_take_profit', 95)) / 100.0,
        }

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

    def trigger_execution(self, mode):
        self.log(mode, "⚡ MANUAL EXECUTION TRIGGERED...", "info")
        threading.Thread(target=self.execute_strategy, args=(mode,), daemon=True).start()

    def clear_positions(self, mode):
        if mode in self.state:
            self.state[mode]['positions'] = {'call': None, 'put': None}
            self.log(mode, "Positions cleared.", "warn")

    # ── Loops ─────────────────────────────────────────────────────────────────
    def _scheduler_loop(self):
        schedule.every().day.at(ENTRY_TIME_UTC).do(self.execute_strategy, mode='PAPER')
        schedule.every().day.at(ENTRY_TIME_UTC).do(self.execute_strategy, mode='LIVE')
        while True:
            schedule.run_pending()
            time.sleep(1)

    def _market_data_loop(self):
        while True:
            try:
                # 1. Update BTC Price & Stats
                now_ts = time.time()
                if now_ts - self.last_stats_update > 60: # More frequent stats
                    price = self.india_client.get_btc_price()
                    if price > 0: self.current_btc_price = price
                    
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

                # 3. Simulate Paper PnL
                if self.state['PAPER']['running'] and self.current_btc_price > 0:
                    pos = self.state['PAPER']['positions']
                    for leg in ['call', 'put']:
                        if pos[leg]:
                            p = pos[leg]
                            dist = abs(self.current_btc_price - p['strike'])
                            sim  = max(0.5, p['entry_price'] - dist * 0.01)
                            p['current_price'] = round(sim, 2)
                            p['pnl'] = round((p['entry_price'] - p['current_price']) * p['size'], 2)
            except Exception as e:
                print(f"[MARKET_LOOP ERROR] {e}")
            time.sleep(5)


    # ── Options chain helpers ─────────────────────────────────────────────────
    def find_best_strike(self, options, option_type, target_premium, target_date):
        """
        Finds the strike that has premium >= target_premium and is closest to it.
        target_date format: 'YYYY-MM-DD'
        """
        valid = []
        for o in options:
            # Filter by type and date
            if o.get('option_type') != option_type: continue
            
            # Delta expiry date is often in 'close_at' timestamp or 'symbol' like 'BTC-11MAY26-...'
            # We'll use the 'symbol' or a date field if available. 
            # For robustness, let's look at the symbol.
            sym = o.get('symbol', '')
            if target_date.upper() not in sym.upper(): continue
            
            prem = float(o.get('mark_price') or o.get('theoretical_price') or 0)
            if prem >= target_premium:
                valid.append((o, prem))
        
        if not valid: return None, target_premium, None
        
        # Sort by premium (ascending) to get the one closest to $100 but >= $100
        valid.sort(key=lambda x: x[1])
        best_opt, best_prem = valid[0]
        return best_opt.get('symbol'), best_prem, best_opt.get('id')

    # ── Strategy execution ────────────────────────────────────────────────────
    def execute_strategy(self, mode='PAPER'):
        s = self.state[mode]
        if not s['running']: return

        self.log(mode, "=" * 45, "info")
        self.log(mode, f"🚀 EXECUTING {mode} STRATEGY", "success")
        self.log(mode, "=" * 45, "info")

        try:
            # Calculate Target Expiry (Next Day)
            # If today is 10 May, target is 11 May. 
            # Trade is 08:00 AM IST, expiry is next day 05:30 PM IST.
            now_dt = datetime.datetime.now()
            target_dt = now_dt + datetime.timedelta(days=1)
            target_date_str = target_dt.strftime('%d%b%y').upper() # e.g., '11MAY26'
            self.log(mode, f"Target Expiry: {target_date_str}", "info")

            if mode == 'LIVE': s['client'].sync_time()

            if self.current_btc_price <= 0:
                self.current_btc_price = self.india_client.get_btc_price()
            if self.current_btc_price <= 0:
                self.log(mode, "❌ Cannot get BTC price. Aborting.", "error")
                return

            btc = self.current_btc_price
            cfg = s['config']
            target_prem = 100.0 # Strict $100 rule as per user request

            # Get Options and find strikes
            options = self.india_client.get_option_chain()
            call_sym, call_prem, call_id = self.find_best_strike(options, 'call', target_prem, target_date_str)
            put_sym,  put_prem,  put_id  = self.find_best_strike(options, 'put',  target_prem, target_date_str)

            if not call_sym or not put_sym:
                self.log(mode, f"❌ Could not find strikes for {target_date_str} with premium >= ${target_prem}", "error")
                return

            self.log(mode, f"SELECTED CE: {call_sym} @ ${call_prem:.2f}", "success")
            self.log(mode, f"SELECTED PE: {put_sym} @ ${put_prem:.2f}", "success")

            # ── PAPER ──
            if mode == 'PAPER':
                bal  = s['balance']
                pos  = s['positions']
                # 200X leverage size calculation
                c_sz = max(1, int((bal * cfg['allocation_pct'] * 200) / (call_prem + 1)))
                p_sz = max(1, int((bal * cfg['allocation_pct'] * 200) / (put_prem + 1)))

                pos['call'] = {
                    'symbol': call_sym, 'strike': 0, 'side': 'SELL CALL',
                    'entry_price': call_prem, 'current_price': call_prem,
                    'size': c_sz, 'pnl': 0.0,
                    'sl': round(call_prem * cfg['call_sl_mult'], 2),
                    'tp': round(call_prem * cfg['call_tp_mult'], 2),
                }
                pos['put'] = {
                    'symbol': put_sym, 'strike': 0, 'side': 'SELL PUT',
                    'entry_price': put_prem, 'current_price': put_prem,
                    'size': p_sz, 'pnl': 0.0,
                    'sl': round(put_prem * cfg['put_sl_mult'], 2),
                    'tp': round(put_prem * cfg['put_tp_mult'], 2),
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
                
                # 200X leverage size calculation
                c_sz = max(1, int((live_bal * cfg['allocation_pct'] * 200) / (call_prem + 1)))
                p_sz = max(1, int((live_bal * cfg['allocation_pct'] * 200) / (put_prem + 1)))
                pos  = s['positions']

                for pid, sym, sz, prem, sl_m, tp_m, leg in [
                    (call_id, call_sym, c_sz, call_prem, cfg['call_sl_mult'], cfg['call_tp_mult'], 'CALL'),
                    (put_id,  put_sym,  p_sz, put_prem,  cfg['put_sl_mult'],  cfg['put_tp_mult'],  'PUT'),
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
                            'tp': round(prem * tp_m, 2),
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

bot_instance = DeltaOptionsBot()

