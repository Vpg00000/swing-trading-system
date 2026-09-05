"""
Unit and Integration Tests for Real-Time Streaming & Infrastructure Expansion (TASK-051 to TASK-055).
"""

import pytest
from fastapi.testclient import TestClient
from web_server import app
from data.websocket_client import DhanWebSocketClient
from data.redis_cache import RedisCacheManager
from data.sync_engine import run_gap_filler_worker
from data.xbrl_parser import parse_xbrl_financial_statement

client = TestClient(app)


def test_task051_dhan_websocket_client():
    ws_client = DhanWebSocketClient()
    assert ws_client.connect() is True
    assert ws_client.subscribe(["RELIANCE", "INFY"]) is True

    received_ticks = []
    ws_client.register_callback(lambda tick: received_ticks.append(tick))

    tick = ws_client.simulate_incoming_tick("RELIANCE", 2850.0, volume=500)
    assert tick["symbol"] == "RELIANCE"
    assert tick["ltp"] == 2850.0
    assert len(received_ticks) == 1
    assert ws_client.disconnect() is True


def test_task052_redis_cache_manager():
    cache = RedisCacheManager()
    assert cache.set("quote_RELIANCE", {"ltp": 2850.0}, ttl=60) is True

    val = cache.get("quote_RELIANCE")
    assert val == {"ltp": 2850.0}

    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["status"] == "HEALTHY"


def test_task053_sse_stream_events_endpoint():
    response = client.get("/api/stream/events")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_task054_gap_filler_worker():
    res = run_gap_filler_worker(["RELIANCE.NS"])
    assert res["status"] in ["SUCCESS", "CONTINUOUS"]
    assert "continuity_score_pct" in res


def test_task055_xbrl_parser_engine():
    payload = '{"revenue": 95000.0, "net_profit": 18500.0, "ebitda": 24000.0, "auditor_qualification": false}'
    res = parse_xbrl_financial_statement(payload)

    assert res["revenue_inr_cr"] == 95000.0
    assert res["net_profit_inr_cr"] == 18500.0
    assert res["ebitda_inr_cr"] == 24000.0
    assert res["auditor_qualification"] is False
    assert res["status"] == "PARSED"
