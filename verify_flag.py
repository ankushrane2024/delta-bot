import os
import requests
import time
import subprocess
import signal

def run_test(enable_ares):
    print(f"\n--- TESTING WITH ENABLE_ARES={enable_ares} ---")
    os.environ['ENABLE_ARES'] = enable_ares
    proc = subprocess.Popen(['python', 'main.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(8) # Wait for server boot
    
    try:
        r1 = requests.get('http://127.0.0.1:5000/api/status')
        print('/api/status (Legacy):', r1.status_code)
        
        r2 = requests.get('http://127.0.0.1:5000/ares/health')
        print('/ares/health:', r2.status_code, r2.json())
        
        r3 = requests.get('http://127.0.0.1:5000/ares/dashboard')
        if enable_ares == 'true':
            print('/ares/dashboard:', r3.status_code, 'MISSION CONTROL' in r3.text)
        else:
            print('/ares/dashboard:', r3.status_code, 'Offline' in r3.text)
    except Exception as e:
        print("Request failed:", e)
    finally:
        proc.send_signal(signal.CTRL_C_EVENT)
        proc.terminate()
        proc.wait()

run_test('false')
run_test('true')
print("\nVERIFICATION COMPLETE")
