import os
import json
import time
import math
import datetime

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from hedge.backtest.black_scholes import black_scholes_price, black_scholes_delta, find_strike_by_delta
from hedge.models.enums import MarketRegime, TrendDirection
from hedge.models.position import StressFusionBreakdown
from hedge.context.position_context import PositionContext
from hedge.engines.position_risk_engine import PositionRiskEngine
from hedge.engines.decision_engine import DecisionEngine
from hedge.engines.sizing_engine import HedgeSizingEngine
from config import LOT_TO_BTC, FUTURES_CONTRACT_SIZE_BTC

def run_1_year_backtest():
    file_path = os.path.join(os.path.dirname(__file__), "historical_btc.json")
    if not os.path.exists(file_path):
        print("Error: historical_btc.json not found. Run fetch_historical_btc.py first.")
        return
        
    with open(file_path, "r") as f:
        candles = json.load(f)
        
    if not candles:
        print("No candles found.")
        return
        
    # Group candles by week
    weeks = []
    current_week = []
    week_start = None
    
    for c in candles:
        t = c["time"]
        if week_start is None:
            week_start = t
        
        current_week.append(c)
        
        # A week is 7 days = 7 * 24 * 60 * 60 seconds = 604800
        if t - week_start >= 604800:
            weeks.append(current_week)
            current_week = []
            week_start = t
            
    if current_week:
        weeks.append(current_week)
        
    print(f"Loaded {len(candles)} candles. Broken into {len(weeks)} trading weeks.")
    
    risk_engine = PositionRiskEngine()
    decision_engine = DecisionEngine()
    sizing_engine = HedgeSizingEngine()
    
    total_strategy_pnl_usd = 0.0
    total_hedge_pnl_usd = 0.0
    hedge_events = 0
    catastrophes_prevented = 0
    
    weekly_results = []
    
    class MockRegime:
        def __init__(self):
            # For the backtester, we will assume trend is confirmed when market drops fast
            self.current_regime = MarketRegime.SAFE_RANGE
            
    class MockTrend:
        def __init__(self):
            self.trend_direction = TrendDirection.NONE
            self.trend_strength = 1.0
            self.trend_duration = 3600.0
            
    for week_idx, week_candles in enumerate(weeks):
        if len(week_candles) < 10: continue
        
        start_candle = week_candles[0]
        end_candle = week_candles[-1]
        
        S_initial = float(start_candle["close"])
        T_initial = 7.0 / 365.0
        r = 0.0
        sigma = 0.50 # Assume 50% IV
        
        # 30 Delta Strangle
        call_strike = find_strike_by_delta(S_initial, 0.30, T_initial, r, sigma, "call")
        put_strike = find_strike_by_delta(S_initial, -0.30, T_initial, r, sigma, "put")
        
        call_entry_price = black_scholes_price(S_initial, call_strike, T_initial, r, sigma, "call")
        put_entry_price = black_scholes_price(S_initial, put_strike, T_initial, r, sigma, "put")
        
        total_lots = 1000
        entry_premium_usd = (call_entry_price + put_entry_price) * (total_lots / 2) * LOT_TO_BTC
        
        hedge_qty_btc = 0.0
        hedge_entry_price = 0.0
        
        hedged_this_week = False
        
        for tick_idx, candle in enumerate(week_candles):
            S_current = float(candle["close"])
            time_elapsed_sec = candle["time"] - start_candle["time"]
            time_remaining_years = max(0.0001, T_initial - (time_elapsed_sec / (365*24*60*60)))
            
            # Recalculate options
            call_current = black_scholes_price(S_current, call_strike, time_remaining_years, r, sigma, "call")
            put_current = black_scholes_price(S_current, put_strike, time_remaining_years, r, sigma, "put")
            
            call_loss_usd = (call_current - call_entry_price) * (total_lots / 2) * LOT_TO_BTC
            put_loss_usd = (put_current - put_entry_price) * (total_lots / 2) * LOT_TO_BTC
            
            ctx = PositionContext()
            ctx.total_lots = total_lots
            ctx.position_size = entry_premium_usd
            ctx.futures_price = S_current
            
            ctx.short_call_strike = call_strike
            ctx.call_mark_price = S_current
            ctx.call_delta = black_scholes_delta(S_current, call_strike, time_remaining_years, r, sigma, "call")
            ctx.call_iv = sigma
            
            ctx.short_put_strike = put_strike
            ctx.put_mark_price = S_current
            ctx.put_delta = black_scholes_delta(S_current, put_strike, time_remaining_years, r, sigma, "put")
            ctx.put_iv = sigma
            
            # PnL is negative if current price > entry price (since we are short)
            ctx.metadata['call_pnl_usd'] = -call_loss_usd
            ctx.metadata['put_pnl_usd'] = -put_loss_usd
            ctx.metadata['total_entry_premium'] = entry_premium_usd
            
            ctx.is_hedged = hedge_qty_btc != 0
            
            regime = MockRegime()
            trend = MockTrend()
            
            # Simple regime logic for backtester based on moving average
            if tick_idx > 20:
                past_price = float(week_candles[tick_idx-20]["close"])
                if S_current < past_price * 0.98:
                    regime.current_regime = MarketRegime.CONFIRMED_TREND
                    trend.trend_direction = TrendDirection.SHORT
                elif S_current > past_price * 1.02:
                    regime.current_regime = MarketRegime.CONFIRMED_TREND
                    trend.trend_direction = TrendDirection.LONG
            
            risk_result = risk_engine.evaluate(regime, trend, ctx)
            
            breakdown = risk_result.debug_information.get("call_stress_breakdown", None)
            if breakdown and hasattr(breakdown, "fusion_breakdown"):
                fusion = breakdown.fusion_breakdown
            else:
                fusion = StressFusionBreakdown()
                
            decision = decision_engine.evaluate(
                fused_score=risk_result.overall_risk_score,
                breakdown=fusion,
                context=ctx,
                current_hedge_ratio=1.0 if hedge_qty_btc != 0 else 0.0,
                current_time=float(candle["time"]),
                regime_result=regime
            )
            
            if decision and decision.action.name not in ("HOLD", "MONITOR", "NO_ACTION"):
                sizing = sizing_engine.evaluate(decision, ctx, hedge_qty_btc)
                
                if decision.action.name == "DEHEDGE":
                    hedge_qty_btc = 0.0
                elif sizing and sizing.hedge_quantity != 0:
                    if hedge_qty_btc == 0:
                        hedge_entry_price = S_current
                        hedge_events += 1
                        hedged_this_week = True
                    hedge_qty_btc = sizing.hedge_quantity
                    
        # Week end
        S_final = float(end_candle["close"])
        call_final = max(0, S_final - call_strike)
        put_final = max(0, put_strike - S_final)
        
        call_pnl = (call_entry_price - call_final) * (total_lots / 2) * LOT_TO_BTC
        put_pnl = (put_entry_price - put_final) * (total_lots / 2) * LOT_TO_BTC
        week_options_pnl = call_pnl + put_pnl
        
        week_hedge_pnl = 0.0
        if hedge_qty_btc != 0:
            # PnL = (Exit - Entry) * Qty_in_contracts * contract_size
            week_hedge_pnl = (S_final - hedge_entry_price) * hedge_qty_btc * FUTURES_CONTRACT_SIZE_BTC
            # print(f"Hedge Debug - Entry: {hedge_entry_price}, Exit: {S_final}, Qty: {hedge_qty_btc}, PnL: {week_hedge_pnl}")
            
        if hedged_this_week and week_options_pnl < -entry_premium_usd:
            catastrophes_prevented += 1
            
        total_strategy_pnl_usd += week_options_pnl
        total_hedge_pnl_usd += week_hedge_pnl
        
        weekly_results.append({
            "week": week_idx + 1,
            "options_pnl": week_options_pnl,
            "hedge_pnl": week_hedge_pnl,
            "combined": week_options_pnl + week_hedge_pnl,
            "hedged": hedged_this_week
        })
        
        print(f"Week {week_idx+1}: Opt PnL: ${week_options_pnl:.2f}, Hedge PnL: ${week_hedge_pnl:.2f}")

    # Generate Report
    report_content = f"""# ARES 1-Year Historical Backtest Report

## Overall Performance
- **Total Option Strategy PnL**: ${total_strategy_pnl_usd:,.2f}
- **Total Hedge PnL**: ${total_hedge_pnl_usd:,.2f}
- **Total Combined PnL**: ${(total_strategy_pnl_usd + total_hedge_pnl_usd):,.2f}

## Hedge Analytics
- **Total Hedge Events (Trips)**: {hedge_events}
- **Catastrophic Losses Prevented**: {catastrophes_prevented}
- **Average Hedge Cost/Benefit per Trade**: ${(total_hedge_pnl_usd / len(weeks)):,.2f}

## Weekly Breakdown
"""
    for r in weekly_results:
        flag = "🛡️ HEDGED" if r["hedged"] else "✅ CLEAN"
        report_content += f"- **Week {r['week']}** ({flag}): Options: ${r['options_pnl']:,.2f} | Hedge: ${r['hedge_pnl']:,.2f} | Net: ${r['combined']:,.2f}\n"
        
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ares_1_year_performance_report.md"), "w", encoding="utf-8") as f:
        f.write(report_content)
        
    # Generate graph using matplotlib
    import matplotlib.pyplot as plt
    weeks_x = [r["week"] for r in weekly_results]
    combined_pnl = [r["combined"] for r in weekly_results]
    cumulative_pnl = []
    curr = 0
    for p in combined_pnl:
        curr += p
        cumulative_pnl.append(curr)
        
    plt.figure(figsize=(10, 6))
    plt.plot(weeks_x, cumulative_pnl, label="Cumulative Net PnL (USD)", color="green", linewidth=2)
    plt.title("ARES 1-Year Backtest - Cumulative Performance")
    plt.xlabel("Week")
    plt.ylabel("PnL (USD)")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ares_1_year_graph.png"))
    
    print("Report generated: ares_1_year_performance_report.md")
    print("Graph generated: ares_1_year_graph.png")

if __name__ == "__main__":
    run_1_year_backtest()
