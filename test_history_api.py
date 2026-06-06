import os, json

def test_history_api():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(base_dir, 'trade_history.json')
    
    print(f"Checking for history file at: {history_file}")
    
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print("SUCCESS: Successfully read trade_history.json")
                print("Data keys found:", data.keys())
                print("Number of trades:", len(data.get('trades', [])))
                
                trade = data['trades'][0]
                print(f"First Trade - Max PnL: {trade.get('max_pnl_pct')}, Time: {trade.get('max_pnl_time')}")
        except Exception as e:
            print(f"ERROR: Failed to read trade_history.json: {e}")
    else:
        print("ERROR: History file does not exist!")

if __name__ == '__main__':
    test_history_api()
