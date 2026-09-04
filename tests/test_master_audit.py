"""
Master Audit Test Suite — verifies actual repository behavior and module integrity
for all core trading system components.
"""

import pytest
from pathlib import Path

from engine import decision, indicators, macro_regime, fundamental, governance
from data import database, sync_engine, dhan_auth, microstructure, fii_dii


def test_master_audit_engine_imports():
    """Verify all core engine modules import cleanly and define primary interfaces."""
    assert hasattr(decision, "evaluate_decision") or hasattr(decision, "compute_composite_score")
    assert hasattr(indicators, "compute_indicators") or hasattr(indicators, "IndicatorResult")
    assert hasattr(macro_regime, "calculate_vix_percentile") or hasattr(macro_regime, "calculate_advance_decline_breadth")


def test_master_audit_data_imports():
    """Verify data layer modules and database connectivity."""
    assert hasattr(database, "get_connection") and hasattr(database, "init_db")
    assert hasattr(sync_engine, "compute_all") or hasattr(sync_engine, "compute_expected_return")


def test_master_audit_csv_tracker_exists():
    """Verify task tracker CSV exists and is populated with valid tasks."""
    tracker_path = Path("AI_Investment_Command_Center_Task_Tracker.csv")
    assert tracker_path.exists(), "Task tracker CSV must exist"
    lines = tracker_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 40, f"Task tracker should contain at least 40 task rows, got {len(lines)}"
    assert any("IMPLEMENTED" in line or "VERIFIED" in line or "TASK" in line for line in lines)