"""
tests/test_ui_notifier_expansion.py - Comprehensive Test Suite for UI & Notifier Expansion Tasks.
Verifies TASK-071, TASK-072, TASK-073, TASK-074, and TASK-075.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from web_server import app
from engine.notifier import TelegramNotifier, WhatsAppNotifier, AlertDispatcher, default_dispatcher

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── TASK-071: TradingView Canvas Chart & Endpoint Tests ──
def test_chart_data_endpoint_defaults():
    """Test GET /api/chart/data with default parameters."""
    response = client.get("/api/chart/data")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "RELIANCE.NS"
    assert data["timeframe"] == "1D"
    assert "candles" in data
    assert "ema20" in data
    assert "ema50" in data
    assert "markers" in data
    assert data["count"] == 100
    assert len(data["candles"]) == 100

    # Verify candle object schema
    first_candle = data["candles"][0]
    for key in ["time", "open", "high", "low", "close", "volume"]:
        assert key in first_candle

    # Verify high >= low and open/close boundaries
    assert first_candle["high"] >= first_candle["low"]
    assert first_candle["volume"] > 0


def test_chart_data_endpoint_custom_params():
    """Test GET /api/chart/data with custom symbol, timeframe, and candle limit."""
    response = client.get("/api/chart/data?symbol=INFY.NS&timeframe=1W&limit=40")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "INFY.NS"
    assert data["timeframe"] == "1W"
    assert len(data["candles"]) == 40
    assert len(data["ema20"]) == 40
    assert len(data["ema50"]) == 40


# ── TASK-072: Telegram & WhatsApp Notifier Engine & Endpoint Tests ──
def test_telegram_notifier_mock_mode():
    """Test TelegramNotifier in mock mode."""
    notifier = TelegramNotifier(bot_token="", chat_id="", enabled=True)
    res = notifier.send_message("Test Telegram alert message")
    assert res["status"] == "success"
    assert res["mode"] == "mock"
    assert "Test Telegram alert message" in res["text"]

    alert_res = notifier.send_alert("OPPORTUNITY", {"symbol": "RELIANCE.NS", "price": 2850.0, "score": 88})
    assert alert_res["status"] == "success"
    assert alert_res["mode"] == "mock"


def test_whatsapp_notifier_mock_mode():
    """Test WhatsAppNotifier in mock mode."""
    notifier = WhatsAppNotifier(account_sid="", auth_token="", to_number="", enabled=True)
    res = notifier.send_message("Test WhatsApp alert message")
    assert res["status"] == "success"
    assert res["mode"] == "mock"

    alert_res = notifier.send_alert("ORDER_FILL", {"symbol": "INFY.NS", "price": 1820.0, "qty": 50})
    assert alert_res["status"] == "success"
    assert alert_res["mode"] == "mock"


def test_alert_dispatcher_flow():
    """Test AlertDispatcher dispatching alerts across channels."""
    dispatcher = AlertDispatcher()
    
    order_res = dispatcher.dispatch_order_alert({"symbol": "TCS.NS", "price": 4120.0, "qty": 25})
    assert order_res["status"] == "dispatched"
    assert order_res["alert_type"] == "ORDER_FILL"
    assert "telegram" in order_res["channels"]
    assert "whatsapp" in order_res["channels"]

    risk_res = dispatcher.dispatch_risk_alert({"symbol": "WELCORP.NS", "price": 410.0, "message": "Stop loss breached"})
    assert risk_res["status"] == "dispatched"
    assert risk_res["alert_type"] == "RISK_WARNING"

    opp_res = dispatcher.dispatch_opportunity_alert({"symbol": "HFCL.NS", "score": 92})
    assert opp_res["status"] == "dispatched"
    assert opp_res["alert_type"] == "OPPORTUNITY"

    logs = dispatcher.get_notification_logs(limit=10)
    assert len(logs) > 0
    assert any(log["channel"] in ["Telegram", "WhatsApp"] for log in logs)


def test_notifier_endpoints():
    """Test FastAPI endpoints /api/notifications/config, /api/notifications/send, /api/notifications/log."""
    # GET config
    res_cfg = client.get("/api/notifications/config")
    assert res_cfg.status_code == 200
    cfg = res_cfg.json()
    assert "telegram_enabled" in cfg
    assert "whatsapp_enabled" in cfg

    # POST update config
    res_update = client.post("/api/notifications/config", json={
        "telegram_enabled": True,
        "whatsapp_enabled": True,
        "telegram_chat_id": "123456789"
    })
    assert res_update.status_code == 200
    assert res_update.json()["status"] == "success"

    # POST dispatch alert
    res_send = client.post("/api/notifications/send", json={
        "alert_type": "OPPORTUNITY",
        "data": {
            "title": "High Alpha Opportunity",
            "symbol": "RELIANCE.NS",
            "price": 2880.0,
            "message": "Breakout above 20 EMA"
        }
    })
    assert res_send.status_code == 200
    assert res_send.json()["status"] == "dispatched"

    # GET log history
    res_log = client.get("/api/notifications/log")
    assert res_log.status_code == 200
    assert isinstance(res_log.json(), list)


# ── TASK-073: PWA Manifest & Mobile Responsive CSS Tests ──
def test_pwa_manifest_endpoint():
    """Test GET /manifest.json endpoint."""
    response = client.get("/manifest.json")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["name"] == "Swing Trading System Command Center"
    assert manifest["short_name"] == "SwingTrader"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert isinstance(manifest["icons"], list)
    assert len(manifest["icons"]) >= 2


def test_pwa_service_worker_endpoint():
    """Test GET /sw.js endpoint."""
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "swing-trading-v1" in response.text
    assert "self.addEventListener" in response.text


def test_index_html_pwa_meta_tags():
    """Verify web/index.html includes viewport meta and PWA manifest link."""
    index_path = PROJECT_ROOT / "web" / "index.html"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")
    assert 'href="/manifest.json"' in content
    assert 'name="viewport"' in content
    assert 'width=device-width' in content
    assert 'name="theme-color"' in content


def test_style_css_mobile_responsive_rules():
    """Verify web/style.css contains mobile responsive @media queries."""
    css_path = PROJECT_ROOT / "web" / "style.css"
    assert css_path.exists()
    content = css_path.read_text(encoding="utf-8")
    assert "@media (max-width: 768px)" in content
    assert "@media (max-width: 480px)" in content
    assert "min-height: 44px" in content  # Touch target requirement


# ── TASK-074: Drag-and-Drop Dashboard Layout Config Tests ──
def test_layout_config_endpoint():
    """Test GET & POST /api/ui/layout-config."""
    # GET default or current layout
    res_get = client.get("/api/ui/layout-config")
    assert res_get.status_code == 200
    data = res_get.json()
    assert "widgets" in data
    assert isinstance(data["widgets"], list)

    # POST custom layout config
    custom_layout = {
        "version": "1.0",
        "widgets": [
            {"id": "chart-widget", "title": "Technical Chart Canvas", "visible": True, "order": 0},
            {"id": "regime-widget", "title": "Market Regime Score", "visible": True, "order": 1},
            {"id": "risk-widget", "title": "Portfolio Risk", "visible": False, "order": 2}
        ]
    }
    res_post = client.post("/api/ui/layout-config", json=custom_layout)
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "success"

    # GET to confirm persistence
    res_verify = client.get("/api/ui/layout-config")
    assert res_verify.status_code == 200
    saved = res_verify.json()
    assert saved["widgets"][0]["id"] == "chart-widget"
    assert saved["widgets"][2]["visible"] is False


# ── TASK-075: Web Audio API Sound Alert Config & Synthesizer Tests ──
def test_audio_config_endpoint():
    """Test GET & POST /api/ui/audio-config."""
    # GET default audio config
    res_get = client.get("/api/ui/audio-config")
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert "muted" in cfg
    assert "volume" in cfg

    # POST updated audio config (mute toggle)
    updated_audio = {
        "muted": True,
        "volume": 0.5,
        "chimes_enabled": True,
        "voice_enabled": False
    }
    res_post = client.post("/api/ui/audio-config", json=updated_audio)
    assert res_post.status_code == 200
    assert res_post.json()["status"] == "success"

    # GET to confirm persistence
    res_verify = client.get("/api/ui/audio-config")
    assert res_verify.status_code == 200
    saved = res_verify.json()
    assert saved["muted"] is True
    assert saved["volume"] == 0.5


def test_frontend_js_integrity():
    """Verify web/app.js contains Web Audio API synthesizer, Lightweight Charts, and drag-and-drop layout logic."""
    app_path = PROJECT_ROOT / "web" / "app.js"
    assert app_path.exists()
    content = app_path.read_text(encoding="utf-8")
    assert "class SoundSynthesizer" in content
    assert "playOrderFillChime" in content
    assert "playStopLossTone" in content
    assert "playOpportunityPing" in content
    assert "speakAlert" in content
    assert "loadChartData" in content
    assert "renderCanvasChartFallback" in content
    assert "initDragAndDropLayout" in content
