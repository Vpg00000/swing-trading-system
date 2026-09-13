"""
Unit tests for Brotli/GZip Payload Compression and SHA-256 ETag Middleware (Phase 4 Task B).
"""

import gzip
import hashlib
import pytest
from fastapi.testclient import TestClient
from web_server import app, HAS_BROTLI

try:
    import brotli
except ImportError:
    brotli = None


@pytest.fixture
def client():
    return TestClient(app)


def test_gzip_compression_header(client):
    """Verify GZip response compression and headers when Accept-Encoding includes gzip."""
    headers = {"Accept-Encoding": "gzip"}
    response = client.get("/api/sectors", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in response.headers.get("vary", "").lower()
    # TestClient automatically decompresses response.content when Content-Encoding is gzip
    data = response.json()
    assert "sectors" in data or "count" in data


def test_brotli_compression_header(client):
    """Verify Brotli response compression and headers when Accept-Encoding includes br."""
    headers = {"Accept-Encoding": "br"}
    response = client.get("/api/sectors", headers=headers)
    assert response.status_code == 200

    if HAS_BROTLI and brotli is not None:
        assert response.headers.get("content-encoding") == "br"
        assert "accept-encoding" in response.headers.get("vary", "").lower()
        decompressed = brotli.decompress(response.content)
        assert len(decompressed) > 0
    else:
        assert response.headers.get("content-encoding") != "gzip"


def test_etag_generation(client):
    """Verify SHA-256 ETag header is generated for JSON responses."""
    response = client.get("/api/watchlist")
    assert response.status_code == 200

    etag = response.headers.get("etag") or response.headers.get("ETag")
    assert etag is not None
    # ETag should be formatted as quoted SHA-256 hex string: "<64 hex chars>"
    raw_etag = etag.strip('"')
    assert len(raw_etag) == 64

    # Verify hash matches SHA-256 of response body
    expected_hash = hashlib.sha256(response.content).hexdigest()
    assert raw_etag == expected_hash


def test_http_304_not_modified_responses(client):
    """Verify HTTP 304 Not Modified status when incoming If-None-Match matches current ETag."""
    res1 = client.get("/api/watchlist")
    assert res1.status_code == 200
    etag = res1.headers.get("etag") or res1.headers.get("ETag")
    assert etag is not None

    # 1. Matching quoted ETag
    res2 = client.get("/api/watchlist", headers={"If-None-Match": etag})
    assert res2.status_code == 304
    assert res2.text == ""
    assert (res2.headers.get("etag") or res2.headers.get("ETag")) == etag

    # 2. Matching unquoted SHA-256 hash string
    raw_hash = etag.strip('"')
    res3 = client.get("/api/watchlist", headers={"If-None-Match": raw_hash})
    assert res3.status_code == 304
    assert res3.text == ""

    # 3. Matching wildcard "*"
    res4 = client.get("/api/watchlist", headers={"If-None-Match": "*"})
    assert res4.status_code == 304
    assert res4.text == ""

    # 4. Non-matching ETag -> returns HTTP 200 with content
    res5 = client.get("/api/watchlist", headers={"If-None-Match": '"invalid-etag-hash"'})
    assert res5.status_code == 200
    assert len(res5.content) > 0


def test_compression_and_etag_combined(client):
    """Verify ETag generation and 304 Not Modified behavior with compression requested."""
    res1 = client.get("/api/watchlist", headers={"Accept-Encoding": "gzip"})
    assert res1.status_code == 200
    assert res1.headers.get("content-encoding") == "gzip"
    etag = res1.headers.get("etag") or res1.headers.get("ETag")
    assert etag is not None

    # Send If-None-Match along with Accept-Encoding
    res2 = client.get("/api/watchlist", headers={"If-None-Match": etag, "Accept-Encoding": "gzip"})
    assert res2.status_code == 304
    assert res2.text == ""


def test_no_compression_without_accept_encoding(client):
    """Verify response payload is not compressed when Accept-Encoding is omitted."""
    # Custom TestClient headers without default accept-encoding
    custom_client = TestClient(app, headers={"User-Agent": "test-client"})
    response = custom_client.get("/api/watchlist", headers={"Accept-Encoding": "identity"})
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
