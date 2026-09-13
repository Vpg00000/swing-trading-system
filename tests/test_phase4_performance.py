"""
test_phase4_performance.py - Phase 4 Task D: Performance & UX Benchmark Verification

Verification Suite covering:
1. /api/grid/stocks endpoint speed (<50ms for 100 items, <100ms for 10,000 grid).
2. ETag 304 Not Modified response latency (<10ms).
3. Compression ratio validation on /api/opportunities and /api/grid/stocks.
4. Static asset response sizes and routing (CSS, JS, worker.js).
"""

import time
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure testing flag is set to avoid long network operations in dependent services
os.environ["TESTING"] = "1"

from web_server import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client():
    """Module-scoped FastAPI TestClient fixture."""
    with TestClient(app) as tc:
        # Pre-warm app endpoints to initialize databases, caches, and middlewares
        tc.get("/api/health")
        tc.get("/api/grid/stocks?limit=100")
        tc.get("/api/opportunities")
        yield tc


def test_grid_stocks_endpoint_speed(client):
    """
    Benchmark /api/grid/stocks endpoint speed:
    - Target: < 50ms for 100 items
    - Target: < 100ms for 10,000 grid items
    """
    # 1. Benchmark 100 items (<50ms)
    execution_times_100 = []
    for _ in range(5):
        start_time = time.perf_counter()
        response_100 = client.get("/api/grid/stocks?limit=100")
        end_time = time.perf_counter()
        execution_times_100.append((end_time - start_time) * 1000)

    assert response_100.status_code == 200, "Expected HTTP 200 for 100 items grid query"
    items_100 = response_100.json()
    assert len(items_100) == 100, f"Expected 100 items in grid response, got {len(items_100)}"

    min_time_100 = min(execution_times_100)
    median_time_100 = sorted(execution_times_100)[len(execution_times_100) // 2]
    print(f"\n[BENCHMARK] /api/grid/stocks (100 items) - Min: {min_time_100:.2f}ms, Median: {median_time_100:.2f}ms")
    assert min_time_100 < 50.0, f"Expected /api/grid/stocks?limit=100 < 50ms, got {min_time_100:.2f}ms"

    # 2. Benchmark 10,000 grid (<100ms)
    execution_times_10k = []
    for _ in range(5):
        start_time = time.perf_counter()
        response_10k = client.get("/api/grid/stocks?limit=10000")
        end_time = time.perf_counter()
        execution_times_10k.append((end_time - start_time) * 1000)

    assert response_10k.status_code == 200, "Expected HTTP 200 for 10,000 items grid query"
    items_10k = response_10k.json()
    assert len(items_10k) >= 10000, f"Expected >= 10,000 items in grid response, got {len(items_10k)}"

    min_time_10k = min(execution_times_10k)
    median_time_10k = sorted(execution_times_10k)[len(execution_times_10k) // 2]
    print(f"[BENCHMARK] /api/grid/stocks (10,000 grid) - Min: {min_time_10k:.2f}ms, Median: {median_time_10k:.2f}ms")
    assert min_time_10k < 100.0, f"Expected /api/grid/stocks?limit=10000 < 100ms, got {min_time_10k:.2f}ms"


def test_etag_304_response_times(client):
    """
    Test ETag 304 response times (<10ms).
    Sends If-None-Match header matching returned ETag and verifies 304 Not Modified status.
    """
    initial_res = client.get("/api/grid/stocks?limit=100")
    assert initial_res.status_code == 200
    etag = initial_res.headers.get("etag")
    assert etag is not None, "Response must include an ETag header"

    execution_times_304 = []
    for _ in range(5):
        start_time = time.perf_counter()
        response_304 = client.get("/api/grid/stocks?limit=100", headers={"If-None-Match": etag})
        end_time = time.perf_counter()
        execution_times_304.append((end_time - start_time) * 1000)

        assert response_304.status_code == 304, f"Expected HTTP 304 Not Modified, got {response_304.status_code}"

    min_time_304 = min(execution_times_304)
    median_time_304 = sorted(execution_times_304)[len(execution_times_304) // 2]
    print(f"[BENCHMARK] ETag 304 Response Time - Min: {min_time_304:.2f}ms, Median: {median_time_304:.2f}ms")
    assert min_time_304 < 10.0, f"Expected ETag 304 response time < 10ms, got {min_time_304:.2f}ms"


def test_compression_ratio(client):
    """
    Test payload compression ratio on /api/opportunities and /api/grid/stocks.
    Verifies content-encoding header and payload size reduction when Accept-Encoding is supplied.
    """
    # 1. /api/opportunities compression
    res_opp_raw = client.get("/api/opportunities", headers={"Accept-Encoding": "identity"})
    res_opp_gz = client.get("/api/opportunities", headers={"Accept-Encoding": "gzip"})

    assert res_opp_raw.status_code == 200
    assert res_opp_gz.status_code == 200
    assert res_opp_gz.headers.get("content-encoding") in ["gzip", "br"], "Expected GZip or Brotli content-encoding header"

    raw_opp_size = int(res_opp_raw.headers.get("content-length", len(res_opp_raw.content)))
    gz_opp_size = int(res_opp_gz.headers.get("content-length", 0))

    assert gz_opp_size > 0, "Compressed content-length must be > 0"
    opp_compression_ratio = (1.0 - gz_opp_size / raw_opp_size) * 100.0
    print(f"[BENCHMARK] /api/opportunities Compression - Uncompressed: {raw_opp_size} B, Compressed: {gz_opp_size} B, Ratio: {opp_compression_ratio:.2f}% reduction")
    assert gz_opp_size < raw_opp_size, "Compressed size must be smaller than uncompressed size"
    assert opp_compression_ratio >= 30.0, f"Expected /api/opportunities compression ratio >= 30%, got {opp_compression_ratio:.2f}%"

    # 2. /api/grid/stocks compression
    res_grid_raw = client.get("/api/grid/stocks?limit=500", headers={"Accept-Encoding": "identity"})
    res_grid_gz = client.get("/api/grid/stocks?limit=500", headers={"Accept-Encoding": "gzip"})

    assert res_grid_raw.status_code == 200
    assert res_grid_gz.status_code == 200
    assert res_grid_gz.headers.get("content-encoding") in ["gzip", "br"], "Expected GZip or Brotli content-encoding header"

    raw_grid_size = int(res_grid_raw.headers.get("content-length", len(res_grid_raw.content)))
    gz_grid_size = int(res_grid_gz.headers.get("content-length", 0))

    assert gz_grid_size > 0, "Compressed content-length must be > 0"
    grid_compression_ratio = (1.0 - gz_grid_size / raw_grid_size) * 100.0
    print(f"[BENCHMARK] /api/grid/stocks Compression - Uncompressed: {raw_grid_size} B, Compressed: {gz_grid_size} B, Ratio: {grid_compression_ratio:.2f}% reduction")
    assert gz_grid_size < raw_grid_size, "Compressed size must be smaller than uncompressed size"
    assert grid_compression_ratio >= 30.0, f"Expected /api/grid/stocks compression ratio >= 30%, got {grid_compression_ratio:.2f}%"


def test_static_asset_response_sizes(client):
    """
    Test static asset response sizes (CSS, JS, worker.js).
    Verifies that static routes return HTTP 200 and non-empty valid asset contents.
    """
    assets = {
        "/static/style.css": {"min_size": 1000, "max_size": 200000},
        "/static/app.js": {"min_size": 10000, "max_size": 1000000},
        "/static/worker.js": {"min_size": 200, "max_size": 50000},
    }

    for asset_route, bounds in assets.items():
        response = client.get(asset_route)
        assert response.status_code == 200, f"Expected HTTP 200 for {asset_route}, got {response.status_code}"
        size = len(response.content)
        print(f"[BENCHMARK] Asset {asset_route} Size: {size} bytes")
        assert bounds["min_size"] <= size <= bounds["max_size"], (
            f"Asset {asset_route} size {size} bytes outside expected range [{bounds['min_size']}, {bounds['max_size']}]"
        )
