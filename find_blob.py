import requests
import urllib3
urllib3.disable_warnings()

blobs = [
    "019f0461-1719-7960-8e15-c826a9966ba1",
    "019f0461-1a9c-799e-8bff-ab2f33f51951",
    "019f0def-9ad6-7633-baa3-528942380706",
    "019ee0f6-b8e2-7730-8c13-e7b064ef417c",
    "019f1338-37ed-7035-a2e3-bae99335e5eb",
    "019f2331-202e-7f00-a31e-f1f0b8fa29e2",
    "019f2332-c085-79ad-add8-4c0f8ef28dc9",
    "019f2c26-6684-755f-8953-2e096f1d4673",
    "019f2c26-6318-711f-9349-99ce26627a00",
    "019f2c26-6318-711f-9349-99ce26627ac1",
    "019f233f-1e6e-74de-857f-a7f211c3e2ac",
    "019f3706-5b11-7821-a3ed-50ded7ac7725"
]

found = False
for b in blobs:
    url = f"https://jsonblob.com/api/jsonBlob/{b}"
    res = requests.get(url, verify=False)
    print(f"ID {b} -> Status {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        trades = data.get("trades", [])
        if not trades and isinstance(data, list): trades = data
        if trades and isinstance(trades, list) and len(trades) > 0:
            last_date = trades[-1].get("date", "Unknown")
            print(f"   -> Contains {len(trades)} trades. Last date: {last_date}")
            if "2026-07-06" in last_date or "2026-07-05" in last_date or "2026-07-04" in last_date:
                print("   *** RECENT TRADES FOUND! ***")
                found = True

if not found:
    print("No recent trades found in any blob.")
