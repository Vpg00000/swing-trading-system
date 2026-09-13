"""
Unit and Performance Test Suite for Virtualized 10,000-Stock Grid Endpoint (/api/grid/stocks).
Verifies pagination, search filtering, sector filter, cap category filter, sorting, and performance.
"""

import time
import pytest
from fastapi.testclient import TestClient
from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_grid_stocks_pagination(client):
    """Verify pagination parameters (page, limit) and response headers."""
    res1 = client.get("/api/grid/stocks?page=1&limit=50")
    assert res1.status_code == 200
    data1 = res1.json()
    assert isinstance(data1, list)
    assert len(data1) == 50
    assert "X-Total-Count" in res1.headers
    total_count = int(res1.headers["X-Total-Count"])
    assert total_count >= 10000

    res2 = client.get("/api/grid/stocks?page=2&limit=50")
    assert res2.status_code == 200
    data2 = res2.json()
    assert isinstance(data2, list)
    assert len(data2) == 50
    assert data1[0]["symbol"] != data2[0]["symbol"]

    # Verify fetching large limit (10,000+ stocks)
    res_large = client.get("/api/grid/stocks?page=1&limit=10500")
    assert res_large.status_code == 200
    data_large = res_large.json()
    assert len(data_large) >= 10000


def test_grid_stocks_search_filtering(client):
    """Verify live search query filtering (q and search parameters)."""
    res_q = client.get("/api/grid/stocks?q=RELIANCE")
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert len(data_q) > 0
    for stock in data_q:
        match = (
            "reliance" in stock.get("symbol", "").lower()
            or "reliance" in stock.get("name", "").lower()
            or "reliance" in stock.get("sector", "").lower()
        )
        assert match

    res_spec = client.get("/api/grid/stocks?q=STOCK_00050")
    assert res_spec.status_code == 200
    data_spec = res_spec.json()
    assert len(data_spec) > 0
    assert any("STOCK_00050" in s["symbol"] for s in data_spec)


def test_grid_stocks_sector_filtering(client):
    """Verify sector filter parameter (sector)."""
    res_it = client.get("/api/grid/stocks?sector=IT&limit=100")
    assert res_it.status_code == 200
    data_it = res_it.json()
    assert len(data_it) > 0
    for stock in data_it:
        assert stock.get("sector", "").lower() in ("it", "technology", "tech")

    res_bank = client.get("/api/grid/stocks?sector=Banking&limit=100")
    assert res_bank.status_code == 200
    data_bank = res_bank.json()
    assert len(data_bank) > 0
    for stock in data_bank:
        assert stock.get("sector", "").lower() in ("banking", "financials", "finance", "financial services")


def test_grid_stocks_cap_filtering(client):
    """Verify cap category filter parameter (cap and cap_category)."""
    res_large = client.get("/api/grid/stocks?cap=LARGE&limit=100")
    assert res_large.status_code == 200
    data_large = res_large.json()
    assert len(data_large) > 0
    for stock in data_large:
        assert stock.get("cap_category") == "LARGE"

    res_small = client.get("/api/grid/stocks?cap_category=SMALL&limit=100")
    assert res_small.status_code == 200
    data_small = res_small.json()
    assert len(data_small) > 0
    for stock in data_small:
        assert stock.get("cap_category") == "SMALL"


def test_grid_stocks_sorting(client):
    """Verify custom sorting (sort_by, order, ascending)."""
    # Sort by close price ascending
    res_asc = client.get("/api/grid/stocks?sort_by=close&order=asc&limit=100")
    assert res_asc.status_code == 200
    data_asc = res_asc.json()
    closes_asc = [s["close"] for s in data_asc]
    assert closes_asc == sorted(closes_asc)

    # Sort by close price descending
    res_desc = client.get("/api/grid/stocks?sort_by=close&order=desc&limit=100")
    assert res_desc.status_code == 200
    data_desc = res_desc.json()
    closes_desc = [s["close"] for s in data_desc]
    assert closes_desc == sorted(closes_desc, reverse=True)

    # Sort by composite_score descending
    res_score = client.get("/api/grid/stocks?sort_by=composite_score&order=desc&limit=100")
    assert res_score.status_code == 200
    data_score = res_score.json()
    scores = [s["composite_score"] for s in data_score]
    assert scores == sorted(scores, reverse=True)


def test_grid_stocks_performance(client):
    """Verify endpoint response time for retrieving 10,000 stock records is under 200ms."""
    # Warmup call
    client.get("/api/grid/stocks?limit=10000")

    times = []
    for _ in range(10):
        start = time.perf_counter()
        res = client.get("/api/grid/stocks?limit=10000")
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert res.status_code == 200
        times.append(elapsed_ms)

    times.sort()
    median_ms = times[len(times) // 2]
    print(f"10,000-stock grid response time median: {median_ms:.2f} ms")
    assert median_ms < 200, f"Expected median response time < 200ms, got {median_ms:.2f}ms"
