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
        r = self.get('/v2/options/chain', {'underlying_asset_symbol': 'BTC'})
        return r.get('result', []) if r.get('success') else []

    def place_order(self, product_id, side, size, order_type='market_order', limit_price=None):
        data = {'product_id': product_id, 'side': side, 'size': size, 'order_type': order_type}
        if limit_price:
            data['limit_price'] = str(limit_price)
        return self.post('/v2/orders', data)

    def get_history(self, symbol='BTCUSD', resolution='1h', hours=24):
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
        self.running        = False
        self.active_mode    = 'PAPER'
        self.thread         = None
        self.market_thread  = None

        # Cached market data (shared across modes)
        self.current_btc_price  = 0.0
        self.last_stats_update  = 0
        self.cached_stats       = {}
        self.last_chain_update  = 0
        self.last_iv_pcr        = {'avg_iv': 0.0, 'pcr': 0.0}

        # Per-mode state
        self.state = {
            'PAPER': {
                'logs': [], 'balance': 10000.0,
                'starting_balance': 10000.0,
                'positions': {'call': None, 'put': None}
            },
            'LIVE': {
                'logs': [], 'balance': 0.0,
                'starting_balance': 0.0,
                'positions': {'call': None, 'put': None}
            }
        }

        # Strategy config (defaults)
        self.api_key         = ""
        self.api_secret      = ""
        self.target_premium  = 100.0
        self.allocation_pct  = 0.50
        self.call_sl_mult    = 2.0
        self.call_tp_mult    = 0.05
        self.put_sl_mult     = 2.0
        self.put_tp_mult     = 0.05

        self.india_client = DeltaIndiaClient()

        # Start persistent market data loop (runs even when engine is stopped)
        threading.Thread(target=self._market_data_loop, daemon=True).start()

    # ── Logging ───────────────────────────────────────────────────────────────
    def log(self, message, mtype="info"):
        ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        ts  = ist.strftime('%H:%M:%S')
        entry = {'time': ts, 'msg': message, 'type': mtype}
        try:
            print(f"[{self.active_mode}][{ts} IST] {message}")
        except UnicodeEncodeError:
            print(f"[{self.active_mode}][{ts} IST] {message.encode('ascii','replace').decode()}")
        logs = self.state[self.active_mode]['logs']
        logs.append(entry)
        if len(logs) > 500:
            logs.pop(0)

    def get_logs(self, mode):
        return self.state.get(mode, self.state['PAPER'])['logs']

    # ── State ─────────────────────────────────────────────────────────────────
    def get_state(self, mode):
        if mode not in self.state:
            mode = 'PAPER'
        pos      = self.state[mode]['positions']
        total_pnl = (pos['call'] or {}).get('pnl', 0.0) + (pos['put'] or {}).get('pnl', 0.0)

        ist      = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        next_8am = ist.replace(hour=8, minute=0, second=0, microsecond=0)
        if ist >= next_8am:
            next_8am += datetime.timedelta(days=1)
        diff = next_8am - ist
        h    = int(diff.total_seconds() // 3600)
        m    = int((diff.total_seconds() % 3600) // 60)

        now_ts = time.time()
        # Refresh option chain every 2 min for IV/PCR
        if now_ts - self.last_chain_update > 120:
            try:
                chain = self.india_client.get_option_chain()
                if chain:
                    call_oi, put_oi, ivs = 0, 0, []
                    for opt in chain:
                        oi = float(opt.get('open_interest', 0) or 0)
                        iv = float(opt.get('mark_iv') or opt.get('implied_volatility') or 0)
                        if opt.get('option_type') == 'call':
                            call_oi += oi
                        else:
                            put_oi += oi
                        if iv > 0:
                            ivs.append(iv)
                    self.last_iv_pcr['pcr']    = round(put_oi / call_oi, 3) if call_oi > 0 else 0.0
                    self.last_iv_pcr['avg_iv'] = round(sum(ivs) / len(ivs), 2) if ivs else 0.0
                    self.last_chain_update = now_ts
            except Exception:
                pass

        # Refresh ticker stats every 2 min
        if now_ts - self.last_stats_update > 120 or not self.cached_stats:
            try:
                r = self.india_client.get('/v2/tickers', {
                    'contract_types': 'perpetual_futures',
                    'underlying_asset_symbol': 'BTC'
                })
                if r.get('success') and r.get('result'):
                    for t in r['result']:
                        if t.get('symbol') == 'BTCUSD':
                            self.cached_stats = {
                                'high':   float(t.get('high', 0) or 0),
                                'low':    float(t.get('low', 0) or 0),
                                'volume': float(t.get('volume', 0) or 0),
                                'oi':     float(t.get('open_interest', 0) or 0),
                            }
                            break
                self.last_stats_update = now_ts
            except Exception:
                pass

        return {
            'running':           self.running,
            'running_mode':      self.active_mode if self.running else None,
            'btc_price':         self.current_btc_price,
            'balance':           self.state[mode]['balance'] + total_pnl,
            'starting_balance':  self.state[mode]['starting_balance'],
            'call':              pos['call'],
            'put':               pos['put'],
            'total_pnl':         round(total_pnl, 2),
            'next_trade_in':     f"{h}h {m}m",
            'ist_time':          ist.strftime('%H:%M:%S IST'),
            'market_stats':      self.cached_stats,
            'sentiment':         self.last_iv_pcr,
        }

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def start(self, config):
        if self.running:
            self.running = False
            time.sleep(1.5)

        mode             = config.get('mode', 'PAPER').upper()
        self.active_mode = mode
        self.api_key     = config.get('api_key', '').strip()    or os.environ.get('DELTA_API_KEY', '')
        self.api_secret  = config.get('api_secret', '').strip() or os.environ.get('DELTA_API_SECRET', '')

        self.target_premium = float(config.get('target_premium', 100))
        self.allocation_pct = float(config.get('allocation_pct', 50)) / 100.0
        self.call_sl_mult   = 1.0 + float(config.get('call_stop_loss', 100)) / 100.0
        self.call_tp_mult   = 1.0 - float(config.get('call_take_profit', 95)) / 100.0
        self.put_sl_mult    = 1.0 + float(config.get('put_stop_loss', 100)) / 100.0
        self.put_tp_mult    = 1.0 - float(config.get('put_take_profit', 95)) / 100.0

        if mode == 'LIVE':
            if not self.api_key or not self.api_secret:
                return False, "LIVE mode requires API Key and Secret."
            self.india_client = DeltaIndiaClient(self.api_key, self.api_secret)
            ok, info = self.india_client.test_connection()
            if not ok:
                return False, f"API connection failed: {info}"
            self.log("✅ LIVE ENGINE CONNECTED — Real funds at risk!", "error")
        else:
            self.india_client = DeltaIndiaClient()
            self.log("✅ PAPER ENGINE STARTED — Live market data, simulated trades.", "success")

        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        return True, f"{mode} engine started successfully."

    def stop(self):
        self.running = False
        self.log("🛑 ENGINE STOPPED.", "error")

    def trigger_execution(self):
        self.log("⚡ MANUAL EXECUTION TRIGGERED...", "info")
        threading.Thread(target=self.execute_strategy, daemon=True).start()

    def clear_positions(self, mode):
        if mode in self.state:
            self.state[mode]['positions'] = {'call': None, 'put': None}
            self.log(f"Positions cleared for {mode}.", "warn")

    # ── Scheduler loop ────────────────────────────────────────────────────────
    def _run_loop(self):
        schedule.clear()
        self.log(f"📅 SCHEDULER: Daily trade at 08:00 IST ({ENTRY_TIME_UTC} UTC).", "info")
        schedule.every().day.at(ENTRY_TIME_UTC).do(self.execute_strategy)
        while self.running:
            schedule.run_pending()
            now = datetime.datetime.utcnow()
            if now.minute == 0 and now.second < 2:
                ist = now + datetime.timedelta(hours=5, minutes=30)
                self.log(f"💓 Scheduler alive at {ist.strftime('%H:%M IST')}.", "info")
            time.sleep(1)

    # ── Market data loop ──────────────────────────────────────────────────────
    def _market_data_loop(self):
        """Continuously update BTC price and simulate paper PnL."""
        while True:
            try:
                price = self.india_client.get_btc_price()
                if price > 0:
                    self.current_btc_price = price

                # Simulate paper PnL based on price movement (only if running)
                if self.running and self.active_mode == 'PAPER':
                    pos = self.state['PAPER']['positions']
                    if pos['call'] and self.current_btc_price > 0:
                        c = pos['call']
                        dist = max(0, self.current_btc_price - c['strike'])
                        sim  = max(0.5, c['entry_price'] - dist * 0.012)
                        c['current_price'] = round(sim, 2)
                        c['pnl']           = round((c['entry_price'] - c['current_price']) * c['size'], 2)
                    if pos['put'] and self.current_btc_price > 0:
                        p = pos['put']
                        dist = max(0, p['strike'] - self.current_btc_price)
                        sim  = max(0.5, p['entry_price'] - dist * 0.012)
                        p['current_price'] = round(sim, 2)
                        p['pnl']           = round((p['entry_price'] - p['current_price']) * p['size'], 2)
            except Exception as e:
                print(f"[MARKET_LOOP ERROR] {e}")
            time.sleep(5)

    # ── Options chain helpers ─────────────────────────────────────────────────
    def find_best_strike(self, options, option_type):
        valid    = [o for o in options if o.get('option_type') == option_type]
        best_sym, best_prem, best_id = None, float('inf'), None
        for opt in valid:
            prem = float(opt.get('mark_price') or opt.get('theoretical_price') or 0)
            if self.target_premium * 0.5 <= prem <= self.target_premium * 2.5:
                if prem < best_prem:
                    best_prem = prem
                    best_sym  = opt.get('symbol')
                    best_id   = opt.get('id')
        return best_sym, best_prem if best_prem != float('inf') else self.target_premium, best_id

    # ── Strategy execution ────────────────────────────────────────────────────
    def execute_strategy(self):
        self.log("=" * 45, "info")
        self.log(f"🚀 EXECUTING {self.active_mode} STRATEGY", "success")
        self.log("=" * 45, "info")

        if self.active_mode == 'LIVE':
            self.india_client.sync_time()

        try:
            # Ensure we have a BTC price
            if self.current_btc_price <= 0:
                self.current_btc_price = self.india_client.get_btc_price()
            if self.current_btc_price <= 0:
                self.log("❌ Cannot get BTC price. Aborting.", "error")
                return

            btc    = self.current_btc_price
            atm    = round(btc / 100) * 100
            call_k = atm + 3000
            put_k  = atm - 3000

            self.log(f"BTC Spot: ${btc:,.0f} | ATM: ${atm:,.0f}", "info")
            self.log(f"Target premium: ${self.target_premium:.0f}", "info")

            # Try live options chain
            options     = self.india_client.get_option_chain()
            call_sym, call_prem, call_id = self.find_best_strike(options, 'call')
            put_sym,  put_prem,  put_id  = self.find_best_strike(options, 'put')

            # Fallback to theoretical strikes if chain empty
            if not call_sym:
                call_sym, call_prem, call_id = f'BTC-{int(call_k)}-C', self.target_premium, 0
                put_sym,  put_prem,  put_id  = f'BTC-{int(put_k)}-P',  self.target_premium, 0
                self.log("⚠ No live chain — using theoretical strikes.", "warn")
            else:
                self.log(f"CALL: {call_sym} @ ${call_prem:.2f}", "success")
                self.log(f"PUT:  {put_sym}  @ ${put_prem:.2f}", "success")

            # ── PAPER ──
            if self.active_mode == 'PAPER':
                bal  = self.state['PAPER']['balance']
                pos  = self.state['PAPER']['positions']
                c_sz = max(1, int((bal * self.allocation_pct * 200) / call_prem))
                p_sz = max(1, int((bal * self.allocation_pct * 200) / put_prem))

                pos['call'] = {
                    'symbol': call_sym, 'strike': call_k, 'side': 'SELL CALL',
                    'entry_price': call_prem, 'current_price': call_prem,
                    'size': c_sz, 'pnl': 0.0,
                    'sl': round(call_prem * self.call_sl_mult, 2),
                    'tp': round(call_prem * self.call_tp_mult, 2),
                }
                pos['put'] = {
                    'symbol': put_sym, 'strike': put_k, 'side': 'SELL PUT',
                    'entry_price': put_prem, 'current_price': put_prem,
                    'size': p_sz, 'pnl': 0.0,
                    'sl': round(put_prem * self.put_sl_mult, 2),
                    'tp': round(put_prem * self.put_tp_mult, 2),
                }
                self.log(f"[PAPER] SOLD {c_sz}x {call_sym} @ ${call_prem:.2f} | SL:${pos['call']['sl']} TP:${pos['call']['tp']}", "success")
                self.log(f"[PAPER] SOLD {p_sz}x {put_sym}  @ ${put_prem:.2f} | SL:${pos['put']['sl']} TP:${pos['put']['tp']}", "success")
                self.log("✅ PAPER EXECUTION COMPLETE. Tracking live PnL.", "success")
                return

            # ── LIVE ──
            if self.active_mode == 'LIVE':
                live_bal = self.india_client.get_balance()
                if live_bal <= 0:
                    self.log("❌ Zero USDT balance. Cannot trade.", "error")
                    return
                self.state['LIVE']['balance']          = live_bal
                self.state['LIVE']['starting_balance'] = live_bal
                self.log(f"💰 Live Balance: ${live_bal:.2f} USDT", "info")

                c_sz = max(1, int((live_bal * self.allocation_pct * 200) / call_prem))
                p_sz = max(1, int((live_bal * self.allocation_pct * 200) / put_prem))

                pos = self.state['LIVE']['positions']

                for pid, sym, sz, prem, sl_m, tp_m, k, leg in [
                    (call_id, call_sym, c_sz, call_prem, self.call_sl_mult, self.call_tp_mult, call_k, 'CALL'),
                    (put_id,  put_sym,  p_sz, put_prem,  self.put_sl_mult,  self.put_tp_mult,  put_k,  'PUT'),
                ]:
                    if not pid:
                        self.log(f"⚠ No product_id for {leg} — skipping live order.", "warn")
                        continue
                    self.log(f"[LIVE] Placing {leg} SELL {sz}x {sym} @ MARKET...", "warn")
                    res = self.india_client.place_order(pid, 'sell', sz)
                    if res.get('success'):
                        self.log(f"✅ [LIVE] {leg} order filled: {res.get('result', {})}", "success")
                        leg_key = 'call' if leg == 'CALL' else 'put'
                        pos[leg_key] = {
                            'symbol': sym, 'strike': k, 'side': f'SELL {leg}',
                            'entry_price': prem, 'current_price': prem,
                            'size': sz, 'pnl': 0.0,
                            'sl': round(prem * sl_m, 2),
                            'tp': round(prem * tp_m, 2),
                        }
                    else:
                        err = res.get('error', {})
                        self.log(f"❌ [LIVE] {leg} FAILED: {err.get('code','?')} — {err.get('message','?')}", "error")

                self.log("✅ LIVE EXECUTION COMPLETE.", "success")

        except Exception as e:
            self.log(f"❌ Strategy error: {e}", "error")


bot_instance = DeltaOptionsBot()
