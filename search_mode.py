lines = open('web_server.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if "'mode'" in l or '"mode"' in l:
        print(f'{i+1}: {l.rstrip()}')
