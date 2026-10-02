import re

BTST_NAV_BTN = '''        <button class="tab-btn"        id="tab-btn-btst"      onclick="switchTab('btst')">🌙 BTST 44H Strangle</button>
'''

BTST_CSS = '''
        #tab-btst.active { display: flex !important; }
        .btst-badge-ce { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px; padding: 2px 8px; font-weight: 700; font-size: 0.75rem; }
        .btst-badge-pe { background: rgba(244, 114, 182, 0.15); color: #f472b6; border: 1px solid rgba(244, 114, 182, 0.3); border-radius: 6px; padding: 2px 8px; font-weight: 700; font-size: 0.75rem; }
        .btst-card {
            background: rgba(22, 32, 68, 0.78);
            border: 1px solid rgba(147, 197, 253, 0.2);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 1px rgba(255,255,255,0.1);
            backdrop-filter: blur(12px);
        }
        .btst-metric-card {
            background: linear-gradient(135deg, rgba(26, 36, 76, 0.75), rgba(15, 23, 52, 0.85));
            border: 1px solid rgba(147, 197, 253, 0.2);
            border-radius: 14px;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25), inset 0 1px 1px rgba(255,255,255,0.08);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .btst-metric-card:hover {
            transform: translateY(-2px);
            border-color: rgba(168, 85, 247, 0.4);
        }
        .btst-metric-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
        .btst-metric-val {
            font-size: 1.55rem;
            font-weight: 800;
            font-family: 'JetBrains Mono', monospace;
            color: #fff;
        }
        .btst-input {
            width: 100%;
            background: rgba(11, 17, 44, 0.85);
            border: 1px solid rgba(147, 197, 253, 0.25);
            border-radius: 10px;
            color: #fff;
            padding: 10px 14px;
            font-size: 0.95rem;
            font-family: 'Inter', sans-serif;
            box-sizing: border-box;
            transition: border-color 0.2s;
        }
        .btst-input:focus {
            outline: none;
            border-color: #38bdf8;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.25);
        }
        .btst-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }
        .btst-table th {
            background: rgba(15, 23, 52, 0.8);
            padding: 12px 14px;
            text-align: left;
            font-size: 0.75rem;
            text-transform: uppercase;
            color: #94a3b8;
            letter-spacing: 0.5px;
            border-bottom: 1px solid rgba(147, 197, 253, 0.2);
        }
        .btst-table td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            color: #e2e8f0;
            font-family: 'JetBrains Mono', monospace;
        }
        .btst-table tr:hover td {
            background: rgba(255,255,255,0.03);
        }
'''

