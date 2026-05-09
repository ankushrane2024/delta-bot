import os
import time
import datetime
import threading
import hmac
import hashlib
import json
import ccxt
import schedule
import requests as _requests

# IST = UTC + 5:30 → 8:00 AM IST = 02:30 UTC
ENTRY_TIME_UTC = "02:30"
DELTA_INDIA_BASE = "https://api.india.delta.exchange"


# ─── DIRECT DELTA INDIA CLIENT (bypasses CCXT's broken India endpoint) ────────
class DeltaIndiaClient:
    """Direct HTTP client for Delta Exchange India using HMAC-SHA256 auth."""

    def __init__(self, api_key="", api_secret=""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base = DELTA_INDIA_BASE

    def _sign(self, method, path, body=""):
        ts = str(int(time.time()))
        msg = method + ts + path + body
        sig = hmac.new(
            self.api_secret.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return ts, sig

    def _headers(self, method, path, body=""):
        headers = {
            'Host': 'api.india.delta.exchange',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        if self.api_key and self.api_secret:
            ts, sig = self._sign(method, path, body)
            headers.update({
                'api-key': self.api_key,
                'timestamp': ts,
                'signature': sig
            })
        return headers

    def get(self, path, params=None):
        # Build query string consistently for both signature and request
        if params:
            # Sort keys to ensure consistent signature
            sorted_params = sorted(params.items())
            qs = '&'.join(f"{k}={v}" for k, v in sorted_params)
            path_with_qs = f"{path}?{qs}"
        else:
            path_with_qs = path

        url = f"{self.base}{path_with_qs}"
        h = self._headers('GET', path_with_qs)
        try:
            r = _requests.get(url, headers=h, timeout=15)
            return r.json()
        except Exception as e:
            return {'success': False, 'error': {'code': 'json_error', 'message': str(e)}}

    def post(self, path, data=None):
        url = self.base + path
        body = json.dumps(data or {}, separators=(',', ':'))
        h = self._headers('POST', path, body)
        try:
            r = _requests.post(url, data=body, headers=h, timeout=15)
            return r.json()
        except Exception as e:
            print(f"[DEBUG] POST request/JSON error: {e}")
            return {'success': False, 'error': {'code': 'json_error', 'message': str(e)}}

    def test_connection(self):
        """Returns (success, message)"""
        result = self.get('/v2/profile')
        if result.get('success'):
            return True, result.get('result', {})
        err = result.get('error', {})
        code = err.get('code', 'unknown')
        ctx = err.get('context', {})
        if code == 'ip_not_whitelisted_for_api_key':
            ip = ctx.get('client_ip', 'unknown')
            return False, f"IP not whitelisted: {ip}. Add this IP to your Delta API key whitelist."
        if code == 'invalid_api_key':
            return False, "Invalid API key. Check key is correct and active on Delta India."
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
        r = self.get('/v2/tickers', {'contract_types': 'perpetual_futures', 'underlying_asset_symbol': 'BTC'})
        if r.get('success') and r.get('result'):
            for t in r['result']:
                # On Delta India, the symbol is often BTCUSD (not BTCUSDT)
                if t.get('symbol') == 'BTCUSD':
                    return float(t.get('mark_price', 0) or t.get('close', 0) or 0)
        return 0.0

    def get_option_chain(self):
        r = self.get('/v2/options/chain', {'underlying_asset_symbol': 'BTC'})
        return r.get('result', []) if r.get('success') else []

    def place_order(self, product_id, side, size, order_type='market_order', limit_price=None):
        data = {
            'product_id': product_id,
            'side': side,
            'size': size,
            'order_type': order_type,
        }
        if limit_price:
            data['limit_price'] = str(limit_price)
        return self.post('/v2/orders', data)

    def get_history(self, symbol, resolution='1h', hours=24):
        now = int(time.time())
        start = now - (hours * 3600)
        params = {'symbol': symbol, 'resolution': resolution, 'start': start, 'end': now}
        r = self.get('/v2/history/candles', params)
        return r.get('result', []) if r.get('success') else []

    def get_ticker_stats(self, symbol):
        r = self.get('/v2/tickers', {'symbol': symbol})
        if r.get('success') and r.get('result'):
            return r['result'][0]
        return {}


# IST = UTC + 5:30 → 8:00 AM IST = 02:30 UTC
# Render cloud servers run on UTC
ENTRY_TIME_UTC = "02:30"


class DeltaOptionsBot:
    def __init__(self):
        self.running = False
        self.active_mode = "PAPER"
        self.thread = None
        self.market_thread = None

        # Separate state per mode
        self.state = {
            'PAPER': {'logs': [], 'positions': {'call': None, 'put': None}, 'balance': 10000.0, 'starting_balance': 10000.0},
            'LIVE':  {'logs': [], 'positions': {'call': None, 'put': None}, 'balance': 0.0, 'starting_balance': 0.0}
        }

        # Strategy config
        self.api_key = ""
        self.api_secret = ""
        self.leverage = 200
        self.target_premium = 100.0
        self.allocation_pct = 0.50
        self.call_sl_mult = 2.0
        self.call_tp_mult = 0.05
        self.put_sl_mult = 2.0
        self.put_tp_mult = 0.05
        self.entry_time_utc = ENTRY_TIME_UTC
        
        self.current_btc_price = 0.0
        self.india_client = DeltaIndiaClient()

    # ─── LOGGING ──────────────────────────────────────────────────────────────
    def log(self, message, mtype="info"):
        utc_now = datetime.datetime.utcnow()
        ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
        timestamp = ist_now.strftime('%H:%M:%S')
        log_entry = {'time': timestamp, 'msg': message, 'type': mtype}
        try:
            print(f"[{self.active_mode}] [{timestamp} IST] {message}")
        except UnicodeEncodeError:
            print(f"[{self.active_mode}] [{timestamp} IST] {message.encode('ascii', 'replace').decode('ascii')}")
        logs = self.state[self.active_mode]['logs']
        logs.append(log_entry)
        if len(logs) > 500:
            logs.pop(0)

    def get_logs(self, mode):
        if mode not in self.state:
            mode = 'PAPER'
        return self.state[mode]['logs']

    def get_state(self, mode):
        if mode not in self.state:
            mode = 'PAPER'
        pos = self.state[mode]['positions']
        total_pnl = 0.0
        if pos['call']:
            total_pnl += pos['call'].get('pnl', 0.0)
        if pos['put']:
            total_pnl += pos['put'].get('pnl', 0.0)

        ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        # Calculate time to next 8AM IST
        next_8am = ist_now.replace(hour=8, minute=0, second=0, microsecond=0)
        if ist_now >= next_8am:
            next_8am += datetime.timedelta(days=1)
        diff = next_8am - ist_now
        hours_left = int(diff.total_seconds() // 3600)
        mins_left = int((diff.total_seconds() % 3600) // 60)

        # Calculate Put-Call Ratio (PCR) and Avg IV from options chain
        chain = self.india_client.get_option_chain()
        total_call_oi = 0
        total_put_oi = 0
        ivs = []
        for opt in chain:
            oi = float(opt.get('open_interest', 0))
            iv = float(opt.get('mark_iv') or opt.get('theoretical_volatility') or 0)
            if opt.get('option_type') == 'call':
                total_call_oi += oi
            else:
                total_put_oi += oi
            if iv > 0: ivs.append(iv)
        
        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0.0
        avg_iv = round(sum(ivs) / len(ivs), 2) if ivs else 0.0

        # Get 24h Stats for BTCUSD
        stats = self.india_client.get_ticker_stats('BTCUSD')

        return {
            'running': self.running,
            'running_mode': self.active_mode if self.running else None,
            'btc_price': self.current_btc_price,
            'balance': self.state[mode]['balance'] + total_pnl,
            'starting_balance': self.state[mode]['starting_balance'],
            'call': pos['call'],
            'put': pos['put'],
            'total_pnl': total_pnl,
            'next_trade_in': f"{hours_left}h {mins_left}m",
            'ist_time': ist_now.strftime('%H:%M:%S IST'),
            'market_stats': {
                'high': stats.get('high', 0),
                'low': stats.get('low', 0),
                'volume': stats.get('volume', 0),
                'oi': stats.get('open_interest', 0)
            },
            'sentiment': {
                'pcr': pcr,
                'avg_iv': avg_iv
            }
        }

    # ─── START / STOP ─────────────────────────────────────────────────────────
    def start(self, config):
        """Start or restart the engine with new config."""
        # If already running, stop first (allows restart with new config)
        if self.running:
            self.running = False
            time.sleep(1.5)

        mode = config.get('mode', 'PAPER').upper()
        self.active_mode = mode
        # Use keys from form, OR fall back to Render environment variables
        self.api_key = config.get('api_key', '').strip() or os.environ.get('DELTA_API_KEY', '')
        self.api_secret = config.get('api_secret', '').strip() or os.environ.get('DELTA_API_SECRET', '')
        self.target_premium = float(config.get('target_premium', 100.0))
        self.allocation_pct = float(config.get('allocation_pct', 50.0)) / 100.0
        self.call_sl_mult = 1.0 + (float(config.get('call_stop_loss', 100.0)) / 100.0)
        self.call_tp_mult = 1.0 - (float(config.get('call_take_profit', 95.0)) / 100.0)
        self.put_sl_mult = 1.0 + (float(config.get('put_stop_loss', 100.0)) / 100.0)
        self.put_tp_mult = 1.0 - (float(config.get('put_take_profit', 95.0)) / 100.0)

        if mode == "LIVE":
            if not self.api_key or not self.api_secret:
                return False, "LIVE mode requires API Key and Secret."
            
            self.india_client = DeltaIndiaClient(self.api_key, self.api_secret)
            success, info = self.india_client.test_connection()
            if success:
                self.log("LIVE ENGINE CONNECTED to Delta India. Real funds at risk.", "error")
            else:
                return False, f"API connection failed: {info}"
        else:
            self.india_client = DeltaIndiaClient() # Public only
            self.log("PAPER ENGINE STARTED. Using Delta India live market data.", "success")

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.market_thread = threading.Thread(target=self._market_data_loop, daemon=True)
        self.market_thread.start()
        return True, "Engine started successfully."

    def stop(self):
        self.running = False
        self.log("ENGINE STOPPED.", "error")
        return True

    def trigger_execution(self):
        self.log("MANUAL EXECUTION TRIGGERED...", "info")
        threading.Thread(target=self.execute_strategy, daemon=True).start()

    def clear_positions(self, mode):
        if mode in self.state:
            self.state[mode]['positions'] = {'call': None, 'put': None}

    # ─── SCHEDULER LOOP ───────────────────────────────────────────────────────
    def _run_loop(self):
        schedule.clear()
        self.log(f"SCHEDULER SET: 08:00 AM IST daily ({self.entry_time_utc} UTC on server).", "info")
        schedule.every().day.at(self.entry_time_utc).do(self.execute_strategy)
        while self.running:
            schedule.run_pending()
            utc_now = datetime.datetime.utcnow()
            ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
            # Heartbeat log every hour
            if utc_now.minute == 0 and utc_now.second < 2:
                self.log(f"SCHEDULER ALIVE at {ist_now.strftime('%H:%M IST')}. Next trade: 08:00 IST.", "info")
            time.sleep(1)

    # ─── MARKET DATA LOOP ─────────────────────────────────────────────────────
    def _market_data_loop(self):
        while self.running:
            try:
                price = self.india_client.get_btc_price()
                if price > 0:
                    self.current_btc_price = price
                pos = self.state[self.active_mode]['positions']
                if pos['call']:
                    c = pos['call']
                    dist = c['strike'] - self.current_btc_price
                    sim_premium = max(0.5, c['entry_price'] - (dist * 0.01))
                    c['current_price'] = round(sim_premium, 2)
                    c['pnl'] = round((c['entry_price'] - c['current_price']) * c['size'], 2)
                if pos['put']:
                    p = pos['put']
                    dist = self.current_btc_price - p['strike']
                    sim_premium = max(0.5, p['entry_price'] - (dist * 0.01))
                    p['current_price'] = round(sim_premium, 2)
                    p['pnl'] = round((p['entry_price'] - p['current_price']) * p['size'], 2)
            except Exception as e:
                pass
            time.sleep(5)

    # ─── OPTIONS CHAIN ────────────────────────────────────────────────────────
    def get_options_chain(self):
        return self.india_client.get_option_chain()

    def find_best_strike(self, options, option_type):
        valid = [o for o in options if o.get('option_type') == option_type]
        best_sym, best_prem, best_prod_id = None, float('inf'), None
        
        for opt in valid:
            # We use mark_price if available, else theoretical
            premium = float(opt.get('mark_price') or opt.get('theoretical_price') or 0)
            if premium >= self.target_premium:
                if premium < best_prem:
                    best_prem = premium
                    best_sym = opt['symbol']
                    best_prod_id = opt['id']
        return best_sym, best_prem, best_prod_id

    # ─── STRATEGY EXECUTION ───────────────────────────────────────────────────
    def execute_strategy(self):
        self.log("=" * 45, "info")
        self.log(f"EXECUTING {self.active_mode} STRATEGY", "success")
        self.log("=" * 45, "info")

        try:
            # Get BTC price
            if self.current_btc_price == 0:
                self.current_btc_price = self.india_client.get_btc_price()

            atm = round(self.current_btc_price / 100) * 100
            call_strike = atm + 3000
            put_strike = atm - 3000

            self.log(f"BTC Spot: ${self.current_btc_price:,.0f} | ATM: ${atm:,.0f}", "info")
            self.log(f"Scanning options chain for ${self.target_premium:.0f} premium strikes...", "info")

            options = self.get_options_chain()
            call_symbol, call_premium, call_id = self.find_best_strike(options, 'call')
            put_symbol, put_premium, put_id = self.find_best_strike(options, 'put')

            if not call_symbol or not put_symbol:
                self.log("No live strikes found — using theoretical strikes.", "warn")
                call_symbol = f'BTC-{int(call_strike)}-C'
                call_premium = self.target_premium
                call_id = 0
                put_symbol = f'BTC-{int(put_strike)}-P'
                put_premium = self.target_premium
                put_id = 0
            else:
                self.log(f"CALL: {call_symbol} @ ${call_premium:.2f}", "success")
                self.log(f"PUT:  {put_symbol} @ ${put_premium:.2f}", "success")

            # ── PAPER MODE ──────────────────────────────────────────────────
            if self.active_mode == "PAPER":
                balance = self.state['PAPER']['balance']
                pos = self.state['PAPER']['positions']

                call_size = max(1, int((balance * self.allocation_pct * self.leverage) / call_premium))
                put_size = max(1, int((balance * self.allocation_pct * self.leverage) / put_premium))

                pos['call'] = {
                    'symbol': call_symbol, 'strike': call_strike,
                    'entry_price': call_premium, 'current_price': call_premium,
                    'size': call_size, 'pnl': 0.0,
                    'sl': round(call_premium * self.call_sl_mult, 2),
                    'tp': round(call_premium * self.call_tp_mult, 2),
                    'side': 'SELL CALL'
                }
                pos['put'] = {
                    'symbol': put_symbol, 'strike': put_strike,
                    'entry_price': put_premium, 'current_price': put_premium,
                    'size': put_size, 'pnl': 0.0,
                    'sl': round(put_premium * self.put_sl_mult, 2),
                    'tp': round(put_premium * self.put_tp_mult, 2),
                    'side': 'SELL PUT'
                }
                self.log(f"[PAPER] SOLD {call_size}x {call_symbol} @ ${call_premium:.2f} | SL: ${pos['call']['sl']} TP: ${pos['call']['tp']}", "success")
                self.log(f"[PAPER] SOLD {put_size}x {put_symbol} @ ${put_premium:.2f} | SL: ${pos['put']['sl']} TP: ${pos['put']['tp']}", "success")
                self.log("PAPER EXECUTION COMPLETE. Tracking live PnL.", "success")
                return

            # ── LIVE MODE ───────────────────────────────────────────────────
            if self.active_mode == "LIVE":
                try:
                    live_balance = self.india_client.get_balance()
                    self.state['LIVE']['balance'] = live_balance
                    self.state['LIVE']['starting_balance'] = live_balance
                    self.log(f"Live Balance: ${live_balance:.2f} USDT", "info")
                    if live_balance <= 0:
                        self.log("Zero balance in LIVE account. Cannot trade.", "error")
                        return
                except Exception as e:
                    self.log(f"Balance fetch failed: {e}", "error")
                    return

                call_size = max(1, int((live_balance * self.allocation_pct * self.leverage) / call_premium))
                put_size = max(1, int((live_balance * self.allocation_pct * self.leverage) / put_premium))

                if call_size < 1 or put_size < 1:
                    self.log("Insufficient balance for minimum lot size.", "error")
                    return

                # Place CALL & PUT orders
                for pid, sym, size, prem, sl_m, tp_m, label in [
                    (call_id, call_symbol, call_size, call_premium, self.call_sl_mult, self.call_tp_mult, "CALL"),
                    (put_id, put_symbol, put_size, put_premium, self.put_sl_mult, self.put_tp_mult, "PUT")
                ]:
                    if pid == 0: continue
                    try:
                        self.log(f"[LIVE] PLACING {label} SELL {size}x {sym} @ MARKET", "warn")
                        res = self.india_client.place_order(pid, 'sell', size)
                        if res.get('success'):
                            sl_price = round(prem * sl_m, 2)
                            tp_price = round(prem * tp_m, 2)
                            # For Stop Loss, Delta uses a different endpoint usually or separate order
                            # We'll just log that entry was successful for now
                            self.log(f"[LIVE] {label} SOLD SUCCESSFULLY.", "success")
                        else:
                            self.log(f"[LIVE] {label} ERROR: {res.get('error', {}).get('code')}", "error")
                    except Exception as e:
                        self.log(f"[LIVE] {label} order error: {e}", "error")

                self.log("LIVE EXECUTION COMPLETE.", "success")

        except Exception as e:
            self.log(f"Strategy error: {e}", "error")


bot_instance = DeltaOptionsBot()
