from smart_hedging import SmartHedgingManager

class MockExecution:
    def __init__(self):
        self.hedge_size_btc = 0.0
        self.hedge_order_id = "None"
        self.mode = "PAPER"

class MockClient:
    pass

class MockDvol:
    pass

class MockRisk:
    pass

def test_payload():
    manager = SmartHedgingManager(
        execution_handler=MockExecution(),
        dvol_provider=MockDvol(),
        risk_manager=MockRisk(),
        api_client=MockClient()
    )
    
    # Simulate a fake state
    manager.hedge_active = True
    manager.hedge_percentage = 50.0
    manager._hedge_peak_pnl = 125.4
    manager._bleeding_leg = "C-BTC-72000-280626"
    
    status = manager.get_status()
    print("PAYLOAD:")
    for key, val in status.items():
        print(f"  {key}: {val} ({type(val).__name__})")

if __name__ == "__main__":
    test_payload()