BTST_TAB_HTML = '''
    <!-- ============================================================================== -->
    <!-- TAB 2: BTST 44H STRANGLE STRATEGY (AlgoTest Forward-Testing Engine)           -->
    <!-- ============================================================================== -->
    <div class="tab-pane" id="tab-btst" style="display:none; max-width: 1800px; width: 100%; flex-direction: column; gap: 24px; animation: fadeIn 0.3s ease;">
        
        <!-- HERO COCKPIT HEADER -->
        <div class="summary-bar-hero" style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; background: linear-gradient(135deg, rgba(26, 36, 76, 0.88), rgba(15, 23, 52, 0.92)); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 16px; padding: 20px 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.15);">
            <div style="display: flex; align-items: center; gap: 18px; flex-wrap: wrap;">
                <div style="width: 48px; height: 48px; border-radius: 12px; background: linear-gradient(135deg, rgba(168, 85, 247, 0.25), rgba(56, 189, 248, 0.25)); border: 1px solid rgba(168, 85, 247, 0.4); display: flex; align-items: center; justify-content: center; font-size: 1.6rem; box-shadow: 0 0 15px rgba(168, 85, 247, 0.3);">
                    🌙
                </div>
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <h2 style="margin: 0; font-size: 1.4rem; font-weight: 800; background: linear-gradient(90deg, #c084fc, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                            BTST 44H Strangle Forward-Tester
                        </h2>
                        <span id="btst-status-badge" style="font-size: 0.75rem; font-weight: 700; padding: 4px 12px; border-radius: 20px; border: 1px solid rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.15); color: #00f59b;">
                            🟢 ENGINE READY
                        </span>
                        <span id="btst-mode-badge" style="font-size: 0.75rem; font-weight: 700; padding: 4px 12px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.4); background: rgba(56, 189, 248, 0.15); color: #38bdf8;">
                            📝 PAPER FORWARD-TEST
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 4px;">
                        Replicated from AlgoTest Strangle BTC | Entry: <b>10:30 PM IST</b> | Exit: <b>05:28 PM IST</b> (D+2 Expiry) | Partial SL Enabled
                    </div>
                </div>
            </div>

            <!-- Action Buttons -->
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
                <button id="btn-btst-trigger" onclick="triggerBtstEntry()" style="background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border: 1px solid rgba(56, 189, 248, 0.4); padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 0.9rem; cursor: pointer; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.35); transition: all 0.2s;">
                    ⚡ Trigger Forward Test Entry Now
                </button>
                <button id="btn-btst-squareoff" onclick="squareOffBtst()" style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.3)); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 0.9rem; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s;">
                    🛑 Square Off All
                </button>
                <button onclick="loadBtstData(true)" style="background: rgba(255,255,255,0.08); color: #cbd5e1; border: 1px solid rgba(255,255,255,0.15); padding: 10px 14px; border-radius: 10px; font-weight: 600; font-size: 0.9rem; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.2s;">
                    🔄 Refresh
                </button>
            </div>
        </div>

        <!-- QUICK STATS BAR -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
            <div class="btst-metric-card">
                <span class="btst-metric-label">Live BTC Spot Price</span>
                <span class="btst-metric-val" id="btst-spot-price" style="color: #38bdf8;">$--</span>
                <span style="font-size: 0.72rem; color: #64748b;">Delta Index / Real-time</span>
            </div>
            <div class="btst-metric-card">
                <span class="btst-metric-label">Strategy Capital</span>
                <span class="btst-metric-val" id="btst-capital-stat" style="color: #00f59b;">₹10,00,000</span>
                <span style="font-size: 0.72rem; color: #64748b;" id="btst-lots-stat">500 Lots (0.5 BTC)</span>
            </div>
            <div class="btst-metric-card">
                <span class="btst-metric-label">Target Holding Time</span>
                <span class="btst-metric-val" style="color: #c084fc;">~44 Hours</span>
                <span style="font-size: 0.72rem; color: #64748b;">10:30 PM to 05:28 PM (D+2)</span>
            </div>
            <div class="btst-metric-card">
                <span class="btst-metric-label">Active Leg Stop Loss</span>
                <span class="btst-metric-val" id="btst-sl-stat" style="color: #fbbf24;">100% (2x)</span>
                <span style="font-size: 0.72rem; color: #34d399;">Partial SL Supported</span>
            </div>
            <div class="btst-metric-card">
                <span class="btst-metric-label">Time to Expiry</span>
                <span class="btst-metric-val" id="btst-time-remaining" style="color: #f472b6;">--</span>
                <span style="font-size: 0.72rem; color: #64748b;" id="btst-expiry-date-stat">05:28 PM IST Target</span>
            </div>
        </div>

        <!-- ACTIVE POSITION DECK -->
        <div class="btst-card" style="border-color: rgba(56, 189, 248, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 1.25rem;">📡</span>
                    <h3 style="margin: 0; font-size: 1.2rem; font-weight: 800; color: #fff;">
                        Active Forward-Test Trade Deck
                    </h3>
                    <span id="btst-pos-status-badge" style="font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 12px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #94a3b8;">
                        NO ACTIVE POSITION
                    </span>
                </div>
                <div id="btst-active-pnl-banner" style="display: none; align-items: center; gap: 14px;">
                    <span style="font-size: 0.85rem; color: #94a3b8; font-weight: 600;">Trade PnL:</span>
                    <span id="btst-active-total-pnl-inr" style="font-size: 1.35rem; font-weight: 900; font-family: 'JetBrains Mono', monospace;">₹0.00</span>
                    <span id="btst-active-total-pnl-usd" style="font-size: 0.95rem; font-weight: 700; color: #94a3b8; font-family: 'JetBrains Mono', monospace;">($0.00)</span>
                </div>
            </div>

            <!-- EMPTY STATE WHEN FLAT -->
            <div id="btst-pos-empty" style="text-align: center; padding: 40px 20px; background: rgba(0,0,0,0.2); border-radius: 14px; border: 1px dashed rgba(147, 197, 253, 0.2);">
                <div style="font-size: 2.2rem; margin-bottom: 12px;">💤</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: #fff; margin-bottom: 6px;">
                    No Active BTST Position Currently Open
                </div>
                <div style="font-size: 0.85rem; color: #94a3b8; max-width: 600px; margin: 0 auto 20px auto;">
                    The BTST engine will automatically calculate ATM straddle width and enter at <b>10:30 PM IST</b> on active trading days. You can also trigger an immediate forward-test trade at any time below.
                </div>
                <button onclick="triggerBtstEntry()" style="background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border: 1px solid rgba(56, 189, 248, 0.4); padding: 10px 22px; border-radius: 10px; font-weight: 700; font-size: 0.9rem; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.35);">
                    ⚡ Open BTST Forward Test Trade Now
                </button>
            </div>

            <!-- ACTIVE LEGS GRID -->
            <div id="btst-pos-details" style="display: none; flex-direction: column; gap: 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.25); padding: 12px 18px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); flex-wrap: wrap; gap: 10px; font-size: 0.85rem;">
                    <div>Trade ID: <b id="btst-trade-id-val" style="color: #38bdf8; font-family: 'JetBrains Mono', monospace;">BTST--</b></div>
                    <div>Entry: <b id="btst-trade-entry-val" style="color: #e2e8f0;">--</b></div>
                    <div>Expiry Target: <b id="btst-trade-expiry-val" style="color: #c084fc;">--</b> (05:28 PM IST)</div>
                    <div>Straddle Offset: <b id="btst-trade-offset-val" style="color: #fbbf24;">-- pts (1.8x)</b></div>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 18px;">
                    <!-- CALL LEG CARD -->
                    <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 14px; padding: 20px; display: flex; flex-direction: column; gap: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <span class="btst-badge-ce">CALL OPTION (CE)</span>
                                <div id="btst-ce-symbol" style="font-size: 1.15rem; font-weight: 800; color: #fff; margin-top: 6px; font-family: 'JetBrains Mono', monospace;">C-BTC--</div>
                                <div id="btst-ce-sub" style="font-size: 0.8rem; color: #94a3b8; margin-top: 2px;">Strike: -- | Lots: --</div>
                            </div>
                            <span id="btst-ce-status" style="font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #00f59b;">
                                OPEN
                            </span>
                        </div>

                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: rgba(255,255,255,0.02); padding: 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); text-align: center;">
                            <div>
                                <div style="font-size: 0.72rem; color: #94a3b8; text-transform: uppercase;">Entry Price</div>
                                <div id="btst-ce-entry" style="font-size: 1.05rem; font-weight: 700; color: #fff; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                            <div>
                                <div style="font-size: 0.72rem; color: #94a3b8; text-transform: uppercase;">Live Mark</div>
                                <div id="btst-ce-current" style="font-size: 1.05rem; font-weight: 700; color: #38bdf8; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                            <div>
                                <div style="font-size: 0.72rem; color: #f87171; text-transform: uppercase;">Stop Loss (100%)</div>
                                <div id="btst-ce-sl" style="font-size: 1.05rem; font-weight: 700; color: #f87171; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                            <span style="font-size: 0.8rem; color: #94a3b8; font-weight: 600;">Leg PnL:</span>
                            <div style="text-align: right;">
                                <div id="btst-ce-pnl-inr" style="font-size: 1.15rem; font-weight: 800; font-family: 'JetBrains Mono', monospace;">₹0.00</div>
                                <div id="btst-ce-pnl-usd" style="font-size: 0.75rem; color: #94a3b8; font-family: 'JetBrains Mono', monospace;">$0.00</div>
                            </div>
                        </div>
                    </div>

                    <!-- PUT LEG CARD -->
                    <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(244, 114, 182, 0.3); border-radius: 14px; padding: 20px; display: flex; flex-direction: column; gap: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                            <div>
                                <span class="btst-badge-pe">PUT OPTION (PE)</span>
                                <div id="btst-pe-symbol" style="font-size: 1.15rem; font-weight: 800; color: #fff; margin-top: 6px; font-family: 'JetBrains Mono', monospace;">P-BTC--</div>
                                <div id="btst-pe-sub" style="font-size: 0.8rem; color: #94a3b8; margin-top: 2px;">Strike: -- | Lots: --</div>
                            </div>
                            <span id="btst-pe-status" style="font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(16,185,129,0.15); border: 1px solid rgba(16,185,129,0.3); color: #00f59b;">
                                OPEN
                            </span>
                        </div>

                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: rgba(255,255,255,0.02); padding: 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05); text-align: center;">
                            <div>
                                <div style="font-size: 0.72rem; color: #94a3b8; text-transform: uppercase;">Entry Price</div>
                                <div id="btst-pe-entry" style="font-size: 1.05rem; font-weight: 700; color: #fff; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                            <div>
                                <div style="font-size: 0.72rem; color: #94a3b8; text-transform: uppercase;">Live Mark</div>
                                <div id="btst-pe-current" style="font-size: 1.05rem; font-weight: 700; color: #f472b6; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                            <div>
                                <div style="font-size: 0.72rem; color: #f87171; text-transform: uppercase;">Stop Loss (100%)</div>
                                <div id="btst-pe-sl" style="font-size: 1.05rem; font-weight: 700; color: #f87171; font-family: 'JetBrains Mono', monospace;">$--</div>
                            </div>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                            <span style="font-size: 0.8rem; color: #94a3b8; font-weight: 600;">Leg PnL:</span>
                            <div style="text-align: right;">
                                <div id="btst-pe-pnl-inr" style="font-size: 1.15rem; font-weight: 800; font-family: 'JetBrains Mono', monospace;">₹0.00</div>
                                <div id="btst-pe-pnl-usd" style="font-size: 0.75rem; color: #94a3b8; font-family: 'JetBrains Mono', monospace;">$0.00</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- PARTIAL SL HIGHLIGHT BANNER -->
                <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 10px; padding: 10px 16px; display: flex; align-items: center; gap: 10px; font-size: 0.82rem; color: #34d399;">
                    <span>🛡️</span>
                    <span><b>Partial Stop Loss Active:</b> If one leg hits its 100% SL, it will square off immediately to cap loss while the surviving leg continues running until 05:28 PM IST expiry to harvest theta decay.</span>
                </div>
            </div>
        </div>

        <!-- DUAL COLUMN: STRATEGY CONFIGURATION & STRIKE CALCULATION PREVIEW -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 24px;">
            
            <!-- COLUMN 1: EDITABLE STRATEGY PARAMETERS -->
            <div class="btst-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 1.2rem;">⚙️</span>
                        <h3 style="margin: 0; font-size: 1.15rem; font-weight: 800; color: #fff;">Strategy Settings</h3>
                    </div>
                    <span style="font-size: 0.75rem; color: #38bdf8; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.25); border-radius: 6px; padding: 2px 8px;">
                        AlgoTest BTC Strangle
                    </span>
                </div>

                <div style="display: flex; flex-direction: column; gap: 16px;">
                    <!-- Capital in INR -->
                    <div>
                        <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                            Strategy Capital (INR ₹)
                        </label>
                        <input type="number" id="btst-cfg-capital" class="btst-input" placeholder="1000000" step="50000">
                        <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">Editable capital base for margin and sizing calculation.</div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                        <!-- Lot Size -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                Lots per Leg
                            </label>
                            <input type="number" id="btst-cfg-lots" class="btst-input" placeholder="500" min="1">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">500 lots = 0.50 BTC</div>
                        </div>

                        <!-- Stop Loss % -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                Stop Loss (%)
                            </label>
                            <input type="number" id="btst-cfg-sl" class="btst-input" placeholder="100" min="10" max="500">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">100% = 2x entry premium</div>
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                        <!-- Straddle Multiplier -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                Straddle Multiplier
                            </label>
                            <input type="number" id="btst-cfg-multiplier" class="btst-input" placeholder="1.8" step="0.1" min="0.5" max="5.0">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">Default 1.8x Straddle Width</div>
                        </div>

                        <!-- USD to INR Rate -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                USD / INR FX Rate
                            </label>
                            <input type="number" id="btst-cfg-fx" class="btst-input" placeholder="85.0" step="0.5">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">Standard Delta rate: ₹85</div>
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px;">
                        <!-- Entry Time IST -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                Entry Time (IST)
                            </label>
                            <input type="text" id="btst-cfg-entry-time" class="btst-input" placeholder="22:30">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">22:30 IST (10:30 PM)</div>
                        </div>

                        <!-- Exit Time IST -->
                        <div>
                            <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                                Exit Time (IST)
                            </label>
                            <input type="text" id="btst-cfg-exit-time" class="btst-input" placeholder="17:28">
                            <div style="font-size: 0.72rem; color: #64748b; margin-top: 3px;">17:28 IST (05:28 PM)</div>
                        </div>
                    </div>

                    <!-- Mode Selection -->
                    <div>
                        <label style="font-size: 0.8rem; font-weight: 700; color: #cbd5e1; display: block; margin-bottom: 6px;">
                            Execution Mode
                        </label>
                        <select id="btst-cfg-mode" class="btst-input">
                            <option value="PAPER">📝 PAPER (Automated Forward-Test Sandbox)</option>
                            <option value="LIVE">⚡ LIVE (Real Exchange Orders via Delta API)</option>
                        </select>
                    </div>

                    <div style="display: flex; gap: 10px; margin-top: 6px;">
                        <button id="btn-save-btst-cfg" onclick="saveBtstConfig()" style="flex: 1; background: linear-gradient(135deg, #059669, #10b981); color: #fff; border: 1px solid rgba(16,185,129,0.4); padding: 12px 18px; border-radius: 10px; font-weight: 800; font-size: 0.95rem; cursor: pointer; box-shadow: 0 4px 15px rgba(16,185,129,0.3); transition: all 0.2s;">
                            💾 Save Strategy Settings
                        </button>
                    </div>
                    <div id="btst-cfg-feedback" style="font-size: 0.82rem; font-weight: 600; text-align: center;"></div>
                </div>
            </div>

            <!-- COLUMN 2: LIVE MATH PREVIEW CARD -->
            <div class="btst-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 1.2rem;">🎯</span>
                        <h3 style="margin: 0; font-size: 1.15rem; font-weight: 800; color: #fff;">
                            Straddle Width Strike Calculation
                        </h3>
                    </div>
                    <button onclick="previewBtstStrikes()" style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); color: #38bdf8; padding: 4px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; cursor: pointer;">
                        🔄 Recalculate
                    </button>
                </div>

                <div style="display: flex; flex-direction: column; gap: 16px;">
                    <div style="background: rgba(0,0,0,0.25); padding: 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.05);">
                        <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 6px; font-weight: 600;">ALGO MATH FORMULA:</div>
                        <div style="font-size: 0.85rem; font-family: 'JetBrains Mono', monospace; color: #c084fc; line-height: 1.6;">
                            ATM Straddle Price = ATM CE + ATM PE<br>
                            Offset = Round(1.8 × ATM Straddle Price)<br>
                            CE Strike = ATM + Offset (Nearest Available)<br>
                            PE Strike = ATM - Offset (Nearest Available)
                        </div>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                        <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.04);">
                            <div style="font-size: 0.72rem; color: #94a3b8;">ATM Strike</div>
                            <div id="btst-preview-atm" style="font-size: 1.1rem; font-weight: 800; color: #fff; font-family: 'JetBrains Mono', monospace;">--</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.04);">
                            <div style="font-size: 0.72rem; color: #94a3b8;">ATM Straddle Price</div>
                            <div id="btst-preview-straddle" style="font-size: 1.1rem; font-weight: 800; color: #00f59b; font-family: 'JetBrains Mono', monospace;">$--</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.04);">
                            <div style="font-size: 0.72rem; color: #94a3b8;">1.8x Straddle Offset</div>
                            <div id="btst-preview-offset" style="font-size: 1.1rem; font-weight: 800; color: #fbbf24; font-family: 'JetBrains Mono', monospace;">-- pts</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.04);">
                            <div style="font-size: 0.72rem; color: #94a3b8;">Target Expiry (D+2)</div>
                            <div id="btst-preview-exp" style="font-size: 1.1rem; font-weight: 800; color: #f472b6; font-family: 'JetBrains Mono', monospace;">--</div>
                        </div>
                    </div>

                    <!-- Projected Strikes Box -->
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 10px 14px;">
                            <div>
                                <span class="btst-badge-ce">CALL STRIKE</span>
                                <div id="btst-preview-ce-sym" style="font-size: 0.95rem; font-weight: 700; color: #fff; font-family: 'JetBrains Mono', monospace; margin-top: 3px;">C-BTC--</div>
                            </div>
                            <div style="text-align: right;">
                                <div id="btst-preview-ce-price" style="font-size: 0.95rem; font-weight: 800; color: #38bdf8; font-family: 'JetBrains Mono', monospace;">$--</div>
                                <div id="btst-preview-ce-sl" style="font-size: 0.72rem; color: #f87171;">SL: $--</div>
                            </div>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(244, 114, 182, 0.08); border: 1px solid rgba(244, 114, 182, 0.25); border-radius: 8px; padding: 10px 14px;">
                            <div>
                                <span class="btst-badge-pe">PUT STRIKE</span>
                                <div id="btst-preview-pe-sym" style="font-size: 0.95rem; font-weight: 700; color: #fff; font-family: 'JetBrains Mono', monospace; margin-top: 3px;">P-BTC--</div>
                            </div>
                            <div style="text-align: right;">
                                <div id="btst-preview-pe-price" style="font-size: 0.95rem; font-weight: 800; color: #f472b6; font-family: 'JetBrains Mono', monospace;">$--</div>
                                <div id="btst-preview-pe-sl" style="font-size: 0.72rem; color: #f87171;">SL: $--</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- PERFORMANCE SUMMARY CARDS (Matching AlgoTest Screenshot Report) -->
        <div class="btst-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 1.25rem;">📈</span>
                    <h3 style="margin: 0; font-size: 1.2rem; font-weight: 800; color: #fff;">
                        AlgoTest Forward-Test Performance Ledger
                    </h3>
                </div>
                <div style="font-size: 0.8rem; color: #94a3b8;">
                    All PnL values calculated in INR (₹) at standard Delta 85 FX rate
                </div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px;">
                <div class="btst-metric-card">
                    <span class="btst-metric-label">Overall Profit</span>
                    <span class="btst-metric-val" id="btst-stat-overall-pnl" style="color: #00f59b;">₹0.00</span>
                    <span id="btst-stat-overall-usd" style="font-size: 0.75rem; color: #94a3b8;">$0.00 USD</span>
                </div>
                <div class="btst-metric-card">
                    <span class="btst-metric-label">No. of Trades</span>
                    <span class="btst-metric-val" id="btst-stat-trades" style="color: #38bdf8;">0</span>
                    <span id="btst-stat-legs" style="font-size: 0.75rem; color: #94a3b8;">0 Total Legs</span>
                </div>
                <div class="btst-metric-card">
                    <span class="btst-metric-label">Win Rate %</span>
                    <span class="btst-metric-val" id="btst-stat-winrate" style="color: #c084fc;">0.0%</span>
                    <span id="btst-stat-lossrate" style="font-size: 0.75rem; color: #94a3b8;">Loss %: 0.0%</span>
                </div>
                <div class="btst-metric-card">
                    <span class="btst-metric-label">Avg Profit / Trade</span>
                    <span class="btst-metric-val" id="btst-stat-avg-trade" style="color: #fbbf24;">₹0.00</span>
                    <span style="font-size: 0.75rem; color: #64748b;">Per Completed Strangle</span>
                </div>
                <div class="btst-metric-card">
                    <span class="btst-metric-label">Max Profit / Loss</span>
                    <span class="btst-metric-val" id="btst-stat-max-profit" style="color: #34d399; font-size: 1.25rem;">₹0.00</span>
                    <span id="btst-stat-max-loss" style="font-size: 0.75rem; color: #f87171;">Max Loss: ₹0.00</span>
                </div>
                <div class="btst-metric-card">
                    <span class="btst-metric-label">Max Drawdown</span>
                    <span class="btst-metric-val" id="btst-stat-mdd" style="color: #ff4b72;">₹0.00</span>
                    <span id="btst-stat-rrr" style="font-size: 0.75rem; color: #94a3b8;">Reward/Risk: 0.00</span>
                </div>
            </div>

            <!-- TRADE HISTORY TABLE (AlgoTest Format) -->
            <div style="border-radius: 12px; overflow: hidden; border: 1px solid rgba(147, 197, 253, 0.2);">
                <div style="background: rgba(15, 23, 52, 0.9); padding: 12px 18px; border-bottom: 1px solid rgba(147, 197, 253, 0.2); font-weight: 700; font-size: 0.9rem; color: #fff; display: flex; justify-content: space-between; align-items: center;">
                    <span>Completed Trades (AlgoTest Schema)</span>
                    <span id="btst-table-count" style="font-size: 0.75rem; color: #94a3b8;">0 records</span>
                </div>
                <div style="overflow-x: auto;">
                    <table class="btst-table">
                        <thead>
                            <tr>
                                <th>Index</th>
                                <th>Entry Date</th>
                                <th>Entry Time</th>
                                <th>Exit Date</th>
                                <th>Exit Time</th>
                                <th>Type</th>
                                <th>Strike</th>
                                <th>B/S</th>
                                <th>Lots</th>
                                <th>Entry Price ($)</th>
                                <th>Exit Price ($)</th>
                                <th>P/L (₹)</th>
                                <th>Exit Reason</th>
                            </tr>
                        </thead>
                        <tbody id="btst-history-tbody">
                            <tr>
                                <td colspan="13" style="text-align: center; color: #94a3b8; padding: 30px;">
                                    No completed forward-test trades yet. Trades will automatically populate here upon leg exit or expiry.
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

    </div><!-- /tab-btst -->
'''

