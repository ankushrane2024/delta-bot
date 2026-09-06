import hmac
import hashlib
import json
import time
import requests
import websocket
import threading
import socket
try:
    import urllib3.util.connection as urllib3_conn
    # Delta Exchange IP whitelist strictly uses IPv4; force IPv4 to avoid IPv6 mismatch
    urllib3_conn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass
from config import DELTA_API_KEY, DELTA_API_SECRET, DELTA_INDIA_BASE_URL, DELTA_INDIA_WS_URL
from logger import app_logger, error_logger
import config

class DeltaIndiaClient:
    def __init__(self, api_key=None, api_secret=None, base_url=None, skip_isolation_guard=False):
        self.base_url = (base_url or getattr(config, 'DELTA_BASE_URL', None) or DELTA_INDIA_BASE_URL).rstrip('/')
        self.api_key = api_key or DELTA_API_KEY
        self.api_secret = api_secret or DELTA_API_SECRET
        self.skip_isolation_guard = skip_isolation_guard
        self.session = requests.Session()
        self.time_offset = 0
        self.ws = None
        self.ticker_data = {} # Live WebSocket Feed
        self.ws_thread = None
        self.ws_connected = False
        self.ws_reconnect_attempts = 0
        self.ws_last_disconnect_time = None
        self.ws_alert_sent = False
        self.last_price_update_time = time.time()
        
        if self.api_key and self.api_secret:
            self.sync_time()

    def get_ws_url(self):
        b = (self.base_url or "").lower()
        if "testnet.deltaex.org" in b:
            return "wss://socket-ind.testnet.deltaex.org"
        elif "testnet-api.delta.exchange" in b or "demo.delta.exchange" in b:
            return "wss://testnet-api.delta.exchange"
        elif "api.delta.exchange" in b:
            return "wss://socket.delta.exchange"
        return DELTA_INDIA_WS_URL

    def sync_time(self):
        try:
            r = requests.get(f"{self.base_url}/v2/tickers", timeout=10)
            server_date = r.headers.get('Date')
            if server_date:
                import email.utils
                server_ts = email.utils.mktime_tz(email.utils.parsedate_tz(server_date))
                self.time_offset = int(server_ts - time.time())
                app_logger.info(f"API: Time synced ({self.base_url}). Offset: {self.time_offset}s")
        except Exception as e:
            error_logger.error(f"API: Time sync failed ({self.base_url}): {e}")

    def _generate_signature(self, method, path, body=""):
        timestamp = str(int(time.time()) + self.time_offset)
        payload = method + timestamp + path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    def request(self, method, path, params=None, data=None):
        # ── AIRTIGHT ACCOUNT ISOLATION GUARD ──────────────────────────────────────
        # When DEMO slot is active, requests to LIVE production gateways are strictly blocked.
        # Credential probes specify skip_isolation_guard=True to safely test connectivity.
        try:
            if not getattr(self, 'skip_isolation_guard', False):
                import db_manager
                active_slot = db_manager.get_active_api_slot()
                if active_slot == 'demo':
                    # LIVE gateway detection: api.india.delta.exchange or api.delta.exchange
                    b_url = (self.base_url or '').lower()
                    is_live_gateway = ('api.india.delta.exchange' in b_url) or (
                        'api.delta.exchange' in b_url and 'testnet' not in b_url
                    )
                    if is_live_gateway:
                        error_logger.critical(
                            f"[SECURITY GUARD BLOCKED] Attempted {method} {path} to LIVE production gateway ({self.base_url}) while DEMO account is active! Request aborted."
                        )
                        return {
                            'success': False,
                            'error': {
                                'code': 'account_isolation_guard_tripped',
                                'message': f'CRITICAL: Request to live gateway ({self.base_url}) strictly blocked while in DEMO mode.'
                            }
                        }
        except Exception:
            pass

        url = self.base_url + path
        query_string = ""
        if params:
            query_string = "?" + "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            url += query_string
        
        body = json.dumps(data) if data else ""
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.api_key and self.api_secret:
            timestamp, signature = self._generate_signature(method, path + query_string, body)
            headers.update({
                "api-key": self.api_key,
                "timestamp": timestamp,
                "signature": signature
            })
            
        try:
            response = self.session.request(method, url, headers=headers, data=body, timeout=15)
            try:
                res_json = response.json()
            except Exception:
                if response.ok:
                    res_json = {"success": True, "result": response.text}
                else:
                    res_json = {"success": False, "error": {"message": response.text, "code": "http_error"}}
                    
            if not res_json.get('success') and 'error' in res_json:
                # Auto re-sync time offset if signature expired using server_time context
                err_dict = res_json.get('error', {})
                if isinstance(err_dict, dict) and err_dict.get('code') == 'expired_signature':
                    server_time = err_dict.get('context', {}).get('server_time')
                    if server_time and not getattr(self, '_retrying_signature', False):
                        self._retrying_signature = True
                        try:
                            self.time_offset = int(server_time - time.time())
                            app_logger.info(f"API: Auto-resynced time offset from expired_signature context: {self.time_offset}s")
                            return self.request(method, path, params=params, data=data)
                        finally:
                            self._retrying_signature = False

                error_logger.warning(f"API Error Response: {method} {path} - {res_json['error']}")
            return res_json
        except Exception as e:
            error_logger.error(f"API Request failed: {method} {path} - {e}")
            return {"success": False, "error": {"message": str(e), "code": "exception"}}

    # --- REST Endpoints ---
    def get_balances(self):
        return self.request("GET", "/v2/wallet/balances")

    def get_tickers(self, params=None):
        return self.request("GET", "/v2/tickers", params=params)

    def get_candles(self, symbol, resolution, start=None, end=None):
        params = {"symbol": symbol, "resolution": resolution}
        if start: params["start"] = start
        if end: params["end"] = end
        return self.request("GET", "/v2/history/candles", params=params)

    @staticmethod
    def _is_live_toggle_shield_active():
        """CRITICAL PROTECTION SHIELD:
        Reads lot_size.json directly from disk on every order attempt.
        Returns True ONLY if the user has manually turned the Live Mode Toggle ON.
        If toggle is OFF, real orders are NEVER placed on Delta Exchange."""
        try:
            import json, os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            p = os.path.join(base_dir, "lot_size.json")
            if os.path.exists(p):
                with open(p, "r") as f:
                    d = json.load(f)
                return bool(d.get("live_mode", False))
        except Exception:
            pass
        return False

    def place_order(self, product_id, side, size, order_type="market_order", limit_price=None, reduce_only=False):
        # ── PROTECTION SHIELD ─────────────────────────────────────────────────
        # Allow reduce_only=True orders so existing open positions can be safely closed/squared off.
        # But STRICTLY FORBID OPENING ANY NEW POSITION unless the user manually enabled the Live Toggle!
        if not reduce_only:
            if not self._is_live_toggle_shield_active():
                app_logger.critical(
                    f"[PROTECTION SHIELD BLOCKED REAL ORDER] Blocked {side.upper()} order (pid={product_id}, size={size}) on Delta Exchange! "
                    f"Reason: Live Mode Toggle is OFF. Real positions are strictly forbidden until manually enabled by you."
                )
                return {
                    "success": False,
                    "error": "PROTECTION SHIELD: Live Mode Toggle is OFF. Real exchange order hard-blocked to protect your funds."
                }

        data = {
            "product_id": product_id,
            "side": side,
            "size": int(size),
            "order_type": order_type
        }
        if limit_price:
            data["limit_price"] = str(limit_price)
        if reduce_only:
            data["reduce_only"] = True
        return self.request("POST", "/v2/orders", data=data)

    def place_stop_order(self, product_id, side, size, stop_price, limit_price=None):
        """Places a stop-limit order (exchange-native SL backup)."""
        # ── PROTECTION SHIELD ──
        if not self._is_live_toggle_shield_active():
            app_logger.critical(
                f"[PROTECTION SHIELD BLOCKED STOP ORDER] Blocked stop order on Delta Exchange! Live Mode Toggle is OFF."
            )
            return {
                "success": False,
                "error": "PROTECTION SHIELD: Live Mode Toggle is OFF. Stop order blocked."
            }

        if limit_price is None:
            if side == 'buy':
                limit_price = round(stop_price * 1.25, 2)
            else:
                limit_price = round(stop_price * 0.75, 2)

        data = {
            "product_id": product_id,
            "side": side,
            "size": int(size),
            "order_type": "limit_order",
            "limit_price": str(limit_price),
            "stop_order_type": "stop_loss_order",
            "stop_price": str(round(stop_price, 4)),
            "isTrailingStopLoss": False
        }
        app_logger.info(f"API: Placing exchange backup stop-SL | product={product_id} side={side} size={size} stop_price={stop_price} limit_price={limit_price}")
        return self.request("POST", "/v2/orders", data=data)

    def cancel_order(self, product_id, order_id):
        """Cancels an open order by ID. Used to cancel the backup SL before normal close.

        Args:
            product_id: Delta Exchange product ID
            order_id: The order ID to cancel (stored as exchange_sl_order_id per leg)
        """
        data = {
            "product_id": product_id,
            "id": order_id
        }
        app_logger.info(f"API: Cancelling order {order_id} for product {product_id}")
        return self.request("DELETE", "/v2/orders", data=data)

    def get_positions(self, product_id=None, underlying_asset_symbol="BTC"):
        params = {}
        if product_id:
            params["product_id"] = product_id
        elif underlying_asset_symbol:
            params["underlying_asset_symbol"] = underlying_asset_symbol
        return self.request("GET", "/v2/positions", params=params)

    def get_profile(self):
        """Fetch user profile details including account margin mode."""
        return self.request("GET", "/v2/profile")

    def set_margin_mode(self, product_id, margin_mode="portfolio"):
        """Sets margin mode before trading. Falls back gracefully to account profile margin."""
        try:
            data = {
                "product_id": product_id,
                "margin_mode": margin_mode
            }
            res = self.request("POST", "/v2/orders/margin_mode", data=data)
            if not res.get('success'):
                err = res.get('error', {})
                err_str = str(err).lower() if isinstance(err, (dict, str)) else ''
                if 'http_error' in err_str or 'not found' in err_str or res.get('message') == 'Not Found':
                    # Delta Exchange uses account-level margin mode. Check profile.
                    prof = self.get_profile()
                    if prof.get('success'):
                        curr_mode = prof.get('result', {}).get('margin_mode', 'cross')
                        return {'success': True, 'margin_mode': curr_mode, 'note': 'account_level_margin'}
            return res
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def set_leverage(self, product_id, leverage):
        return self.request("POST", "/v2/orders/leverage", data={"product_id": product_id, "leverage": str(leverage)})

    # --- Real-Time WebSocket ---
    def start_ws(self, symbols=None):
        if not symbols:
            # By default subscribe to BTCUSD index / perpetual ticker for live capital/PnL % calculations
            symbols = ["BTCUSD"]

        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get('type') == 'v2/ticker':
                    symbol = data.get('symbol')
                    # Guard: only cache if symbol is valid and mark_price is a real positive number
                    if not symbol:
                        return
                    mark_price = data.get('mark_price')
                    try:
                        mp_float = float(mark_price) if mark_price is not None else 0.0
                    except (ValueError, TypeError):
                        mp_float = 0.0
                    # Reject zero, negative, or suspiciously tiny prices (<0.01 USDT for BTC options)
                    if mp_float <= 0.01:
                        app_logger.debug(f"WS: Rejected bad mark_price={mark_price} for {symbol}")
                        return
                    # Ensure mark_price is stored as float for consistent downstream math
                    data['mark_price'] = mp_float
                    # Extract IV from Delta Exchange payload
                    iv_raw = data.get('mark_iv') or data.get('implied_volatility') or data.get('iv')
                    greeks_ws = data.get('greeks') or {}
                    if not iv_raw:
                        iv_raw = greeks_ws.get('iv') or greeks_ws.get('mark_iv') or 0
                    try:
                        iv_float = float(iv_raw) if iv_raw else 0.0
                    except (ValueError, TypeError):
                        iv_float = 0.0
                    data['iv'] = iv_float
                    self.ticker_data[symbol] = data
                    self.last_price_update_time = time.time()
            except Exception as e:
                error_logger.warning(f"WS on_message parse error: {e}")
        
        def on_error(ws, error):
            error_logger.error(f"WS Error: {error}")

        def on_close(ws, close_status_code, close_msg):
            self.ws_connected = False
            if not self.ws_last_disconnect_time:
                self.ws_last_disconnect_time = time.time()
                
            if self.ws_reconnect_attempts < 10:
                delay = min(2 ** self.ws_reconnect_attempts, 60)
                app_logger.warning(f"WS Connection Closed. Reconnecting in {delay}s (Attempt {self.ws_reconnect_attempts + 1}/10)...")
                self.ws_reconnect_attempts += 1
                threading.Timer(delay, self.start_ws, args=[symbols]).start()
            else:
                app_logger.error("WS Max Reconnection Attempts Reached. Falling back purely to HTTP.")

        def on_open(ws):
            app_logger.info("WS Connection Opened")
            self.ws_connected = True
            self.ws_reconnect_attempts = 0
            self.ws_last_disconnect_time = None
            self.ws_alert_sent = False
            if symbols:
                self.subscribe_ws(symbols)

        ws_url = self.get_ws_url()
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()

    def subscribe_ws(self, symbols):
        if self.ws and self.ws.sock and self.ws.sock.connected:
            subscribe_msg = {
                "type": "subscribe",
                "payload": {
                    "channels": [
                        {
                            "name": "v2/ticker",
                            "symbols": symbols
                        }
                    ]
                }
            }
            self.ws.send(json.dumps(subscribe_msg))
            app_logger.info(f"WS: Subscribed to {symbols}")
            
    def get_realtime_ticker(self, symbol):
        """Zero-latency read from memory cache. Returns None if data is missing or invalid."""
        cached = self.ticker_data.get(symbol)
        if not cached:
            return None
        # Safety check: reject cached entry if mark_price is 0, missing, or invalid
        mark_price = cached.get('mark_price')
        try:
            mp_float = float(mark_price) if mark_price is not None else 0.0
        except (ValueError, TypeError):
            mp_float = 0.0
        if mp_float <= 0.01:
            return None   # Treat as unavailable so callers use entry_price fallback
        return cached

    def update_ticker_from_http(self, symbol, data):
        """Safely updates the ticker_data cache with HTTP fallback data."""
        if not symbol or not data:
            return
            
        if isinstance(data, list):
            found = False
            for item in data:
                if item.get('symbol') == symbol:
                    data = item
                    found = True
                    break
            if not found:
                return
            
        # Parse Greeks if available from HTTP. Some endpoints nest it, some keep it flat.
        greeks = data.get('greeks', {})
        if not greeks and 'delta' in data:
            greeks = {
                'delta': data.get('delta', 0),
                'gamma': data.get('gamma', 0),
                'theta': data.get('theta', 0),
                'vega': data.get('vega', 0)
            }
        
        # Resolve mark_price — never store zero/missing as a valid price
        raw_price = data.get('mark_price') or data.get('close')
        try:
            mark_price_float = float(raw_price) if raw_price is not None else 0.0
        except (ValueError, TypeError):
            mark_price_float = 0.0
        
        # Only update cache if the new price is a valid positive number (> 0.01 USDT)
        # This prevents HTTP fallback from overwriting good WS data with a zero/stale price
        if mark_price_float <= 0.01:
            app_logger.warning(f"API: HTTP fallback returned invalid mark_price={raw_price} for {symbol} — keeping old cache")
            return
            
        # Extract IV from HTTP response
        iv_raw = data.get('mark_iv') or data.get('implied_volatility') or data.get('iv')
        if not iv_raw:
            iv_raw = greeks.get('iv') or greeks.get('mark_iv') or 0
        try:
            iv_float = float(iv_raw) if iv_raw else 0.0
        except (ValueError, TypeError):
            iv_float = 0.0
            
        formatted_data = {
            'symbol': symbol,
            'mark_price': mark_price_float,
            'greeks': greeks,
            'iv': iv_float
        }
        
        self.ticker_data[symbol] = formatted_data
        self.last_price_update_time = time.time()
