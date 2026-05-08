import os
import time
import datetime
import threading
import ccxt
import schedule

class DeltaOptionsBot:
    def __init__(self):
        self.running = False
        self.active_mode = "PAPER" # "LIVE" or "PAPER"
        self.thread = None
        
        # Completely separate states
        self.state = {
            'PAPER': {'logs': [], 'positions': {'call': None, 'put': None}, 'balance': 10000.0},
            'LIVE':  {'logs': [], 'positions': {'call': None, 'put': None}, 'balance': 0.0}
        }
        
        # Extended Strategy Parameters
        self.api_key = ""
        self.api_secret = ""
        self.leverage = 200
        self.target_premium = 100.0
        self.allocation_pct = 0.50
        
        # Independent Leg Parameters
        self.call_sl_mult = 2.0
        self.call_tp_mult = 0.05
        self.put_sl_mult = 2.0
        self.put_tp_mult = 0.05
        
        self.entry_time = "08:00"
        self.exchange = ccxt.delta({'enableRateLimit': True, 'options': {'defaultType': 'option'}})
        self.current_btc_price = 0.0

    def log(self, message, mtype="info"):
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        log_entry = {'time': timestamp, 'msg': message, 'type': mtype}
        try:
            print(f"[{self.active_mode}] [{timestamp}] {message}")
        except UnicodeEncodeError:
            print(f"[{self.active_mode}] [{timestamp}] {message.encode('ascii', 'replace').decode('ascii')}")
        
        logs = self.state[self.active_mode]['logs']
        logs.append(log_entry)
        if len(logs) > 300:
            logs.pop(0)

    def get_logs(self, mode):
        if mode not in self.state: mode = 'PAPER'
        return self.state[mode]['logs']
        
    def get_state(self, mode):
        if mode not in self.state: mode = 'PAPER'
        pos = self.state[mode]['positions']
        total_pnl = 0
        if pos['call']: total_pnl += pos['call']['pnl']
        if pos['put']: total_pnl += pos['put']['pnl']
            
        return {
            'running_mode': self.active_mode if self.running else None,
            'btc_price': self.current_btc_price,
            'balance': self.state[mode]['balance'] + total_pnl,
            'call': pos['call'],
            'put': pos['put'],
            'total_pnl': total_pnl
        }

    def start(self, config):
        if self.running:
            return False

        self.active_mode = config.get('mode', 'PAPER').upper()
        self.api_key = config.get('api_key', '')
        self.api_secret = config.get('api_secret', '')
        
        self.target_premium = float(config.get('target_premium', 100.0))
        self.allocation_pct = float(config.get('allocation_pct', 50.0)) / 100.0
        
        self.call_sl_mult = 1.0 + (float(config.get('call_stop_loss', 100.0)) / 100.0)
        self.call_tp_mult = 1.0 - (float(config.get('call_take_profit', 95.0)) / 100.0)
        self.put_sl_mult = 1.0 + (float(config.get('put_stop_loss', 100.0)) / 100.0)
        self.put_tp_mult = 1.0 - (float(config.get('put_take_profit', 95.0)) / 100.0)
        
        if self.active_mode == "LIVE":
            if not self.api_key or not self.api_secret:
                self.log("❌ ERROR: Cannot start LIVE mode without API keys.", "error")
                return False
            self.exchange = ccxt.delta({'apiKey': self.api_key, 'secret': self.api_secret, 'enableRateLimit': True, 'options': {'defaultType': 'option'}})
            self.log("🔴 LIVE TRADING ENGINE ONLINE. REAL FUNDS AT RISK.", "warn")
        else:
            self.exchange = ccxt.delta({'enableRateLimit': True, 'options': {'defaultType': 'option'}}) 
            self.log("🔵 PAPER TRADING ENGINE ONLINE. Using Live Market Data.", "info")

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        threading.Thread(target=self._market_data_loop, daemon=True).start()
        return True

    def stop(self):
        self.running = False
        self.log("⛔ ENGINE HALTED.", "error")
        return True

    def trigger_execution(self):
        self.log("⚡ INITIATING MANUAL EXECUTION SWEEP...", "info")
        threading.Thread(target=self.execute_strategy, daemon=True).start()

    def _run_loop(self):
        schedule.clear()
        self.log(f"⏰ Automated Schedule set for {self.entry_time} IST.", "info")
        schedule.every().day.at(self.entry_time).do(self.execute_strategy)
        while self.running:
            schedule.run_pending()
            time.sleep(1)
            
    def _market_data_loop(self):
        while self.running:
            try:
                ticker = self.exchange.fetch_ticker('BTC/USDT')
                self.current_btc_price = ticker['last']
                
                pos = self.state[self.active_mode]['positions']
                
                if pos['call']:
                    c = pos['call']
                    dist = c['strike'] - self.current_btc_price
                    sim_premium = max(1.0, c['entry_price'] - (dist * 0.01))
                    c['current_price'] = sim_premium
                    c['pnl'] = (c['entry_price'] - c['current_price']) * c['size']
                    
                if pos['put']:
                    p = pos['put']
                    dist = self.current_btc_price - p['strike']
                    sim_premium = max(1.0, p['entry_price'] - (dist * 0.01))
                    p['current_price'] = sim_premium
                    p['pnl'] = (p['entry_price'] - p['current_price']) * p['size']
            except Exception as e:
                pass
            time.sleep(3)

    def get_next_day_options(self):
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
        valid_options = [opt for opt in options if opt.get('optionType') == option_type]
        best_option = None
        best_premium = float('inf')
        
        for opt in valid_options:
            try:
                ticker = self.exchange.fetch_ticker(opt['symbol'])
                last_price = ticker.get('last')
                if last_price is not None and last_price >= self.target_premium:
                    if last_price < best_premium:
                        best_premium = last_price
                        best_option = opt['symbol']
            except Exception:
                continue
        return best_option, best_premium

    def execute_strategy(self):
        self.log("=========================================", "info")
        self.log(f"🚀 EXECUTING {self.active_mode} STRATEGY PIPELINE", "success")
        self.log("=========================================", "info")
        
        try:
            if self.current_btc_price == 0:
                ticker = self.exchange.fetch_ticker('BTC/USDT')
                self.current_btc_price = ticker['last']

            atm_strike = round(self.current_btc_price / 100) * 100
            call_strike = atm_strike + 3000 
            put_strike = atm_strike - 3000
            
            self.log(f"📊 Analyzing live orderbook for optimal strikes...", "info")
            options = self.get_next_day_options()
            call_symbol, call_premium = self.find_best_strike(options, 'call')
            put_symbol, put_premium = self.find_best_strike(options, 'put')

            if not call_symbol or not put_symbol:
                self.log("❌ Could not find valid strikes with target premium. Reverting to theoretical strikes.", "warn")
                call_symbol = f'BTC-{int(call_strike)}C'
                call_premium = self.target_premium
                put_symbol = f'BTC-{int(put_strike)}P'
                put_premium = self.target_premium
            else:
                self.log(f"🎯 Selected Strikes from Delta -> Call: {call_symbol}, Put: {put_symbol}", "info")
            
            if self.active_mode == "PAPER":
                balance = self.state['PAPER']['balance']
                pos = self.state['PAPER']['positions']
                
                pos['call'] = {
                    'symbol': call_symbol,
                    'strike': call_strike,
                    'entry_price': call_premium,
                    'current_price': call_premium,
                    'size': int((balance * self.allocation_pct * self.leverage) / call_premium),
                    'pnl': 0.0
                }
                pos['put'] = {
                    'symbol': put_symbol,
                    'strike': put_strike,
                    'entry_price': put_premium,
                    'current_price': put_premium,
                    'size': int((balance * self.allocation_pct * self.leverage) / put_premium),
                    'pnl': 0.0
                }
                
                self.log(f"✅ CALL LEG: Sold {pos['call']['size']}x {pos['call']['symbol']} @ ${call_premium}", "success")
                self.log(f"   ↳ Risk Params -> SL: {self.call_sl_mult}x Prem | TP: {self.call_tp_mult}x Prem", "warn")
                
                self.log(f"✅ PUT LEG:  Sold {pos['put']['size']}x {pos['put']['symbol']} @ ${put_premium}", "success")
                self.log(f"   ↳ Risk Params -> SL: {self.put_sl_mult}x Prem | TP: {self.put_tp_mult}x Prem", "warn")
                
                self.log("🎉 EXECUTION COMPLETE. Tracking live PnL...", "success")
                return

            if self.active_mode == "LIVE":
                try:
                    balance_info = self.exchange.fetch_balance()
                    balance = balance_info['free'].get('USDT', 0)
                except Exception as e:
                    self.log(f"❌ Failed to fetch balance: {e}", "error")
                    return

                call_size = int((balance * self.allocation_pct * self.leverage) / call_premium)
                put_size = int((balance * self.allocation_pct * self.leverage) / put_premium)
                
                if call_size < 1 or put_size < 1:
                    self.log("❌ Insufficient balance for minimum lot size.", "error")
                    return
                
                # Execute Calls
                try:
                    self.exchange.set_margin_mode('isolated', call_symbol)
                    self.exchange.set_leverage(self.leverage, call_symbol)
                except Exception as e:
                    self.log(f"⚠️ Could not set leverage for {call_symbol}: {e}", "warn")
                
                try:
                    self.log(f"📈 [LIVE] SELLING {call_size}x {call_symbol} @ Market", "info")
                    self.exchange.create_order(call_symbol, 'market', 'sell', call_size)
                    
                    sl_price = call_premium * self.call_sl_mult
                    self.log(f"🛑 [LIVE] STOP LOSS BUY {call_symbol} @ {sl_price}", "info")
                    self.exchange.create_order(call_symbol, 'stop', 'buy', call_size, sl_price)
                    
                    tp_price = call_premium * self.call_tp_mult
                    self.log(f"✅ [LIVE] TAKE PROFIT BUY {call_symbol} @ {tp_price}", "info")
                    self.exchange.create_order(call_symbol, 'limit', 'buy', call_size, tp_price)
                except Exception as e:
                    self.log(f"❌ Order error on Call leg: {e}", "error")

                # Execute Puts
                try:
                    self.exchange.set_margin_mode('isolated', put_symbol)
                    self.exchange.set_leverage(self.leverage, put_symbol)
                except Exception as e:
                    self.log(f"⚠️ Could not set leverage for {put_symbol}: {e}", "warn")

                try:
                    self.log(f"📈 [LIVE] SELLING {put_size}x {put_symbol} @ Market", "info")
                    self.exchange.create_order(put_symbol, 'market', 'sell', put_size)
                    
                    sl_price = put_premium * self.put_sl_mult
                    self.log(f"🛑 [LIVE] STOP LOSS BUY {put_symbol} @ {sl_price}", "info")
                    self.exchange.create_order(put_symbol, 'stop', 'buy', put_size, sl_price)
                    
                    tp_price = put_premium * self.put_tp_mult
                    self.log(f"✅ [LIVE] TAKE PROFIT BUY {put_symbol} @ {tp_price}", "info")
                    self.exchange.create_order(put_symbol, 'limit', 'buy', put_size, tp_price)
                except Exception as e:
                    self.log(f"❌ Order error on Put leg: {e}", "error")
                    
                self.log("🎉 LIVE EXECUTION COMPLETE.", "success")

        except Exception as e:
            self.log(f"❌ Execution Error: {e}", "error")

bot_instance = DeltaOptionsBot()