BTST_JS = '''
        // ==============================================================================
        // 🌙 BTST 44H STRANGLE STRATEGY (AlgoTest Forward-Testing Engine)
        // ==============================================================================
        let btstUserEditing = false;
        let btstPollingTimer = null;

        async function loadBtstData(forcePreview = false) {
            try {
                const res = await fetch('/api/btst/status');
                const data = await res.json();
                renderBtstUI(data);

                if (forcePreview) {
                    previewBtstStrikes();
                }
            } catch (err) {
                console.warn('[BTST] Error loading status:', err);
            }
        }

        function renderBtstUI(data) {
            if (!data) return;

            // Spot Price & Quick Stats
            if (data.btc_spot_price) {
                const spEl = document.getElementById('btst-spot-price');
                if (spEl) spEl.textContent = '$' + Number(data.btc_spot_price).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
            if (data.time_remaining) {
                const trEl = document.getElementById('btst-time-remaining');
                if (trEl) trEl.textContent = data.time_remaining;
            }

            // Fill Configuration Inputs (only if user is not actively editing)
            if (data.config && !btstUserEditing) {
                const cfg = data.config;
                if (document.getElementById('btst-cfg-capital')) document.getElementById('btst-cfg-capital').value = cfg.capital_inr || 1000000;
                if (document.getElementById('btst-cfg-lots')) document.getElementById('btst-cfg-lots').value = cfg.lots || 500;
                if (document.getElementById('btst-cfg-sl')) document.getElementById('btst-cfg-sl').value = cfg.sl_pct || 100;
                if (document.getElementById('btst-cfg-multiplier')) document.getElementById('btst-cfg-multiplier').value = cfg.straddle_multiplier || 1.8;
                if (document.getElementById('btst-cfg-fx')) document.getElementById('btst-cfg-fx').value = cfg.usd_to_inr || 85.0;
                if (document.getElementById('btst-cfg-entry-time')) document.getElementById('btst-cfg-entry-time').value = cfg.entry_time_ist || '22:30';
                if (document.getElementById('btst-cfg-exit-time')) document.getElementById('btst-cfg-exit-time').value = cfg.exit_time_ist || '17:28';
                if (document.getElementById('btst-cfg-mode')) document.getElementById('btst-cfg-mode').value = cfg.mode || 'PAPER';

                // Badges in header
                const mb = document.getElementById('btst-mode-badge');
                if (mb) {
                    if (cfg.mode === 'LIVE') {
                        mb.textContent = '⚡ LIVE REAL ORDERS';
                        mb.style.color = '#ef4444';
                        mb.style.borderColor = 'rgba(239, 68, 68, 0.4)';
                        mb.style.background = 'rgba(239, 68, 68, 0.15)';
                    } else {
                        mb.textContent = '📝 PAPER FORWARD-TEST';
                        mb.style.color = '#38bdf8';
                        mb.style.borderColor = 'rgba(56, 189, 248, 0.4)';
                        mb.style.background = 'rgba(56, 189, 248, 0.15)';
                    }
                }

                const capStat = document.getElementById('btst-capital-stat');
                if (capStat) capStat.textContent = '₹' + Number(cfg.capital_inr || 1000000).toLocaleString('en-IN');
                const lotsStat = document.getElementById('btst-lots-stat');
                if (lotsStat) lotsStat.textContent = (cfg.lots || 500) + ' Lots (' + ((cfg.lots || 500) * 0.001).toFixed(2) + ' BTC)';
                const slStat = document.getElementById('btst-sl-stat');
                if (slStat) slStat.textContent = (cfg.sl_pct || 100) + '% (2x)';
            }

            // Render Active Position Deck
            const trade = data.active_trade;
            const emptyEl = document.getElementById('btst-pos-empty');
            const detailsEl = document.getElementById('btst-pos-details');
            const posBadge = document.getElementById('btst-pos-status-badge');
            const pnlBanner = document.getElementById('btst-active-pnl-banner');

            if (!trade || trade.status === 'CLOSED') {
                if (emptyEl) emptyEl.style.display = 'block';
                if (detailsEl) detailsEl.style.display = 'none';
                if (pnlBanner) pnlBanner.style.display = 'none';
                if (posBadge) {
                    posBadge.textContent = 'STANDBY (NO ACTIVE TRADE)';
                    posBadge.style.color = '#94a3b8';
                    posBadge.style.borderColor = 'rgba(255,255,255,0.15)';
                    posBadge.style.background = 'rgba(255,255,255,0.06)';
                }
            } else {
                if (emptyEl) emptyEl.style.display = 'none';
                if (detailsEl) detailsEl.style.display = 'flex';
                if (pnlBanner) pnlBanner.style.display = 'flex';

                if (posBadge) {
                    posBadge.textContent = trade.status === 'PARTIALLY_CLOSED' ? '🟡 PARTIAL SL TRIGGERED' : '🟢 RUNNING (BOTH LEGS)';
                    posBadge.style.color = trade.status === 'PARTIALLY_CLOSED' ? '#fbbf24' : '#00f59b';
                    posBadge.style.borderColor = trade.status === 'PARTIALLY_CLOSED' ? 'rgba(251, 191, 36, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                    posBadge.style.background = trade.status === 'PARTIALLY_CLOSED' ? 'rgba(251, 191, 36, 0.15)' : 'rgba(16, 185, 129, 0.15)';
                }

                // Top meta
                if (document.getElementById('btst-trade-id-val')) document.getElementById('btst-trade-id-val').textContent = trade.trade_id;
                if (document.getElementById('btst-trade-entry-val')) document.getElementById('btst-trade-entry-val').textContent = trade.entry_time;
                if (document.getElementById('btst-trade-expiry-val')) document.getElementById('btst-trade-expiry-val').textContent = trade.target_exit_time;
                if (document.getElementById('btst-trade-offset-val')) document.getElementById('btst-trade-offset-val').textContent = trade.offset_points + ' pts (' + (trade.straddle_multiplier || 1.8) + 'x)';

                // Overall Active PnL
                const pnlInrEl = document.getElementById('btst-active-total-pnl-inr');
                const pnlUsdEl = document.getElementById('btst-active-total-pnl-usd');
                const totalInr = trade.total_pnl_inr || 0;
                const totalUsd = trade.total_pnl_usd || 0;
                if (pnlInrEl) {
                    pnlInrEl.textContent = (totalInr >= 0 ? '+' : '') + '₹' + Number(totalInr).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    pnlInrEl.style.color = totalInr >= 0 ? '#00f59b' : '#ff4b72';
                }
                if (pnlUsdEl) {
                    pnlUsdEl.textContent = '(' + (totalUsd >= 0 ? '+' : '') + '$' + Number(totalUsd).toFixed(2) + ')';
                }

                // Call Leg
                const ce = trade.ce_leg;
                if (ce) {
                    if (document.getElementById('btst-ce-symbol')) document.getElementById('btst-ce-symbol').textContent = ce.symbol;
                    if (document.getElementById('btst-ce-sub')) document.getElementById('btst-ce-sub').textContent = 'Strike: ' + ce.strike + ' | ' + ce.lots + ' Lots (' + trade.qty_btc + ' BTC)';
                    if (document.getElementById('btst-ce-entry')) document.getElementById('btst-ce-entry').textContent = '$' + Number(ce.entry_price).toFixed(2);
                    if (document.getElementById('btst-ce-current')) document.getElementById('btst-ce-current').textContent = '$' + Number(ce.current_price).toFixed(2);
                    if (document.getElementById('btst-ce-sl')) document.getElementById('btst-ce-sl').textContent = '$' + Number(ce.sl_price).toFixed(2);

                    const ceStatusEl = document.getElementById('btst-ce-status');
                    if (ceStatusEl) {
                        ceStatusEl.textContent = ce.status;
                        if (ce.status === 'SL_HIT') {
                            ceStatusEl.style.color = '#ff4b72';
                            ceStatusEl.style.borderColor = 'rgba(255, 75, 114, 0.4)';
                            ceStatusEl.style.background = 'rgba(255, 75, 114, 0.15)';
                        } else {
                            ceStatusEl.style.color = '#00f59b';
                            ceStatusEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                            ceStatusEl.style.background = 'rgba(16, 185, 129, 0.15)';
                        }
                    }

                    const ceInrEl = document.getElementById('btst-ce-pnl-inr');
                    const ceUsdEl = document.getElementById('btst-ce-pnl-usd');
                    if (ceInrEl) {
                        const inr = ce.pnl_inr || 0;
                        ceInrEl.textContent = (inr >= 0 ? '+' : '') + '₹' + Number(inr).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                        ceInrEl.style.color = inr >= 0 ? '#00f59b' : '#ff4b72';
                    }
                    if (ceUsdEl) {
                        ceUsdEl.textContent = '(' + ((ce.pnl_usd || 0) >= 0 ? '+' : '') + '$' + Number(ce.pnl_usd || 0).toFixed(2) + ')';
                    }
                }

                // Put Leg
                const pe = trade.pe_leg;
                if (pe) {
                    if (document.getElementById('btst-pe-symbol')) document.getElementById('btst-pe-symbol').textContent = pe.symbol;
                    if (document.getElementById('btst-pe-sub')) document.getElementById('btst-pe-sub').textContent = 'Strike: ' + pe.strike + ' | ' + pe.lots + ' Lots (' + trade.qty_btc + ' BTC)';
                    if (document.getElementById('btst-pe-entry')) document.getElementById('btst-pe-entry').textContent = '$' + Number(pe.entry_price).toFixed(2);
                    if (document.getElementById('btst-pe-current')) document.getElementById('btst-pe-current').textContent = '$' + Number(pe.current_price).toFixed(2);
                    if (document.getElementById('btst-pe-sl')) document.getElementById('btst-pe-sl').textContent = '$' + Number(pe.sl_price).toFixed(2);

                    const peStatusEl = document.getElementById('btst-pe-status');
                    if (peStatusEl) {
                        peStatusEl.textContent = pe.status;
                        if (pe.status === 'SL_HIT') {
                            peStatusEl.style.color = '#ff4b72';
                            peStatusEl.style.borderColor = 'rgba(255, 75, 114, 0.4)';
                            peStatusEl.style.background = 'rgba(255, 75, 114, 0.15)';
                        } else {
                            peStatusEl.style.color = '#00f59b';
                            peStatusEl.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                            peStatusEl.style.background = 'rgba(16, 185, 129, 0.15)';
                        }
                    }

                    const peInrEl = document.getElementById('btst-pe-pnl-inr');
                    const peUsdEl = document.getElementById('btst-pe-pnl-usd');
                    if (peInrEl) {
                        const inr = pe.pnl_inr || 0;
                        peInrEl.textContent = (inr >= 0 ? '+' : '') + '₹' + Number(inr).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                        peInrEl.style.color = inr >= 0 ? '#00f59b' : '#ff4b72';
                    }
                    if (peUsdEl) {
                        peUsdEl.textContent = '(' + ((pe.pnl_usd || 0) >= 0 ? '+' : '') + '$' + Number(pe.pnl_usd || 0).toFixed(2) + ')';
                    }
                }
            }

            // Render Metrics (AlgoTest Format)
            const m = data.metrics || {};
            const pnlOverall = document.getElementById('btst-stat-overall-pnl');
            if (pnlOverall) {
                const val = m.overall_profit_inr || 0;
                pnlOverall.textContent = (val >= 0 ? '+' : '') + '₹' + Number(val).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                pnlOverall.style.color = val >= 0 ? '#00f59b' : '#ff4b72';
            }
            if (document.getElementById('btst-stat-overall-usd')) {
                const u = m.overall_profit_usd || 0;
                document.getElementById('btst-stat-overall-usd').textContent = (u >= 0 ? '+' : '') + '$' + Number(u).toFixed(2) + ' USD';
            }
            if (document.getElementById('btst-stat-trades')) document.getElementById('btst-stat-trades').textContent = m.total_trades || 0;
            if (document.getElementById('btst-stat-winrate')) document.getElementById('btst-stat-winrate').textContent = (m.win_pct || 0).toFixed(1) + '%';
            if (document.getElementById('btst-stat-lossrate')) document.getElementById('btst-stat-lossrate').textContent = 'Loss %: ' + (m.loss_pct || 0).toFixed(1) + '%';
            if (document.getElementById('btst-stat-avg-trade')) document.getElementById('btst-stat-avg-trade').textContent = '₹' + Number(m.avg_profit_per_trade_inr || 0).toLocaleString('en-IN', {minimumFractionDigits: 2});
            if (document.getElementById('btst-stat-max-profit')) document.getElementById('btst-stat-max-profit').textContent = '₹' + Number(m.max_profit_inr || 0).toLocaleString('en-IN');
            if (document.getElementById('btst-stat-max-loss')) document.getElementById('btst-stat-max-loss').textContent = 'Max Loss: ₹' + Number(m.max_loss_inr || 0).toLocaleString('en-IN');
            if (document.getElementById('btst-stat-mdd')) document.getElementById('btst-stat-mdd').textContent = '₹' + Number(m.max_drawdown_inr || 0).toLocaleString('en-IN');
            if (document.getElementById('btst-stat-rrr')) document.getElementById('btst-stat-rrr').textContent = 'Reward/Risk: ' + (m.reward_to_risk || 0).toFixed(2);

            // Render Trade History Ledger Table
            const tbody = document.getElementById('btst-history-tbody');
            const history = data.trade_history || [];
            if (document.getElementById('btst-table-count')) document.getElementById('btst-table-count').textContent = history.length + ' records';

            if (tbody) {
                if (history.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: #94a3b8; padding: 30px;">No completed forward-test trades yet. Trades will automatically populate here upon leg exit or expiry.</td></tr>`;
                } else {
                    let rows = '';
                    history.forEach(t => {
                        const isWin = (t.pnl_inr || 0) >= 0;
                        const pnlColor = isWin ? '#00f59b' : '#ff4b72';
                        const typeBadge = t.type === 'CE' ? '<span class="btst-badge-ce">CE</span>' : '<span class="btst-badge-pe">PE</span>';
                        rows += `
                            <tr>
                                <td style="font-weight: 700; color: #fff;">${t.index}</td>
                                <td>${t.entry_date}</td>
                                <td>${t.entry_time}</td>
                                <td>${t.exit_date || '--'}</td>
                                <td>${t.exit_time || '--'}</td>
                                <td>${typeBadge}</td>
                                <td style="font-weight: 700; color: #fff;">${t.strike}</td>
                                <td><span style="color: #f87171; font-weight: 700;">Sell</span></td>
                                <td>${t.lots || 500}</td>
                                <td>$${Number(t.entry_price || 0).toFixed(2)}</td>
                                <td>$${Number(t.exit_price || 0).toFixed(2)}</td>
                                <td style="font-weight: 800; color: ${pnlColor};">${isWin ? '+' : ''}₹${Number(t.pnl_inr || 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                                <td><span style="font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">${t.exit_reason || 'COMPLETE'}</span></td>
                            </tr>
                        `;
                    });
                    tbody.innerHTML = rows;
                }
            }
        }

        async function previewBtstStrikes() {
            try {
                const res = await fetch('/api/btst/preview_strikes');
                const data = await res.json();
                if (data.success && data.preview) {
                    const p = data.preview;
                    if (document.getElementById('btst-preview-atm')) document.getElementById('btst-preview-atm').textContent = p.atm_strike;
                    if (document.getElementById('btst-preview-straddle')) document.getElementById('btst-preview-straddle').textContent = '$' + Number(p.straddle_price).toFixed(2);
                    if (document.getElementById('btst-preview-offset')) document.getElementById('btst-preview-offset').textContent = p.offset + ' pts';
                    if (document.getElementById('btst-preview-exp')) document.getElementById('btst-preview-exp').textContent = p.expiry_str + ' (' + p.expiry_date_str + ')';

                    if (document.getElementById('btst-preview-ce-sym')) document.getElementById('btst-preview-ce-sym').textContent = p.call_symbol;
                    if (document.getElementById('btst-preview-ce-price')) document.getElementById('btst-preview-ce-price').textContent = '$' + Number(p.call_entry_price).toFixed(2);
                    if (document.getElementById('btst-preview-ce-sl')) document.getElementById('btst-preview-ce-sl').textContent = 'SL: $' + Number(p.call_sl_price).toFixed(2);

                    if (document.getElementById('btst-preview-pe-sym')) document.getElementById('btst-preview-pe-sym').textContent = p.put_symbol;
                    if (document.getElementById('btst-preview-pe-price')) document.getElementById('btst-preview-pe-price').textContent = '$' + Number(p.put_entry_price).toFixed(2);
                    if (document.getElementById('btst-preview-pe-sl')) document.getElementById('btst-preview-pe-sl').textContent = 'SL: $' + Number(p.put_sl_price).toFixed(2);
                }
            } catch (e) {
                console.warn('[BTST] previewStrikes error:', e);
            }
        }

        async function saveBtstConfig() {
            const btn = document.getElementById('btn-save-btst-cfg');
            const feedback = document.getElementById('btst-cfg-feedback');
            if (btn) btn.disabled = true;
            if (feedback) feedback.textContent = 'Saving...';

            const payload = {
                capital_inr: parseInt(document.getElementById('btst-cfg-capital')?.value || 1000000, 10),
                lots: parseInt(document.getElementById('btst-cfg-lots')?.value || 500, 10),
                sl_pct: parseFloat(document.getElementById('btst-cfg-sl')?.value || 100),
                straddle_multiplier: parseFloat(document.getElementById('btst-cfg-multiplier')?.value || 1.8),
                usd_to_inr: parseFloat(document.getElementById('btst-cfg-fx')?.value || 85.0),
                entry_time_ist: document.getElementById('btst-cfg-entry-time')?.value || '22:30',
                exit_time_ist: document.getElementById('btst-cfg-exit-time')?.value || '17:28',
                mode: document.getElementById('btst-cfg-mode')?.value || 'PAPER'
            };

            try {
                const res = await fetch('/api/btst/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const resData = await res.json();
                if (resData.success) {
                    if (feedback) {
                        feedback.style.color = '#00f59b';
                        feedback.textContent = '✅ Strategy parameters saved successfully!';
                    }
                    setTimeout(() => { if (feedback) feedback.textContent = ''; }, 4000);
                    loadBtstData();
                } else {
                    if (feedback) {
                        feedback.style.color = '#ff4b72';
                        feedback.textContent = '❌ ' + (resData.message || 'Save failed.');
                    }
                }
            } catch (err) {
                if (feedback) {
                    feedback.style.color = '#ff4b72';
                    feedback.textContent = '❌ Network error saving configuration.';
                }
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function triggerBtstEntry() {
            if (!confirm('Open automated BTST 44H Strangle trade now? (Will select D+2 expiry with 1.8x ATM Straddle Width and 100% partial SL).')) {
                return;
            }
            const btn = document.getElementById('btn-btst-trigger');
            if (btn) btn.disabled = true;

            try {
                const res = await fetch('/api/btst/trigger_entry', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({force: true})
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ BTST Trade Entered Successfully! ' + data.message);
                    loadBtstData();
                } else {
                    alert('⚠️ Could not enter trade: ' + data.message);
                }
            } catch (e) {
                alert('❌ Network error triggering BTST entry.');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function squareOffBtst() {
            if (!confirm('Square off all active BTST strangle positions immediately?')) {
                return;
            }
            const btn = document.getElementById('btn-btst-squareoff');
            if (btn) btn.disabled = true;

            try {
                const res = await fetch('/api/btst/square_off', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ BTST Positions Squared Off: ' + data.message);
                    loadBtstData();
                } else {
                    alert('⚠️ ' + data.message);
                }
            } catch (e) {
                alert('❌ Network error squaring off.');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        // Poll BTST data when tab is active
        setInterval(() => {
            const btstPane = document.getElementById('tab-btst');
            if (btstPane && btstPane.classList.contains('active')) {
                loadBtstData();
            }
        }, 5000);
'''

