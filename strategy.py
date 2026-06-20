from config import DELTA_TARGET, DELTA_TOLERANCE, MIN_OTM_STRIKES, PUT_SKEW_CAP, NET_DELTA_ENTRY_LIMIT
from logger import app_logger

class ShortStrangleStrategy:
    def __init__(self, api_client):
        self.api_client = api_client

    def find_strikes(self, target_delta=DELTA_TARGET, expiry_date=None, check_premium=True, dvol_provider=None):
        """
        Finds the best Call and Put strikes based on the advanced strike selection rules.
        
        Section 1 Rules Applied:
        - Use Deribit DVOL for premium target range (if dvol_provider given)
        - Minimum MIN_OTM_STRIKES (4) strikes OTM from ATM
        - Put premium <= PUT_SKEW_CAP (1.35) × Call premium
        - Net Delta at entry <= NET_DELTA_ENTRY_LIMIT (0.15)
        - If |Net Delta| > 0.15 → Shift higher premium leg 1 strike further OTM (only once)
        
        Args:
            target_delta: Target delta for delta-based fallback selection
            expiry_date: Expiry date string to filter options (e.g., "210526")
            check_premium: If True, apply premium-based pair selection
            dvol_provider: DVOLProvider instance for IV-based premium ranges (optional)
            
        Returns:
            (best_call, best_put) tuple or (None, None) if no valid strikes found
        """
        res = self.api_client.get_tickers({
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        })
        
        if not res or not res.get('success'):
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

        # Determine premium range from DVOL provider (Section 1: IV-Based Premium Target)
        if dvol_provider and check_premium:
            premium_min, premium_max = dvol_provider.get_premium_range()
            current_dvol = dvol_provider.get_current_dvol()
            app_logger.info(
                f"Strategy: Using DVOL-based premium range. DVOL: {current_dvol:.2f}%, "
                f"Target: ${premium_min}–${premium_max}"
            )
        else:
            premium_min, premium_max = 100, 250  # Legacy fallback
            app_logger.info(f"Strategy: Using legacy premium range ${premium_min}–${premium_max}")

        # Separate and filter options (Section 1: Minimum MIN_OTM_STRIKES OTM from ATM)
        min_otm = MIN_OTM_STRIKES  # 5 strikes OTM minimum
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
                if atm_idx + min_otm < len(all_strikes) and strike >= all_strikes[atm_idx + min_otm]:
                    eligible_calls.append(item)
            elif 'put' in c_type:
                if atm_idx - min_otm >= 0 and strike <= all_strikes[atm_idx - min_otm]:
                    eligible_puts.append(item)
                
        best_call = None
        best_put = None
        
        # Filter calls and puts that meet premium boundaries (Section 1: IV-Based Premium Target)
        valid_pairs = []
        if check_premium:
            for c in eligible_calls:
                # STRICT REQUIREMENT: Both legs must have premium >= $50 USD
                if c['premium_inr'] < 50:
                    continue
                if not (premium_min <= c['premium_inr'] <= premium_max):
                    continue
                for p in eligible_puts:
                    if p['premium_inr'] < 50:
                        continue
                    if not (premium_min <= p['premium_inr'] <= premium_max):
                        continue
                    # Put premium must be <= PUT_SKEW_CAP * Call premium (Section 1)
                    if p['premium_inr'] > PUT_SKEW_CAP * c['premium_inr']:
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

        # Net Delta Safety Check (Section 1: Net Delta at entry <= 0.15)
        net_delta = best_call['delta'] + best_put['delta']
        if abs(net_delta) > NET_DELTA_ENTRY_LIMIT:
            app_logger.info(f"Strategy: Net Delta Safety Check triggered. Current Net Delta: {net_delta:.4f} (> {NET_DELTA_ENTRY_LIMIT})")
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

        # Log final selection with net delta
        final_net_delta = best_call['delta'] + best_put['delta']
        app_logger.info(
            f"Strategy: Final selection — Call: {best_call['symbol']} (Delta={best_call['delta']:.4f}, P=${best_call['premium_inr']:.2f}), "
            f"Put: {best_put['symbol']} (Delta={best_put['delta']:.4f}, P=${best_put['premium_inr']:.2f}), "
            f"Net Delta: {final_net_delta:.4f}"
        )

        return best_call, best_put
