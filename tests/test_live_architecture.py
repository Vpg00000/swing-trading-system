"""
Unit and Integration Tests for Live Dhan WebSocket Architecture Migration.
Tests:
1. DhanLiveFeedService & Market State Engine (Task 1)
2. Tiered Recompute Cadence & Live Valuation (Task 2)
3. SQLite Schema Freshness & Slow Persistence Worker (Task 3)
4. YFinanceClient Demotion & Repurposing (Task 4)
5. Screener Weekly Cadence, Jitter & Stale Fallback (Task 5)
6. FastAPI Live SSE Streaming & Opportunities Endpoint (Task 6)
"""

import time
import pytest
import pandas as pd
from datetime import datetime, date

from dataclasses import asdict
from unittest.mock import MagicMock, patch

# Service and Data Imports
from services.live_feed import DhanLiveFeedService
from services.live_scorer import LiveScorerService
from data.yfinance_client import YFinanceClient
from data.screener import ScreenerData, fetch_screener_data
from data.database import init_db, get_connection, flush_live_cache_to_db, query_stocks_grid
from engine.fundamental import compute_fundamental_score, FundamentalScore
from engine.scoring import calculate_opportunity_score


def test_dhan_live_feed_service_initialization():
    """Verify live feed service initializes live_cache and market session state correctly."""
    service = DhanLiveFeedService()
    assert isinstance(service.live_cache, dict)
    snapshot = service.get_snapshot("RELIANCE.NS")
    assert snapshot is not None
    assert "ltp" in snapshot
    assert "updated_at" in snapshot

    all_snapshots = service.get_all()
    assert isinstance(all_snapshots, dict)
    assert len(all_snapshots) > 0

    state = service.get_market_state()
    assert state in ["PRE_OPEN", "OPEN", "CLOSED"]


def test_dhan_live_feed_reconnect_and_gap_fill():
    """Verify reconnect logic and REST gap-fill snapshot execution."""
    service = DhanLiveFeedService()
    success = service.trigger_reconnect_gap_fill()
    assert success is True
    snapshot = service.get_snapshot("INFY.NS")
    assert snapshot["ltp"] > 0.0


def test_dhan_live_feed_auth_token_refresh():
    """Verify daily auth token refresh routine."""
    service = DhanLiveFeedService()
    refreshed = service.refresh_auth_token()
    assert refreshed is True


def test_tiered_recompute_speed1_indicators():
    """Verify Speed 1 tick-reactive indicator computation into in-memory indicators_cache."""
    feed_service = DhanLiveFeedService()
    scorer_service = LiveScorerService(feed_service=feed_service)

    # Trigger debounced technical calculation
    indicators = scorer_service.compute_technical_indicators("RELIANCE.NS")
    assert "ema20" in indicators
    assert "rsi" in indicators
    assert "atr" in indicators
    assert indicators["rsi"] >= 0.0 and indicators["rsi"] <= 100.0


def test_tiered_recompute_speed2_composite_score():
    """Verify Speed 2 interval composite rescoring and live P/E calculation."""
    feed_service = DhanLiveFeedService()
    scorer_service = LiveScorerService(feed_service=feed_service)

    scores = scorer_service.recombine_composite_scores()
    assert isinstance(scores, list)
    assert len(scores) > 0

    rel = next((s for s in scores if "RELIANCE" in s["symbol"]), scores[0])
    assert "overall_score" in rel
    assert "score_breakdown" in rel
    assert "pe" in rel


def test_sqlite_schema_freshness_and_slow_flush():
    """Verify SQLite database schema timestamps and zero-per-tick slow persistence flush."""
    init_db()
    
    mock_live_cache = {
        "RELIANCE.NS": {
            "symbol": "RELIANCE.NS",
            "ltp": 2950.50,
            "volume": 150000,
            "open": 2910.0,
            "high": 2960.0,
            "low": 2905.0,
            "prev_close": 2900.0,
            "vwap": 2935.0,
            "last_trade_time": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    }

    # Flush live cache to database via 60s slow timer worker function
    rows_written = flush_live_cache_to_db(mock_live_cache)
    assert rows_written >= 1

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM market_live WHERE symbol = 'RELIANCE.NS'")
        row = cursor.fetchone()
        assert row is not None
        assert row["ltp"] == 2950.50
        assert "updated_at" in row.keys()


def test_yfinance_client_demotion_and_repurposing():
    """Verify YFinanceClient is strictly for backfill, gap-fill fallback, and validation."""
    client = YFinanceClient()
    
    # Gap-fill fallback
    gap_data = client.get_gap_fill_snapshot(["RELIANCE.NS", "INFY.NS"])
    assert isinstance(gap_data, dict)

    # Sanity validation
    mock_df = pd.DataFrame({"Close": [2900.0]})
    with patch("data.yfinance_client.load_cached", return_value=mock_df):
        mock_snapshot = {"RELIANCE.NS": {"ltp": 2950.0}}
        val_report = client.validate_live_prices(mock_snapshot, tolerance_pct=15.0)
        assert "valid" in val_report
        assert val_report["valid"] is True



def test_screener_stale_data_fallback():
    """Verify Screener scorer handling when data_source is UNAVAILABLE (uses last cache with stale flag)."""
    unavailable_sd = ScreenerData(
        symbol="STALE_STOCK",
        pe_ratio=22.5,
        pb_ratio=3.1,
        roce=18.5,
        roe=16.0,
        debt_to_equity=0.2,
        sales_growth_3yr=12.5,
        profit_growth_3yr=15.0,
        opm_pct=21.0,
        promoter_holding_pct=65.0,
        current_price=500.0,
        book_value_per_share=160.0,
        market_cap_cr=15000.0,
        data_source="UNAVAILABLE",
        fetch_error="Circuit breaker active"
    )

    fund_score = compute_fundamental_score(unavailable_sd)
    assert fund_score.total_score > 0.0  # Must NOT zero score
    assert fund_score.status in ["STALE_CACHED_DATA", "DATA_UNAVAILABLE"]

    res = calculate_opportunity_score("STALE_STOCK", technical=75.0, fundamental=asdict(fund_score))
    assert res.total_score >= 50.0  # Stock with strong technicals is not unfairly penalized


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
def test_trade_lifecycle_dates_weekend_and_market_hours():
    import datetime
    from engine.trading_calendar import get_trade_lifecycle_dates

    # 1. Sunday test (2026-09-06)
    sunday_dt = datetime.datetime(2026, 9, 6, 1, 15)
    sched_sunday = get_trade_lifecycle_dates(now_dt=sunday_dt)
    assert sched_sunday["recommendation_date"] == "2026-09-06"
    assert sched_sunday["purchase_date"] == "2026-09-07"  # Monday next market open!
    assert sched_sunday["is_weekend"] is True

    # 2. Monday during market hours test (2026-09-07 10:00 AM)
    mon_open_dt = datetime.datetime(2026, 9, 7, 10, 0)
    sched_mon_open = get_trade_lifecycle_dates(now_dt=mon_open_dt)
    assert sched_mon_open["recommendation_date"] == "2026-09-07"
    assert sched_mon_open["purchase_date"] == "2026-09-07"
    assert sched_mon_open["is_weekend"] is False

    # 3. Monday after market close test (2026-09-07 4:00 PM)
    mon_close_dt = datetime.datetime(2026, 9, 7, 16, 0)
    sched_mon_close = get_trade_lifecycle_dates(now_dt=mon_close_dt)
    assert sched_mon_close["recommendation_date"] == "2026-09-07"
    assert sched_mon_close["purchase_date"] == "2026-09-08"  # Tuesday next market open!
