"""
Unit & Integration Test Suite for Dashboard UI API Endpoints.
Verifies endpoints mapping for TASK-029 to TASK-035.
"""

import pytest
from fastapi.testclient import TestClient
from web_server import app

@pytest.fixture
def client():
    return TestClient(app)

def test_api_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "overall_status" in data
    assert "components" in data
    assert data["overall_status"] in ["NORMAL", "DEGRADED", "TRADING_BLOCKED", "UNKNOWN"]
    assert isinstance(data["components"], list)

def test_api_opportunities_endpoint(client):
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    data = response.json()
    assert "opportunities" in data
    assert "total_count" in data
    assert isinstance(data["opportunities"], list)
    if data["opportunities"]:
        opp = data["opportunities"][0]
        assert "symbol" in opp
        assert "overall_score" in opp
        assert "suggested_action" in opp
        assert "score_breakdown" in opp
        assert "stop_price" in opp
        assert "target_price" in opp
        assert "rr_ratio" in opp
        assert "net_alpha_pct" in opp

def test_api_priced_in_endpoint(client):
    response = client.get("/api/priced-in?symbol=RELIANCE.NS")
    assert response.status_code == 200
    data = response.json()
    assert "symbol" in data
    assert "status" in data
    assert "priced_in" in data
    assert "evidence" in data["priced_in"]
    assert "inference" in data["priced_in"]

def test_api_risk_endpoint(client):
    response = client.get("/api/risk")
    assert response.status_code == 200
    data = response.json()
    assert "portfolio_beta" in data
    assert "cvar_95" in data
    assert "sub_industry_cap_pct" in data
    assert "kelly_recommended_size_pct" in data
    assert "trading_blocked" in data
    assert "risk_status" in data

def test_api_returns_endpoint(client):
    response = client.get("/api/returns")
    assert response.status_code == 200
    data = response.json()
    assert "sample_net_alpha" in data
    assert "tax_statuses" in data
    assert "countdown_flags" in data
    assert "harvest_candidates" in data

def test_api_sectors_endpoint(client):
    response = client.get("/api/sectors")
    assert response.status_code == 200
    data = response.json()
    assert "sectors" in data or isinstance(data, list)

def test_api_portfolio_endpoint(client):
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)

def test_api_dashboard_endpoint(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "regime" in data
    assert "capital_summary" in data
    assert "top_actions" in data
    assert "system_health" in data

def test_api_grid_stocks_endpoint(client):
    response = client.get("/api/grid/stocks?cap_category=ALL&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_api_prompts_endpoint(client):
    response = client.get("/api/prompts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
