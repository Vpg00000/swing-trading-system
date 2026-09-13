"""
tests/test_ui_feedback.py - Automated Unit & Integration Test Suite for UI Feedback & System Resilience (Phase 35 & 36).
Verifies Tasks T-395 through T-414.
"""

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


def test_index_html_ui_feedback_elements():
    """Verify web/index.html contains all Phase 35 & 36 UI feedback and resilience elements (T-395 to T-413)."""
    index_path = WEB_DIR / "index.html"
    assert index_path.exists(), "web/index.html does not exist"
    content = index_path.read_text(encoding="utf-8")

    # T-395: Level 2 WS Latency Dot & Text
    assert 'id="l2WsStatus"' in content
    assert 'id="l2WsLatencyDot"' in content
    assert 'id="l2WsLatencyText"' in content

    # T-397: SOR Visual Routing Animation Container
    assert 'id="sorRoutingAnimationContainer"' in content

    # T-398: Live Account Balance Refresh Spinner Button
    assert 'id="btnRefreshBrokerBalances"' in content
    assert 'id="brokerBalanceSpinner"' in content

    # T-399: Broker Connection Test Button
    assert 'id="btnTestBrokerConnections"' in content

    # T-400: Paper Trading Banner
    assert 'id="paperTradingBanner"' in content

    # T-401: Order Placement Confirmation Dialog & Fee Breakdown
    assert 'id="orderConfirmationModal"' in content
    assert 'id="confirmOrderSymbol"' in content
    assert 'id="confirmOrderGrossValue"' in content
    assert 'id="confirmFeeStt"' in content
    assert 'id="confirmFeeBrokerage"' in content
    assert 'id="confirmFeeExchange"' in content
    assert 'id="confirmFeeGst"' in content
    assert 'id="confirmFeeStamp"' in content
    assert 'id="confirmFeeNetTotal"' in content
    assert 'id="btnConfirmOrderSubmit"' in content

    # T-402: Slice Order Execution Progress Ring Modal
    assert 'id="sliceOrderProgressModal"' in content
    assert 'id="sliceProgressRingCircle"' in content
    assert 'id="sliceProgressPctText"' in content
    assert 'id="sliceProgressSliceText"' in content
    assert 'id="sliceExecutedQty"' in content
    assert 'id="sliceAlgoName"' in content

    # T-403: Vault API Key Visibility Toggle
    assert 'id="btnToggleVaultApiKey"' in content
    assert 'id="vaultApiKeyEyeIcon"' in content

    # T-404: Broker Disconnect Emergency Alert & 1-Click Failover
    assert 'id="brokerDisconnectModal"' in content
    assert 'id="btnEmergencyFailover"' in content
    assert 'id="disconnectedBrokerName"' in content

    # T-408: Self-Healing Diagnostic Popup
    assert 'id="selfHealingModal"' in content
    assert 'id="selfHealingIssueText"' in content

    # T-409: System Health Status Dot
    assert 'id="systemHealthBadge"' in content
    assert 'id="systemHealthDot"' in content
    assert 'id="systemHealthText"' in content

    # T-410: API Response Time Monitor Bar
    assert 'id="telemetryLatency"' in content

    # T-411: Error Log Viewer Drawer
    assert 'id="errorLogDrawer"' in content
    assert 'id="errorLogContainer"' in content
    assert 'id="headerErrorCountBadge"' in content
    assert 'id="btnOpenErrorLogs"' in content

    # T-412: Network Offline Banner
    assert 'id="networkOfflineText"' in content

    # T-413: Diagnostic Health Check Button & Result Modal
    assert 'id="btnRunDiagnosticCheck"' in content
    assert 'id="diagnosticResultModal"' in content
    assert 'id="diagnosticStatusSummary"' in content
    assert 'id="diagnosticTableBody"' in content


