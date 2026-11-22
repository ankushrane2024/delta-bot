import config
from config import MIN_OTM_STRIKES, PUT_SKEW_CAP, NET_DELTA_ENTRY_LIMIT, MIN_ENTRY_PREMIUM
from logger import app_logger


def find_strikes_straddle_width(api_client, expiry_date=None):
    """
    Balance BTC Midnight Strangle — Straddle Width Strike Selection.
    Call Strike = ATM + CALL_STRADDLE_MULT × ATM_Straddle_Price
    Put  Strike = ATM - PUT_STRADDLE_MULT  × ATM_Straddle_Price
    """
    call_mult = getattr(config, 'CALL_STRADDLE_MULT', 1.6)
    put_mult  = getattr(config, 'PUT_STRADDLE_MULT',  2.3)

    res = api_client.get_tickers({
        'contract_types': 'call_options,put_options',
        'underlying_asset_symbol': 'BTC'
    })
    if not res or not res.get('success'):
        app_logger.error("StraddleWidth: Failed to fetch option chain")
        return None, None

    tickers = res.get('result', [])

    # Auto-detect expiry if not supplied
    if not expiry_date:
        from datetime import datetime
        from utils import get_ist_now
        available = set()
        for t in tickers:
            sym = t.get('symbol', '')
            if '-BTC-' in sym:
                try:
                    exp_str = sym.split('-')[-1]
                    if len(exp_str) == 6 and exp_str.isdigit():
                        available.add(exp_str)
                except Exception:
                    pass
        if available:
            now_ist = get_ist_now()
            valid = [(datetime.strptime(e, '%d%m%y'), e) for e in available
                     if len(e) == 6]
            valid.sort()
            expiry_date = next(
                (e for d, e in valid if d.date() >= now_ist.date()),
                valid[0][1] if valid else None
            )

    expiry_tickers = [t for t in tickers
                      if expiry_date and expiry_date in t.get('symbol', '')
                      and '-BTC-' in t.get('symbol', '')]

    if not expiry_tickers:
        app_logger.warning(f"StraddleWidth: No tickers for expiry {expiry_date}")
        return None, None

    # BTC spot price
    btc_price = 0.0
    for t in expiry_tickers:
        p = float(t.get('spot_price') or t.get('greeks', {}).get('spot') or 0)
        if p > 0:
            btc_price = p
            break
    if not btc_price:
        try:
            r2 = api_client.get_tickers({'symbol': 'BTCUSD'})
            if r2.get('success') and r2.get('result'):
                for t in r2['result']:
                    if t.get('symbol') == 'BTCUSD':
                        btc_price = float(t.get('mark_price') or t.get('close') or 0)
                        break
        except Exception:
            pass

    if not btc_price:
        app_logger.error("StraddleWidth: Could not resolve BTC price")
        return None, None

    # ATM straddle price = ATM Call mark + ATM Put mark
    all_strikes = sorted(set(
        float(t.get('strike_price', 0)) for t in expiry_tickers if t.get('strike_price')
    ))
    if not all_strikes:
        return None, None

    atm_strike = min(all_strikes, key=lambda s: abs(s - btc_price))

    atm_call_prem = 0.0
    atm_put_prem  = 0.0
    for t in expiry_tickers:
        s = float(t.get('strike_price', 0))
        ct = t.get('contract_type', '').lower()
        mp = float(t.get('mark_price', 0))
        if s == atm_strike:
            if 'call' in ct:
                atm_call_prem = mp
            elif 'put' in ct:
                atm_put_prem = mp

    atm_straddle = atm_call_prem + atm_put_prem
    if atm_straddle <= 0:
        app_logger.warning("StraddleWidth: ATM straddle price is 0 — falling back to 1% of BTC price")
        atm_straddle = btc_price * 0.01

    call_target_strike = atm_strike + call_mult * atm_straddle
    put_target_strike  = atm_strike - put_mult  * atm_straddle

    app_logger.info(
        f"StraddleWidth: BTC={btc_price:.0f}, ATM={atm_strike:.0f}, "
        f"Straddle={atm_straddle:.2f}, "
        f"Call target={call_target_strike:.0f} (+{call_mult}x), "
        f"Put target={put_target_strike:.0f} (-{put_mult}x)"
    )

    # Find closest available strikes
    best_call = None
    best_put  = None
    best_call_dist = float('inf')
    best_put_dist  = float('inf')

    for t in expiry_tickers:
        s  = float(t.get('strike_price', 0))
        ct = t.get('contract_type', '').lower()
        mp = float(t.get('mark_price', 0))
        if mp <= 0.0:
            continue   # Skip zero or negative price options

        greeks = t.get('greeks') or {}
        delta  = float(greeks.get('delta', 0))

        item = {
            'symbol':     t.get('symbol'),
            'strike':     s,
            'mark_price': mp,
            'premium_inr': mp,
            'delta':      delta,
            'product_id': t.get('product_id'),
            'underlying_price': btc_price,
        }

        if 'call' in ct and s >= atm_strike:
            dist = abs(s - call_target_strike)
            if dist < best_call_dist:
                best_call_dist = dist
                best_call = item

        elif 'put' in ct and s <= atm_strike:
            dist = abs(s - put_target_strike)
            if dist < best_put_dist:
                best_put_dist = dist
                best_put = item

    if best_call and best_put:
        app_logger.info(
            f"StraddleWidth: Selected CE={best_call['symbol']} "
            f"@${best_call['mark_price']:.2f} | "
            f"PE={best_put['symbol']} @${best_put['mark_price']:.2f}"
        )
    else:
        app_logger.warning("StraddleWidth: Could not find suitable Call or Put strikes")

    return best_call, best_put


