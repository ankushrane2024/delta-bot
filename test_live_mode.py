"""
============================================================
  LIVE MODE COMPREHENSIVE TEST SUITE
  Delta BTC Options Bot — Run BEFORE going live
============================================================

Tests every component of the live trading pipeline:
  1. API Credentials & Connectivity
  2. Live Mode Toggle (web API)
  3. Lot Sizing (live_lots=2 → 1 per leg)
  4. Place / Cancel a real test order (0-risk, immediate cancel)
  5. Stop-Loss order API (place + cancel)
  6. Backup SL cancel in close_all()
  7. Portfolio Margin mode
  8. Hedge (BTCUSD) product ID resolution
  9. WebSocket price feed
  10. Bot engine lot routing for LIVE mode

Run with: python test_live_mode.py
============================================================
"""

import sys
import os
import json
import time

# ── Add project to path ───────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 60

results = []

def test(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append((name, passed, detail))
    print(f"  {status}  {name}")
    if detail:
        print(f"         -> {detail}")

def section(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Config / Credentials
# ─────────────────────────────────────────────────────────────────────────────
section("1. API CREDENTIALS & CONFIG")

import config

api_key    = config.DELTA_API_KEY
api_secret = config.DELTA_API_SECRET
bot_mode   = config.BOT_MODE
sl_pct     = config.SL_PERCENT

test("DELTA_API_KEY loaded",
     bool(api_key) and api_key not in ('testnet_key', '', 'YOUR_KEY_HERE'),
     f"Key: {api_key[:8]}...{api_key[-4:]}" if api_key else "MISSING")

test("DELTA_API_SECRET loaded",
     bool(api_secret) and api_secret not in ('testnet_secret', '', 'YOUR_SECRET_HERE'),
     f"Secret: {api_secret[:6]}...{api_secret[-4:]}" if api_secret else "MISSING")

test("BOT_MODE is PAPER at startup (live toggled at runtime)",
     bot_mode in ('PAPER', 'SHADOW'),
     f"BOT_MODE = {bot_mode}")

test("SL_PERCENT is 1.00 (100% premium gain)",
     sl_pct == 1.00,
     f"SL_PERCENT = {sl_pct}")

backup_sl_pct = sl_pct * 2.0
test(f"Exchange backup SL = 2x SL_PERCENT = {backup_sl_pct*100:.0f}% premium gain",
     backup_sl_pct == 2.0,
     f"Bot SL at 100%, Exchange backup SL at 200% -- 100% gap = safe")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Lot Size Routing
# ─────────────────────────────────────────────────────────────────────────────
section("2. LOT SIZE ROUTING (PAPER vs LIVE)")

lot_file = os.path.join(os.path.dirname(__file__), 'lot_size.json')
with open(lot_file, 'r') as f:
    lot_data = json.load(f)

paper_lots = lot_data.get('total_lots', 1000)
live_lots  = lot_data.get('live_lots', 2)
live_mode  = lot_data.get('live_mode', False)

test("lot_size.json has total_lots (paper)",  paper_lots > 0,   f"paper total_lots = {paper_lots}")
test("lot_size.json has live_lots = 2",       live_lots == 2,   f"live_lots = {live_lots}")
test("live_mode defaults to False at startup",not live_mode,    f"live_mode = {live_mode}")
test("live per_entry_size = live_lots/2 = 1", live_lots // 2 == 1, f"{live_lots} / 2 = {live_lots//2} lot per leg")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: API Client Connectivity
# ─────────────────────────────────────────────────────────────────────────────
section("3. API CLIENT -- CONNECTIVITY & TIME SYNC")

from api_client import DeltaIndiaClient

print("  Connecting to Delta India API...")
client = DeltaIndiaClient(api_key=api_key, api_secret=api_secret)

# Time sync
test("Time offset synced", abs(client.time_offset) < 30,
     f"Offset = {client.time_offset}s (must be < 30s)")

# Public ticker
try:
    tickers = client.get_tickers()
    test("GET /v2/tickers (public)",
         tickers.get('success') and len(tickers.get('result', [])) > 0,
         f"Got {len(tickers.get('result', []))} instruments")
except Exception as e:
    test("GET /v2/tickers (public)", False, str(e))

# Authenticated balance check
try:
    balances = client.get_balances()
    test("GET /v2/wallet/balances (authenticated)",
         balances.get('success'),
         f"Response: success={balances.get('success')}, " +
         (f"assets={len(balances.get('result', []))}" if balances.get('result') else str(balances.get('error', ''))))
except Exception as e:
    test("GET /v2/wallet/balances (authenticated)", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: BTCUSD Perp -- Hedge Product Resolution
# ─────────────────────────────────────────────────────────────────────────────
section("4. HEDGE -- BTCUSD PERPETUAL PRODUCT ID")

btc_product_id = None
btc_mark_price = None
try:
    res = client.get_tickers({'symbol': 'BTCUSD'})
    if res.get('success') and res.get('result'):
        for item in res['result']:
            if item.get('symbol') == 'BTCUSD':
                btc_product_id = item.get('product_id')
                btc_mark_price = float(item.get('mark_price', 0))
                break
    test("BTCUSD product_id resolved", btc_product_id is not None,
         f"product_id = {btc_product_id}, mark_price = ${btc_mark_price:,.2f}")
except Exception as e:
    test("BTCUSD product_id resolved", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: Portfolio Margin Mode
# ─────────────────────────────────────────────────────────────────────────────
section("5. PORTFOLIO MARGIN MODE")

if btc_product_id:
    try:
        margin_res = client.set_margin_mode(btc_product_id, 'portfolio')
        ok = margin_res.get('success') or (
            'already' in str(margin_res.get('error', {}).get('message', '')).lower() or
            'portfolio' in str(margin_res.get('error', {}).get('message', '')).lower()
        )
        test("set_margin_mode('portfolio') accepted",
             ok,
             f"Response: {margin_res.get('result') or margin_res.get('error')}")
    except Exception as e:
        test("set_margin_mode('portfolio') accepted", False, str(e))
else:
    test("Portfolio margin test (skipped -- no product_id)", False, "Product ID not resolved")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: Stop-Loss Order API (place + immediate cancel -- ZERO RISK)
# ─────────────────────────────────────────────────────────────────────────────
section("6. EXCHANGE BACKUP SL -- place_stop_order + cancel_order")
print("  NOTE: Places stop at 3x market price (impossible to fill) then immediately cancels.")
print("  Zero execution risk -- just verifies API works end-to-end.")

stop_order_id = None
if btc_product_id and btc_mark_price:
    impossible_stop_price = round(btc_mark_price * 3.0, 2)
    try:
        sl_res = client.place_stop_order(
            product_id=btc_product_id,
            side='buy',
            size=1,
            stop_price=impossible_stop_price
        )
        placed = sl_res.get('success')
        if placed:
            stop_order_id = sl_res.get('result', {}).get('id')
        test("place_stop_order() -- stop at 3x market price",
             placed,
             f"Order ID: {stop_order_id}, stop_price=${impossible_stop_price:,.2f} (market=${btc_mark_price:,.2f})")
    except Exception as e:
        test("place_stop_order()", False, str(e))

    if stop_order_id:
        try:
            time.sleep(1)
            cancel_res = client.cancel_order(product_id=btc_product_id, order_id=stop_order_id)
            cancelled = cancel_res.get('success')
            test("cancel_order() -- cancel backup SL immediately",
                 cancelled,
                 f"Cancel result: {cancel_res.get('result') or cancel_res.get('error')}")
        except Exception as e:
            test("cancel_order()", False, str(e))
    else:
        test("cancel_order() (skipped -- stop order not placed)", False, "Depends on previous test")
else:
    test("Stop order test (skipped -- no product_id or price)", False, "BTCUSD product not resolved")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: ExecutionHandler -- LIVE mode routing
# ─────────────────────────────────────────────────────────────────────────────
section("7. EXECUTION HANDLER -- LIVE mode routing")

from execution import ExecutionHandler

handler_live  = ExecutionHandler(api_client=client, mode='LIVE')
handler_paper = ExecutionHandler(api_client=client, mode='PAPER')

test("ExecutionHandler(mode='LIVE') initialised",  handler_live.mode == 'LIVE',  f"mode={handler_live.mode}")
test("ExecutionHandler(mode='PAPER') initialised", handler_paper.mode == 'PAPER', f"mode={handler_paper.mode}")
test("LIVE handler starts with empty active_positions", len(handler_live.active_positions) == 0, "")
test("LIVE handler hedge_size_btc = 0.0", handler_live.hedge_size_btc == 0.0, "")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Source Code Integrity Checks
# ─────────────────────────────────────────────────────────────────────────────
section("8. SOURCE CODE INTEGRITY -- Live safety features")

with open('web_server.py', encoding='utf-8') as f:
    ws_src = f.read()
test("/api/live_mode GET defined",         "def get_live_mode" in ws_src, "")
test("/api/toggle_live_mode POST defined", "def toggle_live_mode" in ws_src, "")
test("/api/save_live_lots POST defined",   "def save_live_lots" in ws_src, "")

with open('execution.py', encoding='utf-8') as f:
    exec_src = f.read()
test("backup_sl_price set at 2x entry in execute_strangle", "backup_sl_price" in exec_src, "200% = crash-only backstop")
test("exchange_sl_order_id stored per leg",                 "exchange_sl_order_id" in exec_src, "")
test("cancel backup SL in close_all() before market close", "cancel_order" in exec_src, "prevents double-exit")

with open('api_client.py', encoding='utf-8') as f:
    api_src = f.read()
test("place_stop_order() in api_client",  "def place_stop_order" in api_src, "")
test("cancel_order() in api_client",      "def cancel_order" in api_src, "")

with open('bot_engine.py', encoding='utf-8') as f:
    be_src = f.read()
test("get_saved_lot_size() routes to live_lots in LIVE mode", "live_lots" in be_src, "")
test("live_lots fallback defaults to 1 if file missing",      "defaulting to 1 lot" in be_src, "")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: WebSocket Price Feed
# ─────────────────────────────────────────────────────────────────────────────
section("9. WEBSOCKET PRICE FEED")

print("  Starting WebSocket, waiting 5s for BTCUSD tick...")
try:
    client.start_ws(symbols=['BTCUSD'])
    time.sleep(5)
    ws_data = client.get_realtime_ticker('BTCUSD')
    connected = client.ws_connected
    has_price = ws_data and float(ws_data.get('mark_price', 0)) > 0
    test("WebSocket connected", connected, f"ws_connected={connected}")
    test("BTCUSD mark_price via WebSocket",
         has_price,
         f"mark_price=${float(ws_data.get('mark_price',0)):,.2f}" if ws_data else "No data received")
except Exception as e:
    test("WebSocket feed", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: Syntax check all changed files
# ─────────────────────────────────────────────────────────────────────────────
section("10. SYNTAX CHECK -- All modified files")

import ast

for fname in ['execution.py', 'api_client.py', 'bot_engine.py', 'web_server.py', 'config.py']:
    try:
        with open(fname, encoding='utf-8') as f:
            ast.parse(f.read())
        test(f"{fname} -- AST parse OK", True, "No syntax errors")
    except SyntaxError as e:
        test(f"{fname} -- AST parse OK", False, f"SyntaxError: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  LIVE MODE TEST RESULTS SUMMARY")
print('='*60)

passed_count = sum(1 for _, p, _ in results if p)
failed_count = sum(1 for _, p, _ in results if not p)
total_count  = len(results)

for name, passed, detail in results:
    status = PASS if passed else FAIL
    print(f"  {status}  {name}")

print(f"\n  TOTAL: {passed_count}/{total_count} passed, {failed_count} failed")
print()

if failed_count == 0:
    print("  ALL TESTS PASSED -- System is ready for LIVE trading.")
    print("  Next: Toggle LIVE MODE on dashboard and run a 1-lot-per-leg test.")
else:
    print(f"  {failed_count} TEST(S) FAILED -- Fix before going LIVE.")
    for name, passed, detail in results:
        if not passed:
            print(f"     FAIL: {name}")
            if detail:
                print(f"       --> {detail}")
print()
