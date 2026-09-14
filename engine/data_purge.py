"""
engine/data_purge.py — Total Clean-Slate & Data Purge Engine.

Completely wipes:
1. In-memory web caches (_GRID_STOCKS_CACHE, _cache, report data).
2. Disk caches (data/cache/*.csv, data/cache/delivery/*.csv, reports/*.json, research dossiers).
3. SQLite analysis database tables (stock_grid, market_data, indicators, etc.).
Preserves:
- User authentication, watchlists, portfolio snapshots, and audit logs.
Reclaims disk space via SQLite WAL checkpoint and VACUUM.
"""

import os
import sys
import time
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.database import DB_PATH, get_connection, init_db

log = logging.getLogger("data_purge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Tables that store transient analysis and market data to be purged on clean slate
ANALYSIS_TABLES = [
    "stock_grid",
    "market_data",
    "market_live",
    "indicators",
    "fundamentals",
    "features_daily",
    "ohlcv_daily",
    "corporate_filings",
    "prediction_outcomes",
    "accuracy_evaluation",
    "decision_signals",
    "signal_events",
    "prediction_freeze_log"
]

# Protected tables that must NEVER be deleted during data purge
PROTECTED_TABLES = [
    "portfolio_snapshots",
    "fii_dii_history",
    "institutional_flow",
    "auth_users",
    "watchlists",
    "system_logs",
    "schema_migrations"
]

CACHE_DIRS = [
    PROJECT_ROOT / "data" / "cache",
    PROJECT_ROOT / "data" / "cache" / "delivery",
    PROJECT_ROOT / "reports" / "research"
]

CACHE_FILES = [
    PROJECT_ROOT / "reports" / "latest_report_cache.json"
]


def purge_database_tables(tables: Optional[List[str]] = None) -> Dict[str, int]:
    """Truncates transient market analysis tables and reclaims disk space."""
    target_tables = tables or ANALYSIS_TABLES
    init_db()
    purged_counts: Dict[str, int] = {}

    with get_connection() as conn:
        cursor = conn.cursor()
        for tbl in target_tables:
            if tbl in PROTECTED_TABLES:
                continue
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = cursor.fetchone()[0]
                cursor.execute(f"DELETE FROM {tbl}")
                purged_counts[tbl] = count
            except sqlite3.OperationalError:
                purged_counts[tbl] = 0

        conn.commit()

    # Reclaim disk space and reset WAL
    try:
        raw_conn = sqlite3.connect(DB_PATH)
        raw_conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        raw_conn.execute("VACUUM;")
        raw_conn.close()
    except Exception as exc:
        log.warning(f"WAL checkpoint / VACUUM notice: {exc}")

    return purged_counts


def purge_filesystem_caches() -> Dict[str, int]:
    """Deletes all cached OHLCV CSVs, delivery CSVs, and report cache files."""
    deleted_files = 0
    deleted_bytes = 0

    # 1. Purge cache directories
    for cache_dir in CACHE_DIRS:
        if cache_dir.exists() and cache_dir.is_dir():
            for p in cache_dir.iterdir():
                if p.is_file() and not p.name.startswith("."):
                    try:
                        deleted_bytes += p.stat().st_size
                        p.unlink()
                        deleted_files += 1
                    except Exception as e:
                        log.warning(f"Could not remove {p.name}: {e}")

    # 2. Purge specific cache files
    for cf in CACHE_FILES:
        if cf.exists() and cf.is_file():
            try:
                deleted_bytes += cf.stat().st_size
                cf.unlink()
                deleted_files += 1
            except Exception as e:
                log.warning(f"Could not remove {cf.name}: {e}")

    return {
        "deleted_files_count": deleted_files,
        "deleted_bytes": deleted_bytes,
        "deleted_mb": round(deleted_bytes / (1024 * 1024), 2)
    }


def invalidate_in_memory_caches():
    """Invalidates web server in-memory caches if web_server is running or loaded."""
    try:
        import web_server
        if hasattr(web_server, "invalidate_grid_stocks_cache"):
            web_server.invalidate_grid_stocks_cache()
        if hasattr(web_server, "_cache"):
            web_server._cache["data"] = None
            web_server._cache["timestamp"] = 0.0
    except Exception:
        pass


def clean_slate_wipe(scopes: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Executes an atomic total clean-slate wipe across database tables,
    disk caches, and in-memory caches.
    """
    start_time = time.time()
    log.info("Initiating Full Clean-Slate Purge...")

    # 1. Database tables
    db_stats = purge_database_tables()
    total_db_rows = sum(db_stats.values())
    log.info(f"Purged {total_db_rows} rows across {len(db_stats)} SQLite analysis tables.")

    # 2. File caches
    file_stats = purge_filesystem_caches()
    log.info(f"Purged {file_stats['deleted_files_count']} cache files ({file_stats['deleted_mb']} MB).")

    # 3. In-memory caches
    invalidate_in_memory_caches()
    log.info("Invalidated web server in-memory caches.")

    elapsed = round(time.time() - start_time, 3)
    log.info(f"✓ Clean-Slate Purge Complete in {elapsed}s!")

    return {
        "status": "SUCCESS",
        "elapsed_seconds": elapsed,
        "database_rows_purged": total_db_rows,
        "database_tables": db_stats,
        "files_purged": file_stats["deleted_files_count"],
        "bytes_freed": file_stats["deleted_bytes"],
        "mb_freed": file_stats["deleted_mb"]
    }


if __name__ == "__main__":
    res = clean_slate_wipe()
    print(res)
