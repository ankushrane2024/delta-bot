"""
chart_generator.py — Server-Side P&L Chart Generator
=====================================================
Generates beautiful equity curve + daily PnL charts using matplotlib
so they can be saved permanently and sent to Telegram as a record
after every trade close.
"""

import os
import json
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from logger import app_logger

# Chart styling constants
DARK_BG = '#0f1729'
PANEL_BG = '#1a2332'
GREEN = '#10b981'
RED = '#ef4444'
AMBER = '#f59e0b'
TEXT_COLOR = '#e2e8f0'
GRID_COLOR = '#1e3a5f'
ACCENT_BLUE = '#3b82f6'

CHARTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


def generate_trade_close_chart(trades, current_trade=None, save_path=None):
    """
    Generate a comprehensive 2-panel chart after every trade close:
      Top Panel:  Equity Curve (all-time)
      Bottom Panel: Daily P&L bars
      
    Args:
        trades: List of trade dicts from performance_tracker (each has 'date', 'pnl', 'equity_after', etc.)
        current_trade: Dict with info about the trade that just closed (optional, for annotations)
        save_path: Override the default save location
        
    Returns:
        str: Absolute path to the saved PNG image, or None on failure
    """
    if not trades or len(trades) == 0:
        app_logger.warning("ChartGen: No trades to chart.")
        return None

    try:
        # ── Parse Data ──────────────────────────────────────────
        dates = []
        equities = []
        pnls = []
        colors = []
        exit_reasons = []

        starting_equity = 10000.0  # Default

        for t in trades:
            try:
                date_str = t.get('date', '')
                if not date_str:
                    entry = t.get('entry_time', '')
                    if entry:
                        date_str = entry[:10]
                    else:
                        continue

                dt = datetime.strptime(date_str, '%Y-%m-%d')
                dates.append(dt)
                
                eq = t.get('equity_after', starting_equity)
                equities.append(eq)
                
                pnl = t.get('pnl', 0) + t.get('hedge_pnl', 0)
                pnls.append(pnl)
                colors.append(GREEN if pnl >= 0 else RED)
                exit_reasons.append(t.get('exit_reason', ''))
            except Exception:
                continue

        if len(dates) == 0:
            app_logger.warning("ChartGen: Could not parse any trade dates.")
            return None

        # Add starting point for equity curve
        equity_dates = [dates[0]]
        equity_values = [starting_equity]
        for i, dt in enumerate(dates):
            equity_dates.append(dt)
            equity_values.append(equities[i])

        # ── Create Figure ───────────────────────────────────────
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), 
                                        gridspec_kw={'height_ratios': [2, 1]},
                                        facecolor=DARK_BG)
        fig.subplots_adjust(hspace=0.35, top=0.92, bottom=0.08, left=0.1, right=0.95)

        # ── Top Panel: Equity Curve ─────────────────────────────
        ax1.set_facecolor(PANEL_BG)
        
        # Fill under the curve
        ax1.fill_between(equity_dates, starting_equity, equity_values, 
                         where=[v >= starting_equity for v in equity_values],
                         color=GREEN, alpha=0.15, interpolate=True)
        ax1.fill_between(equity_dates, starting_equity, equity_values,
                         where=[v < starting_equity for v in equity_values],
                         color=RED, alpha=0.15, interpolate=True)
        
        # Main line
        ax1.plot(equity_dates, equity_values, color=ACCENT_BLUE, linewidth=2.5, 
                 marker='o', markersize=5, markerfacecolor='white', markeredgecolor=ACCENT_BLUE,
                 zorder=5)
        
        # Starting capital reference line
        ax1.axhline(y=starting_equity, color=AMBER, linestyle='--', linewidth=1, alpha=0.6, label='Starting Capital')

        # Annotate latest equity
        if len(equity_values) > 1:
            latest_eq = equity_values[-1]
            total_pnl = latest_eq - starting_equity
            pnl_pct = (total_pnl / starting_equity) * 100
            color = GREEN if total_pnl >= 0 else RED
            sign = '+' if total_pnl >= 0 else ''
            ax1.annotate(f'${latest_eq:,.2f}\n({sign}{pnl_pct:.1f}%)', 
                        xy=(equity_dates[-1], latest_eq),
                        xytext=(15, 15), textcoords='offset points',
                        fontsize=11, fontweight='bold', color=color,
                        bbox=dict(boxstyle='round,pad=0.4', facecolor=DARK_BG, edgecolor=color, alpha=0.9),
                        arrowprops=dict(arrowstyle='->', color=color, lw=1.5))

        # Mark the current trade that just closed
        if current_trade and len(equity_dates) > 1:
            trade_pnl = current_trade.get('pnl', 0) + current_trade.get('hedge_pnl', 0)
            marker_color = GREEN if trade_pnl >= 0 else RED
            marker_symbol = '▲' if trade_pnl >= 0 else '▼'
            reason = current_trade.get('exit_reason', 'Closed')
            ax1.annotate(f'{marker_symbol} {reason}\n${trade_pnl:+.2f}',
                        xy=(equity_dates[-1], equity_values[-1]),
                        xytext=(-60, -35), textcoords='offset points',
                        fontsize=8, color=marker_color, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor=PANEL_BG, edgecolor=marker_color, alpha=0.8))

        ax1.set_title('Equity Curve \u2014 All Trades', fontsize=14, fontweight='bold', 
                      color=TEXT_COLOR, pad=10)
        ax1.set_ylabel('Equity ($)', fontsize=11, color=TEXT_COLOR)
        ax1.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax1.grid(True, alpha=0.2, color=GRID_COLOR)
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.spines['left'].set_color(GRID_COLOR)
        ax1.spines['bottom'].set_color(GRID_COLOR)
        ax1.legend(loc='upper left', fontsize=9, facecolor=PANEL_BG, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)

        # ── Bottom Panel: Daily P&L Bars ────────────────────────
        ax2.set_facecolor(PANEL_BG)
        
        bar_width = max(0.5, min(2.0, 30.0 / max(len(dates), 1)))
        bars = ax2.bar(dates, pnls, width=bar_width, color=colors, alpha=0.85, 
                       edgecolor=[c if abs(p) > 0 else 'none' for c, p in zip(colors, pnls)],
                       linewidth=0.8)
        
        # Add value labels on bars
        for bar, pnl_val in zip(bars, pnls):
            if abs(pnl_val) > 0.01:
                va = 'bottom' if pnl_val >= 0 else 'top'
                offset = 1 if pnl_val >= 0 else -1
                ax2.text(bar.get_x() + bar.get_width()/2, pnl_val + offset,
                        f'${pnl_val:+.1f}', ha='center', va=va, fontsize=7, 
                        color=TEXT_COLOR, fontweight='bold')

        ax2.axhline(y=0, color=TEXT_COLOR, linewidth=0.8, alpha=0.3)
        ax2.set_title('Trade P&L History', fontsize=13, fontweight='bold', 
                      color=TEXT_COLOR, pad=10)
        ax2.set_ylabel('P&L ($)', fontsize=11, color=TEXT_COLOR)
        ax2.tick_params(colors=TEXT_COLOR, labelsize=9)
        ax2.grid(True, alpha=0.15, color=GRID_COLOR, axis='y')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_color(GRID_COLOR)
        ax2.spines['bottom'].set_color(GRID_COLOR)

        # Format x-axis dates
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

        # ── Stats Box ───────────────────────────────────────────
        total_pnl = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        total = len(pnls)
        win_rate = (wins / total * 100) if total > 0 else 0
        avg_win = sum(p for p in pnls if p > 0) / wins if wins > 0 else 0
        avg_loss = sum(p for p in pnls if p < 0) / losses if losses > 0 else 0

        stats_text = (
            f"Total Trades: {total}  |  Wins: {wins}  |  Losses: {losses}  |  "
            f"Win Rate: {win_rate:.0f}%  |  "
            f"Net P&L: ${total_pnl:+.2f}  |  "
            f"Avg Win: ${avg_win:+.2f}  |  Avg Loss: ${avg_loss:+.2f}"
        )
        fig.text(0.5, 0.01, stats_text, ha='center', fontsize=9, color=TEXT_COLOR,
                 fontstyle='italic',
                 bbox=dict(boxstyle='round,pad=0.5', facecolor=PANEL_BG, edgecolor=GRID_COLOR, alpha=0.9))

        # ── Watermark ───────────────────────────────────────────
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M IST')
        fig.text(0.95, 0.96, f'Generated: {now_str}', ha='right', fontsize=7, 
                 color=GRID_COLOR, fontstyle='italic')

        # ── Save ────────────────────────────────────────────────
        if save_path is None:
            today_str = datetime.now().strftime('%Y-%m-%d_%H%M')
            save_path = os.path.join(CHARTS_DIR, f"trade_close_{today_str}.png")

        fig.savefig(save_path, dpi=150, facecolor=DARK_BG, bbox_inches='tight')
        plt.close(fig)

        app_logger.info(f"ChartGen: Saved trade close chart to {save_path}")
        return save_path

    except Exception as e:
        app_logger.error(f"ChartGen: Failed to generate chart: {e}")
        try:
            plt.close('all')
        except:
            pass
        return None
