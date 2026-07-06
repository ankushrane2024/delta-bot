import hmac
import hashlib

class DeltaAuthenticator:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        
    def _generate_signature(self, method: str, timestamp: str, path: str, query_string: str = "", payload: str = "") -> str:
        signature_data = method + timestamp + path + query_string + payload
        return hmac.new(
            self.api_secret.encode("utf-8"),
            signature_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def sign_rest_request(self, method: str, timestamp_ms: int, path: str, query_string: str = "", payload: str = "") -> dict:
        timestamp_str = str(timestamp_ms)
        sig = self._generate_signature(method.upper(), timestamp_str, path, query_string, payload)
        return {
            "api-key": self.api_key,
            "signature": sig,
            "timestamp": timestamp_str
        }

    def sign_ws_auth(self, timestamp_ms: int) -> dict:
        timestamp_str = str(timestamp_ms)
        # Delta WS signature typically uses GET + timestamp + /ws or /v2/ws
        # The standard for delta exchange WS auth is:
        sig = self._generate_signature("GET", timestamp_str, "/ws")
        return {
            "type": "auth",
            "payload": {
                "api-key": self.api_key,
                "signature": sig,
                "timestamp": timestamp_str
            }
        }
