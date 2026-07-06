import threading
import json
import logging
import time
import websocket
from typing import Callable, Optional
from hedge.models.core_interfaces import Clock
from hedge.engines.delta.auth import DeltaAuthenticator

logger = logging.getLogger("ARES.DeltaWS")

class DeltaWebSocketClient:
    def __init__(self, ws_url: str, auth: DeltaAuthenticator, clock: Clock):
        self.ws_url = ws_url
        self.auth = auth
        self.clock = clock
        
        self.ws: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        self.is_connected = False
        self.last_sequence: Optional[int] = None
        self.last_msg_time = 0.0
        
        self.on_message_callback: Optional[Callable[[dict], None]] = None
        self.on_gap_detected_callback: Optional[Callable[[], None]] = None
        self.on_reconnect_callback: Optional[Callable[[], None]] = None
        
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def set_callbacks(self, on_message, on_gap, on_reconnect):
        self.on_message_callback = on_message
        self.on_gap_detected_callback = on_gap
        self.on_reconnect_callback = on_reconnect

    def connect(self):
        with self.lock:
            if self.is_connected:
                return
            self._stop_event.clear()
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()
            
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

    def disconnect(self):
        self._stop_event.set()
        if self.ws:
            self.ws.close()

    def _on_open(self, ws):
        with self.lock:
            self.is_connected = True
            logger.info("WebSocket connected. Authenticating...")
            
            # Authenticate
            auth_payload = self.auth.sign_ws_auth(int(self.clock.now() * 1000))
            self.ws.send(json.dumps(auth_payload))
            
            # Subscribe
            sub_payload = {
                "type": "subscribe",
                "payload": {
                    "channels": [
                        {"name": "orders"},
                        {"name": "positions"}
                    ]
                }
            }
            self.ws.send(json.dumps(sub_payload))
            
            if self.on_reconnect_callback:
                self.on_reconnect_callback()

    def _on_message(self, ws, message):
        self.last_msg_time = self.clock.now()
        try:
            data = json.loads(message)
            if "seq" in data:
                seq = data["seq"]
                with self.lock:
                    if self.last_sequence is not None:
                        if seq <= self.last_sequence:
                            # Duplicate or old message
                            return
                        if seq > self.last_sequence + 1:
                            # Sequence Gap
                            logger.warning(f"Sequence gap detected! Expected {self.last_sequence + 1}, got {seq}")
                            if self.on_gap_detected_callback:
                                self.on_gap_detected_callback()
                    self.last_sequence = seq
                    
            if self.on_message_callback:
                self.on_message_callback(data)
                
        except Exception as e:
            logger.error(f"Failed to process WS message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        with self.lock:
            self.is_connected = False
            logger.warning("WebSocket closed. Attempting reconnect in background.")

    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            time.sleep(1) # We use time.sleep for the background thread ticking, but logic uses self.clock
            with self.lock:
                if not self.is_connected:
                    continue
                now = self.clock.now()
                # Ping every 15 seconds
                if now - self.last_msg_time > 15.0:
                    try:
                        self.ws.send(json.dumps({"type": "ping"}))
                    except:
                        pass
                # Timeout if no message in 30 seconds
                if now - self.last_msg_time > 30.0:
                    logger.error("Heartbeat timeout. Forcing reconnect.")
                    self.ws.close()
                    self.last_msg_time = now # Prevent immediate re-trigger
