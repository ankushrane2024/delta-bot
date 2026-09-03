"""
Restore today's Aug 6, 2026 trade to the cloud DB.
Based on: same symbols as Aug 5, manual entry ~9:00AM IST, EOD exit, good profit.
We use entry prices from active_positions.json and estimate exit conservatively.
"""
import db_manager, json
from datetime import datetime, timezone, timedelta

# Load current cloud data
data = db_manager.load_all_data() or {}

existing_trades = data.get('trades', [])
print(f"Existing paper trades: {len(existing_trades)}")
for t in existing_trades:
    print(f"  {t.get('date')} | {t.get('exit_reason')} | PnL: {t.get('pnl')}")

# Aug 6 trade details (reconstructed from evidence)
# Entry prices from active_positions.json + cloud: call=$25.15, put=$31.03
# These options expired Aug 6 (060826 = 6 Aug 2026)
# Entry: 500 lots x 0.001 BTC = 0.5 BTC per leg
# Premium collected = (25.154 + 31.031) * 0.5 BTC = $28.09 per BTC
# LOT_TO_BTC = 0.001, so 500 lots = 0.5 BTC per leg
# Premium = 25.154 * 500 * 0.001 + 31.031 * 500 * 0.001 = 12.577 + 15.516 = $28.09

call_entry = 25.154830575888827
put_entry  = 31.03173397087127
lots       = 500
lot_to_btc = 0.001

premium_collected = (call_entry + put_entry) * lots * lot_to_btc
print(f"\nReconstructed premium collected: ${premium_collected:.4f}")

# For profit, user said "good profit" ~$20-$100.
# Options expired today (060826), so at expiry, OTM options = worth ~$0
# If options expired worthless = 100% profit captured
# Let's use a conservative ~60% profit capture as estimate
# User will verify and we can update
estimated_profit = premium_collected * 0.60  # 60% of premium = $16.85
print(f"Estimated profit (60% capture): ${estimated_profit:.2f}")

# Previous equity was $49999.92 (from Aug 5 trade)
equity_after = 49999.92 + estimated_profit

aug6_trade = {
    "date": "2026-08-06",
    "mode": "PAPER",
    "unprotected_loss": 0,
    "hedge_gain": 0,
    "protection_efficiency": 0,
    "ares_decision": "NONE",
    "ares_risk_score": 0,
    "entry_time": "2026-08-06T09:00:00+05:30",
    "exit_time": "2026-08-06T17:00:00+05:30",
    "call_symbol": "C-BTC-65600-060826",
    "put_symbol": "P-BTC-63600-060826",
    "call_entry_price": call_entry,
    "put_entry_price": put_entry,
    "call_exit_price": 0,
    "put_exit_price": 0,
    "premium_collected": round(premium_collected, 4),
    "pnl": round(estimated_profit, 2),
    "hedge_pnl": 0,
    "pct_profit_captured": 60.0,
    "max_pnl_pct": 0,
    "min_pnl_pct": 0,
    "max_pnl_time": "",
    "min_pnl_time": "",
    "exit_reason": "EOD Square-off",
    "equity_after": round(equity_after, 2),
    "regime_filter_enabled": False,
    "adx": 0,
    "hedge_events": [],
    "chart_data": [],
    "_note": "RECONSTRUCTED - Render server crashed before logging. Profit is approximate (60% of premium). Please update with actual P&L."
}

print(f"\nAug 6 trade to add:")
print(f"  Premium: ${aug6_trade['premium_collected']}")
print(f"  PnL: ${aug6_trade['pnl']}")
print(f"  Equity after: ${aug6_trade['equity_after']}")

# Add to existing trades
all_trades = existing_trades + [aug6_trade]

# Save back to cloud
save_data = {
    "max_equity": max(t.get("equity_after", 0) for t in all_trades),
    "trades": all_trades,
    "live_max_equity": data.get("live_max_equity", 0),
    "live_trades": data.get("live_trades", data.get("live_trade_history", [])),
}

print(f"\nSaving {len(all_trades)} paper trades to cloud...")
success = db_manager.save_all_data(save_data)
print(f"Cloud save: {'SUCCESS' if success else 'FAILED'}")

# Also update local
with open('trade_history.json', 'w') as f:
    json.dump({
        "max_equity": save_data["max_equity"],
        "trades": all_trades
    }, f, indent=4)
print("Local trade_history.json updated.")

# Verify
verify = db_manager.load_all_data()
print(f"\nVerification - Trades in cloud: {len(verify.get('trades', []))}")
for t in verify.get('trades', []):
    print(f"  {t.get('date')} | PnL: {t.get('pnl')} | Equity: {t.get('equity_after')}")
