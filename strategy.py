from config import DELTA_TARGET, DELTA_TOLERANCE
from logger import app_logger

class ShortStrangleStrategy:
    def __init__(self, api_client):
        self.api_client = api_client

    def find_strikes(self, target_delta=DELTA_TARGET, expiry_date=None, check_premium=True):
        """
        Finds the best Call and Put strikes based on the new strike selection rules.
        """
        res = self.api_client.get_tickers({
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        })
        
        if not res.get('success'):
            app_logger.error("Strategy: Failed to fetch option chain")
            return None, None
            
        tickers = res.get('result', [])
        expiry_tickers = []
        for t in tickers:
            symbol = t.get('symbol', '')
            if expiry_date and expiry_date not in symbol:
                continue
            if '-BTC-' not in symbol:
                continue
            expiry_tickers.append(t)
            
        if not expiry_tickers:
            app_logger.warning(f"Strategy: No tickers found for expiry {expiry_date}")
            return None, None
            
        # Get Current BTC Price
        btc_price = 0.0
        for t in expiry_tickers:
            spot = float(t.get('spot_price') or t.get('greeks', {}).get('spot') or 0)
            if spot > 0:
                btc_price = spot
                break
                
        if not btc_price or btc_price <= 0:
            try:
                res_btc = self.api_client.get_tickers({'symbol': 'BTCUSD'})
                if res_btc.get('success') and res_btc.get('result'):
                    for ticker in res_btc['result']:
                        if ticker.get('symbol') == 'BTCUSD':
                            btc_price = float(ticker.get('mark_price') or ticker.get('close') or ticker.get('last_price') or 0)
                            break
            except Exception:
                pass
                
        if not btc_price or btc_price <= 0:
            # Fallback to Binance
            try:
                import urllib.request
                import json
                req = urllib.request.Request(
                    'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT',
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    if 'price' in data:
                        btc_price = float(data['price'])
            except Exception:
                pass
                
        if not btc_price or btc_price <= 0:
            app_logger.error("Strategy: Could not resolve BTC price.")
            return None, None

        # Sorted list of unique strikes for this expiry
        all_strikes = sorted(list(set(float(t.get('strike_price', 0)) for t in expiry_tickers if t.get('strike_price'))))
        if len(all_strikes) < 11:
            app_logger.warning("Strategy: Insufficient strikes in option chain to apply OTM rules.")
            return None, None
            
        ATM = min(all_strikes, key=lambda s: abs(s - btc_price))
        atm_idx = all_strikes.index(ATM)

        # Separate and filter options
        eligible_calls = []
        eligible_puts = []
        for t in expiry_tickers:
            symbol = t.get('symbol', '')
            greeks = t.get('greeks') or {}
            delta = float(greeks.get('delta', 0))
            mark_price = float(t.get('mark_price', 0))
            strike = float(t.get('strike_price', 0))
            premium_inr = mark_price
            
            # Soft fallback/safety cap: absolute delta <= 0.45
            if abs(delta) > 0.45:
                continue
                
            c_type = t.get('contract_type', '').lower()
            item = {
                'symbol': symbol,
                'delta': delta,
                'mark_price': mark_price,
                'strike': strike,
                'product_id': t.get('product_id'),
                'premium_inr': premium_inr
            }
            
            if 'call' in c_type:
                if atm_idx + 5 < len(all_strikes) and strike >= all_strikes[atm_idx + 5]:
                    eligible_calls.append(item)
            elif 'put' in c_type:
                if atm_idx - 5 >= 0 and strike <= all_strikes[atm_idx - 5]:
                    eligible_puts.append(item)
                
        best_call = None
        best_put = None
        
        # Filter calls and puts that meet premium boundaries
        valid_pairs = []
        if check_premium:
            for c in eligible_calls:
                if not (100.0 <= c['premium_inr'] <= 250.0):
                    continue
                for p in eligible_puts:
                    if not (100.0 <= p['premium_inr'] <= 250.0):
                        continue
                    # Put premium must be <= 1.35 * Call premium
                    if p['premium_inr'] > 1.35 * c['premium_inr']:
                        continue
                    valid_pairs.append((c, p))

        if check_premium and valid_pairs:
            # Select the pair with the most balanced premiums (minimum difference)
            best_pair = min(valid_pairs, key=lambda pair: abs(pair[0]['premium_inr'] - pair[1]['premium_inr']))
            best_call, best_put = best_pair
            app_logger.info(
                f"Strategy: Selected balanced strikes (Call: {best_call['symbol']} Premium: {best_call['premium_inr']:.2f}, "
                f"Put: {best_put['symbol']} Premium: {best_put['premium_inr']:.2f}, "
                f"Diff: {abs(best_call['premium_inr'] - best_put['premium_inr']):.2f})"
            )
        else:
            # Soft fallback: closest to target delta (absolute cap of 0.45 individual delta)
            if eligible_calls and eligible_puts:
                best_call = min(eligible_calls, key=lambda x: abs(x['delta'] - target_delta))
                best_put = min(eligible_puts, key=lambda x: abs(x['delta'] - (-target_delta)))
                app_logger.info(
                    f"Strategy: Soft fallback to delta-based selection (Call: {best_call['symbol']} Delta: {best_call['delta']:.4f}, "
                    f"Put: {best_put['symbol']} Delta: {best_put['delta']:.4f})"
                )

        if not best_call or not best_put:
            app_logger.warning("Strategy: No Call or Put strikes could be resolved.")
            return None, None

        # Net Delta Safety Check
        net_delta = best_call['delta'] + best_put['delta']
        if abs(net_delta) > 0.15:
            app_logger.info(f"Strategy: Net Delta Safety Check triggered. Current Net Delta: {net_delta:.4f} (> 0.15)")
            if best_call['premium_inr'] >= best_put['premium_inr']:
                # Call side has higher premium, shift Call 1 strike further OTM (higher strike)
                curr_strike = best_call['strike']
                try:
                    curr_idx = all_strikes.index(curr_strike)
                    if curr_idx + 1 < len(all_strikes):
                        next_strike = all_strikes[curr_idx + 1]
                        next_call = None
                        for c in eligible_calls:
                            if c['strike'] == next_strike:
                                next_call = c
                                break
                        if not next_call:
                            for t in expiry_tickers:
                                if 'call' in t.get('contract_type', '').lower() and float(t.get('strike_price', 0)) == next_strike:
                                    g = t.get('greeks') or {}
                                    mp = float(t.get('mark_price', 0))
                                    next_call = {
                                        'symbol': t.get('symbol', ''),
                                        'delta': float(g.get('delta', 0)),
                                        'mark_price': mp,
                                        'strike': next_strike,
                                        'product_id': t.get('product_id'),
                                        'premium_inr': mp
                                    }
                                    break
                        if next_call:
                            best_call = next_call
                            app_logger.info(f"Strategy: Shifted Call OTM to strike {next_strike} (New Delta: {best_call['delta']:.4f})")
                except ValueError:
                    pass
            else:
                # Put side has higher premium, shift Put 1 strike further OTM (lower strike)
                curr_strike = best_put['strike']
                try:
                    curr_idx = all_strikes.index(curr_strike)
                    if curr_idx - 1 >= 0:
                        next_strike = all_strikes[curr_idx - 1]
                        next_put = None
                        for p in eligible_puts:
                            if p['strike'] == next_strike:
                                next_put = p
                                break
                        if not next_put:
                            for t in expiry_tickers:
                                if 'put' in t.get('contract_type', '').lower() and float(t.get('strike_price', 0)) == next_strike:
                                    g = t.get('greeks') or {}
                                    mp = float(t.get('mark_price', 0))
                                    next_put = {
                                        'symbol': t.get('symbol', ''),
                                        'delta': float(g.get('delta', 0)),
                                        'mark_price': mp,
                                        'strike': next_strike,
                                        'product_id': t.get('product_id'),
                                        'premium_inr': mp
                                    }
                                    break
                        if next_put:
                            best_put = next_put
                            app_logger.info(f"Strategy: Shifted Put OTM to strike {next_strike} (New Delta: {best_put['delta']:.4f})")
                except ValueError:
                    pass

        return best_call, best_put
