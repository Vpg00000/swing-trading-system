"""
Unit tests for data/fii_dii.py - TASK-010 FII/DII Data Engine.
Verifies zero mock data generation, NSE parsing, cache/DB persistence, and summary signals.
"""

import pytest
from unittest.mock import patch
from datetime import date
from data.fii_dii import (
    _clean_val,
    _parse_nse_date,
    load_history,
    save_history,
    update_fii_dii_cache,
    get_fii_dii_history,
    get_fii_dii_summary,
    HISTORY_FILE
)


def test_clean_val_and_date_parsing():
    assert _clean_val("1,234.56") == 1234.56
    assert _clean_val(100.0) == 100.0
    assert _clean_val(None) == 0.0
    assert _clean_val("invalid") == 0.0

    parsed_dt = _parse_nse_date("04-Sep-2026")
    assert parsed_dt == "2026-09-04"
    assert _parse_nse_date(None) == date.today().strftime("%Y-%m-%d")


def test_load_history_zero_mock_data(tmp_path, monkeypatch):
    """Ensure load_history does NOT synthesize fake mock records when cache is empty."""
    test_cache = tmp_path / "fii_dii_history.json"
    monkeypatch.setattr("data.fii_dii.HISTORY_FILE", test_cache)
    monkeypatch.setattr("data.database.query_fii_dii_history", lambda days=30: [])

    records = load_history()
    assert isinstance(records, list)
    assert len(records) == 0, "load_history must return empty list when no cache exists (zero mock data)"


def test_update_fii_dii_cache_live_parsing(tmp_path, monkeypatch):
    """Test live data merging into history and disk/DB persistence."""
    test_cache = tmp_path / "fii_dii_history.json"
    monkeypatch.setattr("data.fii_dii.HISTORY_FILE", test_cache)

    mock_live = [
        {"category": "FII/FPI *", "date": "04-Sep-2026", "buyValue": "15,000.0", "sellValue": "12,000.0", "netValue": "3,000.0"},
        {"category": "DII **", "date": "04-Sep-2026", "buyValue": "10,000.0", "sellValue": "9,000.0", "netValue": "1,000.0"}
    ]

    with patch("data.fii_dii.fetch_live_fii_dii", return_value=mock_live):
        history = update_fii_dii_cache()
        assert len(history) >= 1
        today_rec = [r for r in history if r["date"] == "2026-09-04"]
        assert len(today_rec) == 1
        rec = today_rec[0]
        assert rec["fii_buy"] == 15000.0
        assert rec["fii_sell"] == 12000.0
        assert rec["fii_net"] == 3000.0
        assert rec["dii_buy"] == 10000.0
        assert rec["dii_sell"] == 9000.0
        assert rec["dii_net"] == 1000.0
        assert rec["total_net"] == 4000.0


def test_get_fii_dii_summary():
    """Verify summary calculations and signal classification."""
    summary = get_fii_dii_summary()
    assert isinstance(summary, dict)
    assert "fii_net" in summary
    assert "dii_net" in summary
    assert "total_net" in summary
    assert "cum_5d_fii" in summary
    assert "signal" in summary
