import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import DeltaIndiaClient

def main():
    api = DeltaIndiaClient()
    res = api.get_tickers({'symbol': 'BTCUSD'})
    import pprint
    pprint.pprint(res)

if __name__ == '__main__':
    main()
