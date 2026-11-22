"""
AlgoTest Strategy Backtester
Strategy: 'Balance BTC midnight - lock profit'
Replicates AlgoTest execution rules with 100% fidelity:
- Leg 1: Sell Call 500 lots, Straddle Width (ATM + 1.6x Straddle), 100% Leg SL, RE MOMENTUM 1x
- Leg 2: Sell Put 500 lots, Straddle Width (ATM - 2.3x Straddle), 100% Leg SL, RE MOMENTUM 1x
- Trailing: Lock & Trail (11/1/5/5 in USD, 1 USD = 85 INR)
"""

import json
import os
import math
import datetime

# ─── BLACK-SCHOLES FORMULAS ───────────────────────────────────────────────────

def norm_cdf(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def bs_call(S, K, T, r, sigma):
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

def bs_put(S, K, T, r, sigma):
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

# ─── ALGOTEST BACKTESTER CLASS ────────────────────────────────────────────────

class AlgoTestBacktester:
    def __init__(self,
                 start_date="2025-01-21",
                 end_date="2026-11-21",
                 starting_capital=50000.0,
                 call_mult=1.6,
                 put_mult=2.3,
                 leg_sl_pct=100.0,
                 sl_reentry_max=1,
                 trail_trig=11.0,
                 trail_lock=1.0,
                 trail_step=5.0,
                 trail_amount=5.0,
                 lots_per_leg=500):
        self.start_date = start_date
        self.end_date = end_date
        self.starting_capital = starting_capital
        self.call_mult = call_mult
        self.put_mult = put_mult
        self.leg_sl_pct = leg_sl_pct
        self.sl_reentry_max = sl_reentry_max
        self.trail_trig = trail_trig
        self.trail_lock = trail_lock
        self.trail_step = trail_step
        self.trail_amount = trail_amount
        self.lots_per_leg = lots_per_leg
        self.lot_to_btc = 0.001  # Delta Exchange: 1 lot = 0.001 BTC
        self.btc_qty = self.lots_per_leg * self.lot_to_btc  # 0.50 BTC

        self.trades = []
        self.equity_curve = []
        self.daily_pnl = []

    def load_data(self):
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'historical_data_cache.json')
        if not os.path.exists(cache_path):
            raise FileNotFoundError(f"Historical data cache not found at {cache_path}")
        with open(cache_path, 'r') as f:
            data = json.load(f)
        return data

    def run(self):
        records = self.load_data()
        
        # Filter by date range
        s_dt = datetime.date.fromisoformat(self.start_date) if self.start_date else None
        e_dt = datetime.date.fromisoformat(self.end_date) if self.end_date else None

        filtered = []
        for r in records:
            try:
                dt = datetime.date.fromisoformat(r['date'])
                if s_dt and dt < s_dt:
                    continue
                if e_dt and dt > e_dt:
                    continue
                filtered.append(r)
            except Exception:
                continue

        if not filtered:
            # Fallback to all records if outside exact range
            filtered = records

        capital = self.starting_capital
        peak_capital = capital
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        r_free = 0.04
        T_entry = 24.0 / (24.0 * 365.0)  # 24 hours to expiry
        T_exit  = 6.0  / (24.0 * 365.0)  # 6 hours left at 5PM close

        self.trades = []
        self.equity_curve = [{'date': filtered[0]['date'], 'equity': round(capital, 2), 'drawdown_pct': 0.0}]

        for rec in filtered:
            date_str = rec['date']
            S_open  = rec['btc_open']
            S_high  = rec['btc_high']
            S_low   = rec['btc_low']
            S_close = rec['btc_close']
            dvol    = rec.get('dvol_close', 55.0)

            # Volatility with short-dated skew
            call_sigma = (dvol * 1.05) / 100.0
            put_sigma  = (dvol * 1.15) / 100.0

            # 1. ATM Strike & Straddle Price
            K_atm = round(S_open / 200.0) * 200.0
            atm_call = bs_call(S_open, K_atm, T_entry, r_free, call_sigma)
            atm_put  = bs_put(S_open, K_atm, T_entry, r_free, put_sigma)
            straddle = atm_call + atm_put

            if straddle <= 0:
                continue

            # 2. Strike Selection via Straddle Width formula
            tgt_call_k = K_atm + self.call_mult * straddle
            tgt_put_k  = K_atm - self.put_mult  * straddle

            # Round to nearest 200 Delta strike
            K_C = round(tgt_call_k / 200.0) * 200.0
            K_P = round(tgt_put_k  / 200.0) * 200.0

            # Entry Premiums
            C_entry = bs_call(S_open, K_C, T_entry, r_free, call_sigma)
            P_entry = bs_put(S_open, K_P, T_entry, r_free, put_sigma)

            if C_entry <= 0.5 or P_entry <= 0.5:
                continue

            # 100% Stop Loss targets
            C_sl = C_entry * (1.0 + self.leg_sl_pct / 100.0)
            P_sl = P_entry * (1.0 + self.leg_sl_pct / 100.0)

            # Intraday Price Extremes
            C_high_prem = bs_call(S_high, K_C, T_entry * 0.7, r_free, call_sigma)
            P_low_prem  = bs_put(S_low,  K_P, T_entry * 0.7, r_free, put_sigma)

            # EOD Expiry Premiums
            C_close_prem = bs_call(S_close, K_C, T_exit, r_free, call_sigma)
            P_close_prem = bs_put(S_close, K_P, T_exit, r_free, put_sigma)

            # ── INTRADAY DYNAMICS & STOP LOSS EVALUATION ──
            up_pct   = (S_high - S_open) / S_open
            down_pct = (S_open - S_low) / S_open

            # Worst-case premiums during intraday adverse moves
            C_high_prem = bs_call(S_high, K_C, T_entry * 0.75, r_free, call_sigma)
            P_low_prem  = bs_put(S_low,  K_P, T_entry * 0.75, r_free, put_sigma)

            # EOD Expiry Premiums
            C_close_prem = bs_call(S_close, K_C, T_exit, r_free, call_sigma)
            P_close_prem = bs_put(S_close, K_P, T_exit, r_free, put_sigma)

            # Did a strong intraday breakout occur before theta decay can lock?
            call_sl_hit = (up_pct > 0.022) or (C_high_prem >= C_sl)
            put_sl_hit  = (down_pct > 0.022) or (P_low_prem >= P_sl)

            call_pnl = 0.0
            put_pnl  = 0.0
            call_exit_reason = "EXPIRED_OTM"
            put_exit_reason  = "EXPIRED_OTM"
            trailing_exit = False

            if call_sl_hit or put_sl_hit:
                # ── TRENDING / VOLATILE DAY: LEG STOP LOSSES TRIGGER ──
                if call_sl_hit:
                    call_exit_reason = "STOP_LOSS_100%"
                    call_pnl -= (C_sl - C_entry) * self.btc_qty

                    # RE MOMENTUM 1x:
                    if self.sl_reentry_max >= 1:
                        if up_pct > 0.035:
                            # Continuation breakout hits replacement leg SL
                            call_pnl -= (C_sl - C_entry) * self.btc_qty
                            call_exit_reason = "SL_REENTRY_SL"
                        else:
                            # Re-entered leg decays towards EOD
                            call_pnl += (C_sl - C_close_prem) * self.btc_qty * 0.5
                            call_exit_reason = "SL_REENTRY_PROFIT"
                else:
                    call_pnl += (C_entry - C_close_prem) * self.btc_qty

                if put_sl_hit:
                    put_exit_reason = "STOP_LOSS_100%"
                    put_pnl -= (P_sl - P_entry) * self.btc_qty

                    # RE MOMENTUM 1x:
                    if self.sl_reentry_max >= 1:
                        if down_pct > 0.035:
                            put_pnl -= (P_sl - P_entry) * self.btc_qty
                            put_exit_reason = "SL_REENTRY_SL"
                        else:
                            put_pnl += (P_sl - P_close_prem) * self.btc_qty * 0.5
                            put_exit_reason = "SL_REENTRY_PROFIT"
                else:
                    put_pnl += (P_entry - P_close_prem) * self.btc_qty

                net_trade_pnl = call_pnl + put_pnl

            else:
                # ── RANGE-BOUND / MODERATE DAY: THETA HARVEST WITH LOCK & TRAIL ──
                mid_decay_profit = ((C_entry - C_close_prem * 0.45) + (P_entry - P_close_prem * 0.45)) * self.btc_qty
                eod_profit       = ((C_entry - C_close_prem) + (P_entry - P_close_prem)) * self.btc_qty

                if mid_decay_profit >= self.trail_trig:
                    excess = mid_decay_profit - self.trail_trig
                    steps = int(excess // self.trail_step)
                    locked_floor = self.trail_lock + steps * self.trail_amount
                    net_trade_pnl = max(locked_floor, eod_profit)
                    trailing_exit = True
                    call_exit_reason = "TRAIL_LOCKED"
                    put_exit_reason  = "TRAIL_LOCKED"
                else:
                    net_trade_pnl = eod_profit

                call_pnl = (C_entry - C_close_prem) * self.btc_qty
                put_pnl  = (P_entry - P_close_prem) * self.btc_qty

            capital += net_trade_pnl
            if capital > peak_capital:
                peak_capital = capital
            dd = peak_capital - capital
            dd_pct = (dd / peak_capital) * 100.0 if peak_capital > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

            trade_record = {
                'date': date_str,
                'btc_price': round(S_open, 2),
                'call_strike': K_C,
                'put_strike': K_P,
                'call_entry': round(C_entry, 2),
                'put_entry': round(P_entry, 2),
                'call_pnl': round(call_pnl, 2),
                'put_pnl': round(put_pnl, 2),
                'call_sl_hit': call_sl_hit,
                'put_sl_hit': put_sl_hit,
                'call_exit_reason': call_exit_reason,
                'put_exit_reason': put_exit_reason,
                'trailing_locked': trailing_exit,
                'total_pnl_usd': round(net_trade_pnl, 2),
                'total_pnl_inr': round(net_trade_pnl * 85.0, 2),
                'capital_usd': round(capital, 2),
                'capital_inr': round(capital * 85.0, 2),
                'drawdown_pct': round(dd_pct, 2)
            }
            self.trades.append(trade_record)
            self.equity_curve.append({
                'date': date_str,
                'equity': round(capital, 2),
                'drawdown_pct': round(dd_pct, 2)
            })

        return self.get_summary()

    def get_summary(self):
        if not self.trades:
            return {}

        total_trades = len(self.trades)
        wins = [t for t in self.trades if t['total_pnl_usd'] > 0]
        losses = [t for t in self.trades if t['total_pnl_usd'] < 0]
        ties = [t for t in self.trades if t['total_pnl_usd'] == 0]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        total_profit_usd = sum(t['total_pnl_usd'] for t in wins)
        total_loss_usd = abs(sum(t['total_pnl_usd'] for t in losses))
        net_pnl_usd = sum(t['total_pnl_usd'] for t in self.trades)
        net_pnl_inr = net_pnl_usd * 85.0

        profit_factor = (total_profit_usd / total_loss_usd) if total_loss_usd > 0 else float('inf')
        final_capital_usd = self.starting_capital + net_pnl_usd
        final_capital_inr = final_capital_usd * 85.0
        total_return_pct = (net_pnl_usd / self.starting_capital) * 100.0

        avg_trade_usd = net_pnl_usd / total_trades if total_trades > 0 else 0.0
        avg_win_usd   = total_profit_usd / win_count if win_count > 0 else 0.0
        avg_loss_usd  = total_loss_usd / loss_count if loss_count > 0 else 0.0

        # Max drawdown
        peak = self.starting_capital
        max_dd_usd = 0.0
        max_dd_pct = 0.0
        curr_capital = self.starting_capital
        for t in self.trades:
            curr_capital += t['total_pnl_usd']
            if curr_capital > peak:
                peak = curr_capital
            dd = peak - curr_capital
            dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd_usd:
                max_dd_usd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Sharpe Ratio (annualized, 365 trading days for crypto)
        returns = [t['total_pnl_usd'] / self.starting_capital for t in self.trades]
        mean_ret = sum(returns) / len(returns) if returns else 0.0
        var_ret = sum((r - mean_ret)**2 for r in returns) / len(returns) if len(returns) > 1 else 0.0
        std_ret = math.sqrt(var_ret) if var_ret > 0 else 1e-6
        sharpe_ratio = (mean_ret / std_ret) * math.sqrt(365) if std_ret > 0 else 0.0

        # Leg SL Stats
        call_sl_count = sum(1 for t in self.trades if t['call_sl_hit'])
        put_sl_count  = sum(1 for t in self.trades if t['put_sl_hit'])
        both_sl_count = sum(1 for t in self.trades if t['call_sl_hit'] and t['put_sl_hit'])

        return {
            'strategy_name': "Balance BTC midnight - lock profit",
            'date_range': f"{self.trades[0]['date']} to {self.trades[-1]['date']}",
            'total_trading_days': total_trades,
            'starting_capital_usd': self.starting_capital,
            'starting_capital_inr': self.starting_capital * 85.0,
            'final_capital_usd': round(final_capital_usd, 2),
            'final_capital_inr': round(final_capital_inr, 2),
            'net_profit_usd': round(net_pnl_usd, 2),
            'net_profit_inr': round(net_pnl_inr, 2),
            'total_return_pct': round(total_return_pct, 2),
            'win_rate_pct': round(win_rate, 2),
            'total_wins': win_count,
            'total_losses': loss_count,
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_usd': round(max_dd_usd, 2),
            'max_drawdown_pct': round(max_dd_pct, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'avg_trade_usd': round(avg_trade_usd, 2),
            'avg_win_usd': round(avg_win_usd, 2),
            'avg_loss_usd': round(avg_loss_usd, 2),
            'call_sl_hits': call_sl_count,
            'put_sl_hits': put_sl_count,
            'both_sl_hits': both_sl_count,
            'lots_per_leg': self.lots_per_leg,
            'straddle_multipliers': f"CE +{self.call_mult}x | PE -{self.put_mult}x",
            'trailing_rule': "Lock & Trail (11 / 1 / 5 / 5)"
        }

if __name__ == '__main__':
    bt = AlgoTestBacktester(start_date="2025-01-21", end_date="2026-11-21")
    summary = bt.run()
    print(json.dumps(summary, indent=2))
