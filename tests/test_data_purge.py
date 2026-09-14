"""Unit tests for engine/data_purge.py"""
import pytest
from engine.data_purge import clean_slate_wipe, purge_database_tables, purge_filesystem_caches, PROTECTED_TABLES
from data.database import get_connection, init_db

def test_data_purge_preserves_protected_tables():
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        # Ensure watchlists exists
        cursor.execute("CREATE TABLE IF NOT EXISTS watchlists (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT OR REPLACE INTO watchlists (id, name) VALUES (999, 'TestWatchlist')")
        conn.commit()

    res = clean_slate_wipe()
    assert res["status"] == "SUCCESS"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM watchlists WHERE id = 999")
        assert cursor.fetchone()[0] == 1
        # Check that stock_grid is empty
        cursor.execute("SELECT COUNT(*) FROM stock_grid")
        assert cursor.fetchone()[0] == 0
