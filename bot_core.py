import os
import time
import datetime
import threading
import ccxt
import schedule

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
        self.exchange = ccxt.delta({'enableRateLimit': True, 'options': {'defaultType': 'option'}})

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
            'ist_time': ist_now.strftime('%H:%M:%S IST')
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
            try:
                self.exchange = ccxt.delta({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'option'}
                })
                # Test connection
                self.exchange.fetch_balance()
                self.log("LIVE ENGINE CONNECTED. Real funds at risk.", "error")
            except Exception as e:
                return False, f"API connection failed: {str(e)}"
        else:
            self.exchange = ccxt.delta({'enableRateLimit': True, 'options': {'defaultType': 'option'}})
            self.log("PAPER ENGINE STARTED. Using live market data.", "success")

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
                ticker = self.exchange.fetch_ticker('BTC/USDT')
                self.current_btc_price = ticker['last']
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
        try:
            self.exchange.load_markets(True)
        except Exception:
            pass
        options = []
        for symbol, market in self.exchange.markets.items():
            if market.get('base') == 'BTC' and market.get('type') == 'option':
                options.append(market)
        return options

    def find_best_strike(self, options, option_type):
        valid = [o for o in options if o.get('optionType') == option_type]
        best_sym, best_prem = None, float('inf')
        for opt in valid:
            try:
                ticker = self.exchange.fetch_ticker(opt['symbol'])
                last = ticker.get('last')
                if last and last >= self.target_premium:
                    if last < best_prem:
                        best_prem = last
                        best_sym = opt['symbol']
            except Exception:
                continue
        return best_sym, best_prem

    # ─── STRATEGY EXECUTION ───────────────────────────────────────────────────
    def execute_strategy(self):
        self.log("=" * 45, "info")
        self.log(f"EXECUTING {self.active_mode} STRATEGY", "success")
        self.log("=" * 45, "info")

        try:
            # Get BTC price
            if self.current_btc_price == 0:
                ticker = self.exchange.fetch_ticker('BTC/USDT')
                self.current_btc_price = ticker['last']

            atm = round(self.current_btc_price / 100) * 100
            call_strike = atm + 3000
            put_strike = atm - 3000

            self.log(f"BTC Spot: ${self.current_btc_price:,.0f} | ATM: ${atm:,.0f}", "info")
            self.log(f"Scanning options chain for ${self.target_premium:.0f} premium strikes...", "info")

            options = self.get_options_chain()
            call_symbol, call_premium = self.find_best_strike(options, 'call')
            put_symbol, put_premium = self.find_best_strike(options, 'put')

            if not call_symbol or not put_symbol:
                self.log("No live strikes found — using theoretical strikes.", "warn")
                call_symbol = f'BTC-{int(call_strike)}-C'
                call_premium = self.target_premium
                put_symbol = f'BTC-{int(put_strike)}-P'
                put_premium = self.target_premium
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
                    bal_info = self.exchange.fetch_balance()
                    live_balance = bal_info.get('free', {}).get('USDT', 0)
                    self.state['LIVE']['balance'] = live_balance
                    self.state['LIVE']['starting_balance'] = live_balance
                    self.log(f"Live Balance: ${live_balance:.2f} USDT", "info")
                except Exception as e:
                    self.log(f"Balance fetch failed: {e}", "error")
                    return

                call_size = max(1, int((live_balance * self.allocation_pct * self.leverage) / call_premium))
                put_size = max(1, int((live_balance * self.allocation_pct * self.leverage) / put_premium))

                if call_size < 1 or put_size < 1:
                    self.log("Insufficient balance for minimum lot size.", "error")
                    return

                # Place CALL orders
                for sym, size, prem, sl_m, tp_m, label in [
                    (call_symbol, call_size, call_premium, self.call_sl_mult, self.call_tp_mult, "CALL"),
                    (put_symbol, put_size, put_premium, self.put_sl_mult, self.put_tp_mult, "PUT")
                ]:
                    try:
                        self.exchange.set_margin_mode('isolated', sym)
                        self.exchange.set_leverage(self.leverage, sym)
                    except Exception:
                        pass
                    try:
                        self.log(f"[LIVE] PLACING {label} SELL {size}x {sym} @ MARKET", "warn")
                        self.exchange.create_order(sym, 'market', 'sell', size)
                        sl_price = round(prem * sl_m, 2)
                        tp_price = round(prem * tp_m, 2)
                        self.exchange.create_order(sym, 'stop', 'buy', size, sl_price)
                        self.exchange.create_order(sym, 'limit', 'buy', size, tp_price)
                        self.log(f"[LIVE] {label} ORDERS PLACED: SL=${sl_price} | TP=${tp_price}", "success")
                    except Exception as e:
                        self.log(f"[LIVE] {label} order error: {e}", "error")

                self.log("LIVE EXECUTION COMPLETE.", "success")

        except Exception as e:
            self.log(f"Strategy error: {e}", "error")


bot_instance = DeltaOptionsBot()
