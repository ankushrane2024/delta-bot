import json
import os
import datetime
import math
import numpy as np
import pandas as pd
from logger import app_logger
import config
from config import LOT_TO_BTC

# ─── BLACK-SCHOLES FUNCTIONS ──────────────────────────────────────────────────

def norm_cdf(x):
    """Cumulative distribution function for the standard normal distribution."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def black_scholes_call(S, K, T, r, sigma):
    """Calculates the Black-Scholes price of a Call option."""
    if T <= 0:
        return max(0.0, S - K)
    if sigma <= 0:
        return max(0.0, S - K * math.exp(-r * T))
    
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    except Exception:
        return max(0.0, S - K)

def black_scholes_put(S, K, T, r, sigma):
    """Calculates the Black-Scholes price of a Put option."""
    if T <= 0:
        return max(0.0, K - S)
    if sigma <= 0:
        return max(0.0, K * math.exp(-r * T) - S)
    
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    except Exception:
        return max(0.0, K - S)

def get_option_delta(S, K, T, r, sigma, option_type='CALL'):
    """Calculates the option Delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if (option_type == 'CALL' and S > K) else -1.0 if (option_type == 'PUT' and S < K) else 0.0
    
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if option_type == 'CALL':
            return norm_cdf(d1)
        else:
            return norm_cdf(d1) - 1.0
    except Exception:
        return 0.0

# ──────────────────────────────────────────────────────────────────────────────

