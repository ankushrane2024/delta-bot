import sys

def modify():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # The block inside dashboard.js updating hedge status
    target_str = """                if (data.hedge_status) {
                    const hBadge = document.getElementById('hedge-active-badge');"""

    new_str = """                if (data.hedge_status) {
                    const hBadge = document.getElementById('hedge-active-badge');
                    
                    // --- ARES X Integration Bridge ---
                    const aresBadge = document.getElementById('legacy-ares-status-badge');
                    if (aresBadge) {
                        if (data.hedge_status.hedge_active) {
                            aresBadge.textContent = 'ACTIVE';
                            aresBadge.style.background = 'rgba(16, 185, 129, 0.2)';
                            aresBadge.style.color = '#10b981';
                            aresBadge.style.border = '1px solid rgba(16, 185, 129, 0.4)';
                        } else {
                            aresBadge.textContent = 'STANDBY';
                            aresBadge.style.background = 'rgba(255, 255, 255, 0.1)';
                            aresBadge.style.color = '#94a3b8';
                            aresBadge.style.border = 'none';
                        }
                    }
                    // ---------------------------------
"""

    if target_str in content:
        content = content.replace(target_str, new_str)
        with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Javascript updated successfully.")
    else:
        print("Target string not found in JS.")

if __name__ == '__main__':
    modify()
