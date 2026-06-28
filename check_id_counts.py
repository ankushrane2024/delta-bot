import sys
with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

def check_id(id_name):
    print(id_name, 'count:', content.count(f'id="{id_name}"'))

check_id('call-sym')
check_id('live-call-sym')
check_id('tab-live')
check_id('tab-livemode')
check_id('consecutive-losses-val')
check_id('live-consecutive-losses-val')
