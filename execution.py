from config import HEDGE_SYMBOL, HEDGE_RETRY_COUNT, HEDGE_RETRY_DELAY, HEDGE_LIMIT_ORDER_SPREAD
from logger import app_logger, trade_logger
import math
import db_manager

class ExecutionHandler:
    def __init__(self, api_client, mode='PAPER'):
        self.api_client = api_client
        self.mode = mode
        
        # In PAPER mode, try to recover active positions from cloud DB after a server reboot
        if self.mode != 'LIVE':
            self.active_positions = db_manager.load_active_positions()
        else:
            self.active_positions = {} # symbol -> data
            
        self.hedge_position = 0 # Net BTC futures size
        self.hedge_size_btc = 0.0  # Actual BTC size of current hedge
        self.hedge_order_id = None  # Last hedge order ID
        self.hedge_entry_price = 0.0

    def save_state(self):
        """Persists the current paper trading active positions to the cloud database."""
        if self.mode != 'LIVE':
            db_manager.save_active_positions(self.active_positions)

    def execute_strangle(self, call_opt, put_opt, size):
        """Places the short strangle orders."""
        app_logger.info(f"Execution: Placing {self.mode} Strangle. Size: {size}")
        
        # In PAPER mode, completely skip real API calls and only do pure simulation
        if self.mode != 'LIVE':
            import random
            import time
            from utils import get_ist_now
            
            # Apply simulated execution delay of 200–500 milliseconds
            delay_ms = random.randint(200, 500)
            app_logger.info(f"Execution [PAPER]: Simulating execution delay of {delay_ms}ms...")
            time.sleep(delay_ms / 1000.0)
            
            entry_time_str = get_ist_now().isoformat()
            results = []
            for opt in [call_opt, put_opt]:
                # Apply realistic entry slippage (0.2% to 0.8% of premium)
                raw_mark = float(opt.get('mark_price', 0))
                entry_slippage = random.uniform(0.002, 0.008) * raw_mark if raw_mark > 0 else 0.5
                simulated_entry_price = raw_mark + entry_slippage
                leg_type = 'call' if 'call' in opt.get('contract_type', '').lower() or 'C' in opt.get('symbol', '')[-3:] else 'put'
                
                app_logger.info(f"Execution [PAPER]: Simulating sell of {opt['symbol']} @ {simulated_entry_price:.4f} (slippage: +{entry_slippage:.2f})")
                self.active_positions[opt['symbol']] = {
                    'entry_price': simulated_entry_price,
                    'entry_price_raw': raw_mark,
                    'size': size,
                    'product_id': opt['product_id'],
                    'side': 'SELL',
                    'leg_type': leg_type,
                    'strike': opt.get('strike_price', opt.get('strike', 0)),
                    'entry_time': entry_time_str,
                }
                results.append({'success': True})
            
            self.save_state()
            return results

        # ── LIVE ──
        results = []
        for opt in [call_opt, put_opt]:
            # Set Portfolio Margin mode strictly before executing options
            if self.mode == 'LIVE':
                self.api_client.set_margin_mode(opt['product_id'], "portfolio")
                res = self.api_client.place_order(opt['product_id'], 'sell', size)
                results.append(res)
                if res.get('success'):
                    app_logger.info(f"Execution: Successfully sold {opt['symbol']}")
                    self.active_positions[opt['symbol']] = {
                        'entry_price': opt['mark_price'],
                        'size': size,
                        'product_id': opt['product_id'],
                        'side': 'SELL'
                    }
                else:
                    app_logger.error(f"Execution: Failed to sell {opt['symbol']}: {res}")
        
        return results

    def close_all(self, reason="Manual"):
        """Closes all active options positions and hedges."""
        app_logger.info(f"Execution: Closing all positions due to {reason}")
        
        for symbol, data in list(self.active_positions.items()):
            if self.mode == 'LIVE':
                res = self.api_client.place_order(data['product_id'], 'buy', data['size'])
                if res.get('success'):
                    app_logger.info(f"Execution: Successfully closed {symbol}")
                    del self.active_positions[symbol]
                else:
                    app_logger.error(f"Execution: Failed to close {symbol}: {res}")
            else:
                app_logger.info(f"Execution [PAPER]: Simulating close of {symbol}")
                del self.active_positions[symbol]
        
        # Close Hedge
        if self.hedge_position != 0 or abs(self.hedge_size_btc) > 0.0001:
            self.close_hedge()
            
        self.save_state()

    def partial_close(self, percentage=0.5):
        """Closes a portion of all active positions."""
        app_logger.info(f"Execution: Partial close {percentage*100}% triggered")
        
        for symbol, data in self.active_positions.items():
            close_size = int(data['size'] * percentage)
            if close_size <= 0: continue
            
            if self.mode == 'LIVE':
                res = self.api_client.place_order(data['product_id'], 'buy', close_size)
                if res.get('success'):
                    data['size'] -= close_size
                    app_logger.info(f"Execution: Successfully partially closed {symbol}")
            else:
                data['size'] -= close_size
                app_logger.info(f"Execution [PAPER]: Simulating partial close of {symbol}")
                
        self.save_state()

    def hedge_with_futures(self, target_delta, action="REBALANCE"):
        """
        Executes a market order on BTC Perpetual (HEDGE_SYMBOL) to neutralize Delta.
        If target_delta is positive, we are long delta -> Need to SHORT futures.
        If target_delta is negative, we are short delta -> Need to LONG futures.
        """
        # Calculate required futures size to neutralize Delta
        # Delta 1.0 = 1 BTC. If contract is 1 USD per contract or 0.001 BTC, we calculate.
        # Assuming we need to offset the exact BTC delta amount.
        # For simplicity, assuming the target delta translates to N contracts of the Hedge Symbol.
        
        required_hedge_position = -target_delta # Inverse the delta to hedge
        order_qty = required_hedge_position - self.hedge_position
        
        if math.isclose(order_qty, 0, abs_tol=0.001):
            return

        side = 'buy' if order_qty > 0 else 'sell'
        size_to_execute = abs(int(order_qty * 1000)) # Approximation depending on contract multiplier
        if size_to_execute == 0:
            return

        app_logger.info(f"Execution: Hedging {action}. Required Delta Offset: {order_qty:.4f}. Executing {side} {size_to_execute} contracts.")

        if self.mode == 'LIVE':
            # Resolve Product ID for Hedge Symbol
            res_ticker = self.api_client.get_tickers({'symbol': HEDGE_SYMBOL})
            if res_ticker.get('success') and res_ticker.get('result'):
                prod_id = res_ticker['result'][0]['product_id']
                # Execute Market Order
                res = self.api_client.place_order(prod_id, side, size_to_execute, 'market_order')
                if res.get('success'):
                    self.hedge_position = required_hedge_position
                    app_logger.info(f"Execution: Successfully hedged via {HEDGE_SYMBOL}")
                else:
                    app_logger.error(f"Execution: Hedging Failed: {res}")
            else:
                app_logger.error(f"Execution: Could not find product ID for {HEDGE_SYMBOL}")
        else:
            app_logger.info(f"Execution [PAPER]: Simulating hedge {side} {size_to_execute} on {HEDGE_SYMBOL}")
            self.hedge_position = required_hedge_position

    def place_hedge_order(self, size_btc, direction, use_limit=False):
        """
        Places a hedge order on BTCUSD perpetual with retry logic.
        
        Args:
            size_btc: Size in BTC to hedge
            direction: 'buy' or 'sell' 
            use_limit: If True, use limit order within 0.1% of mark price
            
        Returns:
            dict with 'success', 'order_id', 'fill_price' or None on failure
        """
        if size_btc <= 0:
            return None
            
        contract_size = abs(int(size_btc * 1000))  # Convert BTC to contracts
        if contract_size == 0:
            contract_size = 1
        
        for attempt in range(1, HEDGE_RETRY_COUNT + 2):  # Initial + retries
            try:
                # Resolve product ID and mark price for both LIVE and PAPER
                res_ticker = self.api_client.get_tickers({'symbol': HEDGE_SYMBOL})
                # Check for array response and filter symbol
                if res_ticker and res_ticker.get('success') and res_ticker.get('result'):
                    data_list = res_ticker.get('result')
                    for item in data_list:
                        if item.get('symbol') == HEDGE_SYMBOL:
                            res_ticker['result'] = [item]
                            break
                            
                if not (res_ticker.get('success') and res_ticker.get('result')):
                    app_logger.error(f"Hedge: Could not find {HEDGE_SYMBOL} product ID (attempt {attempt})")
                    if attempt <= HEDGE_RETRY_COUNT:
                        import time
                        time.sleep(HEDGE_RETRY_DELAY)
                        continue
                    return None
                
                prod_id = res_ticker['result'][0]['product_id']
                mark_price = float(res_ticker['result'][0].get('mark_price', 0))
                
                if self.mode == 'LIVE':
                    
                    if use_limit and mark_price > 0:
                        # Place limit order within 0.1% of mark price
                        if direction == 'buy':
                            limit_price = round(mark_price * (1 + HEDGE_LIMIT_ORDER_SPREAD), 2)
                        else:
                            limit_price = round(mark_price * (1 - HEDGE_LIMIT_ORDER_SPREAD), 2)
                        
                        res = self.api_client.place_order(
                            prod_id, direction, contract_size, 
                            order_type='limit_order', limit_price=limit_price
                        )
                    else:
                        res = self.api_client.place_order(
                            prod_id, direction, contract_size, 'market_order'
                        )
                    
                    if res.get('success'):
                        order_id = res.get('result', {}).get('id', 'N/A')
                        fill_price = float(res.get('result', {}).get('average_fill_price', mark_price))
                        signed_change = size_btc if direction == 'buy' else -size_btc
                        self.hedge_size_btc += signed_change
                        self.hedge_order_id = order_id
                        # FIX: DO NOT overwrite entry price — SmartHedgingManager tracks weighted avg
                        if self.hedge_entry_price <= 0:
                            self.hedge_entry_price = fill_price  # First fill only
                        app_logger.info(f"Hedge: Order filled. ID: {order_id}, Size: {contract_size}, Price: {fill_price}")
                        return {'success': True, 'order_id': order_id, 'fill_price': fill_price}
                    else:
                        app_logger.error(f"Hedge: Order failed (attempt {attempt}): {res}")
                else:
                    # PAPER mode simulation
                    import random
                    order_id = f"PAPER-HEDGE-{random.randint(10000, 99999)}"
                    signed_change = size_btc if direction == 'buy' else -size_btc
                    self.hedge_size_btc += signed_change
                    self.hedge_order_id = order_id
                    self.hedge_position += signed_change
                    # FIX: Only set entry_price on first fill; subsequent fills tracked by SmartHedgingManager
                    if self.hedge_entry_price <= 0:
                        self.hedge_entry_price = mark_price
                    app_logger.info(f"Hedge [PAPER]: Simulated {direction} {contract_size} contracts at {mark_price}. ID: {order_id}")
                    return {'success': True, 'order_id': order_id, 'fill_price': mark_price}
                    
            except Exception as e:
                app_logger.error(f"Hedge: Exception on attempt {attempt}: {e}")
            
            if attempt <= HEDGE_RETRY_COUNT:
                import time
                app_logger.info(f"Hedge: Retrying in {HEDGE_RETRY_DELAY}s... (attempt {attempt + 1})")
                time.sleep(HEDGE_RETRY_DELAY)
        
        app_logger.error(f"Hedge: All {HEDGE_RETRY_COUNT + 1} attempts failed!")
        return None

    def close_hedge(self):
        """Closes all active hedge positions."""
        if abs(self.hedge_size_btc) < 0.0001 and self.hedge_position == 0:
            return
        
        direction = 'sell' if self.hedge_size_btc > 0 or self.hedge_position > 0 else 'buy'
        size = abs(self.hedge_size_btc) if abs(self.hedge_size_btc) > 0 else abs(self.hedge_position)
        
        app_logger.info(f"Hedge: Closing hedge position. Size: {size:.6f} BTC")
        result = self.place_hedge_order(size, direction)
        
        if result and result['success']:
            self.hedge_size_btc = 0.0
            self.hedge_position = 0
            self.hedge_order_id = None
            self.hedge_entry_price = 0.0
            app_logger.info("Hedge: All hedge positions closed")
        else:
            app_logger.error("Hedge: Failed to close hedge positions")
