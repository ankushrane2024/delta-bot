import requests
import json
import logging
from typing import Dict, Any, List
from hedge.models.core_interfaces import Clock
from hedge.engines.delta.auth import DeltaAuthenticator
from hedge.engines.delta.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("ARES.DeltaRestClient")

class ProviderUnavailable(Exception):
    pass

class DeltaRestClient:
    def __init__(self, base_url: str, auth: DeltaAuthenticator, clock: Clock, rate_limiter: TokenBucketRateLimiter):
        self.base_url = base_url
        self.auth = auth
        self.clock = clock
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        
        # Circuit Breaker state
        self.cb_failures = 0
        self.cb_threshold = 3
        self.cb_open = False
        self.cb_last_failure_time = 0.0
        self.cb_recovery_timeout = 30.0 # seconds
        
    def _check_circuit_breaker(self):
        if self.cb_open:
            if self.clock.now() - self.cb_last_failure_time > self.cb_recovery_timeout:
                logger.info("Circuit breaker HALF OPEN, attempting request...")
            else:
                raise ProviderUnavailable("Circuit Breaker is OPEN. Delta API is unreachable.")

    def _record_success(self):
        if self.cb_open or self.cb_failures > 0:
            logger.info("Circuit breaker CLOSED. Delta API recovered.")
        self.cb_failures = 0
        self.cb_open = False
        
    def _record_failure(self):
        self.cb_failures += 1
        self.cb_last_failure_time = self.clock.now()
        if self.cb_failures >= self.cb_threshold:
            if not self.cb_open:
                logger.critical("CIRCUIT BREAKER OPENED! Delta API failing.")
            self.cb_open = True
            
    def _request(self, method: str, path: str, payload: dict = None) -> Any:
        self._check_circuit_breaker()
        self.rate_limiter.acquire()
        
        timestamp_ms = int(self.clock.now() * 1000)
        payload_str = json.dumps(payload) if payload else ""
        
        headers = self.auth.sign_rest_request(method, timestamp_ms, path, payload=payload_str)
        headers["Content-Type"] = "application/json"
        
        url = self.base_url + path
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, headers=headers, timeout=5)
            elif method.upper() == "POST":
                resp = self.session.post(url, headers=headers, data=payload_str, timeout=5)
            elif method.upper() == "DELETE":
                resp = self.session.delete(url, headers=headers, data=payload_str, timeout=5)
            else:
                raise ValueError(f"Unsupported method {method}")
                
            if resp.status_code >= 500:
                self._record_failure()
                raise ProviderUnavailable(f"Delta API returned {resp.status_code}")
            
            resp.raise_for_status()
            self._record_success()
            return resp.json().get("result", resp.json())
        except requests.exceptions.RequestException as e:
            self._record_failure()
            raise ProviderUnavailable(f"Network error: {e}")

    def place_order(self, product_id: int, size: float, side: str, order_type: str, client_order_id: str) -> dict:
        payload = {
            "product_id": product_id,
            "size": size,
            "side": side.lower(),
            "order_type": order_type.lower(),
            "client_order_id": client_order_id
        }
        return self._request("POST", "/v2/orders", payload=payload)
        
    def cancel_order(self, client_order_id: str = None, order_id: str = None) -> dict:
        payload = {}
        if client_order_id:
            payload["client_order_id"] = client_order_id
        if order_id:
            payload["id"] = order_id
        return self._request("DELETE", "/v2/orders", payload=payload)
        
    def get_order(self, client_order_id: str) -> dict:
        return self._request("GET", f"/v2/orders?client_order_id={client_order_id}")
        
    def get_open_orders(self) -> List[dict]:
        return self._request("GET", "/v2/orders?state=open")
        
    def get_positions(self) -> List[dict]:
        return self._request("GET", "/v2/positions")
        
    def get_wallet_balances(self) -> List[dict]:
        return self._request("GET", "/v2/wallet/balances")
