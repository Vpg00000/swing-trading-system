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

        // Gauge update (stroke-dashoffset range is 125.6 to , matching 0% to 100%)
        const fill = document.getElementById('regimeGaugeFill');
        const score = regime.regime_score;
        const offset =