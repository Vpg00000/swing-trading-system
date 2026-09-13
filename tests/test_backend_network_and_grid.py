"""
Unit & Integration Test Suite for Backend REST Middleware & Network Optimization (TASK-111, TASK-112, TASK-117, TASK-091 backend).
"""

import pytest
import gzip
from fastapi.testclient import TestClient
from web_server import app, compute_json_patch, apply_json_patch, HAS_BROTLI

@pytest.fixture
def client():
    return TestClient(app)


# ── TASK-111: Brotli / GZip Payload Compression Middleware Test ──
def test_task111_payload_compression_middleware(client):
    headers = {"Accept-Encoding": "gzip"}
    response = client.get("/api/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert "Vary" in response.headers or "vary" in response.headers

    if HAS_BROTLI:
        headers_br = {"Accept-Encoding": "br"}
        response_br = client.get("/api/dashboard", headers=headers_br)
        assert response_br.status_code == 200
        assert response_br.headers.get("content-encoding") in ["br", "gzip"]


# ── TASK-112: SHA-256 ETag Generator & If-None-Match 304 Not Modified Test ──
def test_task112_etag_and_304_not_modified(client):
    res1 = client.get("/api/grid/stocks")
    assert res1.status_code == 200
    etag = res1.headers.get("etag") or res1.headers.get("ETag")
    assert etag is not None
    assert len(etag.strip('"')) == 64  # Full SHA-256 hex string

    # Send If-None-Match matching computed ETag
    res2 = client.get("/api/grid/stocks", headers={"If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.text == ""

    # Send If-None-Match with raw hex string
    raw_hash = etag.strip('"')
    res3 = client.get("/api/grid/stocks", headers={"If-None-Match": raw_hash})
    assert res3.status_code == 304


# ── TASK-117: JSON Patch (RFC 6902) Helpers & Stream Endpoint Test ──
def test_task117_json_patch_helpers():
    old_state = {"symbol": "RELIANCE", "close": 2850.0, "details": {"rsi": 55.0, "score": 80}}
    new_state = {"symbol": "RELIANCE", "close": 2865.0, "details": {"rsi": 58.5, "score": 80}, "new_flag": True}

    patch = compute_json_patch(old_state, new_state)
    assert isinstance(patch, list)
    assert len(patch) >= 2

    # Verify applying patch matches new_state
    reconstructed = apply_json_patch(old_state, patch)
    assert reconstructed == new_state


def test_task117_stream_deltas_endpoint(client):
    response = client.get("/api/stream/deltas?interval=0.01&limit=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_task117_compute_patch_endpoint(client):
    payload = {
        "old_state": {"a": 1, "b": 2},
        "new_state": {"a": 1, "b": 3, "c": 4}
    }
    response = client.post("/api/patch/delta", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "op_count" in data
    assert "patch" in data
    assert data["op_count"] == 2


# ── TASK-091 Backend: 10,000 Virtualized Stock Grid Endpoint Test ──
def test_task091_grid_stocks_endpoint(client):
    # Fetch paginated slice
    res_page = client.get("/api/grid/stocks?page=1&page_size=50&cap_category=ALL")
    assert res_page.status_code == 200
    data_page = res_page.json()
    assert isinstance(data_page, list)
    assert len(data_page) == 50

    # Fetch larger virtualized slice (e.g. 1,000 stocks grid)
    res_large = client.get("/api/grid/stocks?limit=1000&cap_category=ALL")
    assert res_large.status_code == 200
    data_large = res_large.json()
    assert isinstance(data_large, list)
    assert len(data_large) == 1000
    assert "symbol" in data_large[0]
    assert "close" in data_large[0]

    # Test filtering by market cap category
    res_large_cap = client.get("/api/grid/stocks?cap_category=LARGE&limit=20")
    assert res_large_cap.status_code == 200
    data_large_cap = res_large_cap.json()
    assert isinstance(data_large_cap, list)
    for stock in data_large_cap:
        assert stock.get("cap_category") == "LARGE"
