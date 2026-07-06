import os
import copy
from dataclasses import dataclass
from typing import Dict, Any, List

# Try to load python-dotenv if installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

@dataclass(frozen=True)
class AresConfig:
    """
    Immutable Production Configuration.
    Validates presence of all necessary environment variables before allowing ARES to boot.
    """
    mode: str
    delta_api_key: str
    delta_api_secret: str
    sqlite_db_path: str
    log_dir: str
    rest_url: str
    ws_url: str

    @classmethod
    def load(cls, mode_override: str = None) -> "AresConfig":
        mode = mode_override or os.environ.get("BOT_MODE", "SHADOW").upper()
        api_key = os.environ.get("DELTA_API_KEY")
        api_secret = os.environ.get("DELTA_API_SECRET")
        sqlite_db_path = os.environ.get("SQLITE_DB_PATH", "shadow_validation.db")
        log_dir = os.environ.get("LOG_DIR", "logs")
        rest_url = os.environ.get("DELTA_REST_URL", "https://api.delta.exchange")
        ws_url = os.environ.get("DELTA_WS_URL", "wss://socket.delta.exchange")
        
        # Validation checks
        if mode not in ["DEV", "REPLAY", "SHADOW", "PAPER", "LIVE"]:
            raise ValueError(f"Invalid BOT_MODE: {mode}. Must be DEV, REPLAY, SHADOW, PAPER, or LIVE.")
            
        if not api_key or not api_secret:
            if mode in ["PAPER", "SHADOW", "LIVE"]:
                raise ValueError(f"Missing API credentials. DELTA_API_KEY and DELTA_API_SECRET are mandatory for {mode} mode.")

        if not rest_url or not ws_url:
            raise ValueError("Missing API URLs. DELTA_REST_URL and DELTA_WS_URL must be provided.")
            
        return cls(
            mode=mode,
            delta_api_key=api_key or "MOCK_KEY",
            delta_api_secret=api_secret or "MOCK_SECRET",
            sqlite_db_path=sqlite_db_path,
            log_dir=log_dir,
            rest_url=rest_url,
            ws_url=ws_url
        )

    def safe_dict(self) -> Dict[str, Any]:
        """Returns a copy of the config dictionary with secrets redacted for logging."""
        d = dict(
            mode=self.mode,
            delta_api_key="***REDACTED***" if self.delta_api_key and self.delta_api_key != "MOCK_KEY" else self.delta_api_key,
            delta_api_secret="***REDACTED***",
            sqlite_db_path=self.sqlite_db_path,
            log_dir=self.log_dir,
            rest_url=self.rest_url,
            ws_url=self.ws_url
        )
        return d

    def __str__(self):
        # Prevent accidental printing of the dataclass which would expose secrets
        import json
        return f"AresConfig({json.dumps(self.safe_dict())})"
        
    def __repr__(self):
        return self.__str__()