def inject():
    with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Inject CSS
    if '#tab-btst.active' not in content:
        content = content.replace('/* ========================================================\n           GLOBAL EMBOSSED THEME - DELTA OPTIONS ENGINE', BTST_CSS + '\n/* ========================================================\n           GLOBAL EMBOSSED THEME - DELTA OPTIONS ENGINE')
        print("Injected BTST CSS.")

    # 2. Inject Nav Tab Button
    if 'id="tab-btn-btst"' not in content:
        content = content.replace('<button class="tab-btn"        id="tab-btn-history"', BTST_NAV_BTN + '        <button class="tab-btn"        id="tab-btn-history"')
        print("Injected BTST Nav Button.")

    # 3. Inject Tab Content HTML
    if 'id="tab-btst"' not in content:
        anchor = '    <!-- TAB 3b: CONFIG remainder -->'
        if anchor in content:
            content = content.replace(anchor, BTST_TAB_HTML + '\n\n' + anchor)
            print("Injected BTST Tab HTML.")
        else:
            print("Could not find anchor for BTST Tab HTML!")

    # 4. Inject Tab Switch in switchTab()
    if "else if (name === 'btst')" not in content:
        switch_anchor = "if (name === 'live') {\n                document.getElementById('tab-live')?.classList.add('active');\n                document.getElementById('tab-btn-live')?.classList.add('active');\n            }"
        replacement = switch_anchor + """ else if (name === 'btst') {
                document.getElementById('tab-btst')?.classList.add('active');
                document.getElementById('tab-btn-btst')?.classList.add('active');
                loadBtstData(true);
            }"""
        if switch_anchor in content:
            content = content.replace(switch_anchor, replacement)
            print("Updated switchTab function for btst.")
        else:
            # Try alternate formatting
            content = re.sub(
                r"(if\s*\(\s*name\s*===\s*'live'\s*\)\s*\{[^}]+\})",
                r"\1 else if (name === 'btst') {\n                document.getElementById('tab-btst')?.classList.add('active');\n                document.getElementById('tab-btn-btst')?.classList.add('active');\n                loadBtstData(true);\n            }",
                content
            )
            print("Updated switchTab via regex.")

    # 5. Inject JS functions
    if 'loadBtstData' not in content:
        script_anchor = 'function switchTab(name) {'
        content = content.replace(script_anchor, BTST_JS + '\n\n        ' + script_anchor)
        print("Injected BTST JavaScript functions.")

    with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("templates/dashboard.html updated successfully!")

if __name__ == '__main__':
    inject()
