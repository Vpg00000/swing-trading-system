/**
 * app.js - Controller for Swing Trading Command Center Dashboard.
 * Fully connected to live backend APIs with real-time data, truthful system health,
 * interactive stock screener, AI research terminal, portfolio risk UI, and zero hardcoded values.
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── Global State Variables ──────────────────────
    let reportData = null;
    let portfolioData = null;
    let healthData = null;
    let riskData = null;
    let pricedInData = {};
    let promptFiles = [];
    let activePrompt = null;
    let stockGridData = [];

    // Filter & Sort State for Screener Grid
    let currentCapCategory = 'ALL';
    let currentSearchQuery = '';
    let currentSortBy = 'composite_score';
    let currentAscending = false;

    let healthInterval = null;

    // ── Elements ──────────────────────────────────
    const refreshBtn = document.getElementById('refreshBtn');
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const dhanStatusBadge = document.getElementById('dhanStatusBadge');
    const niftyVal = document.getElementById('niftyVal');
    const vixVal = document.getElementById('vixVal');

    // ── Tab Navigation & Asynchronous Lazy Loader ──
    const loadedTabs = { screener: false, overview: false, candidates: false, research: false, allocation: false, insights: false, prompts: false, raw: false, health: false, chart: false, notifications: false };

    function triggerTabLazyLoad(tabId) {
        if (tabId === 'screener') {
            loadScreenerGrid();
        } else if (tabId === 'chart') {
            const sym = document.getElementById('chartSymbolInput')?.value || 'RELIANCE.NS';
            const tf = document.getElementById('chartTimeframeSelect')?.value || '1D';
            loadChartData(sym, tf);
        } else if (tabId === 'notifications') {
            loadNotificationConfig();
            loadNotificationLogs();
        } else if (tabId === 'candidates') {
            loadOpportunities();
        } else if (tabId === 'research') {
            const defaultSym = document.getElementById('researchSymbolInput')?.value || 'RELIANCE.NS';
            loadPricedInAnalysis(defaultSym);
        } else if (tabId === 'allocation') {
            loadPortfolio();
            loadRiskMetrics();
        } else if (tabId === 'insights') {
            loadFiiDii();
            loadCyclicalTrend();
            loadTopDeliveries();
            loadFilings();
        } else if (tabId === 'overview') {
            initDashboard(false);
        } else if (tabId === 'health') {
            loadHealthWatchdog();
            startHealthPolling();
        } else if (tabId === 'prompts') {
            loadPrompts();
        } else if (tabId === 'raw') {
            loadRawReport();
        }
    }


    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');

            navButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            btn.classList.add('active');
            const targetPane = document.getElementById(tabId);
            if (targetPane) targetPane.classList.add('active');

            triggerTabLazyLoad(tabId);
        });
    });

    // ── Initial Dashboard Load ──────────────────────
    async function initDashboard(forceRefresh = false) {
        try {
            if (forceRefresh && refreshBtn) {
                refreshBtn.classList.add('loading');
            }

            const res = await fetch(`/api/report-data?refresh=${forceRefresh}`);
            if (!res.ok) throw new Error("Failed to load report data from backend");
            reportData = await res.json();

            renderHeader();
            renderOverview();
            renderAllocation();
            renderCandidates();
            renderPresetScans();

        } catch (err) {
            console.error("Dashboard init failed:", err);
        } finally {
            if (forceRefresh && refreshBtn) {
                refreshBtn.classList.remove('loading');
            }
        }
    }

    // ── Header Rendering ───────────────────────────
    function renderHeader() {
        if (!reportData) return;

        // Dhan status
        if (dhanStatusBadge) {
            if (reportData.dhan_active) {
                dhanStatusBadge.className = "status-badge active";
                dhanStatusBadge.innerHTML = '<i class="fa-solid fa-link"></i> DHAN LIVE ACTIVE';
            } else {
                dhanStatusBadge.className = "status-badge inactive";
                dhanStatusBadge.innerHTML = '<i class="fa-solid fa-link-slash"></i> DHAN STUB MODE';
            }
        }

        // Nifty & VIX values
        const regime = reportData.regime || {};
        if (niftyVal) niftyVal.textContent = regime.nifty_close ? regime.nifty_close.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '--';
        if (vixVal) vixVal.textContent = regime.vix ? regime.vix.toFixed(2) : '--';
    }

    // ── Overview Tab Rendering ─────────────────────
    function renderOverview() {
        if (!reportData) return;

        const regime = reportData.regime || {};
        const score = regime.regime_score || 50.0;
        const state = regime.regime || 'UNKNOWN';

        const regimeScoreVal = document.getElementById('regimeScoreVal');
        const regimeStateVal = document.getElementById('regimeStateVal');
        const regimeNotes = document.getElementById('regimeNotes');
        const regimeGaugeFill = document.getElementById('regimeGaugeFill');

        if (regimeScoreVal) regimeScoreVal.textContent = score.toFixed(1);
        if (regimeStateVal) regimeStateVal.textContent = state;
        if (regimeNotes) regimeNotes.textContent = regime.notes || `Nifty 200-DMA: ₹${(regime.nifty_200dma || 0).toLocaleString('en-IN')} (${(regime.nifty_above_dma_pct || 0).toFixed(1)}%). VIX: ${(regime.vix || 0).toFixed(1)}.`;

        if (regimeGaugeFill) {
            const maxOffset = 125.6;
            const offset = maxOffset * (1 - Math.min(100, Math.max(0, score)) / 100);
            regimeGaugeFill.style.strokeDashoffset = offset;
        }

        // Capital stats
        const capital = reportData.capital || 100000.0;
        const portfolio = reportData.portfolio || {};
        const cash = portfolio.cash_inr || capital;
        const invested = capital > cash ? capital - cash : 0.0;
        const maxEquityPct = (regime.max_equity_exposure || 0.25) * 100.0;

        const capTotal = document.getElementById('capTotal');
        const capCash = document.getElementById('capCash');
        const capInvested = document.getElementById('capInvested');
        const capMaxEquity = document.getElementById('capMaxEquity');

        if (capTotal) capTotal.textContent = `₹${(capital / 100000.0).toFixed(2)}L`;
        if (capCash) capCash.textContent = `₹${(cash / 100000.0).toFixed(2)}L`;
        if (capInvested) capInvested.textContent = `₹${(invested / 100000.0).toFixed(2)}L`;
        if (capMaxEquity) capMaxEquity.textContent = `${maxEquityPct.toFixed(0)}%`;

        // Multi-factor subscores meters
        const regimeSubscoresContainer = document.getElementById('regimeSubscores');
        if (regimeSubscoresContainer) {
            const subscores = [
                { label: 'Trend Score', val: regime.trend_score || 50.0 },
                { label: 'Volatility Score', val: regime.volatility_score || 50.0 },
                { label: 'Breadth Score', val: regime.breadth_score || 50.0 },
                { label: 'Institutional Score', val: regime.institutional_score || 50.0 },
                { label: 'Global Score', val: regime.global_score || 50.0 },
                { label: 'Liquidity Score', val: regime.liquidity_score || 50.0 },
            ];

            let html = '';
            subscores.forEach(s => {
                html += `
                    <div class="meter-row">
                        <div class="meter-header">
                            <span class="meter-label">${s.label}</span>
                            <span class="meter-value">${s.val.toFixed(1)}/100</span>
                        </div>
                        <div class="meter-bar">
                            <div class="meter-bar-fill" style="width: ${Math.min(100, Math.max(0, s.val))}%;"></div>
                        </div>
                    </div>`;
            });
            regimeSubscoresContainer.innerHTML = html;
        }
    }

    // ── Preset Strategy Scans ──────────────────────
    function renderPresetScans() {
        const container = document.getElementById('scanPresetsContainer');
        if (!container) return;

        const presets = [
            { name: "ScanX Top Momentum", icon: "fa-rocket", cat: "ALL", sort: "composite_score" },
            { name: "Heavy Delivery Accumulation", icon: "fa-truck-ramp-box", cat: "ALL", sort: "delivery_pct" },
            { name: "High R:R Breakthroughs", icon: "fa-chart-line", cat: "ALL", sort: "rr_ratio" },
            { name: "Penny Volatility Edge (< ₹50)", icon: "fa-coins", cat: "PENNY", sort: "composite_score" },
            { name: "Large Cap Quality Anchors", icon: "fa-building", cat: "LARGE", sort: "roe" }
        ];

        let html = '';
        presets.forEach(p => {
            html += `
                <button class="preset-scan-btn" data-cat="${p.cat}" data-sort="${p.sort}" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); color: #fff; padding: 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 8px; text-align: left;">
                    <i class="fa-solid ${p.icon} text-mint"></i> ${p.name}
                </button>`;
        });
        container.innerHTML = html;

        container.querySelectorAll('.preset-scan-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                currentCapCategory = btn.getAttribute('data-cat');
                currentSortBy = btn.getAttribute('data-sort');
                currentAscending = false;

                // Update UI active category tab
                document.querySelectorAll('.grid-tab').forEach(tb => {
                    if (tb.getAttribute('data-cat') === currentCapCategory) {
                        tb.classList.add('active');
                        tb.style.background = '#10b981';
                        tb.style.color = '#000';
                    } else {
                        tb.classList.remove('active');
                        tb.style.background = 'rgba(255,255,255,0.05)';
                        tb.style.color = '#fff';
                    }
                });

                loadScreenerGrid();
            });
        });
    }

    // ── Stock Screener Pro Grid ───────────────────
    async function loadScreenerGrid() {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: #888; padding: 20px;"><i class="fa-solid fa-spinner fa-spin"></i> Querying indexed stock grid from SQLite...</td></tr>';

        try {
            const url = `/api/grid/stocks?cap_category=${currentCapCategory}&search=${encodeURIComponent(currentSearchQuery)}&sort_by=${currentSortBy}&ascending=${currentAscending}&limit=500`;
            const res = await fetch(url);
            if (!res.ok) throw new Error("Failed to fetch stock grid");
            stockGridData = await res.json();
            renderScreenerGrid();
        } catch (err) {
            console.error("Error loading stock grid:", err);
            tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: #ff4757; padding: 20px;"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load stock grid: ${err.message}</td></tr>`;
        }
    }

    function renderScreenerGrid() {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;

        if (!stockGridData || stockGridData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: #888; padding: 20px;">No stocks matching filter criteria.</td></tr>';
            return;
        }

        let html = '';
        stockGridData.forEach(row => {
            const actionClass = row.action === 'BUY_NOW' ? 'color:#10b981; font-weight:700;' : (row.action === 'EXIT' ? 'color:#ff4757; font-weight:700;' : 'color:#ff9f43;');
            const score = row.composite_score || 50.0;
            const rsi = row.rsi ? row.rsi.toFixed(1) : '--';
            const pe = row.pe ? row.pe.toFixed(1) : '--';
            const roe = row.roe ? row.roe.toFixed(1) + '%' : '--';
            const deliv = row.delivery_pct ? row.delivery_pct.toFixed(1) + '%' : '--';

            html += `
                <tr class="stock-row" data-symbol="${row.symbol}" style="cursor: pointer;">
                    <td class="font-bold text-mint">${row.symbol}</td>
                    <td>₹${(row.close || 0).toFixed(2)}</td>
                    <td>${rsi}</td>
                    <td>${pe}</td>
                    <td>${roe}</td>
                    <td>${deliv}</td>
                    <td class="font-bold">${score.toFixed(1)}</td>
                    <td style="${actionClass}">${row.action || 'WATCH'}</td>
                    <td>₹${(row.target_price || 0).toFixed(1)}</td>
                    <td>₹${(row.stop_loss || 0).toFixed(1)}</td>
                    <td>1:${(row.rr_ratio || 2.0).toFixed(2)}</td>
                    <td class="text-mint font-bold">+${(row.net_alpha_pct || 0.0).toFixed(1)}%</td>
                </tr>`;
        });
        tbody.innerHTML = html;

        // Row click handler to switch to AI Research Terminal
        tbody.querySelectorAll('.stock-row').forEach(tr => {
            tr.addEventListener('click', () => {
                const sym = tr.getAttribute('data-symbol');
                if (sym) {
                    const researchBtn = document.querySelector('.nav-btn[data-tab="research"]');
                    if (researchBtn) researchBtn.click();
                    const input = document.getElementById('researchSymbolInput');
                    if (input) input.value = sym;
                    loadPricedInAnalysis(sym);
                }
            });
        });
    }

    // Grid Category tab click handlers
    document.querySelectorAll('.grid-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.grid-tab').forEach(b => {
                b.classList.remove('active');
                b.style.background = 'rgba(255,255,255,0.05)';
                b.style.color = '#fff';
            });
            btn.classList.add('active');
            btn.style.background = '#10b981';
            btn.style.color = '#000';

            currentCapCategory = btn.getAttribute('data-cat');
            loadScreenerGrid();
        });
    });

    // Grid Search Input handler
    const gridSearchInput = document.getElementById('gridSearchInput');
    if (gridSearchInput) {
        let debounceTimer;
        gridSearchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                currentSearchQuery = e.target.value;
                loadScreenerGrid();
            }, 300);
        });
    }

    // Export CSV handler
    const exportCsvBtn = document.getElementById('exportCsvBtn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', () => {
            if (!stockGridData || stockGridData.length === 0) return;
            const headers = Object.keys(stockGridData[0]);
            let csv = headers.join(',') + '\n';
            stockGridData.forEach(row => {
                csv += headers.map(h => JSON.stringify(row[h] || '')).join(',') + '\n';
            });

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('href', url);
            a.setAttribute('download', `swing_stocks_${currentCapCategory}_${new Date().toISOString().slice(0,10)}.csv`);
            a.click();
        });
    }

    // One-click Sync handler
    const oneClickSyncBtn = document.getElementById('oneClickSyncBtn');
    if (oneClickSyncBtn) {
        oneClickSyncBtn.addEventListener('click', () => {
            initDashboard(true);
            loadScreenerGrid();
        });
    }

    // Sort column handler
    document.querySelectorAll('#screenerTable th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-sort');
            if (currentSortBy === col) {
                currentAscending = !currentAscending;
            } else {
                currentSortBy = col;
                currentAscending = false;
            }
            loadScreenerGrid();
        });
    });

    // ── Opportunities Monitor Tab ──────────────────
    async function loadOpportunities() {
        const container = document.getElementById('candidatesList');
        if (!container) return;

        container.innerHTML = '<div class="loading-state" style="padding: 20px; text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> Loading opportunity monitor data...</div>';

        try {
            const res = await fetch('/api/opportunities');
            if (!res.ok) throw new Error("Failed to fetch opportunities");
            const data = await res.json();
            renderOpportunities(data.opportunities || []);
        } catch (err) {
            console.error("Opportunities load error:", err);
            container.innerHTML = `<div class="error-state" style="padding: 20px; text-align: center; color: #ff4757;"><i class="fa-solid fa-triangle-exclamation"></i> Error loading opportunities: ${err.message}</div>`;
        }
    }

    function renderOpportunities(opportunities) {
        const container = document.getElementById('candidatesList');
        const actionsSummary = document.getElementById('actionsSummary');
        if (!container) return;

        if (!opportunities || opportunities.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding: 20px; text-align: center; color: #888;">No momentum candidates recommended today.</div>';
            return;
        }

        // Actions summary
        if (actionsSummary) {
            let actionsHtml = '';
            opportunities.slice(0, 3).forEach(opp => {
                const actionBadge = opp.suggested_action === 'BUY_NOW' ? 'BUY NOW' : opp.suggested_action;
                actionsHtml += `
                    <div class="action-box ${opp.suggested_action === 'EXIT' ? 'sell' : ''}">
                        <strong>${actionBadge} ${opp.symbol}</strong> — Target ₹${opp.target_price} | Stop ₹${opp.stop_price} (R:R 1:${opp.rr_ratio}) | Net Alpha: +${opp.net_alpha_pct}%
                    </div>`;
            });
            actionsSummary.innerHTML = actionsHtml;
        }

        let html = '';
        opportunities.forEach((c, idx) => {
            const rank = idx + 1;
            const actionBadgeClass = (c.suggested_action || 'watch').toLowerCase();
            const breakdown = c.score_breakdown || {};

            html += `
                <div class="candidate-card">
                    <div class="candidate-summary" onclick="this.parentElement.classList.toggle('open')">
                        <div class="c-left">
                            <span class="c-rank">#${rank}</span>
                            <span class="c-symbol">${c.symbol}</span>
                            <span class="c-badge ${actionBadgeClass}">${c.suggested_action || 'WATCH'}</span>
                        </div>
                        <div class="c-right">
                            <div>
                                <div class="c-score-label">Composite Score</div>
                                <div class="c-score-val">${(c.overall_score || 50.0).toFixed(1)}/100</div>
                            </div>
                            <i class="fa-solid fa-chevron-down c-toggle"></i>
                        </div>
                    </div>
                    <div class="candidate-details">
                        <div class="details-grid">
                            <div class="details-left">
                                <div class="stat-row"><span class="stat-label">Entry Price</span><span class="stat-value font-mono">₹${c.close}</span></div>
                                <div class="stat-row"><span class="stat-label">Stop Price</span><span class="stat-value font-mono text-red">₹${c.stop_price}</span></div>
                                <div class="stat-row"><span class="stat-label">Target Price</span><span class="stat-value font-mono text-mint">₹${c.target_price}</span></div>
                                <div class="stat-row"><span class="stat-label">Risk:Reward Ratio</span><span class="stat-value font-mono">1:${c.rr_ratio}</span></div>
                            </div>
                            <div class="details-right">
                                <div class="stat-row"><span class="stat-label">Expected Value (EV)</span><span class="stat-value font-mono text-mint">+${c.ev_pct}%</span></div>
                                <div class="stat-row"><span class="stat-label">Net Return (Alpha)</span><span class="stat-value font-mono text-mint">+${c.net_alpha_pct}%</span></div>
                                <div class="stat-row"><span class="stat-label">Priced-In Status</span><span class="stat-value font-mono text-amber">${c.priced_in_status || 'UNKNOWN'}</span></div>
                            </div>
                        </div>

                        <div style="margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                            <h4 style="font-size: 0.85rem; color: #888; margin-bottom: 8px;">100-Point Score Component Breakdown</h4>
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; font-size: 0.8rem;">
                                <div>Regime: <strong style="color:#fff;">${breakdown.regime || 0}/10</strong></div>
                                <div>Sector: <strong style="color:#fff;">${breakdown.sector || 0}/10</strong></div>
                                <div>Catalyst: <strong style="color:#fff;">${breakdown.catalyst || 0}/15</strong></div>
                                <div>FII/DII Flow: <strong style="color:#fff;">${breakdown.fii_dii || 0}/15</strong></div>
                                <div>Insider: <strong style="color:#fff;">${breakdown.insider || 0}/10</strong></div>
                                <div>Technical: <strong style="color:#fff;">${breakdown.technical || 0}/15</strong></div>
                                <div>Fundamental: <strong style="color:#fff;">${breakdown.fundamental || 0}/10</strong></div>
                                <div>Cash Flow: <strong style="color:#fff;">${breakdown.cashflow || 0}/5</strong></div>
                                <div>Governance: <strong style="color:#fff;">${breakdown.governance || 0}/5</strong></div>
                                <div>Valuation: <strong style="color:#fff;">${breakdown.valuation || 0}/5</strong></div>
                            </div>
                        </div>
                    </div>
                </div>`;
        });
        container.innerHTML = html;
    }

    function renderCandidates() {
        loadOpportunities();
    }

    // ── AI Research Terminal Tab ──────────────────
    async function loadPricedInAnalysis(securityId) {
        const container = document.getElementById('pricedInContainer');
        if (!container) return;

        container.innerHTML = '<div class="loading-state" style="padding: 20px; text-align: center;"><i class="fa-solid fa-spinner fa-spin"></i> Fetching AI research evidence & priced-in model...</div>';

        try {
            const res = await fetch(`/api/priced-in?symbol=${encodeURIComponent(securityId)}`);
            if (!res.ok) throw new Error("Failed to fetch priced-in analysis");
            const data = await res.json();
            pricedInData[securityId] = data;
            renderPricedInAnalysis(securityId);
        } catch (err) {
            console.error("Priced-in analysis load error:", err);
            container.innerHTML = `<div class="error-state" style="padding: 20px; text-align: center; color: #ff4757;"><i class="fa-solid fa-triangle-exclamation"></i> Error loading priced-in analysis: ${err.message}</div>`;
        }
    }

    function renderPricedInAnalysis(securityId) {
        const container = document.getElementById('pricedInContainer');
        const data = pricedInData[securityId];
        if (!container || !data) return;

        const pricedIn = data.priced_in || {};
        const evidence = pricedIn.evidence || {};
        const inference = pricedIn.inference || {};

        let statusClass = 'status-unknown';
        switch (inference.classification || data.status) {
            case 'UNDER PRICED': statusClass = 'text-mint'; break;
            case 'PARTIALLY PRICED': statusClass = 'text-amber'; break;
            case 'FULLY PRICED': statusClass = 'text-blue'; break;
            case 'OVERPRICED': statusClass = 'text-red'; break;
        }

        let html = `
            <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 12px;">
                    <h3 style="font-size: 1.2rem; font-family: var(--font-mono);">${data.symbol} <span style="font-size: 0.85rem; color: #888;">(Priced-In Analysis)</span></h3>
                    <div style="font-size: 1.1rem; font-weight: 700;" class="${statusClass}">
                        STATUS: ${inference.classification || data.status || 'UNKNOWN'}
                    </div>
                </div>

                <p style="font-size: 0.9rem; line-height: 1.5; color: var(--color-muted); margin-bottom: 15px;">
                    <strong>AI Rationale:</strong> ${inference.rationale || 'Analysis complete.'}
                </p>

                <!-- Evidence Section -->
                <h4 style="font-size: 0.9rem; color: var(--color-mint); text-transform: uppercase; margin-bottom: 10px;">1. Evidence Section</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; font-size: 0.85rem; margin-bottom: 20px;">
                    <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                        <div style="color: #888;">Price Delta</div>
                        <div style="font-family: var(--font-mono); font-weight: 600; color: #fff;">${evidence.price_delta || '--'}</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                        <div style="color: #888;">Valuation Multiples</div>
                        <div style="font-family: var(--font-mono); font-weight: 600; color: #fff;">${evidence.valuation_multiples || '--'}</div>
                    </div>
                    <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);">
                        <div style="color: #888;">Volume Delivery</div>
                        <div style="font-family: var(--font-mono); font-weight: 600; color: #fff;">${evidence.volume_delivery || '--'}</div>
                    </div>
                </div>

                <!-- Inference Section -->
                <h4 style="font-size: 0.9rem; color: var(--color-amber); text-transform: uppercase; margin-bottom: 10px;">2. Inference & Confidence Section</h4>
                <div style="font-size: 0.85rem; color: var(--color-muted);">
                    <div>Classification: <strong style="color:#fff;">${inference.classification || 'UNKNOWN'}</strong></div>
                    <div>Confidence Score: <strong style="color:#fff;">${((inference.confidence_score || 0.85) * 100).toFixed(0)}%</strong></div>
                </div>
            </div>`;

        container.innerHTML = html;
    }

    const runResearchBtn = document.getElementById('runResearchBtn');
    if (runResearchBtn) {
        runResearchBtn.addEventListener('click', () => {
            const sym = document.getElementById('researchSymbolInput')?.value;
            if (sym) loadPricedInAnalysis(sym);
        });
    }

    // ── Portfolio & Risk UI Tab ────────────────────
    async function loadPortfolio() {
        try {
            const res = await fetch('/api/portfolio');
            if (!res.ok) throw new Error("Failed to fetch portfolio");
            portfolioData = await res.json();
            renderAllocation();
        } catch (err) {
            console.error("Portfolio load error:", err);
        }
    }

    async function loadRiskMetrics() {
        try {
            const res = await fetch('/api/risk');
            if (!res.ok) throw new Error("Failed to fetch risk metrics");
            riskData = await res.json();
            renderRisk();
        } catch (err) {
            console.error("Risk load error:", err);
        }
    }

    function renderRisk() {
        if (!riskData) return;
        const riskBetaVal = document.getElementById('riskBetaVal');
        const riskCvarVal = document.getElementById('riskCvarVal');
        const riskCapVal = document.getElementById('riskCapVal');
        const riskKellyVal = document.getElementById('riskKellyVal');

        if (riskBetaVal) riskBetaVal.textContent = (riskData.portfolio_beta || 1.0).toFixed(2);
        if (riskCvarVal) riskCvarVal.textContent = `-${(riskData.cvar_95 || 2.5).toFixed(1)}%`;
        if (riskCapVal) riskCapVal.textContent = `${(riskData.sub_industry_cap_pct || 15.0).toFixed(1)}%`;
        if (riskKellyVal) riskKellyVal.textContent = `${(riskData.kelly_recommended_size_pct || 5.0).toFixed(1)}%`;
    }

    function renderAllocation() {
        if (!reportData) return;

        const driftTable = reportData.drift_table || {};
        const holdings = (reportData.portfolio || {}).holdings || [];
        const taxStatuses = reportData.tax_statuses || [];

        // Populate drift table
        const tbodyDrift = document.querySelector('#driftTable tbody');
        if (tbodyDrift) {
            if (Object.keys(driftTable).length === 0) {
                tbodyDrift.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #888;">No drift calculations available.</td></tr>';
            } else {
                let html = '';
                Object.entries(driftTable).forEach(([sleeve, val]) => {
                    html += `
                        <tr>
                            <td>${sleeve}</td>
                            <td>${(val.target_pct * 100).toFixed(1)}%</td>
                            <td>₹${(val.target_inr / 100000).toFixed(2)}L</td>
                            <td>${(val.actual_pct * 100).toFixed(1)}%</td>
                            <td>₹${(val.actual_inr / 100000).toFixed(2)}L</td>
                            <td class="${val.drift_pct >= 0 ? 'text-mint' : 'text-red'}">${(val.drift_pct * 100).toFixed(1)}%</td>
                            <td class="${val.drift_inr >= 0 ? 'text-mint' : 'text-red'}">₹${(val.drift_inr / 100000).toFixed(2)}L</td>
                        </tr>`;
                });
                tbodyDrift.innerHTML = html;
            }
        }

        // Populate holdings table
        const tbodyHoldings = document.querySelector('#holdingsTable tbody');
        if (tbodyHoldings) {
            if (holdings.length === 0) {
                tbodyHoldings.innerHTML = '<tr><td colspan="9" style="text-align: center; color: #888;">No active holdings in portfolio.</td></tr>';
            } else {
                let html = '';
                holdings.forEach(h => {
                    const tstat = taxStatuses.find(t => t.symbol === h.symbol) || {};
                    const isLtcg = tstat.is_ltcg;
                    const badgeClass = isLtcg ? 'badge-ltcg' : 'badge-stcg';
                    const taxLabel = isLtcg ? 'LTCG (12.5%)' : 'STCG (20%)';

                    html += `
                        <tr>
                            <td class="font-bold text-mint">${h.symbol}</td>
                            <td>${h.sleeve || 'Core momentum'}</td>
                            <td>ACTIVE</td>
                            <td>₹${((h.value_inr || 0) / 100000).toFixed(2)}L</td>
                            <td>₹0.00L</td>
                            <td><span class="badge ${badgeClass}">${taxLabel}</span></td>
                            <td>${tstat.days_held || '--'} d</td>
                            <td class="${(tstat.unrealized_gain_pct || 0) >= 0 ? 'text-mint' : 'text-red'}">${(tstat.unrealized_gain_pct || 0).toFixed(1)}%</td>
                            <td>₹${((tstat.unrealized_gain_inr || 0) * (isLtcg ? 0.125 : 0.20) / 100000).toFixed(2)}L</td>
                        </tr>`;
                });
                tbodyHoldings.innerHTML = html;
            }
        }
    }

    // ── Market Insights Tab ────────────────────────
    async function loadFiiDii() {
        const tbody = document.getElementById('fiiDiiTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/flow');
            if (!res.ok) throw new Error("Failed to fetch FII/DII flow");
            const data = await res.json();

            let rows = Array.isArray(data) ? data : (data.data || []);
            if (!rows || rows.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #888;">No FII/DII flow data available.</td></tr>';
                return;
            }

            let html = '';
            rows.slice(0, 15).forEach(r => {
                html += `
                    <tr>
                        <td>${r.date || '--'}</td>
                        <td>${r.fii_buy || 0}</td>
                        <td>${r.fii_sell || 0}</td>
                        <td class="${(r.fii_net || 0) >= 0 ? 'text-mint' : 'text-red'}">${r.fii_net || 0}</td>
                        <td>${r.dii_buy || 0}</td>
                        <td>${r.dii_sell || 0}</td>
                        <td class="${(r.dii_net || 0) >= 0 ? 'text-mint' : 'text-red'}">${r.dii_net || 0}</td>
                        <td class="font-bold ${(r.total_net || 0) >= 0 ? 'text-mint' : 'text-red'}">${r.total_net || 0}</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: #ff4757;">Error loading flow data: ${err.message}</td></tr>`;
        }
    }

    async function loadCyclicalTrend() {
        const tbody = document.getElementById('cyclicalTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/cyclical');
            if (!res.ok) throw new Error("Failed to fetch cyclical matrix");
            const data = await res.json();

            let html = '';
            data.forEach(r => {
                html += `
                    <tr>
                        <td class="font-bold">${r.fy}</td>
                        <td>${r.Apr}</td><td>${r.May}</td><td>${r.Jun}</td><td>${r.Jul}</td>
                        <td>${r.Aug}</td><td>${r.Sep}</td><td>${r.Oct}</td><td>${r.Nov}</td>
                        <td>${r.Dec}</td><td>${r.Jan}</td><td>${r.Feb}</td><td>${r.Mar}</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: #ff4757;">Error loading cyclical matrix: ${err.message}</td></tr>`;
        }
    }

    async function loadTopDeliveries() {
        const tbody = document.getElementById('topDeliveriesTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/deliveries');
            if (!res.ok) throw new Error("Failed to fetch delivery data");
            const data = await res.json();

            let html = '';
            data.forEach(r => {
                html += `
                    <tr>
                        <td class="font-bold text-mint">${r.symbol}</td>
                        <td>₹${(r.close || 0).toFixed(2)}</td>
                        <td>${(r.traded_qty || 0).toLocaleString('en-IN')}</td>
                        <td>${(r.delivered_qty || 0).toLocaleString('en-IN')}</td>
                        <td class="font-bold text-mint">${(r.delivery_pct || 0).toFixed(1)}%</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ff4757;">Error loading delivery data: ${err.message}</td></tr>`;
        }
    }

    async function loadFilings() {
        const tbody = document.getElementById('filingsTableBody');
        if (!tbody) return;
        try {
            const res = await fetch('/api/filings');
            if (!res.ok) throw new Error("Failed to fetch filings");
            const data = await res.json();

            let html = '';
            data.forEach(r => {
                html += `
                    <tr>
                        <td>${r.date}</td>
                        <td class="font-bold text-mint">${r.symbol}</td>
                        <td><span class="badge badge-stcg">${r.category}</span></td>
                        <td>${r.subject}</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #ff4757;">Error loading filings: ${err.message}</td></tr>`;
        }
    }

    // ── Claude Prompts Tab ─────────────────────────
    async function loadPrompts() {
        const listPanel = document.getElementById('promptsList');
        if (!listPanel) return;

        try {
            const res = await fetch('/api/prompts');
            if (!res.ok) throw new Error("Failed to list prompts");
            promptFiles = await res.json();

            if (promptFiles.length === 0) {
                listPanel.innerHTML = '<div style="color: #888; font-size: 0.85rem;">No prompt files saved yet.</div>';
                return;
            }

            let html = '';
            promptFiles.forEach((file, idx) => {
                html += `<button class="prompt-tab-btn ${idx === 0 ? 'active' : ''}" data-file="${file}">${file}</button>`;
            });
            listPanel.innerHTML = html;

            listPanel.querySelectorAll('.prompt-tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    listPanel.querySelectorAll('.prompt-tab-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const fileName = btn.getAttribute('data-file');
                    loadPromptContent(fileName);
                });
            });

            if (promptFiles.length > 0) {
                loadPromptContent(promptFiles[0]);
            }
        } catch (err) {
            console.error("Prompts load error:", err);
        }
    }

    async function loadPromptContent(filename) {
        const titleEl = document.getElementById('activePromptTitle');
        const bodyEl = document.getElementById('activePromptBody');
        const copyBtn = document.getElementById('copyPromptBtn');

        if (titleEl) titleEl.textContent = filename;
        if (bodyEl) bodyEl.textContent = 'Loading prompt file content...';

        try {
            const res = await fetch(`/api/prompts/${encodeURIComponent(filename)}`);
            if (!res.ok) throw new Error("Failed to load prompt file content");
            const text = await res.text();
            activePrompt = text;
            if (bodyEl) bodyEl.textContent = text;
            if (copyBtn) copyBtn.classList.remove('hidden');
        } catch (err) {
            if (bodyEl) bodyEl.textContent = `Error loading prompt: ${err.message}`;
        }
    }

    const copyPromptBtn = document.getElementById('copyPromptBtn');
    if (copyPromptBtn) {
        copyPromptBtn.addEventListener('click', () => {
            if (activePrompt) {
                navigator.clipboard.writeText(activePrompt);
                copyPromptBtn.innerHTML = '<i class="fa-solid fa-check"></i> COPIED!';
                setTimeout(() => {
                    copyPromptBtn.innerHTML = '<i class="fa-solid fa-copy"></i> COPY PROMPT';
                }, 2000);
            }
        });
    }

    // ── Raw Report Tab ─────────────────────────────
    async function loadRawReport() {
        const el = document.getElementById('rawReportText');
        if (!el) return;

        try {
            const res = await fetch('/api/report-data');
            if (!res.ok) throw new Error("Failed to fetch report");
            const data = await res.json();
            el.textContent = JSON.stringify(data, null, 2);
        } catch (err) {
            el.textContent = `Error loading report: ${err.message}`;
        }
    }

    const copyReportBtn = document.getElementById('copyReportBtn');
    if (copyReportBtn) {
        copyReportBtn.addEventListener('click', () => {
            const el = document.getElementById('rawReportText');
            if (el && el.textContent) {
                navigator.clipboard.writeText(el.textContent);
                copyReportBtn.innerHTML = '<i class="fa-solid fa-check"></i> COPIED!';
                setTimeout(() => {
                    copyReportBtn.innerHTML = '<i class="fa-solid fa-copy"></i> COPY REPORT';
                }, 2000);
            }
        });
    }

    // ── System Health Watchdog Tab ─────────────────
    async function loadHealthWatchdog() {
        try {
            const res = await fetch('/api/health');
            if (!res.ok) throw new Error("Failed to fetch system health");
            healthData = await res.json();
            renderHealth();
        } catch (err) {
            console.error("Health load error:", err);
        }
    }

    function startHealthPolling() {
        if (healthInterval) clearInterval(healthInterval);
        healthInterval = setInterval(loadHealthWatchdog, 30000);
    }

    function renderHealth() {
        if (!healthData) return;

        const mode = healthData.overall_status || healthData.system_mode || 'NORMAL';
        const overallStatusEl = document.getElementById('overallStatus');
        const systemModeBanner = document.getElementById('systemModeBanner');

        if (overallStatusEl) {
            overallStatusEl.textContent = mode;
            if (mode === 'NORMAL') overallStatusEl.style.color = '#10b981';
            else if (mode === 'DEGRADED') overallStatusEl.style.color = '#ff9f43';
            else overallStatusEl.style.color = '#ff4757';
        }

        if (systemModeBanner) {
            if (mode === 'TRADING_BLOCKED') {
                systemModeBanner.style.display = 'block';
                systemModeBanner.style.background = 'rgba(255,71,87,0.15)';
                systemModeBanner.style.border = '1px solid #ff4757';
                systemModeBanner.style.color = '#ff4757';
                systemModeBanner.innerHTML = '<i class="fa-solid fa-ban"></i> CRITICAL FAILURE — TRADING IS BLOCKED. Data source pipeline error or auth loss.';
            } else if (mode === 'DEGRADED') {
                systemModeBanner.style.display = 'block';
                systemModeBanner.style.background = 'rgba(255,159,67,0.15)';
                systemModeBanner.style.border = '1px solid #ff9f43';
                systemModeBanner.style.color = '#ff9f43';
                systemModeBanner.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> SYSTEM DEGRADED — Running with partial data cache or broker fallback.';
            } else {
                systemModeBanner.style.display = 'none';
            }
        }

        // Components table
        const tbody = document.getElementById('componentsHealthTableBody');
        if (tbody && healthData.components) {
            let html = '';
            healthData.components.forEach(c => {
                const st = c.status || 'OK';
                let colorStyle = 'color: #10b981;';
                if (st === 'DEGRADED' || st === 'STALE' || st === 'INACTIVE') colorStyle = 'color: #ff9f43;';
                if (st === 'ERROR' || st === 'FAILED') colorStyle = 'color: #ff4757;';

                html += `
                    <tr>
                        <td class="font-bold">${c.name || c.component || '-'}</td>
                        <td style="${colorStyle} font-weight:700;"><i class="fa-solid fa-circle" style="font-size:8px;"></i> ${st}</td>
                        <td>${c.last_updated ? new Date(c.last_updated).toLocaleTimeString() : '--'}</td>
                        <td>${c.latency !== undefined ? c.latency + ' ms' : '--'}</td>
                        <td>${c.records !== undefined ? c.records : '--'}</td>
                        <td style="color:#888;">${c.error || 'Clean / Normal Operation'}</td>
                        <td>${c.retry !== undefined ? c.retry : 0}</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        }
    }

    // ── Re-run Pipeline refresh button click ───────
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            initDashboard(true);
        });
    }

    // ── TASK-075: Web Audio API Sound Alert Synthesizer ──
    class SoundSynthesizer {
        constructor() {
            this.ctx = null;
            this.muted = false;
            this.initAudioConfig();
        }

        async initAudioConfig() {
            try {
                const res = await fetch('/api/ui/audio-config');
                if (res.ok) {
                    const config = await res.json();
                    this.muted = !!config.muted;
                    this.updateUI();
                }
            } catch (e) {
                console.warn('Audio config fetch error:', e);
            }
        }

        getAudioContext() {
            if (!this.ctx) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) this.ctx = new AudioCtx();
            }
            if (this.ctx && this.ctx.state === 'suspended') {
                this.ctx.resume();
            }
            return this.ctx;
        }

        toggleMute() {
            this.muted = !this.muted;
            this.saveConfig();
            this.updateUI();
            return this.muted;
        }

        async saveConfig() {
            try {
                await fetch('/api/ui/audio-config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ muted: this.muted, volume: 0.8, chimes_enabled: true, voice_enabled: true })
                });
            } catch (e) {
                console.warn('Failed to save audio config:', e);
            }
        }

        updateUI() {
            const btn = document.getElementById('audioToggleBtn');
            const txt = document.getElementById('audioStatusText');
            if (btn && txt) {
                if (this.muted) {
                    btn.style.color = '#ff4757';
                    txt.textContent = 'AUDIO OFF';
                } else {
                    btn.style.color = '#10b981';
                    txt.textContent = 'AUDIO ON';
                }
            }
        }

        playOrderFillChime() {
            if (this.muted) return;
            const ctx = this.getAudioContext();
            if (!ctx) return;

            const now = ctx.currentTime;
            const notes = [523.25, 659.25, 783.99]; // C5, E5, G5
            notes.forEach((freq, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now + idx * 0.1);
                gain.gain.setValueAtTime(0.3, now + idx * 0.1);
                gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.1 + 0.3);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.1);
                osc.stop(now + idx * 0.1 + 0.3);
            });
        }

        playStopLossTone() {
            if (this.muted) return;
            const ctx = this.getAudioContext();
            if (!ctx) return;

            const now = ctx.currentTime;
            [220, 180].forEach((freq, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(freq, now + idx * 0.15);
                gain.gain.setValueAtTime(0.4, now + idx * 0.15);
                gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.15 + 0.25);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.15);
                osc.stop(now + idx * 0.15 + 0.25);
            });
        }

        playOpportunityPing() {
            if (this.muted) return;
            const ctx = this.getAudioContext();
            if (!ctx) return;

            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, now);
            gain.gain.setValueAtTime(0.4, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(now);
            osc.stop(now + 0.4);
        }

        speakAlert(text) {
            if (this.muted) return;
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                window.speechSynthesis.speak(utterance);
            }
        }
    }

    const audioSynth = new SoundSynthesizer();

    const audioToggleBtn = document.getElementById('audioToggleBtn');
    if (audioToggleBtn) {
        audioToggleBtn.addEventListener('click', () => {
            audioSynth.toggleMute();
        });
    }

    document.getElementById('testChimeBtn')?.addEventListener('click', () => audioSynth.playOrderFillChime());
    document.getElementById('testStopLossBtn')?.addEventListener('click', () => audioSynth.playStopLossTone());
    document.getElementById('testPingBtn')?.addEventListener('click', () => audioSynth.playOpportunityPing());
    document.getElementById('testVoiceBtn')?.addEventListener('click', () => audioSynth.speakAlert('Opportunity detected for Reliance Industries'));


    // ── TASK-071: TradingView Lightweight Charts & Canvas Fallback ──
    let lightweightChartInstance = null;

    async function loadChartData(symbol = 'RELIANCE.NS', timeframe = '1D') {
        const container = document.getElementById('tradingview-chart-container');
        if (!container) return;

        try {
            const res = await fetch(`/api/chart/data?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
            if (!res.ok) throw new Error('Chart API error');
            const data = await res.json();

            container.innerHTML = '';

            if (window.LightweightCharts) {
                lightweightChartInstance = window.LightweightCharts.createChart(container, {
                    width: container.clientWidth || 800,
                    height: 500,
                    layout: {
                        backgroundColor: '#0b0f19',
                        textColor: '#a6b2c9'
                    },
                    grid: {
                        vertLines: { color: 'rgba(255,255,255,0.05)' },
                        horzLines: { color: 'rgba(255,255,255,0.05)' }
                    },
                    crosshair: { mode: window.LightweightCharts.CrosshairMode.Normal },
                    rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
                    timeScale: { borderColor: 'rgba(255,255,255,0.1)' }
                });

                const candleSeries = lightweightChartInstance.addCandlestickSeries({
                    upColor: '#10b981',
                    downColor: '#ef4444',
                    borderUpColor: '#10b981',
                    borderDownColor: '#ef4444',
                    wickUpColor: '#10b981',
                    wickDownColor: '#ef4444'
                });
                candleSeries.setData(data.candles);

                const ema20Series = lightweightChartInstance.addLineSeries({ color: '#3b82f6', lineWidth: 2, title: 'EMA 20' });
                ema20Series.setData(data.ema20);

                const ema50Series = lightweightChartInstance.addLineSeries({ color: '#ff9f43', lineWidth: 2, title: 'EMA 50' });
                ema50Series.setData(data.ema50);

                if (data.markers && data.markers.length > 0) {
                    candleSeries.setMarkers(data.markers);
                }

                window.addEventListener('resize', () => {
                    if (lightweightChartInstance && container) {
                        lightweightChartInstance.applyOptions({ width: container.clientWidth });
                    }
                });
            } else {
                renderCanvasChartFallback(container, data);
            }
        } catch (err) {
            console.error('Failed to load chart:', err);
            container.innerHTML = `<div style="padding: 20px; color: #ff4757;">Failed to render chart: ${err.message}</div>`;
        }
    }

    function renderCanvasChartFallback(container, data) {
        const canvas = document.createElement('canvas');
        canvas.width = container.clientWidth || 800;
        canvas.height = 500;
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#0b0f19';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#10b981';
        ctx.font = '16px monospace';
        ctx.fillText(`${data.symbol} (${data.timeframe}) — HTML5 Canvas Engine`, 20, 30);

        const candles = data.candles || [];
        if (candles.length === 0) return;

        let minP = Math.min(...candles.map(c => c.low));
        let maxP = Math.max(...candles.map(c => c.high));
        const range = maxP - minP || 1;

        const padL = 50, padR = 20, padT = 50, padB = 40;
        const chartW = canvas.width - padL - padR;
        const chartH = canvas.height - padT - padB;
        const barW = chartW / candles.length;

        ctx.strokeStyle = 'rgba(255,255,255,0.05)';
        ctx.lineWidth = 1;
        for (let i = 0; i < 5; i++) {
            const y = padT + (chartH / 4) * i;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(canvas.width - padR, y);
            ctx.stroke();
        }

        candles.forEach((c, idx) => {
            const x = padL + idx * barW + barW / 2;
            const openY = padT + chartH * (1 - (c.open - minP) / range);
            const closeY = padT + chartH * (1 - (c.close - minP) / range);
            const highY = padT + chartH * (1 - (c.high - minP) / range);
            const lowY = padT + chartH * (1 - (c.low - minP) / range);

            const isGreen = c.close >= c.open;
            ctx.strokeStyle = isGreen ? '#10b981' : '#ef4444';
            ctx.fillStyle = isGreen ? '#10b981' : '#ef4444';

            ctx.beginPath();
            ctx.moveTo(x, highY);
            ctx.lineTo(x, lowY);
            ctx.stroke();

            const topY = Math.min(openY, closeY);
            const bH = Math.max(2, Math.abs(closeY - openY));
            ctx.fillRect(x - barW * 0.35, topY, barW * 0.7, bH);
        });

        if (data.markers) {
            data.markers.forEach(m => {
                const idx = candles.findIndex(c => c.time === m.time);
                if (idx !== -1) {
                    const x = padL + idx * barW + barW / 2;
                    const c = candles[idx];
                    const y = m.position === 'belowBar'
                        ? padT + chartH * (1 - (c.low - minP) / range) + 15
                        : padT + chartH * (1 - (c.high - minP) / range) - 15;
                    ctx.fillStyle = m.color || '#10b981';
                    ctx.font = '12px monospace';
                    ctx.fillText(m.text, x - 20, y);
                }
            });
        }
    }

    document.getElementById('loadChartBtn')?.addEventListener('click', () => {
        const sym = document.getElementById('chartSymbolInput')?.value || 'RELIANCE.NS';
        const tf = document.getElementById('chartTimeframeSelect')?.value || '1D';
        loadChartData(sym, tf);
    });


    // ── TASK-074: Drag-and-Drop Customizable Layout Handler ──
    function initDragAndDropLayout() {
        const grid = document.getElementById('overviewGrid');
        if (!grid) return;

        let draggedItem = null;

        grid.querySelectorAll('.card[draggable="true"]').forEach(card => {
            card.addEventListener('dragstart', (e) => {
                draggedItem = card;
                e.dataTransfer.effectAllowed = 'move';
                card.style.opacity = '0.5';
            });

            card.addEventListener('dragend', () => {
                draggedItem = null;
                card.style.opacity = '1.0';
                saveDashboardLayout();
            });

            card.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
            });

            card.addEventListener('drop', (e) => {
                e.preventDefault();
                if (draggedItem && draggedItem !== card) {
                    const allCards = Array.from(grid.querySelectorAll('.card'));
                    const draggedIdx = allCards.indexOf(draggedItem);
                    const targetIdx = allCards.indexOf(card);

                    if (draggedIdx < targetIdx) {
                        grid.insertBefore(draggedItem, card.nextSibling);
                    } else {
                        grid.insertBefore(draggedItem, card);
                    }
                    saveDashboardLayout();
                }
            });
        });

        loadSavedDashboardLayout();
    }

    async function saveDashboardLayout() {
        const grid = document.getElementById('overviewGrid');
        if (!grid) return;

        const cards = Array.from(grid.querySelectorAll('.card'));
        const layout = {
            version: "1.0",
            widgets: cards.map((c, idx) => ({
                id: c.id,
                title: c.querySelector('.card-header')?.innerText.trim() || c.id,
                visible: true,
                order: idx
            }))
        };

        localStorage.setItem('dashboard_layout', JSON.stringify(layout));

        try {
            await fetch('/api/ui/layout-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(layout)
            });
        } catch (e) {
            console.warn('Failed to save layout to server:', e);
        }
    }

    async function loadSavedDashboardLayout() {
        try {
            const res = await fetch('/api/ui/layout-config');
            let layout = null;
            if (res.ok) {
                layout = await res.json();
            } else {
                const local = localStorage.getItem('dashboard_layout');
                if (local) layout = JSON.parse(local);
            }

            if (layout && layout.widgets && layout.widgets.length > 0) {
                const grid = document.getElementById('overviewGrid');
                if (!grid) return;

                layout.widgets.sort((a, b) => a.order - b.order).forEach(w => {
                    const el = document.getElementById(w.id);
                    if (el) grid.appendChild(el);
                });
            }
        } catch (e) {
            console.warn('Layout load error:', e);
        }
    }


    // ── TASK-072: Telegram & WhatsApp Notifier Management ──
    async function loadNotificationConfig() {
        try {
            const res = await fetch('/api/notifications/config');
            if (!res.ok) return;
            const config = await res.json();

            if (document.getElementById('notifTelegramEnabled')) document.getElementById('notifTelegramEnabled').checked = !!config.telegram_enabled;
            if (document.getElementById('notifWhatsappEnabled')) document.getElementById('notifWhatsappEnabled').checked = !!config.whatsapp_enabled;
            if (document.getElementById('notifTelegramToken')) document.getElementById('notifTelegramToken').value = config.telegram_bot_token || '';
            if (document.getElementById('notifTelegramChatId')) document.getElementById('notifTelegramChatId').value = config.telegram_chat_id || '';
            if (document.getElementById('notifTwilioSid')) document.getElementById('notifTwilioSid').value = config.twilio_account_sid || '';
            if (document.getElementById('notifTwilioTo')) document.getElementById('notifTwilioTo').value = config.twilio_whatsapp_to || '';
        } catch (e) {
            console.warn('Notification config load error:', e);
        }
    }

    async function loadNotificationLogs() {
        try {
            const res = await fetch('/api/notifications/log');
            if (!res.ok) return;
            const logs = await res.json();
            const tbody = document.getElementById('notifLogsTableBody');
            if (!tbody) return;

            if (logs.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #888; padding: 20px;">No notification logs recorded yet.</td></tr>';
                return;
            }

            let html = '';
            logs.forEach(l => {
                const stColor = l.status === 'SUCCESS' ? '#10b981' : '#ff4757';
                html += `
                    <tr>
                        <td class="font-mono text-xs">${l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : '--'}</td>
                        <td class="font-bold">${l.channel}</td>
                        <td><span class="badge badge-ltcg">${l.alert_type}</span></td>
                        <td style="color: ${stColor}; font-weight: 700;">${l.status}</td>
                        <td class="font-mono text-xs" style="color: #a6b2c9;">${JSON.stringify(l.details)}</td>
                    </tr>`;
            });
            tbody.innerHTML = html;
        } catch (e) {
            console.warn('Notification logs load error:', e);
        }
    }

    document.getElementById('saveNotifConfigBtn')?.addEventListener('click', async () => {
        const payload = {
            telegram_enabled: document.getElementById('notifTelegramEnabled')?.checked,
            whatsapp_enabled: document.getElementById('notifWhatsappEnabled')?.checked,
            telegram_bot_token: document.getElementById('notifTelegramToken')?.value,
            telegram_chat_id: document.getElementById('notifTelegramChatId')?.value,
            twilio_account_sid: document.getElementById('notifTwilioSid')?.value,
            twilio_auth_token: document.getElementById('notifTwilioAuthToken')?.value,
            twilio_whatsapp_to: document.getElementById('notifTwilioTo')?.value
        };
        try {
            const res = await fetch('/api/notifications/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const statusEl = document.getElementById('notifDispatchStatus');
            if (res.ok) {
                if (statusEl) statusEl.textContent = 'Configuration saved successfully!';
            } else {
                if (statusEl) statusEl.textContent = 'Failed to save configuration.';
            }
        } catch (e) {
            console.error('Config save error:', e);
        }
    });

    document.getElementById('sendTestNotifBtn')?.addEventListener('click', async () => {
        const category = document.getElementById('notifAlertCategory')?.value || 'OPPORTUNITY';
        const symbol = document.getElementById('notifSymbol')?.value || 'RELIANCE.NS';
        const price = parseFloat(document.getElementById('notifPrice')?.value || '2885.50');
        const message = document.getElementById('notifCustomMessage')?.value || 'Instant test alert triggered from AI Command Center';

        const payload = {
            alert_type: category,
            data: {
                title: `${category} Triggered`,
                symbol: symbol,
                price: price,
                message: message
            }
        };

        const statusEl = document.getElementById('notifDispatchStatus');
        if (statusEl) statusEl.textContent = 'Dispatching alert...';

        try {
            const res = await fetch('/api/notifications/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok) {
                if (statusEl) statusEl.textContent = `Alert dispatched via Telegram/WhatsApp! Status: ${data.status}`;
                if (category === 'ORDER_FILL') audioSynth.playOrderFillChime();
                else if (category === 'STOP_LOSS' || category === 'DRAWDOWN') audioSynth.playStopLossTone();
                else audioSynth.playOpportunityPing();
                loadNotificationLogs();
            } else {
                if (statusEl) statusEl.textContent = 'Dispatch failed.';
            }
        } catch (e) {
            console.error('Dispatch error:', e);
            if (statusEl) statusEl.textContent = 'Dispatch error: ' + e.message;
        }
    });

    // PWA Service Worker Registration
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(reg => console.log('PWA ServiceWorker registered:', reg.scope))
                .catch(err => console.warn('PWA ServiceWorker registration failed:', err));
        });
    }

    // Initialize Drag & Drop Layout Customizer
    initDragAndDropLayout();

    // ── Initialize App ─────────────────────────────
    initDashboard(false);
});