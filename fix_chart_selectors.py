with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("document.querySelectorAll('#pnlChartCanvas')[1]", "document.getElementById('live-pnlChartCanvas')")

# Fix Live Pnl Chart queries
content = content.replace("document.querySelectorAll('#pnl-chart-peak')", "document.querySelectorAll('#live-pnl-chart-peak')")
content = content.replace("document.querySelectorAll('#pnl-chart-trough')", "document.querySelectorAll('#live-pnl-chart-trough')")
content = content.replace("document.querySelectorAll('#pnl-chart-start-label')", "document.querySelectorAll('#live-pnl-chart-start-label')")
content = content.replace("document.querySelectorAll('#pnl-chart-end-label')", "document.querySelectorAll('#live-pnl-chart-end-label')")
content = content.replace("document.querySelectorAll('#pnl-chart-count')", "document.querySelectorAll('#live-pnl-chart-count')")

# In fetchLivePnl, replace the weird card selection
content = content.replace("const cards = document.querySelectorAll('#live-pnl-chart-card');\n                const card = cards.length > 1 ? cards[1] : cards[0];", "const card = document.getElementById('live-pnl-chart-card');")

# Fix peaks array length checks
content = content.replace("if (peaks.length > 1) peaks[1].textContent", "if (peaks.length > 0) peaks[0].textContent")
content = content.replace("if (troughs.length > 1) troughs[1].textContent", "if (troughs.length > 0) troughs[0].textContent")
content = content.replace("if (startLabels.length > 1) startLabels[1].textContent", "if (startLabels.length > 0) startLabels[0].textContent")
content = content.replace("if (endLabels.length > 1) endLabels[1].textContent", "if (endLabels.length > 0) endLabels[0].textContent")
content = content.replace("if (counts.length > 1) counts[1].textContent", "if (counts.length > 0) counts[0].textContent")

with open('c:/Users/AnkushR/Downloads/Delta_BTC_Options_Bot/Delta_BTC_Options_Bot/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed live chart selectors")