def test_style_css_ui_feedback_styles():
    """Verify web/style.css contains Phase 35 & 36 CSS animation keyframes and feedback styles (T-395 to T-413)."""
    style_path = WEB_DIR / "style.css"
    assert style_path.exists(), "web/style.css does not exist"
    content = style_path.read_text(encoding="utf-8")

    # T-395: Latency indicator classes
    assert ".latency-green" in content
    assert ".latency-yellow" in content
    assert ".latency-red" in content

    # T-396: Animated trade tape flash keyframes & classes
    assert "@keyframes tapeRowFlash" in content
    assert "@keyframes tapeRowFlashSell" in content
    assert ".tape-row-flash" in content
    assert ".tape-row-flash-sell" in content

    # T-397: SOR Visual Routing Nodes
    assert ".sor-node" in content
    assert ".sor-node.scanning" in content
    assert ".sor-node.selected" in content

    # T-400: Paper Trading Banner
    assert ".paper-trading-banner" in content

    # T-401, T-402, T-404, T-408, T-413: Modal Overlay & Dialog styles
    assert ".modal-overlay" in content
    assert ".modal-dialog" in content
    assert "@keyframes modalPopIn" in content

    # T-405: Toast progress bar & action button
    assert ".toast-progress-bar" in content
    assert ".toast-action-btn" in content
    assert ".toast-stacked" in content

    # T-411: Side Drawer Animation
    assert ".side-drawer" in content
    assert ".side-drawer.open" in content


def test_app_js_ui_feedback_functions():
    """Verify web/app.js implements all Phase 35 & 36 JavaScript feedback and resilience handlers (T-395 to T-413)."""
    app_path = WEB_DIR / "app.js"
    assert app_path.exists(), "web/app.js does not exist"
    content = app_path.read_text(encoding="utf-8")

    # T-395: Live WebSocket Latency Indicator
    assert "function updateL2WsLatency" in content

    # T-396: Animated Trade Tape Row Insertion Effect
    assert "function appendTradeTapeRow" in content

    # T-397: SOR Visual Routing Animation
    assert "function animateSorRouting" in content
    assert "function executeSorOrder" in content

    # T-398: Live Account Balance Refresh Spinner
    assert "function refreshMultiBrokerBalances" in content

    # T-399: Broker Connection Test Button
    assert "function testBrokerConnection" in content
    assert "function testAllBrokerConnections" in content

    # T-400: Paper Trading Banner Visual Indicator
    assert "function toggleGlobalPaperTradingMode" in content

    # T-401: Order Placement Confirmation Dialog
    assert "function showOrderConfirmationDialog" in content
    assert "function closeOrderConfirmationModal" in content

    # T-402: Slice Order Execution Progress Ring Modal
    assert "function showSliceOrderProgressModal" in content
    assert "function updateSliceProgress" in content
    assert "function closeSliceOrderProgressModal" in content

    # T-403: Vault Password Visibility Toggle
    assert "function toggleVaultApiKeyVisibility" in content

    # T-404: Broker Disconnect Emergency Alert & 1-Click Failover
    assert "function showBrokerDisconnectModal" in content
    assert "function closeBrokerDisconnectModal" in content
    assert "function triggerEmergencyFailover" in content

    # T-405, T-406, T-407: Toast Notification Upgrade & Error Parsing & Retry Action
    assert "function getHumanReadableError" in content
    assert "function showToast" in content
    assert "toast-action-btn" in content

    # T-408: Self-Healing Diagnostic Popup
    assert "function showSelfHealingPopup" in content
    assert "function closeSelfHealingModal" in content
    assert "function applySelfHealingFix" in content

    # T-409: System Health Status Indicator Dot
    assert "function updateSystemHealthStatus" in content

    # T-410: API Response Time Monitor Bar
    assert "function updateApiLatencyMonitor" in content

    # T-411: Error Log Viewer Drawer
    assert "function logSystemError" in content
    assert "function openErrorLogDrawer" in content
    assert "function closeErrorLogDrawer" in content
    assert "function clearSystemErrorLogs" in content
    assert "function exportErrorLogs" in content

    # T-412: Network Offline Detection Banner
    assert "function initNetworkOfflineDetection" in content
    assert "function handleOfflineState" in content
    assert "function handleOnlineState" in content

    # T-413: Diagnostic Health Check Suite
    assert "function runDiagnosticHealthCheck" in content
    assert "function renderDiagnosticResults" in content
    assert "function closeDiagnosticModal" in content


def test_minified_assets_production_readiness():
    """Verify style.min.css and app.min.js are built and non-empty."""
    min_css = WEB_DIR / "style.min.css"
    min_js = WEB_DIR / "app.min.js"
    assert min_css.exists() and min_css.stat().st_size > 0
    assert min_js.exists() and min_js.stat().st_size > 0
