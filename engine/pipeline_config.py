"""
Centralized Configuration & Run Management for Swing Trading System Pipeline.

Provides:
- Unique sequential Run ID generation (`generate_run_id() -> RUN_YYYYMMDD_NNN`)
- Resource detection (CPU cores, memory availability, database paths)
- `PipelineConfig` dataclass for controlling pipeline execution parameters
"""

import os
import sys
import logging
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

# Base database path resolution
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "system.db"


def detect_system_resources() -> Dict[str, Any]:
    """
    Detects hardware resources and environment configuration:
    - CPU cores count
    - System memory (total and available in MB)
    - SQLite database path and file size
    """
    cores = os.cpu_count() or 1
    total_mem_mb = 8192.0
    avail_mem_mb = 4096.0

    # Check via psutil if available
    try:
        import psutil
        vm = psutil.virtual_memory()
        total_mem_mb = round(vm.total / (1024 * 1024), 2)
        avail_mem_mb = round(vm.available / (1024 * 1024), 2)
    except Exception:
        # Fallback via os.sysconf on POSIX/macOS
        try:
            if hasattr(os, "sysconf"):
                page_size = os.sysconf("SC_PAGE_SIZE")
                phys_pages = os.sysconf("SC_PHYS_PAGES")
                total_mem_mb = round((page_size * phys_pages) / (1024 * 1024), 2)
                # Estimate available memory as 50% of total
                avail_mem_mb = round(total_mem_mb * 0.5, 2)
        except Exception:
            pass

    db_path_str = str(DB_PATH)
    db_size_mb = 0.0
    try:
        if DB_PATH.exists():
            db_size_mb = round(DB_PATH.stat().st_size / (1024 * 1024), 2)
    except Exception:
        pass

    return {
        "cpu_cores": cores,
        "total_memory_mb": total_mem_mb,
        "available_memory_mb": avail_mem_mb,
        "database_path": db_path_str,
        "database_size_mb": db_size_mb,
    }


def generate_run_id(prefix: str = "RUN", target_date: Optional[str] = None) -> str:
    """
    Generates a sequential run ID in the format RUN_YYYYMMDD_NNN.
    Queries the SQLite pipeline_runs table to increment the counter for today.
    Example: RUN_20260914_001, RUN_20260914_002.
    """
    if target_date is None:
        today_str = datetime.now().strftime("%Y%m%d")
    else:
        today_str = target_date.replace("-", "")

    next_seq = 1
    pattern = f"{prefix}_{today_str}_%"

    try:
        from data.database import get_connection, init_db
        init_db()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT run_id FROM pipeline_runs WHERE run_id LIKE ? ORDER BY run_id DESC LIMIT 1",
                (pattern,)
            )
            row = cursor.fetchone()
            if row and row["run_id"]:
                latest_id = str(row["run_id"])
                # Extract counter after last underscore
                parts = latest_id.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    next_seq = int(parts[1]) + 1
    except Exception as exc:
        log.warning(f"Could not query pipeline_runs counter from DB: {exc}. Defaulting to 001.")

    return f"{prefix}_{today_str}_{next_seq:03d}"


@dataclass
class PipelineConfig:
    """Centralized configuration for swing trading pipeline runs."""
    run_id: str = field(default_factory=generate_run_id)
    worker_count: int = field(default_factory=lambda: max(1, (os.cpu_count() or 4) - 1))
    batch_size: int = 250
    max_memory_mb: float = 4096.0
    failure_tolerance_pct: float = 5.0
    min_expected_stocks: int = 100
    strategy_version: str = "v2.0.0"
    universe_mode: str = "ALL"
    clean_slate: bool = False
    db_path: str = field(default_factory=lambda: str(DB_PATH))
    timeout_seconds: int = 3600
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration parameters to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineConfig":
        """Instantiate PipelineConfig from dictionary, ignoring unrecognized keys."""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def detect_resources(self) -> Dict[str, Any]:
        """Detect system resources dynamically."""
        return detect_system_resources()
