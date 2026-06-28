"""Test the user's exact scenario: Put bleeds 80%, then reverses to 20% profit."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock notifier
import notifier as nm
class MN:
    def send_message(self, *a, **k): pass
    def send_document(self, *a, **k): pass
    def notify_hedge_executed(self, *a, **k): pass
    def notify_hedge_escalated(self, *a, **k): pass
    def notify_hedge_failed(self, *a, **k): pass
    def notify_error(self, *a, **k): pass
nm.notifier = MN()

from smart_hedging import SmartHedgingManager
from test_hedge_v2 import MockAPIClient, MockDVOLProvider, MockRiskManager, MockExecutionHandler, build_positions, run_scenario

call_sym = 'C-BTC-65000-210626'
put_sym = 'P-BTC-61000-210626'
call_entry = 45.0
put_entry = 40.0

api = MockAPIClient()
api.btc_price = 63000.0
execution = MockExecutionHandler(api)
hedger = SmartHedgingManager(execution, MockDVOLProvider(), MockRiskManager(), api)
positions = build_positions(call_sym, put_sym, call_entry, put_entry, 10)

steps = [
    (-200,   44.0,  44.0),   # Put +10%
    (-300,   42.0,  48.0),   # Put +20% -- hedge triggers
    (-500,   38.0,  56.0),   # Put +40%
    (-400,   35.0,  64.0),   # Put +60%
    (-300,   33.0,  72.0),   # Put +80% MAJOR LOSS
    (-100,   32.0,  76.0),   # Put +90% approaching SL
    # REVERSAL
    (300,    34.0,  68.0),   # BTC bounces
    (500,    38.0,  58.0),   # Recovering
    (600,    42.0,  48.0),   # Put back to +20%
    (400,    44.0,  40.0),   # Put at breakeven
    (300,    45.0,  36.0),   # Put -10% WE WIN
    (200,    45.5,  32.0),   # Put -20% PROFIT
]

print()
print('='*70)
print('  YOUR SCENARIO: Put bleeds to 80%, then reverses to 20% profit')
print('  Entry: Call=$45 | Put=$40 | SL at 130% = Put reaches $92')
print('='*70)

run_scenario(
    'Put Bleeds 80% Then Reverses to 20% Profit',
    api, execution, hedger, positions, steps,
    call_sym, put_sym, call_entry, put_entry
)
