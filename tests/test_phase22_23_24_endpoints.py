"""
Unit tests for Phase 22, 23 & 24 Web Server API routes in web_server.py (Task T-294).
"""

import pytest
from fastapi.testclient import TestClient
from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_risk_summary(client):
    res = client.get("/api/risk/summary")
    assert res.status_code == 200
    data = res.json()
    assert "overall_status" in data
    assert "var" in data
    assert "cvar" in data
    assert "stress_test" in data
    assert "kill_switch" in data
    assert "circuit_breaker" in data
    assert "margin_deleverage" in data


def test_api_risk_stress_test(client):
    res = client.get("/api/risk/stress-test?scenario=corona_2020")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario_key"] == "corona_2020"
    assert "projected_drawdown_pct" in data


def test_api_risk_margin_eval(client):
    res = client.get("/api/risk/margin-eval?margin_used_pct=96.0")
    assert res.status_code == 200
    data = res.json()
    assert data["auto_deleverage_triggered"]
    assert len(data["deleveraging_plan"]) > 0


def test_api_institutional_bulk_deals(client):
    res = client.get("/api/institutional/bulk-deals")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "deals" in data


def test_api_institutional_flow_forecast(client):
    res = client.get("/api/institutional/flow-forecast?horizon=5")
    assert res.status_code == 200
    data = res.json()
    assert data["forecast_horizon_days"] == 5
    assert len(data["forecast_details"]) == 5


def test_api_institutional_smart_money(client):
    res = client.get("/api/institutional/smart-money")
    assert res.status_code == 200
    data = res.json()
    assert "smi" in data
    assert "dark_pool_hits" in data


def test_api_institutional_accumulation_distribution(client):
    res = client.get("/api/institutional/accumulation-distribution")
    assert res.status_code == 200
    data = res.json()
    assert "scores" in data


def test_api_institutional_export(client):
    res = client.get("/api/institutional/export?format=csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]


def test_api_sentiment_summary(client):
    res = client.get("/api/sentiment/summary?symbol=RELIANCE")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert "social_sentiment" in data


def test_api_sentiment_social_buzz(client):
    res = client.get("/api/sentiment/social-buzz?symbol=TCS")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "TCS"
    assert "correlation" in data
    assert "word_cloud" in data


def test_api_sentiment_earnings_shift(client):
    res = client.get("/api/sentiment/earnings-shift?symbol=INFY")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "INFY"
    assert "tone_shift_pct" in data


def test_api_sentiment_spike_alerts(client):
    res = client.get("/api/sentiment/spike-alerts")
    assert res.status_code == 200
    data = res.json()
    assert "spike_count" in data


def test_screener_grid_sentiment_column(client):
    res = client.get("/api/grid/stocks?sort_by=sentiment_score&order=desc")
    assert res.status_code == 200
    items = res.json()
    assert len(items) > 0
    assert "sentiment_score" in items[0]
    assert "sentiment_label" in items[0]
