import unittest
from unittest.mock import Mock, patch
from hedge.deployment.recovery_manager import RecoveryManager
from hedge.models.execution import ExecutionState

class TestCrashRecovery(unittest.TestCase):
    """
    Mandatory Acceptance Test:
    Simulates a crash during order submission and verifies that RecoveryManager
    resumes without submitting duplicate orders.
    """
    def test_no_duplicate_orders_on_recovery(self):
        # 1. Simulate the pre-crash state
        # Order was submitted, and provider has it.
        mock_provider = Mock()
        mock_provider.validate_connectivity.return_value = True
        
        # Suppose the provider reports the open order
        mock_open_order = Mock()
        mock_open_order.client_order_id = "order-123"
        mock_open_order.state = ExecutionState.ACKNOWLEDGED
        
        mock_provider.get_open_orders.return_value = [mock_open_order]
        
        # 2. Simulate the Orchestrator initializing post-crash
        mock_orchestrator = Mock()
        mock_orchestrator.execution_provider = mock_provider
        
        # 3. Recovery Manager resumes
        rm = RecoveryManager(mock_orchestrator)
        result = rm.execute_recovery()
        
        self.assertTrue(result)
        
        # 4. Verify no new order was created during recovery
        mock_provider.submit_order.assert_not_called()
        
        # Verify reconciliation was triggered
        mock_orchestrator.portfolio_synchronizer.reconcile_with_provider.assert_called_once()
        
if __name__ == '__main__':
    unittest.main()
