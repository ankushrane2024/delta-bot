from config import DELTA_TARGET, DELTA_TOLERANCE, RECOST_DELTA_MIN, RECOST_DELTA_MAX, PREMIUM_MIN_USDT, PREMIUM_MAX_USDT
from logger import app_logger

class ShortStrangleStrategy:
    def __init__(self, api_client):
        self.api_client = api_client

    def find_strikes(self, target_delta=DELTA_TARGET, expiry_date=None, check_premium=True):
        """
        Finds the best Call and Put strikes based on target Delta AND Premium rules.
        """
        res = self.api_client.get_tickers({
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        })
        
        if not res.get('success'):
            app_logger.error("Strategy: Failed to fetch option chain")
            return None, None
            
        tickers = res.get('result', [])
        calls = []
        puts = []
        
        for t in tickers:
            symbol = t.get('symbol', '')
            if expiry_date and expiry_date not in symbol:
                continue
                
            greeks = t.get('greeks')
            if not greeks:
                continue
                
            delta = float(greeks.get('delta', 0))
            mark_price = float(t.get('mark_price', 0))
            
            # Premium Check (~70-100 INR equivalent -> ~0.85 to 1.20 USDT)
            if check_premium and not (PREMIUM_MIN_USDT <= mark_price <= PREMIUM_MAX_USDT):
                continue
            
            if 'call' in t.get('contract_type', '').lower():
                calls.append({'symbol': symbol, 'delta': delta, 'mark_price': mark_price, 'product_id': t.get('product_id')})
            elif 'put' in t.get('contract_type', '').lower():
                puts.append({'symbol': symbol, 'delta': delta, 'mark_price': mark_price, 'product_id': t.get('product_id')})
        
        if not calls or not puts:
            app_logger.warning("Strategy: No strikes found matching both Delta and Premium rules.")
            return None, None

        # Find best Call strike (delta closest to target)
        best_call = min(calls, key=lambda x: abs(x['delta'] - target_delta))
        # Find best Put strike (delta closest to -target)
        best_put = min(puts, key=lambda x: abs(x['delta'] - (-target_delta)))
        
        return best_call, best_put

    def get_recost_strikes(self, expiry_date):
        """Finds wider strikes for RECOST re-entry (0.18-0.20 delta). No premium bounds for recost."""
        target = (RECOST_DELTA_MIN + RECOST_DELTA_MAX) / 2
        return self.find_strikes(target_delta=target, expiry_date=expiry_date, check_premium=False)
