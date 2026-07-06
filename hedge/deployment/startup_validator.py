import logging
import os
import requests
import sqlite3
import json
from typing import Dict, Any

from hedge.deployment.config import AresConfig

logger = logging.getLogger("startup")

class StartupValidator:
    """
    Exhaustive pre-flight verification generating a structured startup report.
    ServiceRunner will completely refuse to boot into LIVE/SHADOW mode if this fails.
    """
    def __init__(self, config: AresConfig):
        self.config = config
        self.report: Dict[str, Any] = {
            "status": "PENDING",
            "checks": {}
        }

    def _mark(self, check: str, success: bool, details: str = ""):
        self.report["checks"][check] = {
            "status": "PASS" if success else "FAIL",
            "details": details
        }
        if not success:
            logger.error(f"Startup check failed: {check} - {details}")
        else:
            logger.info(f"Startup check passed: {check}")

    def run_all_checks(self) -> bool:
        logger.info("Starting exhaustive pre-flight verification...")
        
        self.check_configuration()
        self.check_log_permissions()
        self.check_sqlite_permissions()
        
        # Only check network if not in REPLAY or purely local DEV mode
        if self.config.mode not in ["REPLAY", "DEV"]:
            self.check_api_credentials()
            self.check_rest_connectivity()
            
        # Evaluate overall status
        failed = [k for k, v in self.report["checks"].items() if v["status"] == "FAIL"]
        
        if failed:
            self.report["status"] = "FAILED"
            logger.critical(f"STARTUP ABORTED. Mandatory checks failed: {failed}")
            return False
            
        self.report["status"] = "PASSED"
        logger.info("All startup checks PASSED.")
        return True

    def check_configuration(self):
        try:
            # We already validated this in AresConfig.load(), but we log success here.
            self._mark("configuration", True, f"Mode: {self.config.mode}")
        except Exception as e:
            self._mark("configuration", False, str(e))

    def check_api_credentials(self):
        if self.config.delta_api_key == "MOCK_KEY":
            self._mark("api_credentials", False, "Missing DELTA_API_KEY in non-mock mode")
        elif self.config.delta_api_secret == "MOCK_SECRET":
            self._mark("api_credentials", False, "Missing DELTA_API_SECRET in non-mock mode")
        else:
            self._mark("api_credentials", True)

    def check_rest_connectivity(self):
        try:
            resp = requests.get(f"{self.config.rest_url}/v2/products", timeout=5)
            if resp.status_code == 200:
                self._mark("rest_connectivity", True, "Successfully reached Delta REST API")
            else:
                self._mark("rest_connectivity", False, f"HTTP {resp.status_code}")
        except Exception as e:
            self._mark("rest_connectivity", False, str(e))

    def check_sqlite_permissions(self):
        db_path = self.config.sqlite_db_path
        try:
            with sqlite3.connect(db_path) as conn:
                c = conn.cursor()
                c.execute("CREATE TABLE IF NOT EXISTS _startup_test (id INTEGER)")
                c.execute("INSERT INTO _startup_test VALUES (1)")
                c.execute("DROP TABLE _startup_test")
                conn.commit()
            self._mark("sqlite_permissions", True, f"Read/Write OK on {db_path}")
        except Exception as e:
            self._mark("sqlite_permissions", False, str(e))

    def check_log_permissions(self):
        try:
            test_file = os.path.join(self.config.log_dir, ".test_write")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            self._mark("log_permissions", True)
        except Exception as e:
            self._mark("log_permissions", False, str(e))

    def generate_report(self) -> str:
        return json.dumps(self.report, indent=4)