class ShortStrangleStrategy:
    def __init__(self, api_client):
        self.api_client = api_client

    def find_strikes(self, target_delta=0.15, expiry_date=None, check_premium=True, dvol_provider=None, force=False):
        """
        Finds the best Call and Put strikes.
        Primary: Balance BTC Midnight Strangle (Straddle Width: CE = ATM + 1.6x, PE = ATM - 2.3x)
        Fallback: Delta & DVOL-based selection.
        """
        # ── PRIMARY STRATEGY: Balance BTC Midnight Strangle (Straddle Width) ──
        try:
            sw_call, sw_put = find_strikes_straddle_width(self.api_client, expiry_date=expiry_date)
            if sw_call and sw_put:
                app_logger.info(
                    f"Strategy [Balance BTC]: Successfully selected Straddle Width strikes — "
                    f"CE: {sw_call['symbol']} (Strike={sw_call['strike']:.0f}, Prem=${sw_call['mark_price']:.2f}) | "
                    f"PE: {sw_put['symbol']} (Strike={sw_put['strike']:.0f}, Prem=${sw_put['mark_price']:.2f})"
                )
                return sw_call, sw_put
        except Exception as sw_err:
            app_logger.warning(f"Strategy: Straddle width strike selection notice: {sw_err}")

        res = self.api_client.get_tickers({
            'contract_types': 'call_options,put_options',
            'underlying_asset_symbol': 'BTC'
        })
        
        if not res or not res.get('success'):
            app_logger.error("Strategy: Failed to fetch option chain")
            return None, None
            
        tickers = res.get('result', [])
        
        # If no expiry date is forced, find the absolute closest available expiry date in the market.
        if not expiry_date:
            from datetime import datetime
            from utils import get_ist_now
            
            available_expiries = set()
            for t in tickers:
                sym = t.get('symbol', '')
                if '-BTC-' in sym:
                    try:
                        exp_str = sym.split('-')[-1]
                        if len(exp_str) == 6 and exp_str.isdigit():
                            available_expiries.add(exp_str)
                    except:
                        pass
            
            if available_expiries:
                now_ist = get_ist_now()
                valid_expiries = []
                for exp_str in available_expiries:
                    try:
                        exp_date = datetime.strptime(exp_str, '%d%m%y')
                        valid_expiries.append((exp_date, exp_str))
                    except:
                        pass
                
                if valid_expiries:
                    valid_expiries.sort(key=lambda x: x[0])
                    best_expiry = None
                    for exp_date, exp_str in valid_expiries:
                        if exp_date.date() >= now_ist.date():
                            best_expiry = exp_str
                            break
                    if not best_expiry:
                        best_expiry = valid_expiries[0][1]
                        
                    expiry_date = best_expiry
                    app_logger.info(f"Strategy: Auto-detected nearest available expiry: {expiry_date}")
                    
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
        import datetime
        ist_now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
        is_weekend = ist_now.weekday() >= 5  # 5=Sat, 6=Sun
        
        base_min = MIN_ENTRY_PREMIUM
        
        if dvol_provider and check_premium and not force:
            premium_min, premium_max = dvol_provider.get_premium_range()
            premium_min = max(premium_min, base_min)
            current_dvol = dvol_provider.get_current_dvol()
            app_logger.info(
                f"Strategy: Using DVOL-based premium range (Floored to {base_min}). DVOL: {current_dvol:.2f}%, "
                f"Target: ${premium_min}-${premium_max}"
            )
        else:
            premium_min, premium_max = base_min, 250  # Legacy fallback / Force mode
            app_logger.info(f"Strategy: Using premium range ${premium_min}-${premium_max} (Force={force})")

        # --- PREMIUM-MATCHED STRIKE SELECTION ---
        # Rule: Minimum MIN_OTM_STRIKES (5) OTM on EACH leg — hard floor, never violated.
        # Among all valid pairs (call >= 5 OTM, put >= 5 OTM), pick the pair whose
        # |call_premium - put_premium| is smallest → true premium matching.
        # Call can go 6, 7, 8 OTM if needed to equalise with the higher-IV put side.
        # Example: if 5-OTM put = $103, 6-OTM call = $100 → selected over 5-OTM call at $84.
        min_otm = MIN_OTM_STRIKES  # 5 strikes OTM minimum (never go below this)
        eligible_calls = []
        eligible_puts = []
        for t in expiry_tickers:
            symbol = t.get('symbol', '')
            greeks = t.get('greeks') or {}
            delta = float(greeks.get('delta', 0))
            mark_price = float(t.get('mark_price', 0))
            strike = float(t.get('strike_price', 0))
            premium_inr = mark_price

            # Soft safety cap: absolute delta <= 0.45 (deep ITM filter)
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
                # >= min_otm strikes OTM from ATM (no upper limit — allow 6, 7, 8 OTM for matching)
                if atm_idx + min_otm < len(all_strikes) and strike >= all_strikes[atm_idx + min_otm]:
                    eligible_calls.append(item)
            elif 'put' in c_type:
                # >= min_otm strikes OTM from ATM (no upper limit — allow 6, 7, 8 OTM for matching)
                if atm_idx - min_otm >= 0 and strike <= all_strikes[atm_idx - min_otm]:
                    eligible_puts.append(item)

        best_call = None
        best_put = None

        # Build all (call, put) pairs within premium range (minimum $80 floor)
        valid_pairs = []
        if check_premium:
            for c in eligible_calls:
                if c['premium_inr'] < MIN_ENTRY_PREMIUM:
                    continue
                if not (premium_min <= c['premium_inr'] <= premium_max):
                    continue
                for p in eligible_puts:
                    if p['premium_inr'] < MIN_ENTRY_PREMIUM:
                        continue
                    if not (premium_min <= p['premium_inr'] <= premium_max):
                        continue
                    # ── JOINT SCORE: PREMIUM + DELTA MATCH ────────────────────────────
                    # Score formula (lower = better):
                    #   1.5 × |call_prem - put_prem|          ← premium equality (primary)
                    #   50  × ||call_delta| - |put_delta||     ← delta symmetry (secondary)
                    prem_diff  = abs(c['premium_inr'] - p['premium_inr'])
                    delta_diff = abs(abs(c['delta']) - abs(p['delta']))
                    joint_score = 1.5 * prem_diff + 50.0 * delta_diff
                    if p['premium_inr'] > PUT_SKEW_CAP * c['premium_inr']:
                        app_logger.debug(
                            f"Strategy: Skew note — Put {p['symbol']} ({p['premium_inr']:.2f}) "
                            f"vs Call {c['symbol']} ({c['premium_inr']:.2f}) exceeds PUT_SKEW_CAP "
                            f"({PUT_SKEW_CAP}x). Still included in joint-score pool."
                        )
                    valid_pairs.append((c, p, prem_diff, delta_diff, joint_score))

        if check_premium and valid_pairs:
            # ── 2-TIER SELECTION: $100+ PRIORITY, FALLBACK MIN $80 ────────────
            # Rule: If 5+ OTM strikes with premium >= $100 on both legs are available,
            # prioritize $100+ tier. Only if $100+ is unavailable on both legs,
            # fall back to allowing minimum $80 per leg.
            pairs_100 = [t for t in valid_pairs if t[0]['premium_inr'] >= 100.0 and t[1]['premium_inr'] >= 100.0]

            if pairs_100:
                app_logger.info(
                    f"Strategy: [TIER 1] Found {len(pairs_100)} pairs with $100+ premium on both legs (>= {min_otm} OTM). "
                    f"Restricting selection to $100+ tier."
                )
                candidate_pool = pairs_100
            else:
                app_logger.info(
                    f"Strategy: [TIER 2] No pair has $100+ on both legs at >= {min_otm} OTM. "
                    f"Falling back to minimum ${MIN_ENTRY_PREMIUM:.0f}+ tier ({len(valid_pairs)} pairs)."
                )
                candidate_pool = valid_pairs

            # Best pair chosen by joint score (balancing premium equality and delta symmetry)
            best_tuple = min(candidate_pool, key=lambda t5: t5[4])
            best_call, best_put, _prem_diff, _delta_diff, _score = best_tuple
            skew_ratio = best_put['premium_inr'] / best_call['premium_inr'] if best_call['premium_inr'] > 0 else 0
            tier_label = "$100+ TIER" if pairs_100 else f"MIN ${MIN_ENTRY_PREMIUM:.0f}+ TIER"
            app_logger.info(
                f"Strategy: [{tier_label}] Strikes selected — "
                f"Call: {best_call['symbol']} (Strike={best_call['strike']:.0f}, Prem=${best_call['premium_inr']:.2f}, Delta={best_call['delta']:.4f}), "
                f"Put:  {best_put['symbol']} (Strike={best_put['strike']:.0f}, Prem=${best_put['premium_inr']:.2f}, Delta={best_put['delta']:.4f}), "
                f"PremDiff=${_prem_diff:.2f}, |DeltaDiff|={_delta_diff:.4f}, JointScore={_score:.3f}, SkewRatio={skew_ratio:.3f}x"
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
