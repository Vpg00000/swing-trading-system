"""
Unit & Integration Test Suite for UI Action Buttons & Pipeline Execution Endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from web_server import app

@pytest.fixture
def client():
    return TestClient(app)


def test_pipeline_run_endpoint(client):
    """Test POST/GET /api/pipeline/run endpoint triggers background pipeline."""
    response = client.post("/api/pipeline/run")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["STARTED", "RUNNING"]
    assert "pipeline_status" in data
    assert "message" in data


def test_backtest_run_endpoint(client):
    """Test POST/GET /api/backtest/run endpoint executes backtest simulation."""
    response = client.post("/api/backtest/run")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["SUCCESS", "SUCCESS_FALLBACK"]
    assert "metrics" in data
    assert "sharpe_ratio" in data["metrics"]


def test_ai_scan_endpoint(client):
    """Test POST/GET /api/ai/scan endpoint executes AI consensus scan."""
    response = client.post("/api/ai/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "consensus" in data


def test_execution_status_and_stream_endpoints(client):
    """Test GET /api/execution/status and GET /api/stream/execution-logs endpoints."""
    res_status = client.get("/api/execution/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["status"] == "SUCCESS"
    assert "execution_state" in data
    assert "logs" in data["execution_state"]

    res_stream = client.get("/api/stream/execution-logs")
    assert res_stream.status_code == 200
    assert "text/event-stream" in res_stream.headers.get("content-type", "")

