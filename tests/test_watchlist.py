"""
Unit and Integration Tests for Watchlist Engine & API Endpoints.
Verifies Phase 3 Task A: Watchlist Engine & Custom Lists.
"""

import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from engine.watchlist import (
    WatchlistManager,
    get_user_watchlists,
    add_to_watchlist,
    remove_from_watchlist,
    create_watchlist,
    delete_watchlist
)
from web_server import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture to provide a clean SQLite DB with a populated stock_grid table."""
    db_file = tmp_path / "test_system.db"
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_grid (
            symbol TEXT PRIMARY KEY,
            close REAL,
            change_pct REAL,
            composite_score REAL,
            action TEXT,
            volume INTEGER
        );
    """)
    conn.execute(
        "INSERT INTO stock_grid (symbol, close, change_pct, composite_score, action, volume) VALUES (?, ?, ?, ?, ?, ?)",
        ("RELIANCE", 2450.50, 1.25, 82.5, "BUY", 1500000)
    )
    conn.execute(
        "INSERT INTO stock_grid (symbol, close, change_pct, composite_score, action, volume) VALUES (?, ?, ?, ?, ?, ?)",
        ("TCS", 3500.00, -0.50, 75.0, "ACCUMULATE", 800000)
    )
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def client():
    return TestClient(app)


def test_default_watchlists_seeded(temp_db):
    mgr = WatchlistManager(db_path=temp_db)
    watchlists = mgr.get_user_watchlists()

    expected_defaults = ['Nifty 50', 'Breakout Candidates', 'High RSI', 'My Favorites']
    for default_wl in expected_defaults:
        assert default_wl in watchlists, f"Default watchlist '{default_wl}' missing"

    nifty_50_items = watchlists['Nifty 50']
    assert len(nifty_50_items) > 0

    # Verify metrics per item: symbol, ltp, change_pct, score, signal, volume, added_at
    item = nifty_50_items[0]
    required_keys = {"symbol", "ltp", "change_pct", "score", "signal", "volume", "added_at"}
    assert required_keys.issubset(item.keys())

    # Check metric values for RELIANCE enriched from stock_grid fixture
    reliance_item = next((i for i in nifty_50_items if i["symbol"] == "RELIANCE"), None)
    assert reliance_item is not None
    assert reliance_item["ltp"] == 2450.50
    assert reliance_item["change_pct"] == 1.25
    assert reliance_item["score"] == 82.5
    assert reliance_item["signal"] == "BUY"
    assert reliance_item["volume"] == 1500000


def test_helper_functions(temp_db):
    # Test get_user_watchlists
    wls = get_user_watchlists(db_path=temp_db)
    assert 'My Favorites' in wls

    # Test add_to_watchlist
    res = add_to_watchlist("My Favorites", "INFY", db_path=temp_db)
    assert res["name"] == "My Favorites"
    symbols = [item["symbol"] for item in res["items"]]
    assert "INFY" in symbols

    # Test remove_from_watchlist
    removed = remove_from_watchlist("My Favorites", "INFY", db_path=temp_db)
    assert removed is True
    wls_after = get_user_watchlists("My Favorites", db_path=temp_db)
    symbols_after = [item["symbol"] for item in wls_after.get("My Favorites", [])]
    assert "INFY" not in symbols_after

    # Test create_watchlist
    created = create_watchlist("Crypto Watch", ["BTC", "ETH"], db_path=temp_db)
    assert created["name"] == "Crypto Watch"
    assert len(created["items"]) == 2

    # Test delete_watchlist
    deleted = delete_watchlist("Crypto Watch", db_path=temp_db)
    assert deleted is True
    wls_del = get_user_watchlists(db_path=temp_db)
    assert "Crypto Watch" not in wls_del


def test_api_watchlist_get(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "watchlists" in data
    assert "Nifty 50" in data["watchlists"]


def test_api_watchlist_get_by_name(client):
    response = client.get("/api/watchlist?name=My Favorites")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "My Favorites" in data["watchlists"]


def test_api_watchlist_post_add_symbol(client):
    payload = {"name": "My Favorites", "symbol": "TATAMOTORS"}
    response = client.post("/api/watchlist", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["watchlist"]["name"] == "My Favorites"
    symbols = [item["symbol"] for item in data["watchlist"]["items"]]
    assert "TATAMOTORS" in symbols


def test_api_watchlist_post_create_watchlist(client):
    payload = {"name": "Pharma Leaders", "symbols": ["SUNPHARMA", "CIPLA"]}
    response = client.post("/api/watchlist", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["watchlist"]["name"] == "Pharma Leaders"
    symbols = [item["symbol"] for item in data["watchlist"]["items"]]
    assert "SUNPHARMA" in symbols
    assert "CIPLA" in symbols


def test_api_watchlist_post_empty_name_error(client):
    response = client.post("/api/watchlist", json={"name": ""})
    assert response.status_code == 400


def test_api_watchlist_delete_symbol(client):
    # First add a symbol to ensure it exists
    client.post("/api/watchlist", json={"name": "Test Delete WL", "symbol": "WIPRO"})

    # Delete the symbol
    response = client.delete("/api/watchlist?name=Test Delete WL&symbol=WIPRO")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # Verify symbol is removed
    get_res = client.get("/api/watchlist?name=Test Delete WL")
    assert get_res.status_code == 200
    items = get_res.json()["watchlists"]["Test Delete WL"]
    symbols = [item["symbol"] for item in items]
    assert "WIPRO" not in symbols


def test_api_watchlist_delete_entire_watchlist(client):
    client.post("/api/watchlist", json={"name": "Temp WL", "symbols": ["SBIN"]})
    response = client.delete("/api/watchlist?name=Temp WL")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    get_res = client.get("/api/watchlist?name=Temp WL")
    assert get_res.status_code == 404
