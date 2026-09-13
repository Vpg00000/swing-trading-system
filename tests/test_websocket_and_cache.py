"""
Unit tests for Dhan WebSocket & Cache Layer Enhancement (Phase 2 Task D).

Verifies:
1. WebSocket connection setup (sync and async).
2. Sub-second binary/JSON packet decoding and callbacks.
3. Auto-reconnect exponential backoff logic (1s, 2s, 4s, 8s...).
4. Gap-fill REST snapshot requests.
5. Dual-mode RedisCacheManager fallback cache, TTL expiration, hit/miss statistics.
"""

import time
import json
import struct
import pytest
import asyncio
from data.websocket_client import DhanWebSocketClient
from data.redis_cache import RedisCacheManager


# ---------------------------------------------------------------------------
# WebSocket Client Tests
# ---------------------------------------------------------------------------

def test_websocket_connection_setup():
    """Test sync connection, disconnection, and symbol subscriptions."""
    ws = DhanWebSocketClient(client_id="TEST_CLIENT")
    assert ws.is_connected is False

    assert ws.connect() is True
    assert ws.is_connected is True

    assert ws.subscribe(["RELIANCE", "INFY"]) is True
    assert "RELIANCE" in ws.subscribed_symbols
    assert "INFY" in ws.subscribed_symbols

    assert ws.unsubscribe(["INFY"]) is True
    assert "INFY" not in ws.subscribed_symbols
    assert "RELIANCE" in ws.subscribed_symbols

    assert ws.disconnect() is True
    assert ws.is_connected is False


@pytest.mark.anyio
async def test_websocket_async_connection():
    """Test async connection and disconnection methods."""
    ws = DhanWebSocketClient(client_id="TEST_ASYNC_CLIENT")
    assert ws.is_connected is False

    res_conn = await ws.connect_async()
    assert res_conn is True
    assert ws.is_connected is True

    res_disconn = await ws.disconnect_async()
    assert res_disconn is True
    assert ws.is_connected is False


def test_websocket_packet_decoding():
    """Test sub-second packet parsing for dict, JSON string, JSON bytes, and binary struct formats."""
    ws = DhanWebSocketClient()
    received_ticks = []
    ws.register_callback(lambda t: received_ticks.append(t))

    # 1. Dict payload
    dict_tick = ws.simulate_incoming_tick("TCS", 3500.50, volume=250)
    assert dict_tick["symbol"] == "TCS"
    assert dict_tick["ltp"] == 3500.50
    assert dict_tick["volume"] == 250
    assert "latency_ms" in dict_tick
    assert dict_tick["latency_ms"] >= 0.0

    # 2. JSON string payload
    json_str = json.dumps({"symbol": "WIPRO", "ltp": 450.75, "volume": 1000})
    parsed_json = ws.process_packet(json_str)
    assert parsed_json["symbol"] == "WIPRO"
    assert parsed_json["ltp"] == 450.75

    # 3. JSON bytes payload
    json_bytes = json.dumps({"symbol": "HDFCBANK", "ltp": 1600.0, "volume": 500}).encode("utf-8")
    parsed_bytes = ws.process_packet(json_bytes)
    assert parsed_bytes["symbol"] == "HDFCBANK"
    assert parsed_bytes["ltp"] == 1600.0

    # 4. Binary struct payload (security_id: 1001, ltp: 2850.5, volume: 300)
    binary_data = struct.pack("!I f I", 1001, 2850.5, 300)
    parsed_struct = ws.parse_packet(binary_data)
    assert parsed_struct["symbol"] == "SYM_1001"
    assert parsed_struct["ltp"] == 2850.5
    assert parsed_struct["volume"] == 300

    # Verify callback was executed for process_packet / simulate calls
    assert len(received_ticks) == 3  # TCS, WIPRO, HDFCBANK


def test_websocket_auto_reconnect_backoff():
    """Test exponential backoff calculations: 1s, 2s, 4s, 8s, 16s..."""
    ws = DhanWebSocketClient()
    ws.initial_backoff = 1.0

    # Attempt 0: 1 * 2^0 = 1.0s
    assert ws.get_backoff_delay() == 1.0

    # Attempt 1: 1 * 2^1 = 2.0s
    ws.reconnect_attempts = 1
    assert ws.get_backoff_delay() == 2.0

    # Attempt 2: 1 * 2^2 = 4.0s
    ws.reconnect_attempts = 2
    assert ws.get_backoff_delay() == 4.0

    # Attempt 3: 1 * 2^3 = 8.0s
    ws.reconnect_attempts = 3
    assert ws.get_backoff_delay() == 8.0

    # Execute sync reconnect
    ws.reconnect()
    assert ws.is_connected is True


@pytest.mark.anyio
async def test_websocket_async_reconnect():
    """Test async reconnect with backoff execution."""
    ws = DhanWebSocketClient()
    ws.reconnect_attempts = 2
    res = await ws.reconnect_async()
    assert res is True
    assert ws.is_connected is True
    assert len(ws.gap_fill_history) > 0


def test_websocket_gap_fill_snapshot():
    """Test REST snapshot gap-fill request trigger."""
    ws = DhanWebSocketClient()
    ws.subscribe(["TATAMOTORS", "SBIN"])

    snap_res = ws.request_gap_fill()
    assert snap_res["status"] == "SUCCESS"
    assert "TATAMOTORS" in snap_res["symbols"]
    assert "SBIN" in snap_res["symbols"]
    assert snap_res["filled_count"] == 2
    assert len(ws.gap_fill_history) == 1


# ---------------------------------------------------------------------------
# Redis Cache Manager Tests
# ---------------------------------------------------------------------------

def test_redis_cache_fallback_and_crud():
    """Test in-memory dual-mode fallback cache CRUD operations."""
    cache = RedisCacheManager(port=9999)  # Non-existent port forces fallback mode
    assert cache.is_redis_available is False

    # Set & Get
    assert cache.set("stock:RELIANCE", {"ltp": 2900.0, "volume": 15000}, ttl=60) is True
    data = cache.get("stock:RELIANCE")
    assert data == {"ltp": 2900.0, "volume": 15000}

    # Delete
    assert cache.delete("stock:RELIANCE") is True
    assert cache.get("stock:RELIANCE") is None


def test_redis_cache_ttl_expiration():
    """Test TTL expiration in fallback in-memory cache."""
    cache = RedisCacheManager(port=9999)
    # Set key with 1-second TTL
    cache.set("short_key", "temp_value", ttl=1)
    assert cache.get("short_key") == "temp_value"

    # Wait for TTL to expire
    time.sleep(1.1)
    assert cache.get("short_key") is None


def test_redis_cache_hit_miss_stats():
    """Test cache hits, misses, and statistics reporting."""
    cache = RedisCacheManager(port=9999)
    cache.set("key1", "val1", ttl=60)

    # 2 hits
    _ = cache.get("key1")
    _ = cache.get("key1")

    # 1 miss
    _ = cache.get("non_existent_key")

    stats = cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_ratio_pct"] == round(2 / 3 * 100.0, 2)
    assert stats["status"] == "HEALTHY"
    assert stats["mode"] == "IN_MEMORY"
