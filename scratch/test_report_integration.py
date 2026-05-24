import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

def test_reports():
    print("====================================================")
    print("     Delta BTC Options Bot - Report Integration Test  ")
    print("====================================================")
    
    # helper for IST date
    today_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d')
    print(f"   Target date for today's report: {today_str}")

    # 1. Fetch initial reports list
    print("\n1. Fetching initial reports ledger from /api/reports...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/reports", timeout=10)
        initial_reports = r.json()
        print(f"   Initial reports count: {len(initial_reports)}")
        print("   Dates in ledger:", list(initial_reports.keys()))
    except Exception as e:
        print("   [FAIL] Could not fetch initial reports:", e)
        return

    # 2. Trigger manual order
    print("\n2. Triggering manual strangle entry via /api/manual_order...")
    try:
        r = requests.post("http://127.0.0.1:5000/api/manual_order", timeout=10)
        print("   Manual Strangle trigger response:", r.json())
    except Exception as e:
        print("   [FAIL] Manual strangle trigger failed:", e)
        return

    # 3. Wait for positions to establish
    print("\n3. Waiting 5 seconds for trade execution...")
    time.sleep(5)

    # 4. Check active positions
    print("\n4. Verifying active positions via /api/status...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/status")
        status = r.json()
        positions = status.get("positions", [])
        print(f"   Active positions found: {len(positions)}")
        # Note: Position might have hit TP immediately, which is fine since it would trigger report.
        # But if it's still running, we trigger emergency close!
    except Exception as e:
        print("   [FAIL] Could not verify active positions:", e)
        return

    # 5. Trigger square-off (if not already closed by TP)
    if len(positions) > 0:
        print("\n5. Strangle is active. Triggering square-off via /api/emergency_close...")
        try:
            r = requests.post("http://127.0.0.1:5000/api/emergency_close", timeout=10)
            print("   Square-off response:", r.json())
        except Exception as e:
            print("   [FAIL] Square-off failed:", e)
            return
        # Wait for file generation and system log
        time.sleep(3)
    else:
        print("\n5. Positions were already squared off automatically (Target Profit hit).")

    # 6. Verify daily_reports.json has a new entry for today!
    print("\n6. Verifying /api/reports for a fresh report...")
    try:
        r = requests.get("http://127.0.0.1:5000/api/reports", timeout=10)
        updated_reports = r.json()
        print(f"   Updated reports count: {len(updated_reports)}")
        print("   Dates in updated ledger:", list(updated_reports.keys()))
        
        if today_str in updated_reports:
            print(f"   [PASS] Found daily report ledger entry for target date: {today_str}")
            report_data = updated_reports[today_str]
            print("   Report Details:")
            print(f"     * Net P&L: ${report_data['summary']['net_pnl_usd']:.2f}")
            print(f"     * Total Trades: {report_data['summary']['total_trades']}")
            print(f"     * Win Rate: {report_data['summary']['win_rate']:.1f}%")
            print(f"     * PDF Path: {report_data['pdf_path']}")
            print(f"     * Excel Path: {report_data['xlsx_path']}")
        else:
            print(f"   [FAIL] Daily report ledger entry for {today_str} WAS NOT FOUND!")
            return
    except Exception as e:
        print("   [FAIL] Fetch updated reports failed:", e)
        return

    # 7. Check if PDF and Excel files exist on disk
    print("\n7. Checking if PDF and Excel files exist on the filesystem...")
    pdf_filepath = f"reports/Daily_Report_{today_str}.pdf"
    xlsx_filepath = f"reports/Daily_Report_{today_str}.xlsx"
    
    pdf_exists = os.path.exists(pdf_filepath)
    xlsx_exists = os.path.exists(xlsx_filepath)
    
    if pdf_exists:
        print(f"   [PASS] PDF Report file successfully generated: {pdf_filepath} (Size: {os.path.getsize(pdf_filepath)} bytes)")
    else:
        print(f"   [FAIL] PDF Report file does not exist: {pdf_filepath}")
        
    if xlsx_exists:
        print(f"   [PASS] Excel Report file successfully generated: {xlsx_filepath} (Size: {os.path.getsize(xlsx_filepath)} bytes)")
    else:
        print(f"   [FAIL] Excel Report file does not exist: {xlsx_filepath}")

    if pdf_exists and xlsx_exists and today_str in updated_reports:
        print("\n====================================================")
        print("    🌟 ALL REPORT INTEGRATION TESTS PASSED 100%! 🌟  ")
        print("====================================================")
    else:
        print("\n====================================================")
        print("        [FAIL] Report integration checks failed.     ")
        print("====================================================")

if __name__ == '__main__':
    test_reports()
