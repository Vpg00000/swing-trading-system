"""
Unit and Integration Tests for Pipeline Run Management, Configuration,
High-Throughput Staging, and Atomic Publication.
"""

import os
import sqlite3
import pytest
from datetime import datetime, timezone
from pathlib import Path

from engine.pipeline_config import (
    generate_run_id,
    detect_system_resources,
    PipelineConfig,
)
from data.database import (
    init_db,
    get_connection,
    create_pipeline_run,
    update_pipeline_run,
    get_pipeline_run,
    get_recent_pipeline_runs,
    upsert_stock_metrics_staging,
    atomic_publish_stock_grid,
    acquire_pipeline_lock,
    release_pipeline_lock,
    query_stocks_grid,
)


@pytest.fixture(autouse=True)
def setup_db():
    """Ensure database schema is initialized and staging table is clean before each test."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM stock_grid_staging")
        conn.execute("DELETE FROM pipeline_lock")
        conn.commit()
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM stock_grid_staging")
        conn.execute("DELETE FROM pipeline_lock")
        conn.commit()


def test_generate_run_id():
    """Verify run ID generation format RUN_YYYYMMDD_NNN and incrementing counter."""
    test_date = "20260914"
    run_id1 = generate_run_id(target_date=test_date)
    assert run_id1.startswith(f"RUN_{test_date}_")
    
    create_pipeline_run(run_id1, universe_mode="ALL")
    
    run_id2 = generate_run_id(target_date=test_date)
    assert run_id2.startswith(f"RUN_{test_date}_")
    
    seq1 = int(run_id1.rsplit("_", 1)[1])
    seq2 = int(run_id2.rsplit("_", 1)[1])
    assert seq2 == seq1 + 1


def test_system_resource_detection():
    """Verify CPU, memory, and database path resource detection."""
    resources = detect_system_resources()
    assert "cpu_cores" in resources
    assert resources["cpu_cores"] >= 1
    assert "total_memory_mb" in resources
    assert resources["total_memory_mb"] > 0
    assert "available_memory_mb" in resources
    assert "database_path" in resources
    assert resources["database_path"].endswith("system.db")


def test_pipeline_config_dataclass():
    """Verify PipelineConfig defaults, serialization, and override."""
    cfg = PipelineConfig(
        worker_count=4,
        batch_size=100,
        strategy_version="v2.1.0",
        universe_mode="NIFTY500"
    )
    assert cfg.worker_count == 4
    assert cfg.batch_size == 100
    assert cfg.strategy_version == "v2.1.0"
    assert cfg.universe_mode == "NIFTY500"
    assert cfg.run_id.startswith("RUN_")

    data = cfg.to_dict()
    assert isinstance(data, dict)
    assert data["batch_size"] == 100

    reconstructed = PipelineConfig.from_dict(data)
    assert reconstructed.strategy_version == "v2.1.0"
    assert reconstructed.worker_count == 4


def test_pipeline_run_crud():
    """Verify creation, update, retrieval, and listing of pipeline runs."""
    run_id = f"RUN_TEST_{int(datetime.now().timestamp())}"
    create_pipeline_run(run_id, universe_mode="TEST")

    run_data = get_pipeline_run(run_id)
    assert run_data is not None
    assert run_data["run_id"] == run_id
    assert run_data["status"] == "INITIALIZING"
    assert run_data["universe_mode"] == "TEST"

    update_pipeline_run(
        run_id,
        status="COMPLETED",
        discovered_count=500,
        processed_count=500,
        success_count=498,
        failed_count=2,
        quality_score=99.6,
        duration_seconds=42.5
    )

    updated = get_pipeline_run(run_id)
    assert updated["status"] == "COMPLETED"
    assert updated["discovered_count"] == 500
    assert updated["processed_count"] == 500
    assert updated["success_count"] == 498
    assert updated["failed_count"] == 2
    assert updated["quality_score"] == 99.6
    assert updated["duration_seconds"] == 42.5

    recent = get_recent_pipeline_runs(limit=10)
    assert any(r["run_id"] == run_id for r in recent)


def test_staging_upsert_and_atomic_publish_success():
    """Verify high-throughput staging table insertion and atomic publication swap."""
    sample_records = [
        {
            "symbol": f"TEST_STK_{i:03d}.NS",
            "name": f"Test Stock {i}",
            "sector": "Technology",
            "cap_category": "LARGE",
            "close": 1500.0 + i,
            "change_pct": 1.5,
            "volume": 100000,
            "delivery_pct": 45.0,
            "rsi": 55.0,
            "composite_score": 75.0,
            "action": "BUY"
        }
        for i in range(120)
    ]

    inserted = upsert_stock_metrics_staging(sample_records)
    assert inserted == 120

    with get_connection() as conn:
        cnt = conn.execute("SELECT COUNT(*) as cnt FROM stock_grid_staging").fetchone()["cnt"]
        assert cnt == 120

    run_id = f"RUN_STAGING_TEST_{int(datetime.now().timestamp())}"
    create_pipeline_run(run_id, universe_mode="ALL")

    # Atomic publish with minimum expected rows = 100
    published = atomic_publish_stock_grid(run_id, min_expected_rows=100)
    assert published is True

    # After publish, production table should have the 120 rows and staging table should be empty
    with get_connection() as conn:
        prod_count = conn.execute("SELECT COUNT(*) as cnt FROM stock_grid WHERE symbol LIKE 'TEST_STK_%'").fetchone()["cnt"]
        assert prod_count == 120

        staging_count = conn.execute("SELECT COUNT(*) as cnt FROM stock_grid_staging").fetchone()["cnt"]
        assert staging_count == 0


def test_atomic_publish_rollback_when_insufficient_or_empty():
    """Verify that publish aborts and rolls back when staging rows are below threshold."""
    with get_connection() as conn:
        conn.execute("DELETE FROM stock_grid_staging")
        conn.commit()

    run_id = f"RUN_ROLLBACK_TEST_{int(datetime.now().timestamp())}"
    create_pipeline_run(run_id, universe_mode="ALL")

    # Staging has 0 rows, min_expected_rows = 10 -> Must return False
    published = atomic_publish_stock_grid(run_id, min_expected_rows=10)
    assert published is False

    run_data = get_pipeline_run(run_id)
    assert run_data["status"] == "FAILED"
    assert "below minimum threshold" in run_data["error_summary"] or "min_expected_rows" in run_data["error_summary"]


def test_pipeline_locking_mutual_exclusion():
    """Verify pipeline lock acquisition, denial to concurrent runs, and release."""
    run_1 = "RUN_LOCK_001"
    run_2 = "RUN_LOCK_002"

    assert acquire_pipeline_lock(run_1, timeout_seconds=60) is True
    # Re-acquisition by same holder is permitted (idempotent / renew)
    assert acquire_pipeline_lock(run_1, timeout_seconds=60) is True

    # Different run should be denied lock
    assert acquire_pipeline_lock(run_2, timeout_seconds=60) is False

    # Releasing run 1 allows run 2 to acquire
    assert release_pipeline_lock(run_1) is True
    assert acquire_pipeline_lock(run_2, timeout_seconds=60) is True
    assert release_pipeline_lock(run_2) is True


def test_atomic_publish_never_corrupts_production_grid():
    """Verify production stock_grid data is never corrupted if staging publish aborts."""
    # Ensure production table has known records
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO stock_grid (symbol, name, close) VALUES ('PROD_STK_01.NS', 'Prod Stock 1', 1234.5)")
        conn.commit()

    # Clear staging so it's empty
    with get_connection() as conn:
        conn.execute("DELETE FROM stock_grid_staging")
        conn.commit()

    run_id = f"RUN_SAFETY_{int(datetime.now().timestamp())}"
    create_pipeline_run(run_id, universe_mode="ALL")

    success = atomic_publish_stock_grid(run_id, min_expected_rows=50)
    assert success is False

    # Production table must still have PROD_STK_01.NS
    with get_connection() as conn:
        row = conn.execute("SELECT symbol, close FROM stock_grid WHERE symbol = 'PROD_STK_01.NS'").fetchone()
        assert row is not None
        assert row["close"] == 1234.5

