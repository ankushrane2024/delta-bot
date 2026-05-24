import os

html_ui = """
        <!-- Tomorrow's Trade Probability Panel -->
        <div class="panel full-width">
            <h2 style="margin: 0 0 20px 0;">🔮 Tomorrow's Trade Chance</h2>
            <div style="display: flex; align-items: center; gap: 30px; flex-wrap: wrap;">
                
                <!-- Circular Gauge -->
                <div style="position: relative; width: 120px; height: 120px;">
                    <svg viewBox="0 0 36 36" style="width:100%; height:100%; transform: rotate(-90deg);">
                        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="3" />
                        <path id="prob-gauge-path" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--success)" stroke-width="3" stroke-dasharray="0, 100" />
                    </svg>
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;">
                        <div id="prob-percent" style="font-size: 1.8rem; font-weight: 800; color: #fff;">--%</div>
                    </div>
                </div>

                <!-- Details & Factors -->
                <div style="flex: 1; min-width: 250px;">
                    <h3 id="prob-title" style="margin: 0 0 12px 0; color: var(--success); font-size: 1.2rem;">Calculating...</h3>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                        <div class="prob-factor">
                            <div class="prob-label">Schedule & News</div>
                            <div id="prob-schedule" class="prob-value">--</div>
                        </div>
                        <div class="prob-factor">
                            <div class="prob-label">IV Environment</div>
                            <div id="prob-iv" class="prob-value">--</div>
                        </div>
                        <div class="prob-factor">
                            <div class="prob-label">Market Regime (ADX)</div>
                            <div id="prob-adx" class="prob-value">--</div>
                        </div>
                    </div>
                </div>
            </div>
            <style>
                .prob-factor { background: rgba(255,255,255,0.03); padding: 10px 14px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
                .prob-label { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
                .prob-value { font-size: 0.95rem; font-weight: 600; color: #fff; }
                .prob-positive { color: #34d399; }
                .prob-negative { color: #f87171; }
                .prob-neutral { color: #fbbf24; }
            </style>
        </div>
"""

js_logic = """
                // --- Calculate Tomorrow's Probability ---
                if (data.schedule_info && data.schedule_info.upcoming_schedule && data.schedule_info.upcoming_schedule.length > 1) {
                    let prob = 50; // Base probability
                    let titleText = "";
                    let titleColor = "";
                    
                    // 1. Schedule Check
                    const tomorrow = data.schedule_info.upcoming_schedule[1]; // Index 1 is tomorrow
                    let schedStatus = '<span class="prob-positive">Clear</span>';
                    
                    if (tomorrow.skip) {
                        prob = 0;
                        if (tomorrow.reason && tomorrow.reason.includes("Weekend")) {
                            schedStatus = '<span class="prob-negative">Weekend</span>';
                            titleText = "0% - Weekend (No Trading)";
                        } else if (tomorrow.reason && tomorrow.reason.includes("News")) {
                            schedStatus = '<span class="prob-negative">High Impact News</span>';
                            titleText = "Very Low - Major News Expected";
                        } else {
                            schedStatus = '<span class="prob-negative">Skipped</span>';
                            titleText = "0% - Skipped";
                        }
                    } else {
                        // Check if IV is good
                        const ivLimit = (data.avg_7d_iv || 40) * 0.92;
                        const ivGood = (data.current_iv > 0.35 && data.current_iv < ivLimit);
                        let ivText = "";
                        if (ivGood) {
                            prob += 35;
                            ivText = '<span class="prob-positive">Favorable</span>';
                        } else {
                            prob -= 20;
                            ivText = '<span class="prob-negative">Unfavorable</span>';
                        }
                        
                        // Check ADX
                        const adx = data.current_adx_value || 0;
                        let adxText = "";
                        if (adx > 25) {
                            prob -= 20;
                            adxText = `<span class="prob-negative">Trending (${adx.toFixed(1)})</span>`;
                        } else {
                            prob += 15;
                            adxText = `<span class="prob-positive">Ranging (${adx.toFixed(1)})</span>`;
                        }
                        
                        // Clamp
                        if (prob > 95) prob = 95;
                        if (prob < 5) prob = 5;
                        
                        // Set Title
                        if (prob >= 75) {
                            titleText = "High Chance — Conditions look favorable";
                            titleColor = "var(--success)";
                        } else if (prob >= 40) {
                            titleText = "Moderate Chance — Mixed conditions";
                            titleColor = "var(--warning)";
                        } else {
                            titleText = "Low Chance — Unfavorable conditions";
                            titleColor = "var(--danger)";
                        }
                        
                        document.getElementById('prob-iv').innerHTML = ivText;
                        document.getElementById('prob-adx').innerHTML = adxText;
                    }
                    
                    document.getElementById('prob-schedule').innerHTML = schedStatus;
                    if(prob === 0) {
                        titleColor = "var(--danger)";
                        document.getElementById('prob-iv').innerHTML = '<span class="prob-neutral">N/A</span>';
                        document.getElementById('prob-adx').innerHTML = '<span class="prob-neutral">N/A</span>';
                    }
                    
                    document.getElementById('prob-title').textContent = titleText;
                    document.getElementById('prob-title').style.color = titleColor;
                    document.getElementById('prob-percent').textContent = prob + "%";
                    
                    // Update Gauge
                    const dashArray = `${prob}, 100`;
                    const gaugePath = document.getElementById('prob-gauge-path');
                    if (gaugePath) {
                        gaugePath.setAttribute('stroke-dasharray', dashArray);
                        gaugePath.setAttribute('stroke', titleColor);
                    }
                }
"""

def modify_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Avoid duplicate injection
    if "Tomorrow's Trade Chance" in content:
        return

    # Insert UI before Skip & Schedule Info Panel
    target_ui = "<!-- Skip & Schedule Info Panel -->"
    content = content.replace(target_ui, html_ui + "\n        " + target_ui)

    # Insert JS before Update Skip & Schedule Info
    target_js = "// Update Skip & Schedule Info"
    content = content.replace(target_js, js_logic + "\n                " + target_js)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

modify_file("templates/dashboard.html")
modify_file("index.html")

print("Successfully injected UI and JS logic!")
