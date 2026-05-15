from config import HEDGE_SYMBOL
from logger import app_logger, trade_logger
import math

class ExecutionHandler:
    def __init__(self, api_client, mode='PAPER'):
        self.api_client = api_client
        self.mode = mode
        self.active_positions = {} # symbol -> data
        self.hedge_position = 0 # Net BTC futures size

    def execute_strangle(self, call_opt, put_opt, size):
        """Places the short strangle orders."""
        app_logger.info(f"Execution: Placing {self.mode} Strangle. Size: {size}")
        
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
            else:
                app_logger.info(f"Execution [PAPER]: Simulating sell of {opt['symbol']} @ {opt['mark_price']}")
                self.active_positions[opt['symbol']] = {
                    'entry_price': opt['mark_price'],
                    'size': size,
                    'product_id': opt['product_id'],
                    'side': 'SELL'
                }
                results.append({'success': True})
        
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
        if self.hedge_position != 0:
            self.hedge_with_futures(0, action="CLOSE_HEDGE")

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
