import db_manager, json

data = db_manager.load_all_data()
if data:
    trades = data.get('trades', [])
    live_trades = data.get('live_trades', [])
    print("PAPER trades:", len(trades))
    print("LIVE trades:", len(live_trades))
    print()
    print("=== Last 5 PAPER trades ===")
    for t in trades[-5:]:
        d = t.get("date", "?")
        r = t.get("exit_reason", "?")
        p = t.get("pnl", "?")
        e = t.get("equity_after", "?")
        m = t.get("mode", "?")
        print(f"  {d} | {m} | {r} | PnL: {p} | Equity: {e}")
    print()
    print("=== Last 5 LIVE trades ===")
    for t in live_trades[-5:]:
        d = t.get("date", "?")
        r = t.get("exit_reason", "?")
        p = t.get("pnl", "?")
        e = t.get("equity_after", "?")
        print(f"  {d} | {r} | PnL: {p} | Equity: {e}")
else:
    print("No data from cloud DB")
