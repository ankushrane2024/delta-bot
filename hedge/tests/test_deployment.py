import unittest
import os
import time
from unittest.mock import patch, Mock

from hedge.deployment.config import AresConfig
from hedge.deployment.startup_validator import StartupValidator
from hedge.deployment.recovery_manager import RecoveryManager
from hedge.deployment.service_runner import ServiceRunner

class TestDeployment(unittest.TestCase):

    def test_config_validation_missing_secrets(self):
        with patch.dict(os.environ, {"BOT_MODE": "LIVE", "DELTA_API_KEY": "", "DELTA_API_SECRET": ""}, clear=True):
            with self.assertRaises(ValueError):
                AresConfig.load()

    def test_config_validation_success_dev(self):
        with patch.dict(os.environ, {"BOT_MODE": "DEV"}, clear=True):
            config = AresConfig.load()
            self.assertEqual(config.mode, "DEV")

    def test_startup_validator_passes_mock(self):
        import uuid
        db_path = f"test_validator_{uuid.uuid4()}.db"
        # We test that the validator correctly checks credentials
        config = AresConfig(
            mode="LIVE", delta_api_key="KEY", delta_api_secret="SECRET",
            sqlite_db_path=db_path, log_dir="test_logs",
            rest_url="https://mock", ws_url="wss://mock"
        )
        validator = StartupValidator(config)
        
        os.makedirs("test_logs", exist_ok=True)
        # We'll mock the requests check so it doesn't actually hit the internet
        with patch("hedge.deployment.startup_validator.requests.get") as mock_get:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp
            
            # Run checks
            result = validator.run_all_checks()
            self.assertTrue(result)
            self.assertEqual(validator.report["status"], "PASSED")
            
        import time
        time.sleep(0.1)
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
            if os.path.exists("test_logs/.test_write"):
                os.remove("test_logs/.test_write")
        except Exception:
            pass

    def test_startup_validator_fails_rest(self):
        import uuid
        db_path = f"test_validator_{uuid.uuid4()}.db"
        config = AresConfig(
            mode="LIVE", delta_api_key="KEY", delta_api_secret="SECRET",
            sqlite_db_path=db_path, log_dir="test_logs",
            rest_url="https://mock", ws_url="wss://mock"
        )
        validator = StartupValidator(config)
        
        os.makedirs("test_logs", exist_ok=True)
        with patch("hedge.deployment.startup_validator.requests.get") as mock_get:
            mock_resp = Mock()
            mock_resp.status_code = 500
            mock_get.return_value = mock_resp
            
            # Run checks
            result = validator.run_all_checks()
            self.assertFalse(result)
            self.assertEqual(validator.report["status"], "FAILED")
            
        import time
        time.sleep(0.1)
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
            if os.path.exists("test_logs/.test_write"):
                os.remove("test_logs/.test_write")
        except Exception:
            pass

    def test_recovery_manager_success(self):
        # Mock orchestrator
        mock_orch = Mock()
        mock_orch.execution_provider.validate_connectivity.return_value = True
        
        rm = RecoveryManager(mock_orch)
        result = rm.execute_recovery()
        
        self.assertTrue(result)
        self.assertTrue(rm.recovery_success)
        # Should trigger portfolio reconciliation
        mock_orch.portfolio_sync.reconcile_with_provider.assert_called_once()
        
    def test_recovery_manager_fails_no_connectivity(self):
        mock_orch = Mock()
        mock_orch.execution_provider.validate_connectivity.return_value = False
        
        rm = RecoveryManager(mock_orch)
        result = rm.execute_recovery()
        
        self.assertFalse(result)
        self.assertFalse(rm.recovery_success)

if __name__ == '__main__':
    unittest.main()
