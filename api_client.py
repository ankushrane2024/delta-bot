import hmac
import hashlib
import json
import time
import requests
import websocket
import threading
from config import DELTA_API_KEY, DELTA_API_SECRET, DELTA_INDIA_BASE_URL, DELTA_INDIA_WS_URL
from logger import app_logger, error_logger

class DeltaIndiaClient:
    def __init__(self, api_key=None, api_secret=None):
        self.api_key = api_key or DELTA_API_KEY
        self.api_secret = api_secret or DELTA_API_SECRET
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

    def sync_time(self):
        try:
            r = requests.get(f"{DELTA_INDIA_BASE_URL}/v2/tickers", timeout=10)
            server_date = r.headers.get('Date')
            if server_date:
                import email.utils
                server_ts = email.utils.mktime_tz(email.utils.parsedate_tz(server_date))
                self.time_offset = int(server_ts - time.time())
                app_logger.info(f"API: Time synced. Offset: {self.time_offset}s")
        except Exception as e:
            error_logger.error(f"API: Time sync failed: {e}")

    def _generate_signature(self, method, path, body=""):
        timestamp = str(int(time.time() + self.time_offset))
        payload = method + timestamp + path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    def request(self, method, path, params=None, data=None):
        url = DELTA_INDIA_BASE_URL + path
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
            res_json = response.json()
            if not res_json.get('success') and 'error' in res_json:
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

    def place_order(self, product_id, side, size, order_type="market_order", limit_price=None):
        data = {
            "product_id": product_id,
            "side": side,
            "size": int(size),
            "order_type": order_type
        }
        if limit_price:
            data["limit_price"] = str(limit_price)
        return self.request("POST", "/v2/orders", data=data)

    def get_positions(self):
        return self.request("GET", "/v2/positions")

    def set_margin_mode(self, product_id, margin_mode="portfolio"):
        """Strictly sets Portfolio Margin mode before trading."""
        data = {
            "product_id": product_id,
            "margin_mode": margin_mode
        }
        return self.request("POST", "/v2/orders/margin_mode", data=data)

    def set_leverage(self, product_id, leverage):
        return self.request("POST", "/v2/orders/leverage", data={"product_id": product_id, "leverage": str(leverage)})

    # --- Real-Time WebSocket ---
    def start_ws(self, symbols=None):
        if not symbols:
            # By default subscribe to BTC options and perps if possible, 
            # or just all tickers if delta allows. Delta 'all' is usually not supported.
            # We will subscribe to symbols dynamically or just listen to what's active.
            symbols = []

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

        self.ws = websocket.WebSocketApp(
            DELTA_INDIA_WS_URL,
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
            
        # Unpack list if returned from REST query
        if isinstance(data, list):
            if len(data) > 0:
                data = data[0]
            else:
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
            
        formatted_data = {
            'symbol': symbol,
            'mark_price': mark_price_float,
            'greeks': greeks
        }
        
        self.ticker_data[symbol] = formatted_data
        self.last_price_update_time = time.time()
