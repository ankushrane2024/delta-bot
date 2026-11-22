import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_core import bot_instance

def test_delta_matching():
    opts = bot_instance.india_client.get_option_chain()
    btc = bot_instance.india_client.get_btc_price()
    expiries = bot_instance.get_valid_expiries(opts)
    exp = expiries[0]
    print(f"BTC Spot: ${btc:.2f} | Nearest Expiry: {exp}")

    # Surviving Put
    puts = [o for o in opts if o['symbol'].endswith(exp) and o.get('contract_type') == 'put_options' and float(o.get('strike_price', 0)) < btc]
    surv_put = next((p for p in puts if '57800' in p['symbol']), puts[len(puts)//2])
    surv_delta = abs(float(surv_put.get('greeks', {}).get('delta', 0.15)))
    surv_prem = float(surv_put.get('mark_price', 0))
    print(f"Surviving Put Leg: {surv_put['symbol']} | Strike: {surv_put['strike_price']} | Delta: {surv_delta:.4f} | Prem: ${surv_prem:.2f}")

    # Match delta of other on Call side
    calls = [o for o in opts if o['symbol'].endswith(exp) and o.get('contract_type') == 'call_options' and float(o.get('strike_price', 0)) > btc and o.get('greeks')]
    best_call = min(calls, key=lambda c: abs(abs(float(c.get('greeks', {}).get('delta', 0))) - surv_delta))
    call_delta = abs(float(best_call.get('greeks', {}).get('delta', 0)))
    call_prem = float(best_call.get('mark_price', 0))
    print(f"Matched Delta Call Leg: {best_call['symbol']} | Strike: {best_call['strike_price']} | Delta: {call_delta:.4f} | Prem: ${call_prem:.2f} | Delta Delta: {abs(call_delta - surv_delta):.4f}")

    # Surviving Call -> Match Put
    best_put = min(puts, key=lambda p: abs(abs(float(p.get('greeks', {}).get('delta', 0))) - call_delta))
    matched_put_delta = abs(float(best_put.get('greeks', {}).get('delta', 0)))
    matched_put_prem = float(best_put.get('mark_price', 0))
    print(f"Matched Delta Put Leg: {best_put['symbol']} | Strike: {best_put['strike_price']} | Delta: {matched_put_delta:.4f} | Prem: ${matched_put_prem:.2f} | Delta Delta: {abs(matched_put_delta - call_delta):.4f}")

if __name__ == '__main__':
    test_delta_matching()
