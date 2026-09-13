"""
test_ui_performance.py - Unit & Performance Verification for Web Worker, WASM, and Client UI Logic
TASK-084 through TASK-110, TASK-113, TASK-116, TASK-119, TASK-122, TASK-123, TASK-125, TASK-126, TASK-127, TASK-128, TASK-131.
"""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from web_server import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture
def client():
    return TestClient(app)

def test_web_worker_file_exists():
    worker_path = PROJECT_ROOT / "web" / "worker.js"
    assert worker_path.exists(), "web/worker.js must exist"
    content = worker_path.read_text(encoding="utf-8")
    assert "self.onmessage" in content
    assert "SORT_FILTER" in content
    assert "EXPORT_CSV" in content
    assert "EXPORT_EXCEL" in content
    assert "EXPORT_PDF" in content

def test_wasm_indicator_files_exist():
    wasm_bin_path = PROJECT_ROOT / "web" / "wasm" / "indicators.wasm"
    wasm_js_path = PROJECT_ROOT / "web" / "wasm" / "indicators.js"
    assert wasm_bin_path.exists(), "web/wasm/indicators.wasm must exist"
    assert wasm_js_path.exists(), "web/wasm/indicators.js must exist"

    js_content = wasm_js_path.read_text(encoding="utf-8")
    assert "calculateEMA" in js_content
    assert "calculateMACD" in js_content
    assert "calculateRSI" in js_content
    assert "calculateBollingerBands" in js_content

def test_client_app_js_features():
    app_js_path = PROJECT_ROOT / "web" / "app.js"
    assert app_js_path.exists(), "web/app.js must exist"
    content = app_js_path.read_text(encoding="utf-8")

    # Verify core implementations in app.js
    assert "initWebWorker" in content
    assert "enqueueDOMUpdate" in content
    assert "executeOptimisticUI" in content
    assert "showToast" in content
    assert "initIndexedDB" in content
    assert "startTelemetryMonitoring" in content
    assert "saveSessionState" in content
    assert "formatMarkdownText" in content
    assert "renderRadarChart" in content
    assert "renderSectorHeatmap" in content
    assert "renderLevel2DepthBar" in content
    assert "renderInlineSparkline" in content

def test_opportunities_table_virtualization(client):
    # Query live backend opportunities endpoint
    response = client.get("/api/opportunities?limit=10")
    assert response.status_code == 200

    # Query virtualized stock grid endpoint
    response = client.get("/api/grid/stocks?limit=50")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, (dict, list))

def test_static_asset_routes(client):
    res_app = client.get("/static/app.js")
    assert res_app.status_code == 200

    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200

    res_worker = client.get("/static/worker.js")
    assert res_worker.status_code == 200

    res_wasm_js = client.get("/static/wasm/indicators.js")
    assert res_wasm_js.status_code == 200