class AdvancedBacktester:
    """
    High-fidelity Backtester using real historical DVOL and BTC price data.
    Prices options dynamically using the Black-Scholes model.
    """

    def __init__(self, starting_capital=None, dvol_data=None, price_data=None):
        self.starting_capital = starting_capital or config.STARTING_CAPITAL
        self.capital = self.starting_capital
        self.max_equity = self.starting_capital
        self.dvol_data = dvol_data
        self.price_data = price_data

        # Results tracking
        self.trades = []
        self.equity_curve = []
        self.daily_pnl = []

        # State
        self.consecutive_losses = 0
        self.reduced_size_trades_remaining = 0
        self.next_day_paused = False
        self.daily_loss_today = 0.0

    def _load_real_data(self):
        """Loads and returns aligned historical DVOL + price data from cache file."""
        cache_file = "historical_data_cache.json"
        
        # If cache file doesn't exist, download it first
        if not os.path.exists(cache_file):
            app_logger.info("Backtester: Historical data cache not found. Downloading live...")
            from scratch.download_real_history import download_data
            download_data()

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                app_logger.error(f"Backtester: Error loading data cache: {e}")
        return []

    def _get_premium_range(self, dvol):
        """Returns target (min, max) premium per strangle based on DVOL levels."""
        if dvol < 40:
            return 140, 300
        elif dvol <= 55:
            return 120, 260
        else:
            return 110, 240

    def _find_strikes(self, S, dvol, premium_range):
        """
        Selects Call & Put strikes according to final advanced rules.
        S: entry price (btc_open)
        dvol: IV (dvol_close)
        """
        # Apply a realistic volatility skew/smile multiplier for short-dated OTM options
        # Short-dated OTM options have much higher IV than the 30d ATM DVOL index.
        call_sigma = (dvol * 1.95) / 100.0
        put_sigma = (dvol * 2.25) / 100.0
        
        r = 0.05  # 5% risk free rate
        # Delta Exchange daily options expire at 12:00 UTC next day.
        # Entry at 9:00 AM IST = 3:30 AM UTC → ~32.5h to next-day 12:00 UTC expiry
        T_entry = 32.5 / (24.0 * 365.0)  # 32.5 hours to expiry at 9AM IST entry
        
        min_total_prem, max_total_prem = premium_range
        target_leg_prem = (min_total_prem + max_total_prem) / 4.0  # midpoint per leg

        # ATM Strike
        ATM_strike = round(S / 1000.0) * 1000.0
        
        # Minimum 4 strikes OTM
        min_call_strike = ATM_strike + 4000.0
        min_put_strike = ATM_strike - 4000.0
        
        # 1. Select Call Strike
        call_strike = min_call_strike
        best_call_diff = float('inf')
        
        # Scan strikes upward to find premium closest to target
        for strike in range(int(min_call_strike), int(min_call_strike + 20000), 1000):
            prem = black_scholes_call(S, strike, T_entry, r, call_sigma)
            diff = abs(prem - target_leg_prem)
            if diff < best_call_diff:
                best_call_diff = diff
                call_strike = strike
            else:
                # Premium decreases as we go further OTM
                break

        # 2. Select Put Strike
        put_strike = min_put_strike
        best_put_diff = float('inf')
        
        for strike in range(int(min_put_strike), int(min_put_strike - 20000), -1000):
            prem = black_scholes_put(S, strike, T_entry, r, put_sigma)
            diff = abs(prem - target_leg_prem)
            if diff < best_put_diff:
                best_put_diff = diff
                put_strike = strike
            else:
                break

        # 3. Apply Put Skew Cap (Put Premium <= 1.35x Call Premium)
        call_prem = black_scholes_call(S, call_strike, T_entry, r, call_sigma)
        put_prem = black_scholes_put(S, put_strike, T_entry, r, put_sigma)
        
        while put_prem > 1.35 * call_prem and put_strike > ATM_strike - 15000:
            put_strike -= 1000.0
            put_prem = black_scholes_put(S, put_strike, T_entry, r, put_sigma)

        # 4. Check Net Delta Entry Limit (absolute net delta <= 0.15)
        # If net delta is > 0.15, shift both strikes 1 step further OTM
        c_delta = get_option_delta(S, call_strike, T_entry, r, call_sigma, 'CALL')
        p_delta = get_option_delta(S, put_strike, T_entry, r, put_sigma, 'PUT')
        net_delta = c_delta + p_delta  # Call delta > 0, Put delta < 0
        
        if abs(net_delta) > 0.15:
            call_strike += 1000.0
            put_strike -= 1000.0
            call_prem = black_scholes_call(S, call_strike, T_entry, r, call_sigma)
            put_prem = black_scholes_put(S, put_strike, T_entry, r, put_sigma)
            c_delta = get_option_delta(S, call_strike, T_entry, r, call_sigma, 'CALL')
            p_delta = get_option_delta(S, put_strike, T_entry, r, put_sigma, 'PUT')
            net_delta = c_delta + p_delta

        return call_strike, put_strike, call_prem, put_prem, c_delta, p_delta, net_delta

    def _apply_dynamic_sizing(self, dvol):
        """Returns lot size multiplier based on DVOL and loss history."""
        multiplier = 1.0

        # DVOL 40-55% → +20% boost
        if 40 <= dvol <= 55:
            multiplier *= 1.20

        # After 2 consecutive losses → -20%
        if self.consecutive_losses >= 2:
            multiplier *= 0.80

        # Cooldown reduction remaining
        if self.reduced_size_trades_remaining > 0:
            multiplier *= 0.80

        return max(0.2, multiplier)

    def run(self, days=90, start_date=None, end_date=None):
        """
        Runs the backtest using real historical data.
        
        Args:
            days: Backtest period (takes last 'days' matching records if no date range is provided)
            start_date: ISO date string for backtest start
            end_date: ISO date string for backtest end
        """
        aligned_data = self._load_real_data()
        if not aligned_data:
            app_logger.error("Backtester: No historical data loaded.")
            return self.get_results()

        # Parse date boundaries if provided
        s_dt = None
        e_dt = None
        if start_date:
            try:
                s_dt = datetime.date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
            except Exception:
                pass
        if end_date:
            try:
                e_dt = datetime.date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
            except Exception:
                pass

        # Filter the trading days
        # Exclude weekends (weekday >= 5: Fri/Sat/Sun or Mon-Thu only)
        filtered_records = []
        for r in aligned_data:
            try:
                dt = datetime.date.fromisoformat(r['date'])
                
                # Check date boundaries
                if s_dt and dt < s_dt:
                    continue
                if e_dt and dt > e_dt:
                    continue
                    
                # Mon-Sun schedule (All 7 days)
                filtered_records.append(r)
            except Exception:
                continue

        # If date range is not specified, slice the last N records
        if not s_dt or not e_dt:
            if len(filtered_records) > days:
                backtest_records = filtered_records[-days:]
            else:
                backtest_records = filtered_records
        else:
            backtest_records = filtered_records

        if not backtest_records:
            app_logger.warning("Backtester: No records fit the date criteria.")
            return self.get_results()

        self.capital = self.starting_capital
        self.max_equity = self.starting_capital
        self.trades = []
        self.equity_curve = [{'date': backtest_records[0]['date'], 'equity': self.capital}]
        
        self.consecutive_losses = 0
        self.reduced_size_trades_remaining = 0
        self.next_day_paused = False
        self.daily_loss_today = 0.0

        r_free = 0.05
        # 9:00 AM IST entry → 32.5h to next-day 12:00 UTC expiry
        # EOD exit at 5:00 PM IST = 11:30 AM UTC → ~24.5h remaining at exit
        T_entry = 32.5 / (24.0 * 365.0)  # 32.5 hours at entry
        T_exit  = 24.5 / (24.0 * 365.0)  # 24.5 hours at EOD exit (8h hold)

        for i, record in enumerate(backtest_records):
            current_date = record['date']
            btc_open = record['btc_open']
            btc_high = record['btc_high']
            btc_low = record['btc_low']
            btc_close = record['btc_close']
            dvol = record['dvol_close']
            percentile = record['dvol_percentile']

            # Reset daily trackers
            self.daily_loss_today = 0.0

            # --- GUARD CHECKS ---
            
            # Pause check (Daily loss > 2.5% pause tomorrow)
            if self.next_day_paused:
                self.next_day_paused = False
                self.equity_curve.append({'date': current_date, 'equity': round(self.capital, 2)})
                continue

            # DVOL Percentile filter
            if percentile < config.DVOL_PERCENTILE_MIN or percentile > config.DVOL_PERCENTILE_MAX:
                self.equity_curve.append({'date': current_date, 'equity': round(self.capital, 2)})
                continue

            # --- STRIKE SELECTION ---
            premium_range = self._get_premium_range(dvol)
            K_C, K_P, c_prem, p_prem, c_del, p_del, net_del = self._find_strikes(
                btc_open, dvol, premium_range
            )
            
            entry_premium_total = c_prem + p_prem
            if entry_premium_total <= 0:
                self.equity_curve.append({'date': current_date, 'equity': round(self.capital, 2)})
                continue

            # --- POSITION SIZING & RISK LIMITS ---
            size_multiplier = self._apply_dynamic_sizing(dvol)
            
            # Base lots from manual lot size (e.g. 200)
            base_lots = config.MANUAL_TOTAL_LOTS
            adjusted_lots = max(1, int(base_lots * size_multiplier))
            
            # Estimate risk = Entry premium * SL_PERCENT (150% SL means max loss is 1.5x entry)
            # Max Risk Per Trade limit = 1.5% of current equity
            # P&L Formula: Total_PnL = pnl_pct * entry_premium * BTC_Quantity
            # BTC_Quantity = adjusted_lots * LOT_TO_BTC (0.001 BTC per lot on Delta Exchange)
            btc_quantity = adjusted_lots * LOT_TO_BTC
            max_risk_amount = self.capital * 0.015
            estimated_risk = entry_premium_total * 1.50 * btc_quantity
            
            if estimated_risk > max_risk_amount:
                # Scale down lots to keep risk within 1.5% limit
                adjusted_lots = int(max_risk_amount / (entry_premium_total * 1.50 * LOT_TO_BTC))
                adjusted_lots = max(1, adjusted_lots)
                btc_quantity = adjusted_lots * LOT_TO_BTC
                estimated_risk = entry_premium_total * 1.50 * btc_quantity

            # --- SIMULATE OPTIONS P&L PATH ---
            call_sigma = (dvol * 1.95) / 100.0
            put_sigma = (dvol * 2.25) / 100.0

            # 1. Calculate Peak Premium (Max Loss path at daily High/Low extremes)
            # Strangle Call peak at high
            c_high = black_scholes_call(btc_high, K_C, T_exit, r_free, call_sigma)
            p_high = black_scholes_put(btc_high, K_P, T_exit, r_free, put_sigma)
            strangle_high = c_high + p_high

            # Strangle Put peak at low
            c_low = black_scholes_call(btc_low, K_C, T_exit, r_free, call_sigma)
            p_low = black_scholes_put(btc_low, K_P, T_exit, r_free, put_sigma)
            strangle_low = c_low + p_low

            peak_strangle_premium = max(strangle_high, strangle_low)

            # 2. Calculate EOD Closing Premium
            c_close = black_scholes_call(btc_close, K_C, T_exit, r_free, call_sigma)
            p_close = black_scholes_put(btc_close, K_P, T_exit, r_free, put_sigma)
            close_strangle_premium = c_close + p_close

            # 3. Evaluate Exit Rule Conditions
            exit_reason = "EOD_EXIT"
            final_pnl_pct = 0.0
            hedge_triggered = False

            # Check if Smart Hedging triggers based on delta and IV
            # High IV (>55%) -> delta trigger 0.12, Mid (45-55) -> 0.17, Low (<45) -> 0.20
            trigger_delta = 0.20
            if dvol > 55:
                trigger_delta = 0.12
            elif dvol >= 45:
                trigger_delta = 0.17

            # Estimate net delta at high/low
            c_del_high = get_option_delta(btc_high, K_C, T_exit, r_free, call_sigma, 'CALL')
            p_del_high = get_option_delta(btc_high, K_P, T_exit, r_free, put_sigma, 'PUT')
            peak_net_delta_high = abs(c_del_high + p_del_high)

            c_del_low = get_option_delta(btc_low, K_C, T_exit, r_free, call_sigma, 'CALL')
            p_del_low = get_option_delta(btc_low, K_P, T_exit, r_free, put_sigma, 'PUT')
            peak_net_delta_low = abs(c_del_low + p_del_low)

            max_intraday_delta = max(peak_net_delta_high, peak_net_delta_low)

            if max_intraday_delta > trigger_delta:
                hedge_triggered = True

            # ── EXIT LOGIC: Mirrors actual bot config exactly ─────────────────
            # Uses config.SL_PERCENT, EXIT_PROFIT_TARGET, PARTIAL_PROFIT_TRIGGER
            # so backtest always reflects the real strategy parameters.
            unrealized_loss_ratio = (peak_strangle_premium - entry_premium_total) / entry_premium_total

            if hedge_triggered and unrealized_loss_ratio >= config.SL_PERCENT * 0.60:
                # Hedge active + intraday loss reached 60% of SL level.
                # Realistic hedge outcome: reduces loss to ~40% (not a magic 5%).
                exit_reason = "TIGHTENED_SL_HEDGE"
                final_pnl_pct = -0.40  # Realistic hedged loss (-40%)
            elif unrealized_loss_ratio >= config.SL_PERCENT:
                # Stop Loss hit at config.SL_PERCENT (currently 130%)
                exit_reason = "STOP_LOSS"
                final_pnl_pct = -config.SL_PERCENT

            else:
                # No SL hit. Evaluate profit targets matching actual bot config.
                closing_pnl_pct = (entry_premium_total - close_strangle_premium) / entry_premium_total

                # Full Exit Target (config.EXIT_PROFIT_TARGET = 30%)
                if closing_pnl_pct >= config.EXIT_PROFIT_TARGET:
                    exit_reason = "FULL_TARGET"
                    final_pnl_pct = config.EXIT_PROFIT_TARGET

                # Partial Profit (config.PARTIAL_PROFIT_TRIGGER = 20%)
                # 50% closed at trigger, remaining 50% runs to EOD close
                elif closing_pnl_pct >= config.PARTIAL_PROFIT_TRIGGER:
                    exit_reason = "PARTIAL_TARGET"
                    partial_size = config.PARTIAL_PROFIT_SIZE  # 0.50
                    final_pnl_pct = (partial_size * config.PARTIAL_PROFIT_TRIGGER +
                                     (1 - partial_size) * closing_pnl_pct)

                # Trailing SL: if price touched TRAILING_SL_TRIGGER (15%) during day
                # then ended below breakeven, exit at breakeven (0%)
                elif closing_pnl_pct < 0.0 and closing_pnl_pct > -config.SL_PERCENT:
                    c_decayed = black_scholes_call(btc_open, K_C, T_exit, r_free, call_sigma)
                    p_decayed = black_scholes_put(btc_open, K_P, T_exit, r_free, put_sigma)
                    min_strangle_prem = c_decayed + p_decayed
                    min_pnl_pct = (entry_premium_total - min_strangle_prem) / entry_premium_total

                    if min_pnl_pct >= config.TRAILING_SL_TRIGGER:
                        exit_reason = "TRAILING_SL"
                        final_pnl_pct = config.TRAILING_SL_LEVEL  # 0.0 = breakeven
                    else:
                        exit_reason = "EOD_EXIT"
                        final_pnl_pct = closing_pnl_pct
                else:
                    exit_reason = "EOD_EXIT"
                    final_pnl_pct = closing_pnl_pct

            # Calculate P&L USD
            # Formula: PnL = pnl_pct * entry_premium * BTC_Quantity
            # BTC_Quantity = adjusted_lots * LOT_TO_BTC (0.001 BTC per lot on Delta Exchange)
            pnl_usd = final_pnl_pct * entry_premium_total * btc_quantity

            # Cap loss at the max risk amount
            if pnl_usd < 0:
                pnl_usd = max(pnl_usd, -max_risk_amount)

            # Update capital
            self.capital += pnl_usd
            if self.capital > self.max_equity:
                self.max_equity = self.capital

            # Daily tracking
            self.daily_loss_today = pnl_usd

            # Consecutive Loss tracking
            if pnl_usd < 0:
                self.consecutive_losses += 1
                if self.consecutive_losses >= 2:
                    self.reduced_size_trades_remaining = 3
            else:
                self.consecutive_losses = 0

            if self.reduced_size_trades_remaining > 0:
                self.reduced_size_trades_remaining -= 1

            # Pause check for next day (Daily loss exceeds 2.5% of starting capital)
            if abs(self.daily_loss_today) / self.starting_capital > 0.025:
                self.next_day_paused = True

            # Record Trade details
            self.trades.append({
                'date': current_date,
                'dvol': round(dvol, 2),
                'dvol_percentile': round(percentile, 1),
                'btc_price': round(btc_open, 2),
                'btc_high': round(btc_high, 2),
                'btc_low': round(btc_low, 2),
                'btc_close': round(btc_close, 2),
                'call_strike': int(K_C),
                'put_strike': int(K_P),
                'premium_collected': round(entry_premium_total, 2),
                'pnl_pct': round(final_pnl_pct * 100, 2),
                'pnl_usd': round(pnl_usd, 2),
                'exit_reason': exit_reason,
                'size_multiplier': round(size_multiplier, 2),
                'lots': adjusted_lots,
                'hedge_triggered': hedge_triggered,
                'equity_after': round(self.capital, 2)
            })

            self.equity_curve.append({'date': current_date, 'equity': round(self.capital, 2)})

        return self.get_results()

    def get_results(self):
        """Computes and returns comprehensive backtest metrics."""
        if not self.trades:
            return {
                'metrics': self._empty_metrics(),
                'trades': [],
                'equity_curve': self.equity_curve
            }

        wins = [t for t in self.trades if t['pnl_usd'] > 0]
        losses = [t for t in self.trades if t['pnl_usd'] <= 0]
        pnls = [t['pnl_usd'] for t in self.trades]

        total_pnl = sum(pnls)
        win_rate = (len(wins) / len(self.trades) * 100) if self.trades else 0
        avg_winner = np.mean([t['pnl_usd'] for t in wins]) if wins else 0
        avg_loser = np.mean([t['pnl_usd'] for t in losses]) if losses else 0
        best_trade = max(pnls) if pnls else 0
        worst_trade = min(pnls) if pnls else 0

        # Profit factor
        gross_profit = sum(t['pnl_usd'] for t in wins)
        gross_loss = abs(sum(t['pnl_usd'] for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        # Max drawdown
        peak = self.starting_capital
        max_dd = 0
        for entry in self.equity_curve:
            eq = entry['equity']
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio
        if len(pnls) > 1:
            daily_returns = np.array(pnls) / self.starting_capital
            std_dev = np.std(daily_returns)
            sharpe = (np.mean(daily_returns) / std_dev) * math.sqrt(250) if std_dev > 0 else 0
        else:
            sharpe = 0

        # Monthly returns
        monthly_returns = {}
        for t in self.trades:
            month_key = t['date'][:7]  # YYYY-MM
            monthly_returns[month_key] = monthly_returns.get(month_key, 0) + t['pnl_usd']

        # Round monthly returns
        for key in monthly_returns:
            monthly_returns[key] = round(monthly_returns[key], 2)

        # Hedge statistics
        hedge_count = sum(1 for t in self.trades if t['hedge_triggered'])

        metrics = {
            'total_trades': len(self.trades),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_usd': round(total_pnl, 2),  # Frontend compatibility
            'avg_winner': round(avg_winner, 2),
            'avg_loser': round(avg_loser, 2),
            'best_trade': round(best_trade, 2),
            'worst_trade': round(worst_trade, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999.0,
            'max_drawdown_pct': round(max_dd * 100, 2),
            'max_drawdown': round(max_dd * 100, 2),  # Frontend compatibility
            'sharpe_ratio': round(sharpe, 2),
            'final_equity': round(self.capital, 2),
            'total_return_pct': round((self.capital - self.starting_capital) / self.starting_capital * 100, 2),
            'hedge_triggered_count': hedge_count,
            'hedge_trades': hedge_count,  # Frontend compatibility
            'monthly_returns': monthly_returns
        }

        return {
            'metrics': metrics,
            'trades': self.trades,
            'equity_curve': self.equity_curve
        }

    def _empty_metrics(self):
        """Returns empty metrics dict when no trades were executed."""
        return {
            'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
            'win_rate': 0, 'total_pnl': 0, 'total_pnl_usd': 0.0, 'avg_winner': 0, 'avg_loser': 0,
            'best_trade': 0, 'worst_trade': 0, 'profit_factor': 0,
            'max_drawdown_pct': 0, 'max_drawdown': 0.0, 'sharpe_ratio': 0,
            'final_equity': self.starting_capital, 'total_return_pct': 0,
            'hedge_triggered_count': 0, 'hedge_trades': 0, 'monthly_returns': {}
        }


# Keep backward compatibility
class SimplifiedBacktester:
    """Legacy wrapper for backward compatibility. Delegates to AdvancedBacktester."""
    def __init__(self, data_path=None):
        self.backtester = AdvancedBacktester()

    def run(self):
        results = self.backtester.run(days=90)
        df = pd.DataFrame(results['equity_curve'])
        if 'date' in df.columns:
            df.rename(columns={'date': 'Date', 'equity': 'Equity'}, inplace=True)
        df['Profit'] = df['Equity'].diff().fillna(0)
        return df
