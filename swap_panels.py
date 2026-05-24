import os

for filename in ['templates/dashboard.html', 'index.html']:
    if not os.path.exists(filename): continue
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # The exact block for Tomorrow's panel is between:
    # "<!-- Tomorrow's Trade Probability Panel -->"
    # and "<!-- Skip & Schedule Info Panel -->"
    
    start_marker = "<!-- Tomorrow's Trade Probability Panel -->"
    end_marker = "<!-- Skip & Schedule Info Panel -->"
    perf_marker = "<!-- Performance Summary Panel -->"
    
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    perf_idx = content.find(perf_marker)
    
    if start_idx != -1 and end_idx != -1 and perf_idx != -1 and start_idx > perf_idx:
        # Extract Tomorrow block
        tomorrow_html = content[start_idx:end_idx]
        
        # Remove from old location
        content = content[:start_idx] + content[end_idx:]
        
        # Insert before Performance Summary Panel
        perf_idx = content.find(perf_marker)
        content = content[:perf_idx] + tomorrow_html + content[perf_idx:]
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Swapped panels in {filename}")
    else:
        print(f"Could not swap in {filename}: start={start_idx}, end={end_idx}, perf={perf_idx}")
