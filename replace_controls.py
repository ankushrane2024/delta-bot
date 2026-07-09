import sys
import re

def modify():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the block starting at Section 4
    start_str = '<!-- Section 4: Controls Panel (Moved to top) -->'
    end_str = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 24px;">'
    
    idx_start = content.find(start_str)
    idx_end = content.find(end_str)
    
    if idx_start == -1 or idx_end == -1:
        print("Could not find the target section")
        return

    new_section = """<!-- Section 4: Controls Panel (Moved to top) -->
        <div class="glass-panel" style="border: 1px solid rgba(0, 210, 255, 0.2); background: linear-gradient(180deg, rgba(30, 41, 59, 0.6) 0%, rgba(0, 210, 255, 0.05) 100%);">
            <h2>⚙️ Core Systems & Modules</h2>
            
            <div style="display: flex; flex-direction: column; gap: 16px; margin-top: 20px; padding-bottom: 24px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: rgba(0,0,0,0.15); border-radius: 12px; border: 1px solid rgba(0, 210, 255, 0.15); box-shadow: inset 0 0 20px rgba(0, 210, 255, 0.02);">
                    <div>
                        <div style="font-weight: 800; font-size: 1.1rem; color: #00d2ff; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px;">⚡ ARES X AI Integration</div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary);">Autonomous hedge and risk management engine</div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 16px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 0.8rem; font-weight: 600; color: #94a3b8; text-transform: uppercase;">Status:</span>
                            <span id="legacy-ares-status-badge" style="padding: 4px 10px; background: rgba(255, 255, 255, 0.1); border-radius: 6px; font-size: 0.8rem; font-weight: 700; color: #94a3b8;">STANDBY</span>
                        </div>
                        <button onclick="window.location.href='/ares/dashboard'"
                            style="padding: 8px 18px; border-radius: 8px; border: 1px solid #00d2ff; background: rgba(0, 210, 255, 0.1); color: #00d2ff; font-weight: 700; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 6px;">
                            Command Center <span style="font-size: 1.2rem; line-height: 1;">→</span>
                        </button>
                    </div>
                </div>
            </div>

            """
    
    content = content[:idx_start] + new_section + content[idx_end:]

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Replaced Manual Controls with ARES module successfully.")

if __name__ == '__main__':
    modify()
