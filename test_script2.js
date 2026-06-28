
        document.addEventListener("DOMContentLoaded", () => {
            setTimeout(() => { document.getElementById('line1').style.opacity = '1'; }, 300);
            setTimeout(() => { document.getElementById('line2').style.opacity = '1'; }, 800);
            setTimeout(() => { document.getElementById('line3').style.opacity = '1'; }, 1500);
            setTimeout(() => { document.getElementById('line4').style.opacity = '1'; }, 2200);
            setTimeout(() => { 
                const bs = document.getElementById('boot-screen');
                bs.style.opacity = '0'; 
                setTimeout(() => { bs.style.display = 'none'; }, 500);
            }, 3000);
        });
    

        console.log("Dashboard: Script Initializing...");

        // ── P&L Smoothing Cache ──────────────────────────────────────────────
        // Prevents wild jumps when switching screens or tab-switching.
        // Uses Exponential Moving Average (EMA) with alpha=0.25 for smooth updates.
        // Caches the last known good values; only updates when new data is valid.
        const PNL_EMA_ALPHA = 0.25;   // Smoothing factor (lower = smoother but slower)
        const pnlCache = {
            totalPnlUsd: null,
            totalPnlInr: null,
            legs: {}           // sym -> { currentPrice, legPnlUsd, legPnlInr }
        };

        function smoothValue(cached, newVal) {
            // If no cached value yet, accept immediately (first render)
            if (cached === null || cached === undefined) return newVal;
            // EMA smoothing: new = alpha * newVal + (1 - alpha) * cached
            return PNL_EMA_ALPHA * newVal + (1 - PNL_EMA_ALPHA) * cached;
        }

        function applyPnlSmoothing(positions, totalPnlUsd, totalPnlInr) {
            // Smooth total P&L
            pnlCache.totalPnlUsd = smoothValue(pnlCache.totalPnlUsd, totalPnlUsd);
            pnlCache.totalPnlInr = smoothValue(pnlCache.totalPnlInr, totalPnlInr);

            // Smooth per-leg prices and P&L
            const smoothedPositions = positions.map(pos => {
                const sym = pos.symbol;
                if (!pnlCache.legs[sym]) {
                    pnlCache.legs[sym] = {
                        currentPrice: pos.current_price,
                        legPnlUsd:    pos.leg_pnl_usd,
                        legPnlInr:    pos.leg_pnl_inr
                    };
                } else {
                    pnlCache.legs[sym].currentPrice = smoothValue(pnlCache.legs[sym].currentPrice, pos.current_price);
                    pnlCache.legs[sym].legPnlUsd    = smoothValue(pnlCache.legs[sym].legPnlUsd,    pos.leg_pnl_usd);
                    pnlCache.legs[sym].legPnlInr    = smoothValue(pnlCache.legs[sym].legPnlInr,    pos.leg_pnl_inr);
                }
                return {
                    ...pos,
                    current_price: pnlCache.legs[sym].currentPrice,
                    leg_pnl_usd:   pnlCache.legs[sym].legPnlUsd,
                    leg_pnl_inr:   pnlCache.legs[sym].legPnlInr
                };
            });

            // Prune symbols no longer in positions
            const activeSyms = new Set(positions.map(p => p.symbol));
            Object.keys(pnlCache.legs).forEach(sym => {
                if (!activeSyms.has(sym)) delete pnlCache.legs[sym];
            });
            if (!positions.length) {
                pnlCache.totalPnlUsd = null;
                pnlCache.totalPnlInr = null;
            }

            return {
                smoothedPositions,
                smoothedTotalPnlUsd: pnlCache.totalPnlUsd,
                smoothedTotalPnlInr: pnlCache.totalPnlInr
            };
        }
        // ────────────────────────────────────────────────────────────────────

        // Command API
        async function sendCommand(action) {
            try {
                await fetch(`/api/${action}`, { method: 'POST' });
                fetchStatus();
            } catch (e) {
                console.error("Command failed", e);
            }
        }

        // Status Polling
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();


                // Update Badge
                const badge = document.getElementById('status-badge');
                if(data.is_running) {
                    badge.textContent = `🟢 ENGINE RUNNING`;
                    badge.className = 'status-badge';
                } else {
                    badge.textContent = `🔴 ENGINE STOPPED`;
                    badge.className = 'status-badge offline';
                }

                // Update Stats
                document.getElementById('equity-val').textContent = `$${data.equity.toLocaleString()}`;
                document.getElementById('mode-val').textContent = data.mode;
                document.getElementById('loss-hits-val').textContent = `${data.daily_loss_hits} / 2`;

                // Update IV Status Card
                if (data.current_iv !== undefined) {
                    document.getElementById('current-iv-val').textContent = `${data.current_iv.toFixed(2)}%`;
                    document.getElementById('avg-iv-val').textContent = `${data.avg_7d_iv.toFixed(2)}%`;
                    
                    const ivBadge = document.getElementById('iv-status-badge');
                    if (data.iv_status === 'Normal') {
                        ivBadge.textContent = '🟢 Normal';
                        ivBadge.style.color = 'var(--success)';
                        ivBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                        ivBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                    } else if (data.iv_status === 'Bypassed' || data.iv_status === 'Disabled') {
                        ivBadge.textContent = '🟢 Bypassed (Testing)';
                        ivBadge.style.color = 'var(--success)';
                        ivBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                        ivBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                    } else {
                        ivBadge.textContent = '🔴 Low';
                        ivBadge.style.color = 'var(--danger)';
                        ivBadge.style.background = 'rgba(239, 68, 68, 0.1)';
                        ivBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                    }
                }

                // Update PAPER Mode enhancements
                const paperNote = document.getElementById('paper-mode-note');
                if (paperNote) {
                    paperNote.style.display = data.mode === 'PAPER' ? 'block' : 'none';
                }
                const lotMultVal = document.getElementById('lot-multiplier-val');
                if (lotMultVal) {
                    lotMultVal.textContent = `${(data.size_multiplier * 100).toFixed(0)}% of base (${data.size_multiplier.toFixed(2)}x)`;
                }
                const apiStatusBadge = document.getElementById('api-status-badge');
                if (apiStatusBadge) {
                    if (data.api_connected) {
                        apiStatusBadge.textContent = '🟢 Connected';
                        apiStatusBadge.style.color = 'var(--success)';
                    } else {
                        apiStatusBadge.textContent = '🔴 Disconnected';
                        apiStatusBadge.style.color = 'var(--danger)';
                    }
                }

                // Update Advanced Rules and Dynamic Sizing stats
                document.getElementById('consecutive-losses-val').textContent = data.consecutive_loss_count || 0;
                const cooldownEl = document.getElementById('sizing-cooldown-val');
                if (data.reduced_size_trades_remaining > 0) {
                    cooldownEl.textContent = `${data.reduced_size_trades_remaining} trades remaining (-20%)`;
                    cooldownEl.style.color = 'var(--warning)';
                } else if (data.size_multiplier < 0.99 && data.size_multiplier > 0.69) {
                    cooldownEl.textContent = 'Daily Loss Cooldown (-30%)';
                    cooldownEl.style.color = 'var(--warning)';
                } else {
                    cooldownEl.textContent = 'No Cooldown';
                    cooldownEl.style.color = 'var(--text-secondary)';
                }
                const pauseContainer = document.getElementById('next-day-paused-container');
                if (pauseContainer) {
                    pauseContainer.style.display = data.next_day_paused ? 'block' : 'none';
                }

                // Update IV & DVOL Panel
                if (data.dvol_status) {
                    document.getElementById('dvol-val').textContent = `${data.dvol_status.current_dvol.toFixed(2)}%`;
                    document.getElementById('dvol-percentile-val').textContent = `${data.dvol_status.dvol_percentile.toFixed(1)}%`;
                    document.getElementById('dvol-percentile-bar').style.width = `${data.dvol_status.dvol_percentile}%`;
                    
                    if (data.dvol_status.premium_range) {
                        document.getElementById('premium-range-val').textContent = `$${data.dvol_status.premium_range[0]} - $${data.dvol_status.premium_range[1]}`;
                    }
                    
                    const dvolBadge = document.getElementById('dvol-can-trade-badge');
                    if (dvolBadge) {
                        if (data.dvol_status.is_bypassed) {
                            dvolBadge.textContent = '🟢 Bypassed (Testing)';
                            dvolBadge.style.color = 'var(--success)';
                            dvolBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else if (data.dvol_status.eligible_to_trade) {
                            dvolBadge.textContent = '🟢 Safe to Trade';
                            dvolBadge.style.color = 'var(--success)';
                            dvolBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else {
                            dvolBadge.textContent = '🔴 Skip (DVOL Extreme)';
                            dvolBadge.style.color = 'var(--danger)';
                            dvolBadge.style.background = 'rgba(239, 68, 68, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                        }
                    }
                }

                // Update Smart Hedging Panel
                if (data.hedge_status) {
                    const hBadge = document.getElementById('hedge-active-badge');
                    if (hBadge) {
                        if (data.hedge_status.hedge_active) {
                            hBadge.textContent = '🛡️ ACTIVE';
                            hBadge.style.color = 'var(--success)';
                            hBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            hBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else {
                            hBadge.textContent = '⚪ INACTIVE';
                            hBadge.style.color = 'var(--text-secondary)';
                            hBadge.style.background = 'rgba(255, 255, 255, 0.05)';
                            hBadge.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                        }
                    }
                    
                    document.getElementById('hedge-type-val').textContent = (data.hedge_status.hedge_type || 'none').toUpperCase();
                    document.getElementById('hedge-size-val').textContent = `${(data.hedge_status.hedge_size_btc || 0).toFixed(6)} BTC`;
                    
                    const hedgePnl = data.hedge_status.hedge_pnl_usd || 0;
                    const pnlSpan = document.getElementById('hedge-pnl-val');
                    pnlSpan.textContent = `${hedgePnl >= 0 ? '+' : ''}$${hedgePnl.toFixed(2)}`;
                    pnlSpan.style.color = hedgePnl > 0 ? 'var(--success)' : (hedgePnl < 0 ? 'var(--danger)' : 'var(--text-secondary)');
                    
                    document.getElementById('hedge-percentage-val').textContent = `${(data.hedge_status.hedge_percentage || 0).toFixed(0)}%`;
                    document.getElementById('hedge-percentage-bar').style.width = `${data.hedge_status.hedge_percentage || 0}%`;
                    
                    const slTight = document.getElementById('sl-tightened-badge');
                    if (slTight) {
                        slTight.style.display = data.hedge_status.sl_tightened ? 'block' : 'none';
                    }
                }

                // Show/Hide Test Order button based on mode
                const testBtn = document.getElementById('btn-test-order');
                if (testBtn) {
                    testBtn.style.display = data.mode === 'PAPER' ? 'block' : 'none';
                }
                
                // Update Badge and Toggle
                const regimeBadge = document.getElementById('regime-badge');
                if(data.current_market_regime !== undefined) {
                    let rColor = data.current_market_regime === 'Trending' ? 'var(--danger)' : 'var(--success)';
                    let rIcon = data.current_market_regime === 'Trending' ? '🔴' : '🟢';
                    if (data.current_market_regime === 'Unknown') { rColor = 'var(--text-secondary)'; rIcon = '⚪'; }
                    regimeBadge.innerHTML = `${rIcon} ${data.current_market_regime} (ADX: ${data.current_adx_value.toFixed(1)})`;
                    regimeBadge.style.color = rColor;
                }
                
                // Update Market Regime Detector UI
                if (data.current_market_regime) {
                    const regime = data.current_market_regime.toUpperCase();
                    const adx = data.current_adx_value || 0;
                    
                    const mainLabel = document.getElementById('regime-main-label');
                    const recLabel = document.getElementById('regime-recommendation');
                    if (mainLabel && recLabel) {
                        mainLabel.textContent = regime;
                        if (regime === 'TRENDING') {
                            mainLabel.style.color = 'var(--rose)';
                            mainLabel.style.background = 'rgba(244, 63, 94, 0.1)';
                            mainLabel.style.boxShadow = '0 0 20px rgba(244, 63, 94, 0.2)';
                            recLabel.textContent = '⚠️ Caution - Trending Market';
                        } else if (regime === 'SIDEWAYS' || regime === 'RANGING') {
                            mainLabel.style.color = 'var(--emerald)';
                            mainLabel.style.background = 'rgba(16, 185, 129, 0.1)';
                            mainLabel.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.2)';
                            recLabel.textContent = '✅ Best for Short Strangle';
                        } else {
                            mainLabel.style.color = 'var(--text-secondary)';
                            mainLabel.style.background = 'rgba(255, 255, 255, 0.05)';
                            mainLabel.style.boxShadow = 'none';
                            recLabel.textContent = 'Waiting for stable data...';
                        }
                    }

                    const gaugePath = document.getElementById('adx-gauge-path');
                    const gaugeVal = document.getElementById('adx-gauge-val');
                    if (gaugePath && gaugeVal) {
                        gaugeVal.textContent = adx.toFixed(1);
                        const maxAdx = 60;
                        const percentage = Math.min(Math.max(adx / maxAdx, 0), 1);
                        const offset = 125 - (percentage * 125);
                        gaugePath.style.strokeDashoffset = offset;
                        
                        let strokeColor = 'var(--emerald)';
                        if (adx > 25) strokeColor = 'var(--rose)';
                        else if (adx >= 22) strokeColor = 'var(--warning)';
                        gaugePath.style.stroke = strokeColor;
                    }

                    const history = data.adx_history || [];
                    const sparkline = document.getElementById('adx-sparkline');
                    const trendDirection = document.getElementById('adx-trend-direction');
                    if (sparkline && history.length >= 2) {
                        const min = Math.min(...history) - 2;
                        const max = Math.max(...history) + 2;
                        const range = max - min === 0 ? 1 : max - min;
                        
                        let pathD = '';
                        history.forEach((val, i) => {
                            const x = (i / (history.length - 1)) * 100;
                            const y = 40 - (((val - min) / range) * 40);
                            if (i === 0) pathD += `M ${x} ${y} `;
                            else pathD += `L ${x} ${y} `;
                        });
                        sparkline.innerHTML = `<path d="${pathD}"></path>`;
                        
                        const curr = history[history.length - 1];
                        const prev = history[history.length - 2];
                        if (curr > prev) {
                            trendDirection.innerHTML = '📈 RISING';
                            trendDirection.style.color = 'var(--rose)';
                            sparkline.style.stroke = 'var(--rose)';
                        } else if (curr < prev) {
                            trendDirection.innerHTML = '📉 FALLING';
                            trendDirection.style.color = 'var(--emerald)';
                            sparkline.style.stroke = 'var(--emerald)';
                        } else {
                            trendDirection.innerHTML = 'FLAT';
                            trendDirection.style.color = 'var(--text-secondary)';
                            sparkline.style.stroke = 'var(--text-secondary)';
                        }
                    }
                }
                
                // Sync pill button state
                const pill = document.getElementById('regime-pill');
                if(pill && data.regime_filter_enabled !== undefined) {
                    if(data.regime_filter_enabled) {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    } else {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    }
                }

                const hedgePill = document.getElementById('hedge-pill');
                if(hedgePill && data.smart_hedging_enabled !== undefined) {
                    if(data.smart_hedging_enabled) {
                        hedgePill.textContent = 'ON';
                        hedgePill.style.background = 'var(--success)';
                        hedgePill.style.borderColor = 'var(--success)';
                        hedgePill.style.color = '#fff';
                        hedgePill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    } else {
                        hedgePill.textContent = 'OFF';
                        hedgePill.style.background = '#334155';
                        hedgePill.style.borderColor = '#334155';
                        hedgePill.style.color = '#94a3b8';
                        hedgePill.style.boxShadow = 'none';
                    }
                }


                // ── Update Active Positions ──────────────────────────────────────────
                const posCards  = document.getElementById('positions-cards');
                const totalBar  = document.getElementById('pos-total-bar');
                const posContainer = document.getElementById('active-positions-container');
                
                if (data.positions && data.positions.length > 0) {
                    if (posContainer) posContainer.classList.add('active-trade-glow');
                    totalBar.style.display = 'flex';
                    
                    // ── Apply EMA smoothing to prevent wild jumps on tab switch / refresh ──
                    // Formula: PnL = (Entry_Premium - Current_Premium) * Lots * 0.001 BTC
                    const rawTotalPnlUsd = data.total_pnl_usd || 0;
                    const rawTotalPnlInr = data.total_pnl_inr || 0;
                    const { smoothedPositions, smoothedTotalPnlUsd, smoothedTotalPnlInr } =
                        applyPnlSmoothing(data.positions, rawTotalPnlUsd, rawTotalPnlInr);
                    const totalPnlUsd = smoothedTotalPnlUsd;
                    const totalPnlInr = smoothedTotalPnlInr;

                    // Update summary bar
                    const totalEntryPremium = data.total_entry_premium || 0;
                    document.getElementById('pos-total-entry').textContent = totalEntryPremium.toFixed(4);
                    
                    // Display Capital Used and reference BTC price
                    const totalCapitalUsed = data.total_capital_used || 0;
                    document.getElementById('pos-total-capital').textContent = totalCapitalUsed.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    document.getElementById('pos-btc-price').textContent = (data.btc_price || 70000).toLocaleString(undefined, {maximumFractionDigits: 0});
                    
                    // Recalculate percentages based on smoothed P&L and actual denominators
                    const totalPnlPctPrem = totalEntryPremium > 0 ? (totalPnlUsd / totalEntryPremium * 100) : 0.0;
                    const totalPnlPctCap = totalCapitalUsed > 0 ? (totalPnlUsd / totalCapitalUsed * 100) : 0.0;
                    
                    const pnlPctSignPrem = totalPnlPctPrem >= 0 ? '+' : '';
                    const pnlPctSignCap = totalPnlPctCap >= 0 ? '+' : '';
                    
                    const pnlUsdEl = document.getElementById('pos-total-pnl-usd');
                    pnlUsdEl.innerHTML = `<div style="display: flex; flex-direction: column; gap: 2px; padding-top: 4px;">
                        <span style="font-size: 1.6rem; font-weight: 800; line-height: 1;">${totalPnlUsd >= 0 ? '+' : ''}${totalPnlUsd.toFixed(4)} USDT</span>
                        <span style="font-size: 0.8rem; font-weight: 500; opacity: 0.8; letter-spacing: 0.2px; color: var(--text-secondary);">(${pnlPctSignPrem}${totalPnlPctPrem.toFixed(2)}% Prem &nbsp;|&nbsp; ${pnlPctSignCap}${totalPnlPctCap.toFixed(2)}% Cap)</span>
                    </div>`;
                    pnlUsdEl.className = totalPnlUsd >= 0 ? 'pnl-pos' : 'pnl-neg';
                    
                    const pnlInrEl = document.getElementById('pos-total-pnl-inr');
                    pnlInrEl.textContent = '₹' + (totalPnlInr >= 0 ? '+' : '') + totalPnlInr.toFixed(2);
                    pnlInrEl.className = totalPnlInr >= 0 ? 'pnl-pos' : 'pnl-neg';
                    
                    const mins = data.positions[0]?.mins_to_squareoff ?? 0;
                    const hh = Math.floor(mins / 60);
                    const mm = mins % 60;
                    document.getElementById('pos-time-remaining').textContent = mins > 0 ? `${hh}h ${mm}m` : 'Market Closed';

                    // Build one card per leg (using smoothed positions)
                    posCards.innerHTML = smoothedPositions.map(pos => {

                        const isCall = pos.leg_type === 'call';
                        const legLabel = isCall
                            ? '<span class="pos-call-label">📈 CALL</span>'
                            : '<span class="pos-put-label">📉 PUT</span>';
                        
                        const pnlClass  = pos.leg_pnl_usd >= 0 ? 'pnl-pos' : 'pnl-neg';
                        const pnlSign   = pos.leg_pnl_usd >= 0 ? '+' : '';
                        const pnlInrSign = pos.leg_pnl_inr >= 0 ? '+' : '';

                        let statusClass = 'status-running';
                        let statusIcon  = '🟢 Running';
                        if (pos.trade_status === 'Trailing SL Active') { statusClass = 'status-trailing'; statusIcon = '🔴 Trailing SL'; }
                        else if (pos.trade_status === 'Partial Profit Booked') { statusClass = 'status-partial'; statusIcon = '🟡 Partial Profit'; }

                        // Entry time formatting
                        let entryTimeDisplay = '—';
                        if (pos.entry_time) {
                            try {
                                const d = new Date(pos.entry_time);
                                entryTimeDisplay = d.toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit', hour12: true});
                            } catch(e) { entryTimeDisplay = pos.entry_time.slice(11, 16); }
                        }

                        const minsLeft = pos.mins_to_squareoff || 0;
                        const hh2 = Math.floor(minsLeft / 60), mm2 = minsLeft % 60;
                        const timeLeft = minsLeft > 0 ? `${hh2}h ${mm2}m` : '—';

                        // Premium change %
                        const premChangePct = pos.entry_price > 0
                            ? (((pos.current_price - pos.entry_price) / pos.entry_price) * 100).toFixed(1)
                            : '0.0';
                        const premChangeSign = parseFloat(premChangePct) >= 0 ? '+' : '';

                        // Calculate accurate leg capital used and smoothed leg P&L percentages
                        const legCapitalUsed = pos.leg_capital_used || 0;
                        const legEntryPremium = pos.leg_entry_premium_total || 0;
                        
                        const legPnlPctPremium = legEntryPremium > 0 ? (pos.leg_pnl_usd / legEntryPremium * 100) : 0.0;
                        const legPnlPctCapital = legCapitalUsed > 0 ? (pos.leg_pnl_usd / legCapitalUsed * 100) : 0.0;
                        
                        const legPnlPctPremiumStr = (legPnlPctPremium >= 0 ? '+' : '') + legPnlPctPremium.toFixed(2);
                        const legPnlPctCapitalStr = (legPnlPctCapital >= 0 ? '+' : '') + legPnlPctCapital.toFixed(2);

                        return `
                        <div class="pos-card">
                            <div class="pos-card-header">
                                <div>
                                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                                        ${legLabel}
                                        <span style="font-size:0.7rem;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">${pos.side}</span>
                                    </div>
                                    <div class="pos-symbol">${pos.symbol}</div>
                                    ${pos.strike ? `<div class="pos-strike-label">Strike: $${parseFloat(pos.strike).toLocaleString()}</div>` : ''}
                                </div>
                                <div class="pos-status-badge ${statusClass}">${statusIcon}</div>
                            </div>

                            <div class="pos-metrics">
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Entry Premium</div>
                                    <div class="pos-metric-value">${pos.entry_price.toFixed(2)}</div>
                                    <div class="pos-metric-sub">USDT / lot</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Current Premium</div>
                                    <div class="pos-metric-value" style="color:${parseFloat(premChangePct)<0?'#34d399':'#f87171'}">${pos.current_price.toFixed(2)}</div>
                                    <div class="pos-metric-sub">${premChangeSign}${premChangePct}% from entry</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Leg P&amp;L</div>
                                    <div style="display: flex; flex-direction: column; gap: 2px; margin-top: 2px;">
                                        <div class="pos-metric-value ${pnlClass}" style="line-height: 1;">${pnlSign}${pos.leg_pnl_usd.toFixed(2)} USD</div>
                                        <div style="font-size: 0.75rem; font-weight: 500; opacity: 0.8; color: var(--text-secondary);">(${legPnlPctPremiumStr}% Prem | ${legPnlPctCapitalStr}% Cap)</div>
                                        <div class="pos-metric-sub ${pnlClass}" style="margin-top: 0;">${pnlInrSign}₹${pos.leg_pnl_inr.toFixed(0)}</div>
                                    </div>
                                </div>
                                <div class="pos-metric" style="background: rgba(16,185,129,0.04); border: 1px solid rgba(16,185,129,0.08);">
                                    <div class="pos-metric-label" style="color: #34d399;">Capital Used</div>
                                    <div class="pos-metric-value" style="color: #34d399; font-weight: 800;">$${legCapitalUsed.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                                    <div class="pos-metric-sub">at $${(data.btc_price || 70000).toLocaleString(undefined, {maximumFractionDigits: 0})} BTC</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Lot Size</div>
                                    <div class="pos-metric-value">${pos.size}</div>
                                    <div class="pos-metric-sub">contracts</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Delta / Gamma</div>
                                    <div class="pos-metric-value">${pos.delta.toFixed(3)}</div>
                                    <div class="pos-metric-sub">γ ${pos.gamma.toFixed(4)}</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Live IV</div>
                                    <div class="pos-metric-value">${pos.current_iv_pct.toFixed(2)}%</div>
                                    <div class="pos-metric-sub">Implied Volatility</div>
                                </div>
                            </div>

                            <div class="pos-divider"></div>
                            <div class="pos-footer">
                                <div class="pos-footer-chip">🕐 Entry: <strong>${entryTimeDisplay} IST</strong></div>
                                <div class="pos-footer-chip">⏱ SqOff in: <strong>${timeLeft}</strong></div>
                            </div>
                        </div>`;
                    }).join('');

                } else {
                    totalBar.style.display = 'none';
                    posCards.innerHTML = `
                        <div class="pos-empty">
                            <div class="pos-empty-icon">📭</div>
                            <div style="font-weight:600;color:var(--text-secondary);">No Active Positions</div>
                            <div style="font-size:0.8rem;margin-top:6px;opacity:0.6;">The bot has no open trades right now.</div>
                        </div>`;
                    if (posContainer) posContainer.classList.remove('active-trade-glow');
                }

                // Update Rule Compliance
                if(data.rule_report && data.rule_report.results) {
                    // Check if today was skipped and map to rules
                    const skipReason = data.today_skip_reason || "";
                    let failedRuleName = null;
                    
                    if (skipReason) {
                        const reasonLower = skipReason.toLowerCase();
                        if (reasonLower.includes("loss limit") || reasonLower.includes("sls") || reasonLower.includes("max loss")) {
                            failedRuleName = "Daily Loss Limit";
                        } else if (reasonLower.includes("strike") || reasonLower.includes("premium") || reasonLower.includes("net delta")) {
                            failedRuleName = "Strike Selection";
                        } else if (reasonLower.includes("capital") || reasonLower.includes("lot size") || reasonLower.includes("insufficient") || reasonLower.includes("consecutive losses")) {
                            failedRuleName = "Lot Size";
                        } else if (reasonLower.includes("exit")) {
                            failedRuleName = "Exit Time";
                        } else if (reasonLower.includes("hedge")) {
                            failedRuleName = "Hedging";
                        }
                    }

                    const badge = document.getElementById('compliance-badge');
                    if (failedRuleName) {
                        const failedCount = data.rule_report.results.filter(r => r.name === failedRuleName || !r.passed).length;
                        const compliancePct = Math.round(((data.rule_report.results.length - failedCount) / data.rule_report.results.length) * 100);
                        badge.textContent = `${compliancePct}% Compliant`;
                        badge.style.color = 'var(--danger)';
                        badge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                        badge.style.background = 'rgba(239, 68, 68, 0.1)';
                    } else {
                        badge.textContent = `100% Compliant`;
                        badge.style.color = 'var(--success)';
                        badge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        badge.style.background = 'rgba(16, 185, 129, 0.1)';
                    }

                    const rulesGrid = document.getElementById('rules-grid');
                    rulesGrid.innerHTML = data.rule_report.results.map(r => {
                        const isFailed = (r.name === failedRuleName) || !r.passed;
                        const bg = isFailed ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.06)';
                        const border = isFailed ? '1px solid rgba(239, 68, 68, 0.25)' : '1px solid rgba(16, 185, 129, 0.18)';
                        const icon = isFailed ? '❌' : '✅';
                        
                        return `
                            <div style="background: ${bg}; padding: 12px; border-radius: 8px; border: ${border}; display: flex; align-items: center; gap: 10px; transition: all 0.3s ease;">
                                <div style="font-size: 1.2rem;">${icon}</div>
                                <div>
                                    <div style="font-weight: 600; font-size: 0.9rem; color: #fff;">${r.name}</div>
                                    <div style="font-size: 0.8rem; color: var(--text-secondary);">${r.expected}</div>
                                </div>
                            </div>
                        `;
                    }).join('');

                    // Today's Skip Reason Section update
                    const skipTitle = document.getElementById('skip-reason-title');
                    const skipText = document.getElementById('skip-reason-text');
                    
                    if (data.today_skip_reason) {
                        // We have an active skip today! Style in red.
                        skipTitle.innerHTML = "🚫 Today's Skip Reason";
                        skipText.textContent = data.today_skip_reason;
                        skipText.style.color = "#fca5a5";
                        skipText.style.background = "rgba(239, 68, 68, 0.08)";
                        skipText.style.borderColor = "rgba(239, 68, 68, 0.15)";
                    } else if (data.schedule_info && data.schedule_info.today_status === "Trade Taken") {
                        // Trade taken successfully! Style in green.
                        skipTitle.innerHTML = "✅ Today's Status";
                        skipText.textContent = "Trade taken successfully";
                        skipText.style.color = "#a7f3d0";
                        skipText.style.background = "rgba(16, 185, 129, 0.08)";
                        skipText.style.borderColor = "rgba(16, 185, 129, 0.18)";
                    } else {
                        // No active skips/trades yet today (system normal). Style in grey/secondary.
                        skipTitle.innerHTML = "ℹ️ Today's Status";
                        skipText.textContent = "None (System running normally)";
                        skipText.style.color = "var(--text-secondary)";
                        skipText.style.background = "rgba(255, 255, 255, 0.03)";
                        skipText.style.borderColor = "rgba(255, 255, 255, 0.08)";
                    }
                }

                
                // Update Skip & Schedule Info
                if(data.schedule_info) {
                    const statusBadge = document.getElementById('today-status-badge');
                    const status = data.schedule_info.today_status;
                    const reason = data.schedule_info.today_reason;
                    
                    if (status === "Trade Taken") {
                        statusBadge.textContent = "✅ " + status;
                        statusBadge.style.color = "var(--success)";
                        statusBadge.style.background = "rgba(16, 185, 129, 0.1)";
                        statusBadge.style.border = "1px solid rgba(16, 185, 129, 0.2)";
                    } else if (status === "Trade Skipped") {
                        statusBadge.textContent = "⏭️ " + status + (reason ? ` (${reason})` : "");
                        if (reason && (reason.includes("Weekend") || reason.includes("News"))) {
                            statusBadge.style.color = "var(--danger)";
                            statusBadge.style.background = "rgba(239, 68, 68, 0.1)";
                            statusBadge.style.border = "1px solid rgba(239, 68, 68, 0.2)";
                        } else {
                            statusBadge.style.color = "var(--warning)";
                            statusBadge.style.background = "rgba(245, 158, 11, 0.1)";
                            statusBadge.style.border = "1px solid rgba(245, 158, 11, 0.2)";
                        }
                    } else {
                        statusBadge.textContent = "⏳ " + status;
                        statusBadge.style.color = "var(--text-secondary)";
                        statusBadge.style.background = "rgba(255, 255, 255, 0.05)";
                        statusBadge.style.border = "1px solid rgba(255, 255, 255, 0.1)";
                    }

                    // ── TRADE SKIP ALERT CARD ──────────────────────────────────────
                    (function() {
                        const skipAlertCard = document.getElementById('trade-skip-alert-card');
                        if (!skipAlertCard) return;
                        const skipReasonEl = document.getElementById('skip-reason-text');
                        const skipHintEl   = document.getElementById('skip-hint-text');
                        const skipTsEl     = document.getElementById('skip-timestamp');
                        const skipHistEl   = document.getElementById('skip-history-list');
                        const skipHistSec  = document.getElementById('skip-history-section');

                        if (status === 'Trade Skipped' && reason) {
                            skipAlertCard.style.display = 'block';
                            skipAlertCard.style.animation = 'slide-down-in 0.4s ease';
                            skipReasonEl.textContent = reason;

                            const hist = data.schedule_info.skip_history || [];
                            skipTsEl.textContent = hist.length > 0 ? hist[0].time : '';

                            const hintMap = [
                                ['Maximum 1 trade',     'Next entry window will be tomorrow at 09:00 AM IST.'],
                                ['Next day pause',      'Trading resumes once the daily P&L is above -2.5%.'],
                                ['consecutive losses',  'Bot will resume trading after tonight\'s daily reset.'],
                                ['API connection',      'Check your internet connection and API key in the Config tab.'],
                                ['Daily Loss Limit',    'The -3% daily loss limit was hit. Trading resumes tomorrow.'],
                                ['No suitable strikes', 'DVOL premium targets not matched. Strikes retry at next slot.'],
                                ['risk per trade',      'Position size too large for equity. Reduce lot size in Config.'],
                                ['Trending',            'ADX > 25 means trending market. Bot waits for sideways.'],
                                ['DVOL',                'Volatility index out of safe range. Waiting for DVOL to normalize.'],
                                ['Weekend',             'Markets closed. Trading resumes Monday 09:00 AM IST.'],
                            ];
                            let hint = 'Trade skipped by risk management. Next slot will be checked automatically.';
                            for (const [key, val] of hintMap) {
                                if (reason.includes(key)) { hint = val; break; }
                            }
                            skipHintEl.textContent = hint;

                            if (hist.length > 0) {
                                skipHistEl.innerHTML = hist.map((e, i) => `
                                    <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                                        background:${i===0?'rgba(245,158,11,0.10)':'rgba(255,255,255,0.02)'};
                                        border:1px solid ${i===0?'rgba(245,158,11,0.22)':'rgba(255,255,255,0.05)'};
                                        border-radius:7px;font-size:0.78rem;">
                                        <span>${i===0?'🔴':'🟡'}</span>
                                        <span style="color:rgba(255,255,255,0.5);min-width:145px;flex-shrink:0;">${e.time}</span>
                                        <span style="color:${i===0?'#fbbf24':'rgba(255,255,255,0.6)'};font-weight:${i===0?700:400};">${e.reason}</span>
                                    </div>`).join('');
                                skipHistSec.style.display = 'block';
                            } else {
                                skipHistSec.style.display = 'none';
                            }
                        } else {
                            skipAlertCard.style.display = 'none';
                        }
                    })();
                    // ──────────────────────────────────────────────────────────────

                    const schedBody = document.getElementById('schedule-body');
                    let showWarning = false;
                    let warningText = "";
                    
                    if (data.schedule_info.upcoming_schedule && data.schedule_info.upcoming_schedule.length > 0) {
                        schedBody.innerHTML = '';
                        data.schedule_info.upcoming_schedule.forEach((day, index) => {
                            if ((index === 1 || index === 2) && day.skip && !showWarning) {
                                showWarning = true;
                                warningText = `⚠️ EARLY WARNING: Trading will be skipped on ${day.day} (${day.reason})`;
                            }
                            
                            let statusColor = day.skip ? (day.skip_type === 'severe' ? 'var(--danger)' : 'var(--warning)') : 'var(--success)';
                            let statusText = day.skip ? '⏭️ Skipped' : '✅ Scheduled';
                            
                            schedBody.innerHTML += `
                                <tr>
                                    <td style="font-weight: 600;">${day.date}</td>
                                    <td style="color: var(--text-secondary);">${day.day}</td>
                                    <td style="color: ${statusColor}; font-weight: 600;">${statusText}</td>
                                    <td style="color: var(--text-secondary);">${day.reason || '-'}</td>
                                </tr>
                            `;
                        });
                    }
                    
                    const warningBox = document.getElementById('early-warning-box');
                    if (showWarning) {
                        warningBox.style.display = 'flex';
                        warningBox.textContent = warningText;
                    } else {
                        warningBox.style.display = 'none';
                    }
                }

                // Update Logs
                const logTerm = document.getElementById('log-terminal');
                const isScrolledToBottom = logTerm.scrollHeight - logTerm.clientHeight <= logTerm.scrollTop + 10;
                
                logTerm.innerHTML = data.logs.map(line => {
                    let color = "#a7f3d0"; // default green-ish
                    if(line.includes("ERROR") || line.includes("CRITICAL")) color = "#fca5a5";
                    if(line.includes("WARNING")) color = "#fde047";
                    return `<div class="log-line" style="color: ${color};">${line}</div>`;
                }).join('');

                if (isScrolledToBottom) {
                    logTerm.scrollTop = logTerm.scrollHeight;
                }

            } catch (e) {
                console.error("Polling failed", e);
                const badge = document.getElementById('status-badge');
                badge.textContent = `🔴 OFFLINE`;
                badge.className = 'status-badge offline';
            }
        }

        async function runTestOrder() {
            console.log("Dashboard: runTestOrder() triggered");
            const btn = document.getElementById('btn-test-order');
            const originalText = btn.innerHTML;
            
            if (!confirm("Place a REAL 1-lot order for testing?\n\nIt will automatically close after 10 seconds.\n\nOnly works in PAPER mode.")) {
                console.log("Dashboard: Test order cancelled by user");
                return;
            }
            
            try {
                console.log("Dashboard: Sending POST to /api/test_order...");
                btn.disabled = true;
                btn.innerHTML = "⌛ PLACING TEST ORDER...";
                
                const response = await fetch('/api/test_order', { method: 'POST' });
                
                // Always read as text first to diagnose non-JSON responses
                const raw = await response.text();
                console.log("Dashboard: Raw response:", raw);
                
                let result;
                try {
                    result = JSON.parse(raw);
                } catch (parseErr) {
                    console.error("Dashboard: Response is not valid JSON:", raw);
                    alert("❌ Server Error: The server returned an unexpected response.\nCheck backend logs for details.\n\n" + raw.substring(0, 200));
                    return;
                }
                
                if (result.success === true) {
                    alert("✅ Test Order Success!\n\n" + result.message);
                } else {
                    alert("❌ Test Order Failed:\n\n" + (result.error || result.message || "Unknown error"));
                }
            } catch (error) {
                console.error("Dashboard: Test order fetch error:", error);
                alert("❌ Network Error: " + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        async function runManualOrder() {
            console.log("Dashboard: runManualOrder() triggered");
            const btn = document.getElementById('btn-manual-order');
            const originalText = btn.innerHTML;
            
            if (!confirm("Are you sure you want to FORCE trigger the strangle entry cycle immediately?\n\nThis will look up strikes and execute a trade in the current mode (LIVE or PAPER).")) {
                console.log("Dashboard: Manual order cancelled by user");
                return;
            }
            
            try {
                console.log("Dashboard: Sending POST to /api/manual_order...");
                btn.disabled = true;
                btn.innerHTML = "⌛ TRIGGERING STRANGLE ENTRY...";
                
                const response = await fetch('/api/manual_order', { method: 'POST' });
                const raw = await response.text();
                console.log("Dashboard: Raw response:", raw);
                
                let result;
                try {
                    result = JSON.parse(raw);
                } catch (parseErr) {
                    console.error("Dashboard: Response is not valid JSON:", raw);
                    alert("❌ Server Error: The server returned an unexpected response.\n\n" + raw.substring(0, 200));
                    return;
                }
                
                if (result.status === 'success') {
                    alert("✅ Success!\n\n" + (result.message || "Manual strangle entry cycle triggered successfully!"));
                } else {
                    alert("❌ Failed:\n\n" + (result.error || result.message || "Unknown error"));
                }
            } catch (error) {
                console.error("Dashboard: Manual order fetch error:", error);
                alert("❌ Network Error: " + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        async function emergencyClose() {
            if (confirm("⚠️ ARE YOU SURE YOU WANT TO EMERGENCY CLOSE ALL POSITIONS? ⚠️\n\nThis will execute MARKET orders to square off your ENTIRE portfolio immediately.\n\nThis action CANNOT be undone.")) {
                try {
                    const btn = document.querySelector('.btn-emergency-pulse');
                    if (btn) {
                        btn.innerHTML = '⏳ Closing...';
                        btn.disabled = true;
                    }
                    const res = await fetch('/api/emergency_close', { method: 'POST' });
                    if(res.ok) {
                        if (btn) {
                            btn.innerHTML = '✅ All Closed';
                            setTimeout(() => { 
                                btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF'; 
                                btn.disabled = false; 
                            }, 3000);
                        }
                        alert("Emergency Square Off Successful! All positions closed.");
                        fetchStatus();
                    } else {
                        const errData = await res.json();
                        alert("Failed to emergency close: " + (errData.error || "Unknown error"));
                        if (btn) {
                            btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF';
                            btn.disabled = false;
                        }
                    }
                } catch(e) { 
                    console.error("Emergency fail", e); 
                    alert("Network error: Could not reach server for emergency close.");
                    const btn = document.querySelector('.btn-emergency-pulse');
                    if (btn) {
                        btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF';
                        btn.disabled = false;
                    }
                }
            }
        }

        async function toggleRegimeFilter() {
            const pill = document.getElementById('regime-pill');
            try {
                // Optimistic UI update before server confirms
                const isCurrentlyOn = pill && pill.textContent.trim() === 'ON';
                if(pill) {
                    if(isCurrentlyOn) {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    } else {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    }
                }
                const res = await fetch('/api/toggle_regime', { method: 'POST' });
                if(res.ok) fetchStatus();
            } catch(e) {
                console.error('Toggle fail', e);
            }
        }

        async function toggleSmartHedging() {
            const pill = document.getElementById('hedge-pill');
            try {
                // Optimistic UI update
                const isCurrentlyOn = pill && pill.textContent.trim() === 'ON';
                if(pill) {
                    if(isCurrentlyOn) {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    } else {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    }
                }
                const res = await fetch('/api/toggle_hedge', { method: 'POST' });
                if(res.ok) fetchStatus();
            } catch(e) { console.error('Toggle fail', e); }
        }

        // Poll every 2 seconds
        setInterval(fetchStatus, 4000);
        fetchStatus();

// Poll Live Mode
setInterval(() => {
    if (document.getElementById('tab-livemode').classList.contains('active')) {
        fetchLiveStatus();
    }
}, 4000);
setInterval(() => {
    if (document.getElementById('tab-livemode').classList.contains('active')) {
        fetchLivePnl();
    }
}, 3000);
setTimeout(() => { fetchLiveStatus(); fetchLivePnl(); }, 500);

// ================== LIVE MODE JS ==================

// ================== LIVE HANDLERS ==================

async function liveSendCommand(action) {
    try {
        const res = await fetch('/api/live/' + action, { method: 'POST' });
        if (res.ok) {
            fetchLiveStatus();
        } else {
            const errData = await res.json();
            alert('Command failed: ' + (errData.error || 'Unknown error'));
        }
    } catch (e) {
        console.error(action + ' fail', e);
    }
}

async function runLiveManualOrder() {
    console.log("Dashboard: runLiveManualOrder() triggered");
    const btn = document.getElementById('btn-manual-order');
    if (btn) btn.disabled = true;
    
    if (!confirm("Are you sure you want to FORCE trigger the LIVE strangle entry cycle immediately?")) {
        if (btn) btn.disabled = false;
        return;
    }
    
    try {
        const response = await fetch('/api/live/manual_order', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'success') {
            alert("Success!\n" + (result.message || "Manual strangle entry cycle triggered successfully!"));
        } else {
            alert("Failed:
" + (result.error || result.message || "Unknown error"));
        }
    } catch (error) {
        console.error("Dashboard: Manual order fetch error:", error);
        alert("Network Error: " + error.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function liveEmergencyClose() {
    if (confirm("ARE YOU SURE YOU WANT TO EMERGENCY CLOSE ALL LIVE POSITIONS?")) {
        try {
            const res = await fetch('/api/live/emergency_close', { method: 'POST' });
            if(res.ok) {
                alert("Emergency Square Off Successful! All live positions closed.");
                fetchLiveStatus();
            } else {
                const errData = await res.json();
                alert("Failed to emergency close: " + (errData.error || "Unknown error"));
            }
        } catch(e) { 
            console.error("Emergency fail", e); 
            alert("Network error: Could not reach server for emergency close.");
        }
    }
}

async function liveToggleRegimeFilter() {
    try {
        const res = await fetch('/api/live/toggle_regime', { method: 'POST' });
        if(res.ok) fetchLiveStatus();
    } catch(e) { console.error('Toggle fail', e); }
}

async function liveToggleSmartHedging() {
    try {
        const res = await fetch('/api/live/toggle_hedge', { method: 'POST' });
        if(res.ok) fetchLiveStatus();
    } catch(e) { console.error('Toggle fail', e); }
}

async function runLiveTestOrder() {
    alert("Test orders are not supported in LIVE mode.");
}

async function saveLiveLotSize() {
    const input = document.getElementById('live-manual-lot-size');
    if(!input) return;
    const val = parseFloat(input.value);
    if(isNaN(val) || val <= 0) {
        alert("Invalid lot multiplier.");
        return;
    }
    try {
        const res = await fetch('/api/live/set_lot_multiplier', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ multiplier: val })
        });
        if(res.ok) {
            alert('Live manual lot size updated to ' + val);
            fetchLiveStatus();
        } else {
            const data = await res.json();
            alert('Failed: ' + (data.error || 'Unknown error'));
        }
    } catch(e) { console.error(e); }
}


        let livePnlChart = null;
        function initLivePnlChart() {
            const canvas = document.getElementById('live-pnlChartCanvas');
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            const greenGrad = ctx.createLinearGradient(0, 0, 0, 260);
            greenGrad.addColorStop(0,   'rgba(16, 185, 129, 0.35)');
            greenGrad.addColorStop(1,   'rgba(16, 185, 129, 0.0)');
            const redGrad = ctx.createLinearGradient(0, 0, 0, 260);
            redGrad.addColorStop(0,   'rgba(239, 68, 68, 0.0)');
            redGrad.addColorStop(1,   'rgba(239, 68, 68, 0.35)');

            livePnlChart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'Options P&L ($)', data: [], borderColor: '#10b981', borderWidth: 2.5, pointRadius: 0, fill: true, backgroundColor: greenGrad, tension: 0.2 }, { label: 'Total P&L incl. Hedge', data: [], borderColor: '#3b82f6', borderDash: [5, 5], borderWidth: 1.5, pointRadius: 0, fill: false, tension: 0.2 }] },
                options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: false }, tooltip: { backgroundColor: '#1e293b', titleColor: '#f8fafc', bodyColor: '#e2e8f0', borderColor: '#334155', borderWidth: 1, callbacks: { label: ctx => ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2) } } }, scales: { x: { display: false }, y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } } } }
            });
        }

        async function fetchLivePnl() {
            try {
                const res = await fetch('/api/live/pnl_chart');
                if (!res.ok) return;
                const data = await res.json();
                
                const card = document.getElementById('live-pnl-chart-card');
                if (!card) return;

                if (!data.active || data.points.length === 0) {
                    card.style.display = 'none';
                    return;
                }
                card.style.display = 'block';

                if (!livePnlChart) initLivePnlChart();

                const pts = data.points;
                livePnlChart.data.labels = pts.map(p => p.t);
                livePnlChart.data.datasets[0].data = pts.map(p => p.pnl);
                livePnlChart.data.datasets[1].data = pts.map(p => p.total);
                livePnlChart.update('none');

                const peak = Math.max(...pts.map(p => p.pnl));
                const trough = Math.min(...pts.map(p => p.pnl));
                
                const peaks = document.querySelectorAll('#live-pnl-chart-peak');
                if (peaks.length > 0) peaks[0].textContent = (peak >= 0 ? '+' : '') + '$' + peak.toFixed(4);
                
                const troughs = document.querySelectorAll('#live-pnl-chart-trough');
                if (troughs.length > 0) troughs[0].textContent = (trough >= 0 ? '+' : '') + '$' + trough.toFixed(4);
                
                const counts = document.querySelectorAll('#live-pnl-chart-count');
                if (counts.length > 0) counts[0].textContent = pts.length + ' min';
            } catch (e) {
                console.error('fetchLivePnl fail', e);
            }
        }

        async function fetchLiveStatus() {
            try {
                const res = await fetch('/api/live/status');
                const data = await res.json();


                // Update Badge
                const badge = document.getElementById('status-badge');
                if(data.is_running) {
                    badge.textContent = `🟢 ENGINE RUNNING`;
                    badge.className = 'status-badge';
                } else {
                    badge.textContent = `🔴 ENGINE STOPPED`;
                    badge.className = 'status-badge offline';
                }

                // Update Stats
                document.getElementById('live-equity-val').textContent = `$${data.equity.toLocaleString()}`;
                document.getElementById('live-mode-val').textContent = data.mode;
                document.getElementById('live-loss-hits-val').textContent = `${data.daily_loss_hits} / 2`;

                // Update IV Status Card
                if (data.current_iv !== undefined) {
                    document.getElementById('current-iv-val').textContent = `${data.current_iv.toFixed(2)}%`;
                    document.getElementById('avg-iv-val').textContent = `${data.avg_7d_iv.toFixed(2)}%`;
                    
                    const ivBadge = document.getElementById('iv-status-badge');
                    if (data.iv_status === 'Normal') {
                        ivBadge.textContent = '🟢 Normal';
                        ivBadge.style.color = 'var(--success)';
                        ivBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                        ivBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                    } else if (data.iv_status === 'Bypassed' || data.iv_status === 'Disabled') {
                        ivBadge.textContent = '🟢 Bypassed (Testing)';
                        ivBadge.style.color = 'var(--success)';
                        ivBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                        ivBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                    } else {
                        ivBadge.textContent = '🔴 Low';
                        ivBadge.style.color = 'var(--danger)';
                        ivBadge.style.background = 'rgba(239, 68, 68, 0.1)';
                        ivBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                    }
                }

                // Update PAPER Mode enhancements
                const paperNote = document.getElementById('paper-mode-note');
                if (paperNote) {
                    paperNote.style.display = data.mode === 'PAPER' ? 'block' : 'none';
                }
                const lotMultVal = document.getElementById('live-lot-multiplier-val');
                if (lotMultVal) {
                    lotMultVal.textContent = `${(data.size_multiplier * 100).toFixed(0)}% of base (${data.size_multiplier.toFixed(2)}x)`;
                }
                const apiStatusBadge = document.getElementById('live-api-status-badge');
                if (apiStatusBadge) {
                    if (data.api_connected) {
                        apiStatusBadge.textContent = '🟢 Connected';
                        apiStatusBadge.style.color = 'var(--success)';
                    } else {
                        apiStatusBadge.textContent = '🔴 Disconnected';
                        apiStatusBadge.style.color = 'var(--danger)';
                    }
                }

                // Update Advanced Rules and Dynamic Sizing stats
                document.getElementById('live-consecutive-losses-val').textContent = data.consecutive_loss_count || 0;
                const cooldownEl = document.getElementById('live-sizing-cooldown-val');
                if (data.reduced_size_trades_remaining > 0) {
                    cooldownEl.textContent = `${data.reduced_size_trades_remaining} trades remaining (-20%)`;
                    cooldownEl.style.color = 'var(--warning)';
                } else if (data.size_multiplier < 0.99 && data.size_multiplier > 0.69) {
                    cooldownEl.textContent = 'Daily Loss Cooldown (-30%)';
                    cooldownEl.style.color = 'var(--warning)';
                } else {
                    cooldownEl.textContent = 'No Cooldown';
                    cooldownEl.style.color = 'var(--text-secondary)';
                }
                const pauseContainer = document.getElementById('live-next-day-paused-container');
                if (pauseContainer) {
                    pauseContainer.style.display = data.next_day_paused ? 'block' : 'none';
                }

                // Update IV & DVOL Panel
                if (data.dvol_status) {
                    document.getElementById('dvol-val').textContent = `${data.dvol_status.current_dvol.toFixed(2)}%`;
                    document.getElementById('dvol-percentile-val').textContent = `${data.dvol_status.dvol_percentile.toFixed(1)}%`;
                    document.getElementById('dvol-percentile-bar').style.width = `${data.dvol_status.dvol_percentile}%`;
                    
                    if (data.dvol_status.premium_range) {
                        document.getElementById('premium-range-val').textContent = `$${data.dvol_status.premium_range[0]} - $${data.dvol_status.premium_range[1]}`;
                    }
                    
                    const dvolBadge = document.getElementById('dvol-can-trade-badge');
                    if (dvolBadge) {
                        if (data.dvol_status.is_bypassed) {
                            dvolBadge.textContent = '🟢 Bypassed (Testing)';
                            dvolBadge.style.color = 'var(--success)';
                            dvolBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else if (data.dvol_status.eligible_to_trade) {
                            dvolBadge.textContent = '🟢 Safe to Trade';
                            dvolBadge.style.color = 'var(--success)';
                            dvolBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else {
                            dvolBadge.textContent = '🔴 Skip (DVOL Extreme)';
                            dvolBadge.style.color = 'var(--danger)';
                            dvolBadge.style.background = 'rgba(239, 68, 68, 0.1)';
                            dvolBadge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                        }
                    }
                }

                // Update Smart Hedging Panel
                if (data.hedge_status) {
                    const hBadge = document.getElementById('hedge-active-badge');
                    if (hBadge) {
                        if (data.hedge_status.hedge_active) {
                            hBadge.textContent = '🛡️ ACTIVE';
                            hBadge.style.color = 'var(--success)';
                            hBadge.style.background = 'rgba(16, 185, 129, 0.1)';
                            hBadge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        } else {
                            hBadge.textContent = '⚪ INACTIVE';
                            hBadge.style.color = 'var(--text-secondary)';
                            hBadge.style.background = 'rgba(255, 255, 255, 0.05)';
                            hBadge.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                        }
                    }
                    
                    document.getElementById('hedge-type-val').textContent = (data.hedge_status.hedge_type || 'none').toUpperCase();
                    document.getElementById('hedge-size-val').textContent = `${(data.hedge_status.hedge_size_btc || 0).toFixed(6)} BTC`;
                    
                    const hedgePnl = data.hedge_status.hedge_pnl_usd || 0;
                    const pnlSpan = document.getElementById('hedge-pnl-val');
                    pnlSpan.textContent = `${hedgePnl >= 0 ? '+' : ''}$${hedgePnl.toFixed(2)}`;
                    pnlSpan.style.color = hedgePnl > 0 ? 'var(--success)' : (hedgePnl < 0 ? 'var(--danger)' : 'var(--text-secondary)');
                    
                    document.getElementById('hedge-percentage-val').textContent = `${(data.hedge_status.hedge_percentage || 0).toFixed(0)}%`;
                    document.getElementById('hedge-percentage-bar').style.width = `${data.hedge_status.hedge_percentage || 0}%`;
                    
                    const slTight = document.getElementById('sl-tightened-badge');
                    if (slTight) {
                        slTight.style.display = data.hedge_status.sl_tightened ? 'block' : 'none';
                    }
                }

                // Show/Hide Test Order button based on mode
                const testBtn = document.getElementById('btn-test-order');
                if (testBtn) {
                    testBtn.style.display = data.mode === 'PAPER' ? 'block' : 'none';
                }
                
                // Update Badge and Toggle
                const regimeBadge = document.getElementById('regime-badge');
                if(data.current_market_regime !== undefined) {
                    let rColor = data.current_market_regime === 'Trending' ? 'var(--danger)' : 'var(--success)';
                    let rIcon = data.current_market_regime === 'Trending' ? '🔴' : '🟢';
                    if (data.current_market_regime === 'Unknown') { rColor = 'var(--text-secondary)'; rIcon = '⚪'; }
                    regimeBadge.innerHTML = `${rIcon} ${data.current_market_regime} (ADX: ${data.current_adx_value.toFixed(1)})`;
                    regimeBadge.style.color = rColor;
                }
                
                // Update Market Regime Detector UI
                if (data.current_market_regime) {
                    const regime = data.current_market_regime.toUpperCase();
                    const adx = data.current_adx_value || 0;
                    
                    const mainLabel = document.getElementById('regime-main-label');
                    const recLabel = document.getElementById('regime-recommendation');
                    if (mainLabel && recLabel) {
                        mainLabel.textContent = regime;
                        if (regime === 'TRENDING') {
                            mainLabel.style.color = 'var(--rose)';
                            mainLabel.style.background = 'rgba(244, 63, 94, 0.1)';
                            mainLabel.style.boxShadow = '0 0 20px rgba(244, 63, 94, 0.2)';
                            recLabel.textContent = '⚠️ Caution - Trending Market';
                        } else if (regime === 'SIDEWAYS' || regime === 'RANGING') {
                            mainLabel.style.color = 'var(--emerald)';
                            mainLabel.style.background = 'rgba(16, 185, 129, 0.1)';
                            mainLabel.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.2)';
                            recLabel.textContent = '✅ Best for Short Strangle';
                        } else {
                            mainLabel.style.color = 'var(--text-secondary)';
                            mainLabel.style.background = 'rgba(255, 255, 255, 0.05)';
                            mainLabel.style.boxShadow = 'none';
                            recLabel.textContent = 'Waiting for stable data...';
                        }
                    }

                    const gaugePath = document.getElementById('adx-gauge-path');
                    const gaugeVal = document.getElementById('adx-gauge-val');
                    if (gaugePath && gaugeVal) {
                        gaugeVal.textContent = adx.toFixed(1);
                        const maxAdx = 60;
                        const percentage = Math.min(Math.max(adx / maxAdx, 0), 1);
                        const offset = 125 - (percentage * 125);
                        gaugePath.style.strokeDashoffset = offset;
                        
                        let strokeColor = 'var(--emerald)';
                        if (adx > 25) strokeColor = 'var(--rose)';
                        else if (adx >= 22) strokeColor = 'var(--warning)';
                        gaugePath.style.stroke = strokeColor;
                    }

                    const history = data.adx_history || [];
                    const sparkline = document.getElementById('adx-sparkline');
                    const trendDirection = document.getElementById('adx-trend-direction');
                    if (sparkline && history.length >= 2) {
                        const min = Math.min(...history) - 2;
                        const max = Math.max(...history) + 2;
                        const range = max - min === 0 ? 1 : max - min;
                        
                        let pathD = '';
                        history.forEach((val, i) => {
                            const x = (i / (history.length - 1)) * 100;
                            const y = 40 - (((val - min) / range) * 40);
                            if (i === 0) pathD += `M ${x} ${y} `;
                            else pathD += `L ${x} ${y} `;
                        });
                        sparkline.innerHTML = `<path d="${pathD}"></path>`;
                        
                        const curr = history[history.length - 1];
                        const prev = history[history.length - 2];
                        if (curr > prev) {
                            trendDirection.innerHTML = '📈 RISING';
                            trendDirection.style.color = 'var(--rose)';
                            sparkline.style.stroke = 'var(--rose)';
                        } else if (curr < prev) {
                            trendDirection.innerHTML = '📉 FALLING';
                            trendDirection.style.color = 'var(--emerald)';
                            sparkline.style.stroke = 'var(--emerald)';
                        } else {
                            trendDirection.innerHTML = 'FLAT';
                            trendDirection.style.color = 'var(--text-secondary)';
                            sparkline.style.stroke = 'var(--text-secondary)';
                        }
                    }
                }
                
                // Sync pill button state
                const pill = document.getElementById('regime-pill');
                if(pill && data.regime_filter_enabled !== undefined) {
                    if(data.regime_filter_enabled) {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    } else {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    }
                }

                const hedgePill = document.getElementById('hedge-pill');
                if(hedgePill && data.smart_hedging_enabled !== undefined) {
                    if(data.smart_hedging_enabled) {
                        hedgePill.textContent = 'ON';
                        hedgePill.style.background = 'var(--success)';
                        hedgePill.style.borderColor = 'var(--success)';
                        hedgePill.style.color = '#fff';
                        hedgePill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    } else {
                        hedgePill.textContent = 'OFF';
                        hedgePill.style.background = '#334155';
                        hedgePill.style.borderColor = '#334155';
                        hedgePill.style.color = '#94a3b8';
                        hedgePill.style.boxShadow = 'none';
                    }
                }


                // ── Update Active Positions ──────────────────────────────────────────
                const posCards  = document.getElementById('positions-cards');
                const totalBar  = document.getElementById('pos-total-bar');
                const posContainer = document.getElementById('active-positions-container');
                
                if (data.positions && data.positions.length > 0) {
                    if (posContainer) posContainer.classList.add('active-trade-glow');
                    totalBar.style.display = 'flex';
                    
                    // ── Apply EMA smoothing to prevent wild jumps on tab switch / refresh ──
                    // Formula: PnL = (Entry_Premium - Current_Premium) * Lots * 0.001 BTC
                    const rawTotalPnlUsd = data.total_pnl_usd || 0;
                    const rawTotalPnlInr = data.total_pnl_inr || 0;
                    const { smoothedPositions, smoothedTotalPnlUsd, smoothedTotalPnlInr } =
                        applyPnlSmoothing(data.positions, rawTotalPnlUsd, rawTotalPnlInr);
                    const totalPnlUsd = smoothedTotalPnlUsd;
                    const totalPnlInr = smoothedTotalPnlInr;

                    // Update summary bar
                    const totalEntryPremium = data.total_entry_premium || 0;
                    document.getElementById('pos-total-entry').textContent = totalEntryPremium.toFixed(4);
                    
                    // Display Capital Used and reference BTC price
                    const totalCapitalUsed = data.total_capital_used || 0;
                    document.getElementById('pos-total-capital').textContent = totalCapitalUsed.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    document.getElementById('pos-btc-price').textContent = (data.btc_price || 70000).toLocaleString(undefined, {maximumFractionDigits: 0});
                    
                    // Recalculate percentages based on smoothed P&L and actual denominators
                    const totalPnlPctPrem = totalEntryPremium > 0 ? (totalPnlUsd / totalEntryPremium * 100) : 0.0;
                    const totalPnlPctCap = totalCapitalUsed > 0 ? (totalPnlUsd / totalCapitalUsed * 100) : 0.0;
                    
                    const pnlPctSignPrem = totalPnlPctPrem >= 0 ? '+' : '';
                    const pnlPctSignCap = totalPnlPctCap >= 0 ? '+' : '';
                    
                    const pnlUsdEl = document.getElementById('pos-total-pnl-usd');
                    pnlUsdEl.innerHTML = `<div style="display: flex; flex-direction: column; gap: 2px; padding-top: 4px;">
                        <span style="font-size: 1.6rem; font-weight: 800; line-height: 1;">${totalPnlUsd >= 0 ? '+' : ''}${totalPnlUsd.toFixed(4)} USDT</span>
                        <span style="font-size: 0.8rem; font-weight: 500; opacity: 0.8; letter-spacing: 0.2px; color: var(--text-secondary);">(${pnlPctSignPrem}${totalPnlPctPrem.toFixed(2)}% Prem &nbsp;|&nbsp; ${pnlPctSignCap}${totalPnlPctCap.toFixed(2)}% Cap)</span>
                    </div>`;
                    pnlUsdEl.className = totalPnlUsd >= 0 ? 'pnl-pos' : 'pnl-neg';
                    
                    const pnlInrEl = document.getElementById('pos-total-pnl-inr');
                    pnlInrEl.textContent = '₹' + (totalPnlInr >= 0 ? '+' : '') + totalPnlInr.toFixed(2);
                    pnlInrEl.className = totalPnlInr >= 0 ? 'pnl-pos' : 'pnl-neg';
                    
                    const mins = data.positions[0]?.mins_to_squareoff ?? 0;
                    const hh = Math.floor(mins / 60);
                    const mm = mins % 60;
                    document.getElementById('pos-time-remaining').textContent = mins > 0 ? `${hh}h ${mm}m` : 'Market Closed';

                    // Build one card per leg (using smoothed positions)
                    posCards.innerHTML = smoothedPositions.map(pos => {

                        const isCall = pos.leg_type === 'call';
                        const legLabel = isCall
                            ? '<span class="pos-call-label">📈 CALL</span>'
                            : '<span class="pos-put-label">📉 PUT</span>';
                        
                        const pnlClass  = pos.leg_pnl_usd >= 0 ? 'pnl-pos' : 'pnl-neg';
                        const pnlSign   = pos.leg_pnl_usd >= 0 ? '+' : '';
                        const pnlInrSign = pos.leg_pnl_inr >= 0 ? '+' : '';

                        let statusClass = 'status-running';
                        let statusIcon  = '🟢 Running';
                        if (pos.trade_status === 'Trailing SL Active') { statusClass = 'status-trailing'; statusIcon = '🔴 Trailing SL'; }
                        else if (pos.trade_status === 'Partial Profit Booked') { statusClass = 'status-partial'; statusIcon = '🟡 Partial Profit'; }

                        // Entry time formatting
                        let entryTimeDisplay = '—';
                        if (pos.entry_time) {
                            try {
                                const d = new Date(pos.entry_time);
                                entryTimeDisplay = d.toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit', hour12: true});
                            } catch(e) { entryTimeDisplay = pos.entry_time.slice(11, 16); }
                        }

                        const minsLeft = pos.mins_to_squareoff || 0;
                        const hh2 = Math.floor(minsLeft / 60), mm2 = minsLeft % 60;
                        const timeLeft = minsLeft > 0 ? `${hh2}h ${mm2}m` : '—';

                        // Premium change %
                        const premChangePct = pos.entry_price > 0
                            ? (((pos.current_price - pos.entry_price) / pos.entry_price) * 100).toFixed(1)
                            : '0.0';
                        const premChangeSign = parseFloat(premChangePct) >= 0 ? '+' : '';

                        // Calculate accurate leg capital used and smoothed leg P&L percentages
                        const legCapitalUsed = pos.leg_capital_used || 0;
                        const legEntryPremium = pos.leg_entry_premium_total || 0;
                        
                        const legPnlPctPremium = legEntryPremium > 0 ? (pos.leg_pnl_usd / legEntryPremium * 100) : 0.0;
                        const legPnlPctCapital = legCapitalUsed > 0 ? (pos.leg_pnl_usd / legCapitalUsed * 100) : 0.0;
                        
                        const legPnlPctPremiumStr = (legPnlPctPremium >= 0 ? '+' : '') + legPnlPctPremium.toFixed(2);
                        const legPnlPctCapitalStr = (legPnlPctCapital >= 0 ? '+' : '') + legPnlPctCapital.toFixed(2);

                        return `
                        <div class="pos-card">
                            <div class="pos-card-header">
                                <div>
                                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                                        ${legLabel}
                                        <span style="font-size:0.7rem;color:var(--text-secondary);background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">${pos.side}</span>
                                    </div>
                                    <div class="pos-symbol">${pos.symbol}</div>
                                    ${pos.strike ? `<div class="pos-strike-label">Strike: $${parseFloat(pos.strike).toLocaleString()}</div>` : ''}
                                </div>
                                <div class="pos-status-badge ${statusClass}">${statusIcon}</div>
                            </div>

                            <div class="pos-metrics">
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Entry Premium</div>
                                    <div class="pos-metric-value">${pos.entry_price.toFixed(2)}</div>
                                    <div class="pos-metric-sub">USDT / lot</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Current Premium</div>
                                    <div class="pos-metric-value" style="color:${parseFloat(premChangePct)<0?'#34d399':'#f87171'}">${pos.current_price.toFixed(2)}</div>
                                    <div class="pos-metric-sub">${premChangeSign}${premChangePct}% from entry</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Leg P&amp;L</div>
                                    <div style="display: flex; flex-direction: column; gap: 2px; margin-top: 2px;">
                                        <div class="pos-metric-value ${pnlClass}" style="line-height: 1;">${pnlSign}${pos.leg_pnl_usd.toFixed(2)} USD</div>
                                        <div style="font-size: 0.75rem; font-weight: 500; opacity: 0.8; color: var(--text-secondary);">(${legPnlPctPremiumStr}% Prem | ${legPnlPctCapitalStr}% Cap)</div>
                                        <div class="pos-metric-sub ${pnlClass}" style="margin-top: 0;">${pnlInrSign}₹${pos.leg_pnl_inr.toFixed(0)}</div>
                                    </div>
                                </div>
                                <div class="pos-metric" style="background: rgba(16,185,129,0.04); border: 1px solid rgba(16,185,129,0.08);">
                                    <div class="pos-metric-label" style="color: #34d399;">Capital Used</div>
                                    <div class="pos-metric-value" style="color: #34d399; font-weight: 800;">$${legCapitalUsed.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
                                    <div class="pos-metric-sub">at $${(data.btc_price || 70000).toLocaleString(undefined, {maximumFractionDigits: 0})} BTC</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Lot Size</div>
                                    <div class="pos-metric-value">${pos.size}</div>
                                    <div class="pos-metric-sub">contracts</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Delta / Gamma</div>
                                    <div class="pos-metric-value">${pos.delta.toFixed(3)}</div>
                                    <div class="pos-metric-sub">γ ${pos.gamma.toFixed(4)}</div>
                                </div>
                                <div class="pos-metric">
                                    <div class="pos-metric-label">Live IV</div>
                                    <div class="pos-metric-value">${pos.current_iv_pct.toFixed(2)}%</div>
                                    <div class="pos-metric-sub">Implied Volatility</div>
                                </div>
                            </div>

                            <div class="pos-divider"></div>
                            <div class="pos-footer">
                                <div class="pos-footer-chip">🕐 Entry: <strong>${entryTimeDisplay} IST</strong></div>
                                <div class="pos-footer-chip">⏱ SqOff in: <strong>${timeLeft}</strong></div>
                            </div>
                        </div>`;
                    }).join('');

                } else {
                    totalBar.style.display = 'none';
                    posCards.innerHTML = `
                        <div class="pos-empty">
                            <div class="pos-empty-icon">📭</div>
                            <div style="font-weight:600;color:var(--text-secondary);">No Active Positions</div>
                            <div style="font-size:0.8rem;margin-top:6px;opacity:0.6;">The bot has no open trades right now.</div>
                        </div>`;
                    if (posContainer) posContainer.classList.remove('active-trade-glow');
                }

                // Update Rule Compliance
                if(data.rule_report && data.rule_report.results) {
                    // Check if today was skipped and map to rules
                    const skipReason = data.today_skip_reason || "";
                    let failedRuleName = null;
                    
                    if (skipReason) {
                        const reasonLower = skipReason.toLowerCase();
                        if (reasonLower.includes("loss limit") || reasonLower.includes("sls") || reasonLower.includes("max loss")) {
                            failedRuleName = "Daily Loss Limit";
                        } else if (reasonLower.includes("strike") || reasonLower.includes("premium") || reasonLower.includes("net delta")) {
                            failedRuleName = "Strike Selection";
                        } else if (reasonLower.includes("capital") || reasonLower.includes("lot size") || reasonLower.includes("insufficient") || reasonLower.includes("consecutive losses")) {
                            failedRuleName = "Lot Size";
                        } else if (reasonLower.includes("exit")) {
                            failedRuleName = "Exit Time";
                        } else if (reasonLower.includes("hedge")) {
                            failedRuleName = "Hedging";
                        }
                    }

                    const badge = document.getElementById('compliance-badge');
                    if (failedRuleName) {
                        const failedCount = data.rule_report.results.filter(r => r.name === failedRuleName || !r.passed).length;
                        const compliancePct = Math.round(((data.rule_report.results.length - failedCount) / data.rule_report.results.length) * 100);
                        badge.textContent = `${compliancePct}% Compliant`;
                        badge.style.color = 'var(--danger)';
                        badge.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                        badge.style.background = 'rgba(239, 68, 68, 0.1)';
                    } else {
                        badge.textContent = `100% Compliant`;
                        badge.style.color = 'var(--success)';
                        badge.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        badge.style.background = 'rgba(16, 185, 129, 0.1)';
                    }

                    const rulesGrid = document.getElementById('rules-grid');
                    rulesGrid.innerHTML = data.rule_report.results.map(r => {
                        const isFailed = (r.name === failedRuleName) || !r.passed;
                        const bg = isFailed ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.06)';
                        const border = isFailed ? '1px solid rgba(239, 68, 68, 0.25)' : '1px solid rgba(16, 185, 129, 0.18)';
                        const icon = isFailed ? '❌' : '✅';
                        
                        return `
                            <div style="background: ${bg}; padding: 12px; border-radius: 8px; border: ${border}; display: flex; align-items: center; gap: 10px; transition: all 0.3s ease;">
                                <div style="font-size: 1.2rem;">${icon}</div>
                                <div>
                                    <div style="font-weight: 600; font-size: 0.9rem; color: #fff;">${r.name}</div>
                                    <div style="font-size: 0.8rem; color: var(--text-secondary);">${r.expected}</div>
                                </div>
                            </div>
                        `;
                    }).join('');

                    // Today's Skip Reason Section update
                    const skipTitle = document.getElementById('skip-reason-title');
                    const skipText = document.getElementById('skip-reason-text');
                    
                    if (data.today_skip_reason) {
                        // We have an active skip today! Style in red.
                        skipTitle.innerHTML = "🚫 Today's Skip Reason";
                        skipText.textContent = data.today_skip_reason;
                        skipText.style.color = "#fca5a5";
                        skipText.style.background = "rgba(239, 68, 68, 0.08)";
                        skipText.style.borderColor = "rgba(239, 68, 68, 0.15)";
                    } else if (data.schedule_info && data.schedule_info.today_status === "Trade Taken") {
                        // Trade taken successfully! Style in green.
                        skipTitle.innerHTML = "✅ Today's Status";
                        skipText.textContent = "Trade taken successfully";
                        skipText.style.color = "#a7f3d0";
                        skipText.style.background = "rgba(16, 185, 129, 0.08)";
                        skipText.style.borderColor = "rgba(16, 185, 129, 0.18)";
                    } else {
                        // No active skips/trades yet today (system normal). Style in grey/secondary.
                        skipTitle.innerHTML = "ℹ️ Today's Status";
                        skipText.textContent = "None (System running normally)";
                        skipText.style.color = "var(--text-secondary)";
                        skipText.style.background = "rgba(255, 255, 255, 0.03)";
                        skipText.style.borderColor = "rgba(255, 255, 255, 0.08)";
                    }
                }

                
                // Update Skip & Schedule Info
                if(data.schedule_info) {
                    const statusBadge = document.getElementById('today-status-badge');
                    const status = data.schedule_info.today_status;
                    const reason = data.schedule_info.today_reason;
                    
                    if (status === "Trade Taken") {
                        statusBadge.textContent = "✅ " + status;
                        statusBadge.style.color = "var(--success)";
                        statusBadge.style.background = "rgba(16, 185, 129, 0.1)";
                        statusBadge.style.border = "1px solid rgba(16, 185, 129, 0.2)";
                    } else if (status === "Trade Skipped") {
                        statusBadge.textContent = "⏭️ " + status + (reason ? ` (${reason})` : "");
                        if (reason && (reason.includes("Weekend") || reason.includes("News"))) {
                            statusBadge.style.color = "var(--danger)";
                            statusBadge.style.background = "rgba(239, 68, 68, 0.1)";
                            statusBadge.style.border = "1px solid rgba(239, 68, 68, 0.2)";
                        } else {
                            statusBadge.style.color = "var(--warning)";
                            statusBadge.style.background = "rgba(245, 158, 11, 0.1)";
                            statusBadge.style.border = "1px solid rgba(245, 158, 11, 0.2)";
                        }
                    } else {
                        statusBadge.textContent = "⏳ " + status;
                        statusBadge.style.color = "var(--text-secondary)";
                        statusBadge.style.background = "rgba(255, 255, 255, 0.05)";
                        statusBadge.style.border = "1px solid rgba(255, 255, 255, 0.1)";
                    }

                    // ── TRADE SKIP ALERT CARD ──────────────────────────────────────
                    (function() {
                        const skipAlertCard = document.getElementById('trade-skip-alert-card');
                        if (!skipAlertCard) return;
                        const skipReasonEl = document.getElementById('skip-reason-text');
                        const skipHintEl   = document.getElementById('skip-hint-text');
                        const skipTsEl     = document.getElementById('skip-timestamp');
                        const skipHistEl   = document.getElementById('skip-history-list');
                        const skipHistSec  = document.getElementById('skip-history-section');

                        if (status === 'Trade Skipped' && reason) {
                            skipAlertCard.style.display = 'block';
                            skipAlertCard.style.animation = 'slide-down-in 0.4s ease';
                            skipReasonEl.textContent = reason;

                            const hist = data.schedule_info.skip_history || [];
                            skipTsEl.textContent = hist.length > 0 ? hist[0].time : '';

                            const hintMap = [
                                ['Maximum 1 trade',     'Next entry window will be tomorrow at 09:00 AM IST.'],
                                ['Next day pause',      'Trading resumes once the daily P&L is above -2.5%.'],
                                ['consecutive losses',  'Bot will resume trading after tonight\'s daily reset.'],
                                ['API connection',      'Check your internet connection and API key in the Config tab.'],
                                ['Daily Loss Limit',    'The -3% daily loss limit was hit. Trading resumes tomorrow.'],
                                ['No suitable strikes', 'DVOL premium targets not matched. Strikes retry at next slot.'],
                                ['risk per trade',      'Position size too large for equity. Reduce lot size in Config.'],
                                ['Trending',            'ADX > 25 means trending market. Bot waits for sideways.'],
                                ['DVOL',                'Volatility index out of safe range. Waiting for DVOL to normalize.'],
                                ['Weekend',             'Markets closed. Trading resumes Monday 09:00 AM IST.'],
                            ];
                            let hint = 'Trade skipped by risk management. Next slot will be checked automatically.';
                            for (const [key, val] of hintMap) {
                                if (reason.includes(key)) { hint = val; break; }
                            }
                            skipHintEl.textContent = hint;

                            if (hist.length > 0) {
                                skipHistEl.innerHTML = hist.map((e, i) => `
                                    <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                                        background:${i===0?'rgba(245,158,11,0.10)':'rgba(255,255,255,0.02)'};
                                        border:1px solid ${i===0?'rgba(245,158,11,0.22)':'rgba(255,255,255,0.05)'};
                                        border-radius:7px;font-size:0.78rem;">
                                        <span>${i===0?'🔴':'🟡'}</span>
                                        <span style="color:rgba(255,255,255,0.5);min-width:145px;flex-shrink:0;">${e.time}</span>
                                        <span style="color:${i===0?'#fbbf24':'rgba(255,255,255,0.6)'};font-weight:${i===0?700:400};">${e.reason}</span>
                                    </div>`).join('');
                                skipHistSec.style.display = 'block';
                            } else {
                                skipHistSec.style.display = 'none';
                            }
                        } else {
                            skipAlertCard.style.display = 'none';
                        }
                    })();
                    // ──────────────────────────────────────────────────────────────

                    const schedBody = document.getElementById('schedule-body');
                    let showWarning = false;
                    let warningText = "";
                    
                    if (data.schedule_info.upcoming_schedule && data.schedule_info.upcoming_schedule.length > 0) {
                        schedBody.innerHTML = '';
                        data.schedule_info.upcoming_schedule.forEach((day, index) => {
                            if ((index === 1 || index === 2) && day.skip && !showWarning) {
                                showWarning = true;
                                warningText = `⚠️ EARLY WARNING: Trading will be skipped on ${day.day} (${day.reason})`;
                            }
                            
                            let statusColor = day.skip ? (day.skip_type === 'severe' ? 'var(--danger)' : 'var(--warning)') : 'var(--success)';
                            let statusText = day.skip ? '⏭️ Skipped' : '✅ Scheduled';
                            
                            schedBody.innerHTML += `
                                <tr>
                                    <td style="font-weight: 600;">${day.date}</td>
                                    <td style="color: var(--text-secondary);">${day.day}</td>
                                    <td style="color: ${statusColor}; font-weight: 600;">${statusText}</td>
                                    <td style="color: var(--text-secondary);">${day.reason || '-'}</td>
                                </tr>
                            `;
                        });
                    }
                    
                    const warningBox = document.getElementById('early-warning-box');
                    if (showWarning) {
                        warningBox.style.display = 'flex';
                        warningBox.textContent = warningText;
                    } else {
                        warningBox.style.display = 'none';
                    }
                }

                // Update Logs
                const logTerm = document.getElementById('log-terminal');
                const isScrolledToBottom = logTerm.scrollHeight - logTerm.clientHeight <= logTerm.scrollTop + 10;
                
                logTerm.innerHTML = data.logs.map(line => {
                    let color = "#a7f3d0"; // default green-ish
                    if(line.includes("ERROR") || line.includes("CRITICAL")) color = "#fca5a5";
                    if(line.includes("WARNING")) color = "#fde047";
                    return `<div class="log-line" style="color: ${color};">${line}</div>`;
                }).join('');

                if (isScrolledToBottom) {
                    logTerm.scrollTop = logTerm.scrollHeight;
                }

            } catch (e) {
                console.error("Polling failed", e);
                const badge = document.getElementById('status-badge');
                badge.textContent = `🔴 OFFLINE`;
                badge.className = 'status-badge offline';
            }
        }

        async function runLiveTestOrder() {
            console.log("Dashboard: runLiveTestOrder() triggered");
            const btn = document.getElementById('btn-test-order');
            const originalText = btn.innerHTML;
            
            if (!confirm("Place a REAL 1-lot order for testing?\n\nIt will automatically close after 10 seconds.\n\nOnly works in PAPER mode.")) {
                console.log("Dashboard: Test order cancelled by user");
                return;
            }
            
            try {
                console.log("Dashboard: Sending POST to /api/live/test_order...");
                btn.disabled = true;
                btn.innerHTML = "⌛ PLACING TEST ORDER...";
                
                const response = await fetch('/api/live/test_order', { method: 'POST' });
                
                // Always read as text first to diagnose non-JSON responses
                const raw = await response.text();
                console.log("Dashboard: Raw response:", raw);
                
                let result;
                try {
                    result = JSON.parse(raw);
                } catch (parseErr) {
                    console.error("Dashboard: Response is not valid JSON:", raw);
                    alert("❌ Server Error: The server returned an unexpected response.\nCheck backend logs for details.\n\n" + raw.substring(0, 200));
                    return;
                }
                
                if (result.success === true) {
                    alert("✅ Test Order Success!\n\n" + result.message);
                } else {
                    alert("❌ Test Order Failed:\n\n" + (result.error || result.message || "Unknown error"));
                }
            } catch (error) {
                console.error("Dashboard: Test order fetch error:", error);
                alert("❌ Network Error: " + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        async function runLiveManualOrder() {
            console.log("Dashboard: runLiveManualOrder() triggered");
            const btn = document.getElementById('btn-manual-order');
            const originalText = btn.innerHTML;
            
            if (!confirm("Are you sure you want to FORCE trigger the strangle entry cycle immediately?\n\nThis will look up strikes and execute a trade in the current mode (LIVE or PAPER).")) {
                console.log("Dashboard: Manual order cancelled by user");
                return;
            }
            
            try {
                console.log("Dashboard: Sending POST to /api/live/manual_order...");
                btn.disabled = true;
                btn.innerHTML = "⌛ TRIGGERING STRANGLE ENTRY...";
                
                const response = await fetch('/api/live/manual_order', { method: 'POST' });
                const raw = await response.text();
                console.log("Dashboard: Raw response:", raw);
                
                let result;
                try {
                    result = JSON.parse(raw);
                } catch (parseErr) {
                    console.error("Dashboard: Response is not valid JSON:", raw);
                    alert("❌ Server Error: The server returned an unexpected response.\n\n" + raw.substring(0, 200));
                    return;
                }
                
                if (result.status === 'success') {
                    alert("✅ Success!\n\n" + (result.message || "Manual strangle entry cycle triggered successfully!"));
                } else {
                    alert("❌ Failed:\n\n" + (result.error || result.message || "Unknown error"));
                }
            } catch (error) {
                console.error("Dashboard: Manual order fetch error:", error);
                alert("❌ Network Error: " + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }

        async function liveEmergencyClose() {
            if (confirm("⚠️ ARE YOU SURE YOU WANT TO EMERGENCY CLOSE ALL POSITIONS? ⚠️\n\nThis will execute MARKET orders to square off your ENTIRE portfolio immediately.\n\nThis action CANNOT be undone.")) {
                try {
                    const btn = document.querySelector('.btn-emergency-pulse');
                    if (btn) {
                        btn.innerHTML = '⏳ Closing...';
                        btn.disabled = true;
                    }
                    const res = await fetch('/api/live/emergency_close', { method: 'POST' });
                    if(res.ok) {
                        if (btn) {
                            btn.innerHTML = '✅ All Closed';
                            setTimeout(() => { 
                                btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF'; 
                                btn.disabled = false; 
                            }, 3000);
                        }
                        alert("Emergency Square Off Successful! All positions closed.");
                        fetchLiveStatus();
                    } else {
                        const errData = await res.json();
                        alert("Failed to emergency close: " + (errData.error || "Unknown error"));
                        if (btn) {
                            btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF';
                            btn.disabled = false;
                        }
                    }
                } catch(e) { 
                    console.error("Emergency fail", e); 
                    alert("Network error: Could not reach server for emergency close.");
                    const btn = document.querySelector('.btn-emergency-pulse');
                    if (btn) {
                        btn.innerHTML = '<span style="font-size:1.2rem;">🚨</span> EMERGENCY SQUARE OFF';
                        btn.disabled = false;
                    }
                }
            }
        }

        async function liveToggleRegimeFilter() {
            const pill = document.getElementById('regime-pill');
            try {
                // Optimistic UI update before server confirms
                const isCurrentlyOn = pill && pill.textContent.trim() === 'ON';
                if(pill) {
                    if(isCurrentlyOn) {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    } else {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    }
                }
                const res = await fetch('/api/live/toggle_regime', { method: 'POST' });
                if(res.ok) fetchLiveStatus();
            } catch(e) {
                console.error('Toggle fail', e);
            }
        }

        async function liveToggleSmartHedging() {
            const pill = document.getElementById('hedge-pill');
            try {
                // Optimistic UI update
                const isCurrentlyOn = pill && pill.textContent.trim() === 'ON';
                if(pill) {
                    if(isCurrentlyOn) {
                        pill.textContent = 'OFF';
                        pill.style.background = '#334155';
                        pill.style.borderColor = '#334155';
                        pill.style.color = '#94a3b8';
                        pill.style.boxShadow = 'none';
                    } else {
                        pill.textContent = 'ON';
                        pill.style.background = 'var(--success)';
                        pill.style.borderColor = 'var(--success)';
                        pill.style.color = '#fff';
                        pill.style.boxShadow = '0 0 10px rgba(16,185,129,0.4)';
                    }
                }
                const res = await fetch('/api/live/toggle_hedge', { method: 'POST' });
                if(res.ok) fetchLiveStatus();
            } catch(e) { console.error('Toggle fail', e); }
        }

        // Poll every 2 seconds
        setInterval(fetchLiveStatus, 4000);
        fetchLiveStatus();

        // ════════════════════════════════════════════════════
        // LIVE P&L CHART — Chart.js with green/red zone fill
        // ════════════════════════════════════════════════════
        let pnlChart = null;

        function initPnlChart() {
            const ctx = document.getElementById('pnlChartCanvas').getContext('2d');

            // Green gradient above 0
            const greenGrad = ctx.createLinearGradient(0, 0, 0, 260);
            greenGrad.addColorStop(0,   'rgba(16, 185, 129, 0.35)');
            greenGrad.addColorStop(0.5, 'rgba(16, 185, 129, 0.10)');
            greenGrad.addColorStop(1,   'rgba(16, 185, 129, 0.0)');

            // Red gradient below 0
            const redGrad = ctx.createLinearGradient(0, 0, 0, 260);
            redGrad.addColorStop(0,   'rgba(239, 68, 68, 0.0)');
            redGrad.addColorStop(0.5, 'rgba(239, 68, 68, 0.10)');
            redGrad.addColorStop(1,   'rgba(239, 68, 68, 0.35)');

            pnlChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Options P&L ($)',
                            data: [],
                            borderColor: '#10b981',
                            borderWidth: 2.5,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.35,
                            fill: {
                                target: { value: 0 },
                                above: greenGrad,
                                below: redGrad
                            }
                        },
                        {
                            label: 'Total P&L incl. Hedge ($)',
                            data: [],
                            borderColor: '#38bdf8',
                            borderWidth: 1.5,
                            borderDash: [5, 3],
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.35,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 0 },
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(15, 23, 42, 0.95)',
                            borderColor: 'rgba(255,255,255,0.1)',
                            borderWidth: 1,
                            titleColor: 'rgba(255,255,255,0.6)',
                            bodyColor: '#fff',
                            padding: 12,
                            callbacks: {
                                label: ctx => {
                                    const val = ctx.raw;
                                    const sign = val >= 0 ? '+' : '';
                                    const color = val >= 0 ? '🟢' : '🔴';
                                    return `${color} ${ctx.dataset.label}: ${sign}$${val.toFixed(4)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: {
                                color: 'rgba(255,255,255,0.3)',
                                font: { size: 10 },
                                maxTicksLimit: 8,
                                maxRotation: 0
                            }
                        },
                        y: {
                            grid: { 
                                color: ctx => ctx.tick.value === 0 ? 'rgba(255, 255, 255, 0.4)' : 'rgba(255,255,255,0.05)',
                                lineWidth: ctx => ctx.tick.value === 0 ? 2 : 1
                            },
                            suggestedMax: 1, // Ensure the axis goes at least slightly above 0
                            suggestedMin: -1, // Ensure the axis goes at least slightly below 0
                            ticks: {
                                color: 'rgba(255,255,255,0.4)',
                                font: { size: 10 },
                                callback: v => (v >= 0 ? '+' : '') + '$' + v.toFixed(2)
                            }
                        }
                    }
                }
            });
        }

        async function fetchPnlChart() {
            try {
                const res = await fetch('/api/pnl_chart');
                if (!res.ok) return;
                const data = await res.json();

                const card = document.getElementById('live-pnl-chart-card');

                if (!data.active || data.points.length === 0) {
                    card.style.display = 'none';
                    return;
                }

                card.style.display = 'block';

                if (!pnlChart) initPnlChart();

                const pts = data.points;
                const labels  = pts.map(p => p.t);
                const optPnl  = pts.map(p => p.pnl);
                const totPnl  = pts.map(p => p.total);

                pnlChart.data.labels = labels;
                pnlChart.data.datasets[0].data = optPnl;
                pnlChart.data.datasets[1].data = totPnl;
                pnlChart.update('none');

                // Update summary stats — use ALL data points for true peak/trough
                const peak   = Math.max(...optPnl);
                const trough = Math.min(...optPnl);
                document.getElementById('pnl-chart-peak').textContent   = (peak >= 0 ? '+' : '') + '$' + peak.toFixed(4);
                document.getElementById('pnl-chart-trough').textContent = (trough >= 0 ? '+' : '') + '$' + trough.toFixed(4);
                // Show trade duration in minutes instead of raw count
                document.getElementById('pnl-chart-count').textContent  = pts.length + ' min';
                // Always show trade start time on left, "Now" on right
                if (pts.length > 0) {
                    document.getElementById('pnl-chart-start-label').textContent = '▶ ' + pts[0].t;
                    document.getElementById('pnl-chart-end-label').textContent   = 'Now (' + pts[pts.length-1].t + ')';
                }
            } catch(e) {
                // Fail silently — chart just stays hidden
            }
        }

        // Poll chart every 3 seconds (slightly offset from status poll)
        setInterval(fetchPnlChart, 3000);
        fetchPnlChart();

        // --- News & Events ---
        async function fetchNews() {
            try {
                const res = await fetch('/api/news');
                if(!res.ok) return;
                const events = await res.json();

                const tbody = document.getElementById('news-body');
                const alertBadge = document.getElementById('news-alert-badge');
                
                if(!events || events.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: var(--text-secondary);">No high/medium impact USD events found this week.</td></tr>';
                    if(alertBadge) alertBadge.style.display = 'none';
                    return;
                }

                // Check if any HIGH impact event is within 48 hours
                const now = Date.now();
                const in48h = now + (48 * 60 * 60 * 1000);
                const urgentEvent = events.find(e => {
                    const t = new Date(e.date).getTime();
                    return e.impact === 'High' && t >= now && t <= in48h;
                });
                if(alertBadge) alertBadge.style.display = urgentEvent ? 'block' : 'none';

                // Render rows
                tbody.innerHTML = events.map(e => {
                    const isHigh = e.impact === 'High';
                    const impactColor = isHigh ? 'var(--danger)' : 'var(--warning)';
                    const impactBg   = isHigh ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)';
                    const rowHighlight = isHigh ? 'border-left: 3px solid var(--danger);' : '';
                    return `<tr style="${rowHighlight}">
                        <td style="font-weight:600; color: var(--text-primary);">${e.date}</td>
                        <td>${e.title}</td>
                        <td style="color: var(--text-secondary);">${e.country}</td>
                        <td><span style="background:${impactBg}; color:${impactColor}; padding: 3px 10px; border-radius: 12px; font-weight:700; font-size:0.8rem;">${e.impact}</span></td>
                        <td style="color: var(--text-secondary);">${e.previous || '-'}</td>
                        <td style="color: var(--text-secondary);">${e.forecast || '-'}</td>
                    </tr>`;
                }).join('');
            } catch(e) {
                console.error('News fetch failed', e);
            }
        }



        // --- Daily Reports ---
        async function fetchReports() {
            try {
                const res = await fetch('/api/reports');
                const reports = await res.json();
                const tbody = document.getElementById('reports-body');
                
                if (!reports || Object.keys(reports).length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary);">No reports available yet.</td></tr>';
                    return;
                }
                
                let html = '';
                for (const [date, data] of Object.entries(reports)) {
                    const pnl = data.summary.net_pnl_usd;
                    const pnlColor = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
                    html += `
                        <tr>
                            <td style="font-weight: 600;">${date}</td>
                            <td style="color: ${pnlColor}; font-weight: 800;">$${pnl.toFixed(2)}</td>
                            <td>${data.summary.total_trades} Trades (${data.summary.win_rate.toFixed(1)}% Win)</td>
                            <td style="display: flex; gap: 8px; justify-content: flex-end;">
                                <button onclick="window.open('${data.pdf_path}', '_blank')" style="padding: 4px 10px; font-size: 0.8rem; background: rgba(255,255,255,0.1); color: #fff; width: auto; flex: none; border-radius: 8px;">View</button>
                                <a href="${data.pdf_path}" download style="padding: 6px 12px; font-size: 0.8rem; background: rgba(16, 185, 129, 0.2); color: var(--success); border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block;">PDF</a>
                                <a href="${data.xlsx_path}" download style="padding: 6px 12px; font-size: 0.8rem; background: rgba(245, 158, 11, 0.2); color: var(--warning); border-radius: 8px; text-decoration: none; font-weight: 600; display: inline-block;">Excel</a>
                            </td>
                        </tr>
                    `;
                }
                tbody.innerHTML = html;
            } catch (e) {
                console.error('Fetch reports failed', e);
            }
        }

        async function generateReportNow(event) {
            const btn = event.target;
            const originalText = btn.textContent;
            btn.textContent = "Generating...";
            btn.disabled = true;
            try {
                const res = await fetch('/api/generate_report', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    alert('✅ ' + data.message);
                    fetchReports();
                } else {
                    alert('❌ Error: ' + (data.message || data.error));
                }
            } catch (e) {
                alert('❌ Network Error');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        }

        async function updateJournal() {
            try {
                const response = await fetch('/api/journal');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        const journalTerm = document.getElementById('journal-terminal');
                        // Simple helper to clean markdown symbols for a clean display
                        let formattedContent = data.content;
                        // Replace alerts markdown > [!NOTE] with clean visual icons
                        formattedContent = formattedContent
                            .replace(/> \[!NOTE\]\s*\n*>\s*\*\*Performance/g, '📓 [AI Quant Advisor Performance')
                            .replace(/## (.*)/g, '■ $1')
                            .replace(/### (.*)/g, '  • $1')
                            .replace(/\*\*(.*?)\*\*/g, '$1')
                            .replace(/`(.*?)`/g, '$1');
                        
                        journalTerm.textContent = formattedContent;
                    }
                }
            } catch (err) {
                console.error("Dashboard: Error fetching journal:", err);
            }
        }

        // Initialize
        fetchReports();
        fetchNews();
        setInterval(fetchNews, 6 * 60 * 60 * 1000);

        updateJournal();
        setInterval(updateJournal, 20000);

        // ── Manual Lot Size Settings ───────────────────────────────────────────
        async function loadLotSize() {
            try {
                const res = await fetch('/api/get_lot_size');
                const data = await res.json();
                document.getElementById('active-lot-display').textContent = data.total_lots + ' lots';
                document.getElementById('active-lot-perleg').textContent = data.per_leg + ' per leg';
                // Pre-fill the input with the current saved value
                document.getElementById('lotSizeInput').value = data.total_lots;
            } catch (e) {
                console.warn('loadLotSize failed:', e);
            }
        }

        async function saveLotSize() {
            const input = document.getElementById('lotSizeInput');
            const feedback = document.getElementById('lotSizeFeedback');
            const btn = document.getElementById('saveLotSizeBtn');
            const val = parseInt(input.value, 10);

            if (isNaN(val) || val < 1) {
                feedback.style.color = '#f87171';
                feedback.textContent = '⚠ Please enter a valid lot size (minimum 1).';
                return;
            }

            btn.textContent = '⏳ Saving...';
            btn.disabled = true;
            feedback.textContent = '';

            try {
                const res = await fetch('/api/save_lot_size', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ total_lots: val })
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('active-lot-display').textContent = data.total_lots + ' lots';
                    document.getElementById('active-lot-perleg').textContent = data.per_leg + ' per leg';
                    feedback.style.color = '#4ade80';
                    feedback.textContent = `✅ Saved! ${data.total_lots} total lots (${data.per_leg} per leg). Active immediately.`;
                } else {
                    feedback.style.color = '#f87171';
                    feedback.textContent = '❌ ' + (data.error || 'Save failed.');
                }
            } catch (e) {
                feedback.style.color = '#f87171';
                feedback.textContent = '❌ Network error – could not save.';
            } finally {
                btn.textContent = '💾 Save';
                btn.disabled = false;
            }
        }

        // Load lot size on page load
        loadLotSize();

        // ── Advanced Backtester Integration ─────────────────────────────────────
        let backtestChart = null;

        function initBacktestDates() {
            const endInput = document.getElementById('backtest-end-date');
            const startInput = document.getElementById('backtest-start-date');
            if (endInput && startInput) {
                const today = new Date();
                const yyyy = today.getFullYear();
                let mm = today.getMonth() + 1; // Months start at 0!
                let dd = today.getDate();
                if (dd < 10) dd = '0' + dd;
                if (mm < 10) mm = '0' + mm;
                const todayStr = yyyy + '-' + mm + '-' + dd;
                endInput.value = todayStr;

                // 90 days ago
                const ago90 = new Date();
                ago90.setDate(today.getDate() - 90);
                const yyyy2 = ago90.getFullYear();
                let mm2 = ago90.getMonth() + 1;
                let dd2 = ago90.getDate();
                if (dd2 < 10) dd2 = '0' + dd2;
                if (mm2 < 10) mm2 = '0' + mm2;
                const agoStr = yyyy2 + '-' + mm2 + '-' + dd2;
                startInput.value = agoStr;
            }
        }

        async function runBacktest() {
            const btn = document.getElementById('btn-run-backtest');
            const loading = document.getElementById('backtest-loading');
            const resultsContainer = document.getElementById('backtest-results-container');
            const capInput = document.getElementById('backtest-capital');
            const startInput = document.getElementById('backtest-start-date');
            const endInput = document.getElementById('backtest-end-date');

            const capital = parseFloat(capInput.value) || 50000.0;
            const startDate = startInput.value;
            const endDate = endInput.value;

            btn.disabled = true;
            const originalText = btn.textContent;
            btn.textContent = '⏳ Running...';
            loading.style.display = 'block';
            resultsContainer.style.display = 'none';

            try {
                const response = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        starting_capital: capital,
                        start_date: startDate,
                        end_date: endDate
                    })
                });

                const data = await response.json();
                if (!data.success) {
                    alert('❌ Backtest failed: ' + data.error);
                    return;
                }

                // Render metrics
                const metrics = data.metrics;
                document.getElementById('bt-winrate').textContent = `${metrics.win_rate.toFixed(1)}%`;
                
                const totalReturn = metrics.total_pnl_usd || 0.0;
                const returnEl = document.getElementById('bt-return');
                returnEl.textContent = `${totalReturn >= 0 ? '+' : ''}$${totalReturn.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                returnEl.style.color = totalReturn >= 0 ? 'var(--success)' : 'var(--danger)';

                document.getElementById('bt-drawdown').textContent = `${(metrics.max_drawdown || 0.0).toFixed(1)}%`;
                document.getElementById('bt-pf').textContent = (metrics.profit_factor || 0.0).toFixed(2);
                document.getElementById('bt-sharpe').textContent = (metrics.sharpe_ratio || 0.0).toFixed(2);
                document.getElementById('bt-hedges').textContent = metrics.hedge_trades || 0;

                resultsContainer.style.display = 'flex';

                // Render Chart
                const curve = data.equity_curve || [];
                const labels = curve.map(c => c.date);
                const points = curve.map(c => c.equity);

                if (backtestChart) {
                    backtestChart.destroy();
                }

                const ctx = document.getElementById('backtest-chart').getContext('2d');
                backtestChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Equity Curve (USDT)',
                            data: points,
                            borderColor: '#38bdf8',
                            backgroundColor: 'rgba(56, 189, 248, 0.05)',
                            borderWidth: 2.5,
                            fill: true,
                            tension: 0.15,
                            pointRadius: curve.length > 100 ? 0 : 2,
                            pointHoverRadius: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                                titleColor: '#94a3b8',
                                bodyColor: '#fff',
                                borderColor: 'rgba(255, 255, 255, 0.1)',
                                borderWidth: 1
                            }
                        },
                        scales: {
                            x: {
                                grid: { color: 'rgba(255, 255, 255, 0.02)' },
                                ticks: { color: '#94a3b8', maxTicksLimit: 12 }
                            },
                            y: {
                                grid: { color: 'rgba(255, 255, 255, 0.04)' },
                                ticks: { color: '#94a3b8' }
                            }
                        }
                    }
                });

            } catch (err) {
                console.error(err);
                alert('❌ Connection error: could not run backtest');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
                loading.style.display = 'none';
            }
        }

        // Initialize backtester date fields
        initBacktestDates();

        function switchTab(name) {
            // Hide all panes
            document.querySelectorAll('.tab-pane').forEach(p => { p.classList.remove('active'); });
            // Update buttons
            document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); });

            if (name === 'live') {
                document.getElementById('tab-live').classList.add('active');
                document.getElementById('tab-btn-live').classList.add('active');
            } else if (name === 'livemode') {
                document.getElementById('tab-livemode').classList.add('active');
                document.getElementById('tab-btn-livemode').classList.add('active');
            } else if (name === 'analytics') {
                document.getElementById('tab-analytics').classList.add('active');
                document.getElementById('tab-btn-analytics').classList.add('active');
            } else if (name === 'config') {
                document.getElementById('tab-config').classList.add('active');
                document.getElementById('tab-config-b').classList.add('active');
                document.getElementById('tab-btn-config').classList.add('active');
            }
        }
    

      if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
          navigator.serviceWorker.register('/sw.js').catch(err => {
            console.log('SW reg failed:', err);
          });
        });
      }
    
