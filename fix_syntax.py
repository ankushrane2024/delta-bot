with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix unescaped newlines in alert("Success!\n")
# If it is an actual newline character, it's represented as \n in Python string
if 'alert("Success!\n' in content:
    content = content.replace('alert("Success!\n', 'alert("Success!\\n')
    with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed syntax error")
else:
    print("Syntax error string not found!")
