"""
Unit tests for Institutional Flow & Cyclical Sector Matrix (Phase 2 Task C).
Verifies:
- InstitutionalFlowTracker fetching/calculating daily FII/DII net cash figures in Crores (₹ Cr).
- SectorMomentumMatrix calculating relative strength momentum scores across 12 NSE sector indices.
- LiveScorerService integration.
- FastAPI web_server /api/flow and /api/sectors endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from engine.scoring import InstitutionalFlowTracker, SectorMomentumMatrix, score_opportunity
from services.live_scorer import LiveScorerService
from web_server import app

EXPECTED_12_SECTORS = {
    "Nifty Bank",
    "Nifty IT",
    "Nifty Auto",
    "Nifty Pharma",
    "Nifty FMCG",
    "Nifty Metal",
    "Nifty Realty",
    "Nifty Energy",
    "Nifty Infra",
    "Nifty PSE",
    "Nifty PSU Bank",
    "Nifty Private Bank",
}


def test_institutional_flow_tracker_daily_flows():
    tracker = InstitutionalFlowTracker()
    daily_flows = tracker.fetch_daily_flows(days=15)
    assert len(daily_flows) == 15
    for record in daily_flows:
        assert "date" in record
        assert "fii_buy" in record
        assert "fii_sell" in record
        assert "fii_net" in record
        assert "dii_buy" in record
        assert "dii_sell" in record
        assert "dii_net" in record
        assert "total_net" in record
        assert "fii_net_inflow_cr" in record
        assert "dii_net_inflow_cr" in record
        # Verify net = buy - sell relation
        assert round(record["fii_net"], 2) == round(record["fii_buy"] - record["fii_sell"], 2)
        assert round(record["dii_net"], 2) == round(record["dii_buy"] - record["dii_sell"], 2)
        assert round(record["total_net"], 2) == round(record["fii_net"] + record["dii_net"], 2)


def test_institutional_flow_tracker_latest_flow_and_score():
    tracker = InstitutionalFlowTracker()
    summary = tracker.get_latest_flow()
    assert "fii_net" in summary
    assert "dii_net" in summary
    assert "total_net" in summary
    assert "signal" in summary
    assert "flow_score" in summary
    assert "daily_flows" in summary
    assert 0.0 <= summary["flow_score"] <= 100.0

    # Test custom flow scoring math
    high_score = tracker.calculate_flow_score(fii_net=2000.0, dii_net=1500.0)
    assert high_score > 75.0

    low_score = tracker.calculate_flow_score(fii_net=-2000.0, dii_net=-1500.0)
    assert low_score < 25.0


def test_sector_momentum_matrix_12_sectors():
    matrix = SectorMomentumMatrix()
    rankings = matrix.calculate_matrix()
    assert len(rankings) == 12

    sectors_returned = {item["sector"] for item in rankings}
    assert sectors_returned == EXPECTED_12_SECTORS

    # Ranks should be 1 to 12 strictly in descending order of score
    ranks = [item["rank"] for item in rankings]
    scores = [item["score"] for item in rankings]
    assert ranks == list(range(1, 13))
    assert scores == sorted(scores, reverse=True)

    for item in rankings:
        assert "sector" in item
        assert "score" in item
        assert "momentum_score" in item
        assert "relative_strength" in item
        assert "change_pct" in item
        assert "status" in item
        assert 0.0 <= item["score"] <= 100.0


def test_sector_momentum_matrix_get_score():
    matrix = SectorMomentumMatrix()
    score_bank = matrix.get_sector_score("Nifty Bank")
    assert isinstance(score_bank, float)
    assert 0.0 <= score_bank <= 100.0

    score_it = matrix.get_sector_score("Nifty IT")
    assert isinstance(score_it, float)
    assert 0.0 <= score_it <= 100.0


def test_live_scorer_service_flow_and_sector_integration():
    service = LiveScorerService()
    flow_summary = service.get_institutional_flow()
    assert "fii_net" in flow_summary
    assert "dii_net" in flow_summary

    sector_matrix = service.get_sector_matrix()
    assert len(sector_matrix) == 12
    returned_sectors = {s["sector"] for s in sector_matrix}
    assert returned_sectors == EXPECTED_12_SECTORS


def test_api_flow_endpoint():
    client = TestClient(app)
    response = client.get("/api/flow")
    assert response.status_code == 200
    data = response.json()
    assert "fii_net" in data or "net_fii" in data or "fii_net_inflow_cr" in data
    assert "dii_net" in data or "net_dii" in data or "dii_net_inflow_cr" in data
    assert "daily_flows" in data or "history" in data


def test_api_sectors_endpoint():
    client = TestClient(app)
    response = client.get("/api/sectors")
    assert response.status_code == 200
    data = response.json()
    assert "sectors" in data
    sectors = data["sectors"]
    assert len(sectors) == 12

    sector_names = {s.get("sector") or s.get("name") for s in sectors}
    assert sector_names == EXPECTED_12_SECTORS

    # Check rank presence
    ranks = [s["rank"] for s in sectors]
    assert sorted(ranks) == list(range(1, 13))
