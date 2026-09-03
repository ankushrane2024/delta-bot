import time
import pandas as pd
import numpy as np
from api_client import DeltaIndiaClient

api = DeltaIndiaClient()

def get_pivot_points():
    end_time = int(time.time())
    start_time = end_time - (3 * 86400) # Get last 3 days
    res = requests.get(f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT&resolution=1d&start={start_time}&end={end_time}')
    data = res.json()
    print("1d res:", data.get('success'))
    if data.get('success'):
        candles = data.get('result', [])
        candles.sort(key=lambda x: x['time'])
        if len(candles) >= 2:
            prev_day = candles[-2]
            H = float(prev_day['high'])
            L = float(prev_day['low'])
            C = float(prev_day['close'])
            P = (H + L + C) / 3
            R1 = (P * 2) - L
            R2 = P + (H - L)
            S1 = (P * 2) - H
            S2 = P - (H - L)
            return {'P': P, 'R1': R1, 'R2': R2, 'S1': S1, 'S2': S2}
    return None

import requests
def get_supertrend(period=10, multiplier=3):
    end_time = int(time.time())
    start_time = end_time - (100 * 5 * 60) # Last 100 5m candles
    res = requests.get(f'https://api.delta.exchange/v2/history/candles?symbol=BTCUSDT&resolution=5m&start={start_time}&end={end_time}')
    data = res.json()
    if not data.get('success'): return None
    candles = data.get('result', [])
    if len(candles) < period * 2: return None
    
    df = pd.DataFrame(candles)
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df = df.sort_values(by='time').reset_index(drop=True)
    
    df['tr0'] = abs(df['high'] - df['low'])
    df['tr1'] = abs(df['high'] - df['close'].shift())
    df['tr2'] = abs(df['low'] - df['close'].shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (df['high'] + df['low']) / 2
    df['basic_ub'] = hl2 + (multiplier * df['atr'])
    df['basic_lb'] = hl2 - (multiplier * df['atr'])
    
    df['final_ub'] = 0.0
    df['final_lb'] = 0.0
    for i in range(period, len(df)):
        if df['basic_ub'].iloc[i] < df['final_ub'].iloc[i-1] or df['close'].iloc[i-1] > df['final_ub'].iloc[i-1]:
            df.loc[df.index[i], 'final_ub'] = df['basic_ub'].iloc[i]
        else:
            df.loc[df.index[i], 'final_ub'] = df['final_ub'].iloc[i-1]
        
        if df['basic_lb'].iloc[i] > df['final_lb'].iloc[i-1] or df['close'].iloc[i-1] < df['final_lb'].iloc[i-1]:
            df.loc[df.index[i], 'final_lb'] = df['basic_lb'].iloc[i]
        else:
            df.loc[df.index[i], 'final_lb'] = df['final_lb'].iloc[i-1]

    df['supertrend'] = 0.0
    for i in range(period, len(df)):
        if df['supertrend'].iloc[i-1] == df['final_ub'].iloc[i-1] and df['close'].iloc[i] < df['final_ub'].iloc[i]:
            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i]
        elif df['supertrend'].iloc[i-1] == df['final_ub'].iloc[i-1] and df['close'].iloc[i] > df['final_ub'].iloc[i]:
            df.loc[df.index[i], 'supertrend'] = df['final_lb'].iloc[i]
        elif df['supertrend'].iloc[i-1] == df['final_lb'].iloc[i-1] and df['close'].iloc[i] > df['final_lb'].iloc[i]:
            df.loc[df.index[i], 'supertrend'] = df['final_lb'].iloc[i]
        elif df['supertrend'].iloc[i-1] == df['final_lb'].iloc[i-1] and df['close'].iloc[i] < df['final_lb'].iloc[i]:
            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i]
        else:
            df.loc[df.index[i], 'supertrend'] = df['final_ub'].iloc[i] if df['close'].iloc[i] < df['final_ub'].iloc[i] else df['final_lb'].iloc[i]

    df['trend'] = np.where(df['close'] > df['supertrend'], 'BUY', 'SELL')
    
    if len(df) >= 2:
        latest_closed = df.iloc[-2]
    else:
        latest_closed = df.iloc[-1]
    
    return {
        'trend': latest_closed['trend'], 
        'value': float(latest_closed['supertrend']), 
        'close': float(latest_closed['close']),
        'open': float(latest_closed['open'])
    }

def is_rejection_candle(st_data, direction):
    c_open = st_data['open']
    c_high = st_data['high']
    c_low = st_data['low']
    c_close = st_data['close']
    
    total_size = c_high - c_low
    body = abs(c_open - c_close)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low
    
    if total_size == 0: return False
    
    if direction == 'UP':
        if upper_wick > body and (upper_wick / total_size) > 0.4:
            return True
    elif direction == 'DOWN':
        if lower_wick > body and (lower_wick / total_size) > 0.4:
            return True
    return False

if __name__ == "__main__":
    pivots = get_pivot_points()
    print("Pivots:", pivots)
    st = get_supertrend()
    print("Supertrend:", st)
    
    if pivots and st:
        print("\n--- Testing Breakout Logic ---")
        for name, val in pivots.items():
            if st['open'] < val and st['close'] > val:
                if is_rejection_candle(st, 'UP'):
                    print(f"FAKEOUT DETECTED ABOVE {name} ({val})")
                else:
                    print(f"Candle broke ABOVE {name} ({val})")
            elif st['open'] > val and st['close'] < val:
                if is_rejection_candle(st, 'DOWN'):
                    print(f"FAKEOUT DETECTED BELOW {name} ({val})")
                else:
                    print(f"Candle broke BELOW {name} ({val})")
                    
    print("\n--- Testing Mock Rejection Candle ---")
    mock_st_up = {'open': 64000, 'close': 64100, 'high': 64500, 'low': 63900} # Body 100, Upper Wick 400
    mock_st_down = {'open': 64100, 'close': 64000, 'high': 64200, 'low': 63500} # Body 100, Lower Wick 500
    
    print(f"Mock UP Breakout (Shooting Star) Rejection? {is_rejection_candle(mock_st_up, 'UP')}")
    print(f"Mock DOWN Breakout (Hammer) Rejection? {is_rejection_candle(mock_st_down, 'DOWN')}")
    print("Done testing.")
