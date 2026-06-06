import requests as req
from datetime import datetime, timezone, timedelta

url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
headers = {'User-Agent': 'Mozilla/5.0'}
r = req.get(url, headers=headers, timeout=10)
all_events = r.json()

now_utc = datetime.now(timezone.utc)
week_end = now_utc + timedelta(days=7)

print(f"Total events returned: {len(all_events)}")
print(f"Now UTC: {now_utc}")
print(f"Week End UTC: {week_end}")

filtered = []
for e in all_events:
    impact = e.get('impact', '')
    country = e.get('country', '')
    
    if impact not in ('High', 'Medium'):
        continue
    if country not in ('USD', 'EUR', 'GBP', 'JPY', 'CNY', 'BTC'):
        continue
    
    raw_date = e.get('date', '')
    try:
        dt = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
        if dt < now_utc or dt > week_end:
            print(f"Skipped because of date: {dt} (Event: {e.get('title')})")
            continue
        date_str = dt.strftime('%b %d  %H:%M UTC')
    except Exception as ex:
        print(f"Parse error: {ex}")
        date_str = raw_date
        
    filtered.append(e)

print(f"Filtered events: {len(filtered)}")
if filtered:
    for f in filtered:
        print(f["date"], f["title"])
