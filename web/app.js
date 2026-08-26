/**
 * app.js - Controller for Swing Trading Command Center dashboard.
 */

document.addEventListener('DOMContentLoaded', () => {
    // State Variables
    let reportData = null;
    let promptFiles = [];
    let activePrompt = null;

    // Elements
    const bootOverlay = document.getElementById('bootOverlay');
    const bootText = document.getElementById('bootText');
    const refreshBtn = document.getElementById('refreshBtn');
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    // ── Boot sequence simulation ──────────────────
    const bootMsgs = [
        'Connecting to local data pipeline...',
        'Parsing yfinance Nifty index history...',
        'Loading mutual fund NAVs from AMFI...',
        'Analyzing promoter holdings & pledge XBRL...',
        'Computing composite decision engine scores...',
        'Command center ready.'
    ];

    function runBoot(callback) {
        // Hide boot overlay immediately (< 50ms instant load)
        if (bootOverlay) {
            bootOverlay.classList.add('hide');
            bootOverlay.style.display = 'none';
            bootOverlay.remove();
        }
        if (callback) callback();
    }

    // ── Tab Navigation & Asynchronous Lazy Loader ──
    const loadedTabs = { screener: false, overview: false, insights: false, health: false };

    function triggerTabLazyLoad(tabId) {
        if (loadedTabs[tabId]) return;
        loadedTabs[tabId] = true;

        if (tabId === 'insights') {
            loadTopDeliveries();
            loadFiiDii();
            loadCyclicalTrend();
            loadFilings();
        } else if (tabId === 'overview') {
            initDashboard(false);
        } else if (tabId === 'health') {
            loadHealthWatchdog();
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

    // ── Data Fetching & Rendering ──────────────────
    async function initDashboard(forceRefresh = false) {
        try {
            if (forceRefresh) {
                refreshBtn.classList.add('loading');
            }

            // Fetch report calculations
            const res = await fetch(`/api/report-data?refresh=${forceRefresh}`);
            if (!res.ok) throw new Error("Failed to load report data");
            reportData = await res.json();

            // Fetch prompt templates
            const pres = await fetch('/api/prompts');
            if (pres.ok) {
                promptFiles = await pres.json();
            }

            // Render elements
            renderHeader();
            renderOverview();
            renderAllocation();
            renderCandidates();
            renderPrompts();
            renderRawText();
            renderHealth();

        } catch (err) {
            console.error("Dashboard init failed", err);
            alert("Error running dashboard calculations: " + err.message);
        } finally {
            if (forceRefresh) {
                refreshBtn.classList.remove('loading');
            }
        }
    }

    // ── Rendering Helpers ─────────────────────────

    function renderHeader() {
        if (!reportData) return;
        
        // Dhan active badge
        const badge = document.getElementById('dhanStatusBadge');
        if (reportData.dhan_active) {
            badge.className = 'status-badge active';
            badge.innerHTML = '<i class="fa-solid fa-link"></i> DHAN LIVE';
        } else {
            badge.className = 'status-badge inactive';
            badge.innerHTML = '<i class="fa-solid fa-link-slash"></i> DHAN STUB';
        }

        // Nifty and VIX tickers
        const regime = reportData.regime;
        document.getElementById('niftyVal').textContent = formatNum(regime.nifty_close);
        document.getElementById('vixVal').textContent = regime.vix.toFixed(2);
    }

    function renderOverview() {
        if (!reportData) return;
        const regime = reportData.regime;

        // Gauge update (stroke-dashoffset range is 125.6 to 0, matching 0% to 100%)
        const fill = document.getElementById('regimeGaugeFill');
        const score = regime.regime_score;
        const offset = 125.6 * (1 - score / 100);
        fill.style.strokeDashoffset = offset;
        
        // Gauge colors based on score
        if (score >= 60) fill.style.stroke = 'var(--color-mint)';
        else if (score >= 25) fill.style.stroke = 'var(--color-amber)';
        else fill.style.stroke = 'var(--color-red)';

        document.getElementById('regimeScoreVal').textContent = score.toFixed(1);
        document.getElementById('regimeStateVal').textContent = regime.regime;
        document.getElementById('regimeNotes').textContent = regime.notes;

        // Capital
        const cap = reportData.capital;
        const cash = reportData.portfolio.cash_inr || 0.0;
        const invested = cap - cash;
        document.getElementById('capTotal').textContent = formatLakh(cap);
        document.getElementById('capCash').textContent = formatLakh(cash);
        document.getElementById('capInvested').textContent = formatLakh(invested);
        document.getElementById('capMaxEquity').textContent = (regime.max_equity_exposure * 100).toFixed(0) + '%';

        // Subscores meters
        const container = document.getElementById('regimeSubscores');
        container.innerHTML = '';
        const subfactors = [
            { label: 'Trend Score', val: regime.trend_score, color: 'var(--color-blue)' },
            { label: 'Volatility Score', val: regime.volatility_score, color: 'var(--color-mint)' },
            { label: 'Breadth Score', val: regime.breadth_score, color: 'var(--color-blue)' },
            { label: 'Institutional Score', val: regime.institutional_score, color: 'var(--color-blue)' },
            { label: 'Global Score', val: regime.global_score, color: 'var(--color-blue)' },
            { label: 'Liquidity Score', val: regime.liquidity_score, color: 'var(--color-mint)' }
        ];

        subfactors.forEach(f => {
            const row = document.createElement('div');
            row.className = 'meter-row';
            row.innerHTML = `
                <div class="meter-header">
                    <span class="meter-label">${f.label}</span>
                    <span class="meter-value">${f.val.toFixed(1)}</span>
                </div>
                <div class="meter-bar">
                    <div class="meter-bar-fill" style="width: ${f.val}%; background-color: ${f.color};"></div>
                </div>
            `;
            container.appendChild(row);
        });
    }

    function renderAllocation() {
        if (!reportData) return;
        const drift = reportData.drift_table;
        const tbody = document.querySelector('#driftTable tbody');
        tbody.innerHTML = '';

        if (!drift) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No drift data available</td></tr>';
        } else {
            let totalTargetPct = 0, totalTargetVal = 0, totalActualPct = 0, totalActualVal = 0;
            for (const [sleeve, v] of Object.entries(drift)) {
                totalTargetPct += v.target_pct;
                totalTargetVal += v.target_inr;
                totalActualPct += v.actual_pct;
                totalActualVal += v.actual_inr;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="font-sans font-bold">${sleeve}</td>
                    <td>${(v.target_pct * 100).toFixed(1)}%</td>
                    <td>${formatLakh(v.target_inr)}</td>
                    <td>${(v.actual_pct * 100).toFixed(1)}%</td>
                    <td>${formatLakh(v.actual_inr)}</td>
                    <td class="${v.drift_pct >= 0 ? 'text-mint' : 'text-red'}">${v.drift_pct >= 0 ? '+' : ''}${(v.drift_pct * 100).toFixed(1)}%</td>
                    <td class="${v.drift_inr >= 0 ? 'text-mint' : 'text-red'}">${v.drift_inr >= 0 ? '+' : ''}${formatLakh(v.drift_inr)}</td>
                `;
                tbody.appendChild(tr);
            }
            
            const totalDriftPct = totalActualPct - totalTargetPct;
            const totalDriftVal = totalActualVal - totalTargetVal;

            const tfoot = document.createElement('tr');
            tfoot.style.borderTop = '2px solid var(--border-color)';
            tfoot.className = 'font-bold';
            tfoot.innerHTML = `
                <td>Total</td>
                <td>${(totalTargetPct * 100).toFixed(1)}%</td>
                <td>${formatLakh(totalTargetVal)}</td>
                <td>${(totalActualPct * 100).toFixed(1)}%</td>
                <td>${formatLakh(totalActualVal)}</td>
                <td class="${totalDriftPct >= 0 ? 'text-mint' : 'text-red'}">${totalDriftPct >= 0 ? '+' : ''}${(totalDriftPct * 100).toFixed(1)}%</td>
                <td class="${totalDriftVal >= 0 ? 'text-mint' : 'text-red'}">${totalDriftVal >= 0 ? '+' : ''}${formatLakh(totalDriftVal)}</td>
            `;
            tbody.appendChild(tfoot);
        }

        // Holdings Reconciliation
        const holdingsTbody = document.querySelector('#holdingsTable tbody');
        holdingsTbody.innerHTML = '';
        const holdings = reportData.portfolio.holdings;

        if (!holdings || holdings.length === 0) {
            holdingsTbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">No holdings currently active — portfolio is in cash</td></tr>';
        } else {
            holdings.forEach(h => {
                const dec = reportData.decisions[h.symbol];
                const match = reportData.ranked_candidates.find(c => c.symbol === h.symbol);
                const rank = match ? reportData.ranked_candidates.indexOf(match) + 1 : null;
                const status = rank ? `Rank #${rank}` : 'Out of universe';

                // Find drift
                const sleeve = h.sleeve || 'Core momentum equity';
                let target = 0.0;
                if (drift && sleeve in drift) {
                    if (sleeve === 'Core momentum equity') {
                        target = match ? Math.min(match.position_size_inr, reportData.capital * MAX_SINGLE_STOCK_PCT) : reportData.capital * MAX_SINGLE_STOCK_PCT;
                    } else {
                        target = drift[sleeve].target_inr;
                    }
                }
                const driftVal = h.value_inr - target;

                // Tax details
                const tax = reportData.tax_statuses.find(ts => ts.symbol === h.symbol);
                
                let gainPct = 0.0;
                if (h.buy_price && h.quantity) {
                    const cost = h.buy_price * h.quantity;
                    gainPct = (h.value_inr / cost - 1) * 100;
                }

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="font-sans font-bold text-mint">${h.symbol}</td>
                    <td class="font-sans text-xs">${sleeve}</td>
                    <td class="font-sans text-xs">${status}</td>
                    <td>${formatLakh(h.value_inr)}</td>
                    <td class="${driftVal >= 0 ? 'text-mint' : 'text-red'}">${driftVal >= 0 ? '+' : ''}${formatLakh(driftVal)}</td>
                    <td>${tax ? `<span class="badge ${tax.is_ltcg ? 'badge-ltcg' : 'badge-stcg'}">${tax.is_ltcg ? 'LTCG' : 'STCG'}</span>` : '--'}</td>
                    <td>${tax ? tax.days_held + 'd' : '--'}</td>
                    <td class="${gainPct >= 0 ? 'text-mint' : 'text-red'}">${gainPct >= 0 ? '+' : ''}${gainPct.toFixed(1)}%</td>
                    <td>${tax ? formatLakh(estimateTax(tax)) : '₹0.00L'}</td>
                `;
                holdingsTbody.appendChild(tr);
            });
        }

        // Tax Harvesting & Alerts
        const alertContainer = document.getElementById('taxHarvestingContainer');
        const alertsDiv = document.getElementById('taxAlerts');
        alertsDiv.innerHTML = '';
        let hasAlerts = false;

        if (reportData.countdown_flags && reportData.countdown_flags.length > 0) {
            hasAlerts = true;
            reportData.countdown_flags.forEach(f => {
                const item = document.createElement('div');
                item.className = 'alert-item info';
                item.innerHTML = `<i class="fa-solid fa-hourglass-half"></i> <strong>${f.symbol}</strong> is approaching LTCG status in <strong>${f.days_to_ltcg} day(s)</strong>. Holding onto this position could significantly reduce tax liabilities.`;
                alertsDiv.appendChild(item);
            });
        }

        if (reportData.harvest_candidates && reportData.harvest_candidates.length > 0) {
            hasAlerts = true;
            reportData.harvest_candidates.forEach(f => {
                const item = document.createElement('div');
                item.className = 'alert-item';
                item.innerHTML = `<i class="fa-solid fa-arrow-down-trend-line"></i> <strong>${f.symbol}</strong> has an unrealized loss of <strong>${formatLakh(Math.abs(f.unrealized_gain_inr))}</strong>. Consider tax-loss harvesting to offset capital gains.`;
                alertsDiv.appendChild(item);
            });
        }

        if (hasAlerts) {
            alertContainer.classList.remove('hidden');
        } else {
            alertContainer.classList.add('hidden');
        }
    }

    function renderCandidates() {
        if (!reportData) return;
        const candidates = reportData.ranked_candidates;
        const container = document.getElementById('candidatesList');
        container.innerHTML = '';

        // Render suggested actions summary
        const actionsDiv = document.getElementById('actionsSummary');
        actionsDiv.innerHTML = '';
        if (reportData.suggested_actions && reportData.suggested_actions.length > 0) {
            reportData.suggested_actions.forEach(act => {
                const box = document.createElement('div');
                const isSell = act.includes('EXIT') || act.includes('REDUCE');
                box.className = `action-box ${isSell ? 'sell' : 'buy'}`;
                box.innerHTML = `<strong>${act.split(' ')[0]}</strong> ${act.split(' ').slice(1).join(' ')}`;
                actionsDiv.appendChild(box);
            });
        } else {
            actionsDiv.innerHTML = '<div class="action-box text-center text-muted">No actions recommended today (regime risk-off or no setups).</div>';
        }

        // Render cards
        candidates.forEach((c, idx) => {
            const dec = reportData.decisions[c.symbol];
            if (!dec) return;

            const rank = idx + 1;
            const normMomentum = (1.0 - (rank - 1) / Math.max(candidates.length - 1, 1)) * 100;
            const actionClass = dec.suggested_action.toLowerCase().replace(/_/g, '_');
            const mf = reportData.money_flow[c.symbol];
            
            const card = document.createElement('div');
            card.className = 'candidate-card';
            card.innerHTML = `
                <div class="candidate-summary">
                    <div class="c-left">
                        <span class="c-rank">RANK #${rank}</span>
                        <span class="c-symbol">${c.symbol}</span>
                        <span class="c-badge ${actionClass}">${dec.suggested_action}</span>
                    </div>
                    <div class="c-right">
                        <button class="btn btn-sm" onclick="event.stopPropagation(); window.viewInGrid('${c.symbol}');" style="background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid rgba(59,130,246,0.4); padding: 4px 10px; border-radius: 4px; font-weight: 600; cursor: pointer; margin-right: 10px;">
                            <i class="fa-solid fa-table"></i> Grid
                        </button>
                        <div>
                            <div class="c-score-label">Composite Score</div>
                            <div class="c-score-val">${(dec.overall_score || 0).toFixed(1)}/100</div>
                        </div>
                        <i class="fa-solid fa-chevron-down c-toggle"></i>
                    </div>
                </div>
                <div class="candidate-details">
                    <div class="details-grid">
                        <div class="details-left">
                            <div class="meter-row">
                                <div class="meter-header">
                                    <span class="meter-label">Technical / RS Score</span>
                                    <span class="meter-value">${(dec.technical_component || 0).toFixed(1)}/15</span>
                                </div>
                                <div class="meter-bar"><div class="meter-bar-fill" style="width: ${((dec.technical_component || 0)/15)*100}%; background-color: var(--color-blue);"></div></div>
                            </div>
                            <div class="meter-row">
                                <div class="meter-header">
                                    <span class="meter-label">Sector Strength (${c.sector || 'N/A'})</span>
                                    <span class="meter-value">${(dec.sector_component || 0).toFixed(1)}/10</span>
                                </div>
                                <div class="meter-bar"><div class="meter-bar-fill" style="width: ${((dec.sector_component || 0)/10)*100}%; background-color: var(--color-blue);"></div></div>
                            </div>
                            <div class="meter-row">
                                <div class="meter-header">
                                    <span class="meter-label">FII / DII Flow</span>
                                    <span class="meter-value">${(dec.fii_dii_component || 0).toFixed(1)}/15</span>
                                </div>
                                <div class="meter-bar"><div class="meter-bar-fill" style="width: ${((dec.fii_dii_component || 0)/15)*100}%; background-color: var(--color-blue);"></div></div>
                            </div>
                        </div>
                        <div class="details-right">
                            <div class="meter-row">
                                <div class="meter-header">
                                    <span class="meter-label">Catalyst Score</span>
                                    <span class="meter-value">${(dec.catalyst_component || 0).toFixed(1)}/15</span>
                                </div>
                                <div class="meter-bar"><div class="meter-bar-fill" style="width: ${((dec.catalyst_component || 0)/15)*100}%; background-color: var(--color-blue);"></div></div>
                            </div>
                            <div class="meter-row">
                                <div class="meter-header">
                                    <span class="meter-label">Fundamental & Valuation Score</span>
                                    <span class="meter-value">${((dec.fundamental_component || 0) + (dec.valuation_component || 0)).toFixed(1)}/15</span>
                                </div>
                                <div class="meter-bar"><div class="meter-bar-fill" style="width: ${(((dec.fundamental_component || 0) + (dec.valuation_component || 0))/15)*100}%; background-color: var(--color-blue);"></div></div>
                            </div>
                            
                            <div class="stat-row" style="padding-top:0.4rem; padding-bottom:0.4rem;">
                                <span class="stat-label" style="font-size:0.8rem;">ATR Stop Price</span>
                                <span class="stat-value" style="font-size:0.95rem;">₹${(c.stop_price || 0).toFixed(1)} (${((c.stop_distance_pct || 0)*100).toFixed(1)}%)</span>
                            </div>
                        </div>
                        <div class="detail-notes font-mono">
                            <strong>MONEY FLOW NOTES:</strong> ${mf && mf.notes && mf.notes.length > 0 ? mf.notes.join('; ') : 'No special institutional activity recorded.'}<br/>
                            <strong>RISK CONCERNS:</strong> ${dec.concerns && dec.concerns.length > 0 ? dec.concerns.join(', ') : 'No high-risk warnings active.'}
                        </div>
                    </div>
                </div>
            `;

            // Accordion listener
            const summary = card.querySelector('.candidate-summary');
            summary.addEventListener('click', () => {
                card.classList.toggle('open');
            });

            container.appendChild(card);
        });
    }

    function renderPrompts() {
        const listDiv = document.getElementById('promptsList');
        listDiv.innerHTML = '';
        const titleSpan = document.getElementById('activePromptTitle');
        const bodyPre = document.getElementById('activePromptBody');
        const copyBtn = document.getElementById('copyPromptBtn');

        if (!promptFiles || promptFiles.length === 0) {
            listDiv.innerHTML = '<span class="text-center text-muted font-mono text-xs">No active event prompts saved today.</span>';
            titleSpan.textContent = 'No prompts available';
            bodyPre.textContent = 'Run a report to trigger news-catalyst prompt writing.';
            copyBtn.classList.add('hidden');
            return;
        }

        // Render buttons
        promptFiles.forEach((p, idx) => {
            const btn = document.createElement('button');
            btn.className = 'prompt-tab-btn';
            btn.textContent = p.filename;
            btn.title = p.filename;
            
            btn.addEventListener('click', () => {
                document.querySelectorAll('.prompt-tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                activePrompt = p;
                
                titleSpan.textContent = p.filename;
                bodyPre.textContent = p.content;
                copyBtn.classList.remove('hidden');
            });
            
            listDiv.appendChild(btn);
        });

        // Load first prompt as default
        listDiv.children[0].click();
    }

    function renderRawText() {
        if (!reportData) return;
        fetch('/api/text-report')
            .then(res => res.text())
            .then(text => {
                document.getElementById('rawReportText').textContent = text;
            });
    }

    function renderHealth() {
        if (!reportData) return;
        const tbody = document.querySelector('#healthTable tbody');
        tbody.innerHTML = '';

        for (const [source, status] of Object.entries(reportData.data_health)) {
            const isSuccess = status.includes('SUCCESS');
            const statusClass = isSuccess ? 'text-mint' : 'text-red';
            const icon = isSuccess ? '<i class="fa-solid fa-circle-check"></i>' : '<i class="fa-solid fa-circle-exclamation"></i>';
            
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="font-sans font-bold">${source}</td>
                <td class="${statusClass}">${icon} ${status}</td>
            `;
            tbody.appendChild(tr);
        }
    }

    // ── Button Triggers ───────────────────────────

    // Refresh Pipeline button
    refreshBtn.addEventListener('click', () => {
        initDashboard(true);
    });

    // Copy prompt button
    document.getElementById('copyPromptBtn').addEventListener('click', () => {
        if (!activePrompt) return;
        navigator.clipboard.writeText(activePrompt.content)
            .then(() => {
                const btn = document.getElementById('copyPromptBtn');
                btn.innerHTML = '<i class="fa-solid fa-circle-check"></i> COPIED!';
                setTimeout(() => {
                    btn.innerHTML = '<i class="fa-solid fa-copy"></i> COPY PROMPT';
                }, 1500);
            });
    });

    // Copy text report button
    document.getElementById('copyReportBtn').addEventListener('click', () => {
        const text = document.getElementById('rawReportText').textContent;
        navigator.clipboard.writeText(text)
            .then(() => {
                const btn = document.getElementById('copyReportBtn');
                btn.innerHTML = '<i class="fa-solid fa-circle-check"></i> COPIED!';
                setTimeout(() => {
                    btn.innerHTML = '<i class="fa-solid fa-copy"></i> COPY REPORT';
                }, 1500);
            });
    });

    // ── Number Format Utilities ────────────────────
    
    function formatNum(val) {
        if (val === null || val === undefined) return '--';
        return val.toLocaleString('en-IN', { maximumFractionDigits: 2 });
    }

    function formatLakh(val) {
        if (val === null || val === undefined) return '₹0.00L';
        const lakhs = val / 1e5;
        return '₹' + lakhs.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'L';
    }

    function estimateTax(taxStat) {
        const rate = taxStat.is_ltcg ? 0.125 : 0.20;
        return Math.max(0.0, taxStat.unrealized_gain_inr * rate);
    }

    // ── Screener & Market Insights Module ─────────────

    async function loadScreenerTemplates() {
        const container = document.getElementById('scanPresetsContainer');
        if (!container) return;

        try {
            const resp = await fetch('/api/screener/templates');
            const templates = await resp.json();
            
            container.innerHTML = templates.map(t => `
                <div class="preset-card" style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); padding: 12px; border-radius: 6px; cursor: pointer; transition: all 0.2s;"
                     onclick="runScreenerTemplate('${t.id}')"
                     onmouseover="this.style.borderColor='#10b981'"
                     onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                    <div style="font-weight: 600; color: #10b981; font-size: 0.95rem; margin-bottom: 4px;">${t.name}</div>
                    <div style="font-size: 0.8rem; color: #aaa;">${t.description}</div>
                </div>
            `).join('');
        } catch (e) {
            console.error('Failed to load screener templates:', e);
        }
    }

    window.runScreenerTemplate = async function(templateId) {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: #10b981; padding: 20px;"><i class="fa-solid fa-spinner fa-spin"></i> Screening universe & computing AI predictions...</td></tr>';

        try {
            const resp = await fetch('/api/screener/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ template_id: templateId })
            });
            const data = await resp.json();
            renderScreenerResults(data.results || []);
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: #ef4444; padding: 20px;">Failed to execute screener: ${e.message}</td></tr>`;
        }
    };

    function renderScreenerResults(results) {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;

        if (!results.length) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; color: #888; padding: 20px;">No candidates passed the filter criteria.</td></tr>';
            return;
        }

        tbody.innerHTML = results.map(r => {
            const actionColor = r.action === 'BUY_NOW' ? '#10b981' : (r.action === 'WATCH' ? '#f59e0b' : '#ef4444');
            return `
                <tr>
                    <td class="font-bold">${r.symbol.replace('.NS', '')}</td>
                    <td>₹${formatNum(r.close)}</td>
                    <td>${formatNum(r.rsi)}</td>
                    <td>${r.macd_bullish ? '<span style="color:#10b981;">BULLISH</span>' : '<span style="color:#888;">BEARISH</span>'}</td>
                    <td>${formatNum(r.pe)}</td>
                    <td>${formatNum(r.roe)}%</td>
                    <td style="font-weight:700; color:#10b981;">${r.composite_score}/100</td>
                    <td style="font-weight:700; color:${actionColor};">${r.action}</td>
                    <td>₹${formatNum(r.target_price)}</td>
                    <td>₹${formatNum(r.stop_loss)}</td>
                    <td style="font-weight:600;">1:${formatNum(r.rr_ratio)}</td>
                </tr>
            `;
        }).join('');
    }

    async function loadTopDeliveries() {
        const tbody = document.getElementById('topDeliveriesTableBody');
        if (!tbody) return;

        try {
            const resp = await fetch('/api/insights/top-deliveries');
            const data = await resp.json();

            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #888; padding: 20px;">No delivery data available for today. Run NSE Bhavcopy fetcher first.</td></tr>';
                return;
            }

            tbody.innerHTML = data.map(r => `
                <tr>
                    <td class="font-bold">${r.symbol}</td>
                    <td>₹${formatNum(r.close)}</td>
                    <td>${r.traded_qty.toLocaleString('en-IN')}</td>
                    <td>${r.delivered_qty.toLocaleString('en-IN')}</td>
                    <td style="font-weight:700; color:#10b981;">${r.delivery_pct}%</td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 20px;">Failed to load delivery data: ${e.message}</td></tr>`;
        }
    }

    // Bind Run Custom Screener button
    const runBtn = document.getElementById('runCustomScreenerBtn');
    if (runBtn) {
        runBtn.addEventListener('click', () => {
            window.runScreenerTemplate('momentum-breakout');
        });
    }

    async function loadFiiDii() {
        const tbody = document.getElementById('fiiDiiTableBody');
        if (!tbody) return;
        try {
            const resp = await fetch('/api/insights/fii-dii');
            const data = await resp.json();
            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #888; padding: 20px;">No FII/DII flow records found.</td></tr>';
                return;
            }
            tbody.innerHTML = data.map(r => {
                const fiiNet = r.fii_net || 0;
                const diiNet = r.dii_net || 0;
                const total = fiiNet + diiNet;
                const fiiColor = fiiNet >= 0 ? '#10b981' : '#ef4444';
                const diiColor = diiNet >= 0 ? '#10b981' : '#ef4444';
                const totColor = total >= 0 ? '#10b981' : '#ef4444';
                return `
                    <tr>
                        <td class="font-bold">${r.date}</td>
                        <td>₹${formatNum(r.fii_buy)}</td>
                        <td>₹${formatNum(r.fii_sell)}</td>
                        <td style="font-weight:700; color:${fiiColor};">₹${fiiNet > 0 ? '+' : ''}${formatNum(fiiNet)}</td>
                        <td>₹${formatNum(r.dii_buy)}</td>
                        <td>₹${formatNum(r.dii_sell)}</td>
                        <td style="font-weight:700; color:${diiColor};">₹${diiNet > 0 ? '+' : ''}${formatNum(diiNet)}</td>
                        <td style="font-weight:700; color:${totColor};">₹${total > 0 ? '+' : ''}${formatNum(total)}</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: #ef4444; padding: 20px;">Failed to load FII/DII data: ${e.message}</td></tr>`;
        }
    }

    async function loadCyclicalTrend() {
        const tbody = document.getElementById('cyclicalTableBody');
        if (!tbody) return;
        try {
            const resp = await fetch('/api/insights/cyclical');
            const data = await resp.json();
            const months = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"];
            tbody.innerHTML = data.map(r => `
                <tr>
                    <td class="font-bold">${r.fy}</td>
                    ${months.map(m => {
                        const val = r[m] || '-';
                        let color = '#aaa';
                        if (val.startsWith('+')) color = '#10b981';
                        else if (val.startsWith('-') && val !== '-') color = '#ef4444';
                        return `<td style="color:${color}; font-weight:600;">${val}</td>`;
                    }).join('')}
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="13" style="text-align: center; color: #ef4444; padding: 20px;">Failed to load cyclical matrix: ${e.message}</td></tr>`;
        }
    }

    async function loadFilings() {
        const tbody = document.getElementById('filingsTableBody');
        if (!tbody) return;
        try {
            const resp = await fetch('/api/insights/filings');
            const data = await resp.json();
            if (!data.length) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #888; padding: 20px;">No corporate announcements recorded today.</td></tr>';
                return;
            }
            tbody.innerHTML = data.map(f => `
                <tr>
                    <td style="color:#aaa; font-size:0.85rem;">${f.date || '--'}</td>
                    <td class="font-bold">${f.symbol}</td>
                    <td><span style="background:rgba(255,255,255,0.05); padding:2px 8px; border-radius:4px; font-size:0.8rem;">${f.category}</span></td>
                    <td style="font-size:0.9rem;">${f.subject}</td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #ef4444; padding: 20px;">Failed to load corporate filings: ${e.message}</td></tr>`;
        }
    }

    // ── PRO DATA GRID & SQLITE FAST QUERY MODULE ─────────────

    let currentGridCategory = 'ALL';
    let currentGridSort = 'composite_score';
    let currentGridAscending = false;
    let currentGridSearch = '';

    async function loadStocksGrid() {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: #10b981; padding: 20px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading sub-10ms SQLite grid...</td></tr>';

        try {
            const queryParams = new URLSearchParams({
                category: currentGridCategory,
                sort_by: currentGridSort,
                ascending: currentGridAscending,
                search: currentGridSearch
            });

            const resp = await fetch(`/api/grid/stocks?${queryParams.toString()}`);
            const data = await resp.json();
            renderProGridResults(data.results || []);
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: #ef4444; padding: 20px;">Failed to load grid: ${e.message}</td></tr>`;
        }
    }

    function renderProGridResults(results) {
        const tbody = document.getElementById('screenerTableBody');
        if (!tbody) return;

        if (!results.length) {
            tbody.innerHTML = '<tr><td colspan="12" style="text-align: center; color: #888; padding: 20px;">No stocks found matching the active category or search query. Click "SYNC ALL DATA" to refresh.</td></tr>';
            return;
        }

        tbody.innerHTML = results.map(r => {
            const actionColor = r.action === 'BUY_NOW' ? '#10b981' : (r.action === 'WATCH' ? '#f59e0b' : '#ef4444');
            const capColor = r.cap_category === 'PENNY' ? '#f59e0b' : (r.cap_category === 'LARGE' ? '#3b82f6' : '#a855f7');
            const netReturn = r.net_alpha_pct || 0;
            const netColor = netReturn >= 0 ? '#10b981' : '#ef4444';

            return `
                <tr>
                    <td class="font-bold">
                        ${r.symbol.replace('.NS', '')}
                        <span style="font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: rgba(255,255,255,0.08); color: ${capColor}; margin-left: 4px;">${r.cap_category || 'SM'}</span>
                    </td>
                    <td>₹${formatNum(r.close)}</td>
                    <td>${formatNum(r.rsi)}</td>
                    <td>${formatNum(r.pe)}</td>
                    <td>${formatNum(r.roe)}%</td>
                    <td style="font-weight:600;">${formatNum(r.delivery_pct)}%</td>
                    <td style="font-weight:700; color:#10b981;">${r.composite_score}/100</td>
                    <td style="font-weight:700; color:${actionColor};">${r.action}</td>
                    <td>₹${formatNum(r.target_price)}</td>
                    <td>₹${formatNum(r.stop_loss)}</td>
                    <td style="font-weight:600;">1:${formatNum(r.rr_ratio)}</td>
                    <td style="font-weight:700; color:${netColor};">+${formatNum(netReturn)}%</td>
                </tr>
            `;
        }).join('');
    }

    // Category Tabs Handler
    document.querySelectorAll('.grid-tab').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.grid-tab').forEach(b => {
                b.style.background = 'rgba(255,255,255,0.05)';
                b.style.color = b.dataset.cat === 'PENNY' ? '#f59e0b' : '#fff';
            });
            e.target.style.background = '#10b981';
            e.target.style.color = '#000';
            currentGridCategory = e.target.dataset.cat;
            loadStocksGrid();
        });
    });

    // Sortable Headers Handler
    document.querySelectorAll('#screenerTable thead th[data-sort]').forEach(th => {
        th.addEventListener('click', (e) => {
            const sortKey = th.dataset.sort;
            if (currentGridSort === sortKey) {
                currentGridAscending = !currentGridAscending;
            } else {
                currentGridSort = sortKey;
                currentGridAscending = false;
            }
            loadStocksGrid();
        });
    });

    // Search Input Handler (debounce 300ms)
    let searchTimeout;
    const searchInput = document.getElementById('gridSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                currentGridSearch = e.target.value;
                loadStocksGrid();
            }, 300);
        });
    }

    // One-Click Sync All Button Handler
    const syncBtn = document.getElementById('oneClickSyncBtn');
    if (syncBtn) {
        syncBtn.addEventListener('click', async () => {
            syncBtn.disabled = true;
            syncBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> SYNCING ALL 500 STOCKS...';
            try {
                const resp = await fetch('/api/sync/all', { method: 'POST' });
                const res = await resp.json();
                syncBtn.innerHTML = '<i class="fa-solid fa-check"></i> SYNCED!';
                loadStocksGrid();
                setTimeout(() => {
                    syncBtn.disabled = false;
                    syncBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> SYNC ALL DATA';
                }, 2000);
            } catch (e) {
                syncBtn.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> SYNC ERROR';
                setTimeout(() => {
                    syncBtn.disabled = false;
                    syncBtn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> SYNC ALL DATA';
                }, 2000);
            }
        });
    }

    // Toast Notification Manager Overlay
    function showToast(message, type = 'info') {
        let toastContainer = document.getElementById('toastContainer');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toastContainer';
            toastContainer.style.cssText = 'position: fixed; bottom: 20px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 8px;';
            document.body.appendChild(toastContainer);
        }

        const toast = document.createElement('div');
        const bg = type === 'success' ? '#10b981' : (type === 'error' ? '#ef4444' : '#3b82f6');
        toast.style.cssText = `background: ${bg}; color: #fff; padding: 10px 16px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; box-shadow: 0 4px 12px rgba(0,0,0,0.3); opacity: 0; transition: opacity 0.3s ease;`;
        toast.innerHTML = message;
        toastContainer.appendChild(toast);

        setTimeout(() => toast.style.opacity = '1', 50);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // Export Table Data to CSV
    const exportCsvBtn = document.getElementById('exportCsvBtn');
    if (exportCsvBtn) {
        exportCsvBtn.addEventListener('click', () => {
            const table = document.getElementById('screenerTable');
            if (!table) return;
            let csv = [];
            for (let row of table.rows) {
                let cols = Array.from(row.cells).map(c => `"${c.innerText.replace(/"/g, '""').trim()}"`);
                csv.push(cols.join(','));
            }
            const blob = new Blob([csv.join('\n')], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `stock_grid_${new Date().toISOString().split('T')[0]}.csv`;
            a.click();
            showToast('✓ Stock Grid exported to CSV successfully!', 'success');
        });
    }

    // Global Hotkeys (/ for Search, S for Screener, R for Refresh)
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === '/') {
            e.preventDefault();
            const searchInput = document.getElementById('gridSearchInput');
            if (searchInput) searchInput.focus();
        } else if (e.key.toLowerCase() === 'r') {
            e.preventDefault();
            loadStocksGrid();
            showToast('Refreshed Stock Grid', 'info');
        }
    });

    // Jump to Stock Screener Grid for a specific symbol
    window.viewInGrid = function(symbol) {
        const screenerBtn = document.querySelector('.nav-btn[data-tab="screener"]');
        const tabPanes = document.querySelectorAll('.tab-pane');
        const navButtons = document.querySelectorAll('.nav-btn');

        navButtons.forEach(b => b.classList.remove('active'));
        tabPanes.forEach(p => p.classList.remove('active'));

        if (screenerBtn) screenerBtn.classList.add('active');
        const screenerPane = document.getElementById('screener');
        if (screenerPane) screenerPane.classList.add('active');

        const searchInput = document.getElementById('gridSearchInput');
        const cleanSym = (symbol || '').replace('.NS', '').trim();
        if (searchInput) searchInput.value = cleanSym;
        currentGridSearch = cleanSym;
        loadStocksGrid();
        showToast(`Filtered Grid for ${cleanSym}`, 'success');
    };

    async function loadHealthWatchdog() {
        try {
            const resp = await fetch('/healthz');
            const data = await resp.json();
            const watchdogEl = document.getElementById('healthWatchdogVal');
            const diskEl = document.getElementById('healthDiskVal');
            const pyEl = document.getElementById('healthPyVal');
            if (watchdogEl) watchdogEl.textContent = data.status || 'HEALTHY';
            if (diskEl) diskEl.textContent = `${data.free_disk_gb || 0} GB`;
            if (pyEl) pyEl.textContent = `Python ${data.python_version || ''}`;
        } catch (e) {
            console.warn("Health check fetch notice:", e);
        }
    }

    // Immediate Non-Blocking UI Initialization
    loadScreenerTemplates();
    loadStocksGrid();

    // Lazy Background Fetching for other tabs
    setTimeout(() => {
        initDashboard(false);
        loadHealthWatchdog();
    }, 100);
});
