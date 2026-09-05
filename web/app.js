/**
 * app.js - Controller for Swing Trading Command Center dashboard.
 */

document.addEventListener('DOMContentLoaded', () => {
    // State Variables
    let portfolioData = null;
    let promptFiles = [];
    let activePrompt = null;
    let healthData = null;
    let pricedInData = {};
    let healthInterval = null;

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
    const loadedTabs = { screener: false, overview: false, insights: false, health: false, sectors: false, sector: false, portfolio: false };

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
            startHealthPolling();
        } else if (tabId === 'sectors' || tabId === 'sector') {
            loadSectorRotation();
        } else if (tabId === 'portfolio') {
            loadPortfolio();
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
            loadSectorRotation();

        } catch (err) {
            console.error("Dashboard init failed", err);
            alert("Error running dashboard calculations: " + err.message);
        } finally {
            if (forceRefresh) {
                refreshBtn.classList.remove('loading');
            }
        }
    }

    // ── Portfolio Data Loading ──────────────────────
    async function loadPortfolio() {
        const container = document.getElementById('portfolioContainer');
        if (!container) return;

        container.innerHTML = '<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading portfolio data...</div>';

        try {
            const res = await fetch('/api/portfolio');
            if (!res.ok) throw new Error("Failed to fetch portfolio data");
            portfolioData = await res.json();
            renderPortfolio();
        } catch (err) {
            console.error("Portfolio load error:", err);
            container.innerHTML = `<div class="error-state"><i class="fa-solid fa-triangle-exclamation"></i> Error loading portfolio data: ${err.message}</div>`;
        }
    }

    function renderPortfolio() {
        const container = document.getElementById('portfolioContainer');
        if (!container || !portfolioData) return;

        let html = '';

        if (portfolioData.is_stale) {
            html += `<div class="stale-banner"><i class="fa-solid fa-triangle-exclamation"></i> Warning: Portfolio data may be stale. As of ${portfolioData.as_of ? new Date(portfolioData.as_of).toLocaleString() : 'unknown'}</div>`;
        } else if (portfolioData.as_of) {
            html += `<div class="timestamp-info"><i class="fa-solid fa-clock"></i> As of: ${new Date(portfolioData.as_of).toLocaleString()}</div>`;
        }

        // Render target allocation
        html += renderTargetAllocation(portfolioData.target_allocation);

        // Render actual holdings
        html += renderHoldings(portfolioData.holdings);

        // Render open positions
        html += renderPositions(portfolioData.positions);

        // Render daily trades
        html += renderTrades(portfolioData.trades);

        // Render open orders
        html += renderOrders(portfolioData.orders);

        // Render funds/cash
        html += renderFunds(portfolioData.funds);

        // Render drift metrics
        html += renderDriftMetrics(portfolioData.drift_metrics);

        container.innerHTML = html;
    }

    function renderTargetAllocation(allocation) {
        if (!allocation || allocation.length === 0) {
            return '<div class="empty-state">No target allocation data available.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Target Allocation</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Weight (%)</th>
                        </tr>
                    </thead>
                    <tbody>`;

        allocation.forEach(item => {
            html += `
                <tr>
                    <td>${item.symbol || '-'}</td>
                    <td>${item.quantity || '-'}</td>
                    <td>${item.weight ? item.weight.toFixed(2) : '-'}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    function renderHoldings(holdings) {
        if (!holdings || holdings.length === 0) {
            return '<div class="empty-state">No holdings data available.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Actual Holdings</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Average Price</th>
                            <th>Last Price</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>`;

        holdings.forEach(holding => {
            const pnl = holding.last_price && holding.average_price ?
                (holding.last_price - holding.average_price) * holding.quantity : 0;

            html += `
                <tr>
                    <td>${holding.symbol || '-'}</td>
                    <td>${holding.quantity || '-'}</td>
                    <td>${holding.average_price ? holding.average_price.toFixed(2) : '-'}</td>
                    <td>${holding.last_price ? holding.last_price.toFixed(2) : '-'}</td>
                    <td>${pnl.toFixed(2)}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    function renderPositions(positions) {
        if (!positions || positions.length === 0) {
            return '<div class="empty-state">No open positions.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Open Positions</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Entry Price</th>
                            <th>Current Price</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>`;

        positions.forEach(position => {
            const pnl = position.current_price && position.entry_price ?
                (position.current_price - position.entry_price) * position.quantity : 0;

            html += `
                <tr>
                    <td>${position.symbol || '-'}</td>
                    <td>${position.quantity || '-'}</td>
                    <td>${position.entry_price ? position.entry_price.toFixed(2) : '-'}</td>
                    <td>${position.current_price ? position.current_price.toFixed(2) : '-'}</td>
                    <td>${pnl.toFixed(2)}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    function renderTrades(trades) {
        if (!trades || trades.length === 0) {
            return '<div class="empty-state">No trades today.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Daily Trades</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Trade Type</th>
                            <th>Timestamp</th>
                        </tr>
                    </thead>
                    <tbody>`;

        trades.forEach(trade => {
            html += `
                <tr>
                    <td>${trade.symbol || '-'}</td>
                    <td>${trade.quantity || '-'}</td>
                    <td>${trade.price ? trade.price.toFixed(2) : '-'}</td>
                    <td>${trade.trade_type || '-'}</td>
                    <td>${trade.timestamp ? new Date(trade.timestamp).toLocaleString() : '-'}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    function renderOrders(orders) {
        if (!orders || orders.length === 0) {
            return '<div class="empty-state">No open orders.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Open Orders</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Order Type</th>
                            <th>Status</th>
                            <th>Timestamp</th>
                        </tr>
                    </thead>
                    <tbody>`;

        orders.forEach(order => {
            html += `
                <tr>
                    <td>${order.symbol || '-'}</td>
                    <td>${order.quantity || '-'}</td>
                    <td>${order.price ? order.price.toFixed(2) : '-'}</td>
                    <td>${order.order_type || '-'}</td>
                    <td>${order.status || '-'}</td>
                    <td>${order.timestamp ? new Date(order.timestamp).toLocaleString() : '-'}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    function renderFunds(funds) {
        if (!funds) {
            return '<div class="empty-state">No funds data available.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Funds & Cash</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Account</th>
                            <th>Balance</th>
                            <th>Currency</th>
                        </tr>
                    </thead>
                    <tbody>`;

        if (funds.cash) {
            html += `
                <tr>
                    <td>Cash</td>
                    <td>${funds.cash.balance ? funds.cash.balance.toFixed(2) : '-'}</td>
                    <td>${funds.cash.currency || '-'}</td>
                </tr>`;
        }

        if (funds.margin) {
            html += `
                <tr>
                    <td>Margin</td>
                    <td>${funds.margin.balance ? funds.margin.balance.toFixed(2) : '-'}</td>
                    <td>${funds.margin.currency || '-'}</td>
                </tr>`;
        }

        html += `</tbody></table></div>`;
        return html;
    }

    function renderDriftMetrics(metrics) {
        if (!metrics) {
            return '<div class="empty-state">No drift metrics available.</div>';
        }

        let html = `
            <div class="portfolio-section">
                <h3>Drift Metrics</h3>
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>Metric</th>
                            <th>Value</th>
                            <th>Threshold</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>`;

        if (metrics.allocation_drift) {
            html += `
                <tr>
                    <td>Allocation Drift</td>
                    <td>${metrics.allocation_drift.value ? metrics.allocation_drift.value.toFixed(2) : '-'}</td>
                    <td>${metrics.allocation_drift.threshold ? metrics.allocation_drift.threshold.toFixed(2) : '-'}</td>
                    <td>${metrics.allocation_drift.status || '-'}</td>
                </tr>`;
        }

        if (metrics.sector_drift) {
            html += `
                <tr>
                    <td>Sector Drift</td>
                    <td>${metrics.sector_drift.value ? metrics.sector_drift.value.toFixed(2) : '-'}</td>
                    <td>${metrics.sector_drift.threshold ? metrics.sector_drift.threshold.toFixed(2) : '-'}</td>
                    <td>${metrics.sector_drift.status || '-'}</td>
                </tr>`;
        }

        html += `</tbody></table></div>`;
        return html;
    }

    // ── Health Monitoring ──────────────────────────
    async function loadHealthWatchdog() {
        const container = document.getElementById('healthContainer');
        if (!container) return;

        container.innerHTML = '<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading system health data...</div>';

        try {
            const res = await fetch('/api/health');
            if (!res.ok) throw new Error("Failed to fetch health data");
            healthData = await res.json();
            renderHealth();
        } catch (err) {
            console.error("Health load error:", err);
            container.innerHTML = `<div class="error-state"><i class="fa-solid fa-triangle-exclamation"></i> Error loading health data: ${err.message}</div>`;
        }
    }

    function startHealthPolling() {
        if (healthInterval) clearInterval(healthInterval);
        healthInterval = setInterval(loadHealthWatchdog, 30000); // Poll every 30 seconds
    }

    function renderHealth() {
        const container = document.getElementById('healthContainer');
        if (!container || !healthData) return;

        let html = '';

        // Render overall system status
        html += renderSystemStatus(healthData.overall_status);

        // Render component health
        html += renderComponentHealth(healthData.components);

        container.innerHTML = html;
    }

    function renderSystemStatus(status) {
        if (!status) {
            return '<div class="empty-state">No system status available.</div>';
        }

        let statusClass = '';
        let statusIcon = '';

        switch (status.state) {
            case 'NORMAL':
                statusClass = 'status-normal';
                statusIcon = 'fa-solid fa-check-circle';
                break;
            case 'DEGRADED':
                statusClass = 'status-degraded';
                statusIcon = 'fa-solid fa-exclamation-triangle';
                break;
            case 'SAFE MODE':
                statusClass = 'status-safe-mode';
                statusIcon = 'fa-solid fa-shield';
                break;
            case 'TRADING BLOCKED':
                statusClass = 'status-trading-blocked';
                statusIcon = 'fa-solid fa-ban';
                break;
            default:
                statusClass = 'status-unknown';
                statusIcon = 'fa-solid fa-question-circle';
        }

        let html = `
            <div class="system-status ${statusClass}">
                <h3><i class="${statusIcon}"></i> System Status: ${status.state}</h3>
                <div class="status-details">
                    <p><strong>Last Updated:</strong> ${status.last_updated ? new Date(status.last_updated).toLocaleString() : 'Unknown'}</p>
                    <p><strong>Message:</strong> ${status.message || 'No additional information'}</p>
                </div>
            </div>`;

        return html;
    }

    function renderComponentHealth(components) {
        if (!components || components.length === 0) {
            return '<div class="empty-state">No component health data available.</div>';
        }

        let html = `
            <div class="component-health">
                <h3>Component Health</h3>
                <table class="health-table">
                    <thead>
                        <tr>
                            <th>Component</th>
                            <th>Status</th>
                            <th>Last Updated</th>
                            <th>Latency (ms)</th>
                            <th>Records</th>
                            <th>Error</th>
                            <th>Retry</th>
                        </tr>
                    </thead>
                    <tbody>`;

        components.forEach(component => {
            let statusClass = '';
            let statusIcon = '';

            switch (component.status) {
                case 'OK':
                    statusClass = 'status-ok';
                    statusIcon = 'fa-solid fa-check-circle';
                    break;
                case 'WARNING':
                    statusClass = 'status-warning';
                    statusIcon = 'fa-solid fa-exclamation-triangle';
                    break;
                case 'ERROR':
                    statusClass = 'status-error';
                    statusIcon = 'fa-solid fa-times-circle';
                    break;
                case 'UNKNOWN':
                    statusClass = 'status-unknown';
                    statusIcon = 'fa-solid fa-question-circle';
                    break;
                default:
                    statusClass = 'status-unknown';
                    statusIcon = 'fa-solid fa-question-circle';
            }

            html += `
                <tr>
                    <td>${component.name || '-'}</td>
                    <td class="${statusClass}"><i class="${statusIcon}"></i> ${component.status || '-'}</td>
                    <td>${component.last_updated ? new Date(component.last_updated).toLocaleString() : '-'}</td>
                    <td>${component.latency !== undefined ? component.latency : '-'}</td>
                    <td>${component.records !== undefined ? component.records : '-'}</td>
                    <td>${component.error || '-'}</td>
                    <td>${component.retry !== undefined ? component.retry : '-'}</td>
                </tr>`;
        });

        html += `</tbody></table></div>`;
        return html;
    }

    // ── Event Listeners ─────────────────────────────
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            const activeTab = document.querySelector('.nav-btn.active');
            if (activeTab) {
                const tabId = activeTab.getAttribute('data-tab');
                if (tabId === 'overview') {
                    initDashboard(true);
                } else if (tabId === 'health') {
                    loadHealthWatchdog();
                } else if (tabId === 'portfolio') {
                    loadPortfolio();
                }
            }
        });
    }

    // ── Initialize ──────────────────────────────────
    runBoot(() => {
        // Set default tab
        const defaultTab = document.querySelector('.nav-btn[data-tab="overview"]');
        if (defaultTab) {
            defaultTab.click();
        }
    });
});