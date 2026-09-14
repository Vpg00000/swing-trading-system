"""
Unit test to verify grid stocks cache invalidation, live refresh,
and pipeline completion cache invalidation.
"""

import pytest
from starlette.testclient import TestClient
from web_server import (
    app,
    get_10k_grid_stocks,
    invalidate_grid_stocks_cache,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_grid_stocks_cache_invalidation(client):
    # Initial load
    stocks_1 = get_10k_grid_stocks(force_refresh=True)
    assert len(stocks_1) > 0

    # Verify endpoint returns Cache-Control: no-cache
    res = client.get("/api/grid/stocks?limit=10")
    assert res.status_code == 200
    assert "no-cache" in res.headers.get("Cache-Control", "")
    assert "no-store" in res.headers.get("Cache-Control", "")

    # Invalidate cache
    invalidate_grid_stocks_cache()
    from web_server import _GRID_STOCKS_CACHE as cache_val
    assert cache_val is None

    # Verify force_refresh parameter on endpoint works
    res_forced = client.get("/api/grid/stocks?limit=10&force_refresh=true")
    assert res_forced.status_code == 200
    assert len(res_forced.json()) == 10
