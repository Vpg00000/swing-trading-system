"""
Unit Test Suite for Data Validation & Integrity Engine.
Verifies Phase 6 (Tasks 84–113) invariants and permanently confirms the AUROPHARMA bug fix.
"""

import sqlite3
import numpy as np
import pandas as pd
import pytest

from engine.validation_engine import (
    DataStatus,
    VALID,
    MISSING,
    UNKNOWN,
    INVALID,
    STALE,
    CALCULATION_FAILED,
    NOT_APPLICABLE,
    clean_missing_indicator,
    compute_data_quality_score,
    evaluate_condition,
    get_run_validation_summary,
    init_validation_db,
    is_delivery_acceptable,
    is_null_or_na,
    record_validation_error,
    validate_52w_range,
    validate_and_sanitize_stock_record,
    validate_delivery,
    validate_ohlcv_record,
    validate_price_change,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Constants & Status Enums
# ─────────────────────────────────────────────────────────────────────────────

def test_data_status_enums_and_constants():
    assert DataStatus.VALID.value == "VALID"
    assert DataStatus.MISSING.value == "MISSING"
    assert DataStatus.UNKNOWN.value == "UNKNOWN"
    assert DataStatus.INVALID.value == "INVALID"
    assert DataStatus.STALE.value == "STALE"
    assert DataStatus.CALCULATION_FAILED.value == "CALCULATION_FAILED"
    assert DataStatus.NOT_APPLICABLE.value == "NOT_APPLICABLE"

    assert VALID == "VALID"
    assert MISSING == "MISSING"
    assert UNKNOWN == "UNKNOWN"
    assert INVALID == "INVALID"
    assert STALE == "STALE"
    assert CALCULATION_FAILED == "CALCULATION_FAILED"
    assert NOT_APPLICABLE == "NOT_APPLICABLE"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Non-negotiable Rules: N/A ≠ 0, NULL ≠ 0, UNKNOWN ≠ PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_non_negotiable_na_and_null_rules():
    # N/A ≠ 0: Never replace missing indicators or prices with 0
    assert clean_missing_indicator(None) is None
    assert clean_missing_indicator("") is None
    assert clean_missing_indicator("None") is None
    assert clean_missing_indicator(np.nan) is None
    assert clean_missing_indicator(0.0) is None
    assert clean_missing_indicator(0) is None

    # Valid indicators are preserved
    assert clean_missing_indicator(45.5) == 45.5
    assert clean_missing_indicator("102.3") == 102.3

    # NULL checks
    assert is_null_or_na(None) is True
    assert is_null_or_na(np.nan) is True
    assert is_null_or_na(pd.NA) is True
    assert is_null_or_na("") is True
    assert is_null_or_na("   ") is True
    assert is_null_or_na(100.0) is False


def test_unknown_not_pass_rule():
    # UNKNOWN ≠ PASS: Unknown or missing values must NEVER evaluate to True
    assert evaluate_condition(value=50.0, status=DataStatus.UNKNOWN) is False
    assert evaluate_condition(value=50.0, status=UNKNOWN) is False
    assert evaluate_condition(value=50.0, status=DataStatus.MISSING) is False
    assert evaluate_condition(value=50.0, status=DataStatus.INVALID) is False
    assert evaluate_condition(value=None, status=DataStatus.VALID) is False
    assert evaluate_condition(value=np.nan, status=DataStatus.VALID) is False

    # Valid evaluations
    assert evaluate_condition(value=50.0, status=DataStatus.VALID, op=">=", threshold=40.0) is True
    assert evaluate_condition(value=30.0, status=DataStatus.VALID, op=">=", threshold=40.0) is False
    assert evaluate_condition(value=50.0, status=DataStatus.VALID, op=">", threshold=50.0) is False
    assert evaluate_condition(value=50.1, status=DataStatus.VALID, op=">", threshold=50.0) is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Delivery Validation & Filter Rules
# ─────────────────────────────────────────────────────────────────────────────

def test_delivery_validation_and_filter():
    # Missing delivery must be delivery_pct = None, status UNKNOWN (NEVER 0!)
    val, status, is_valid = validate_delivery(None)
    assert val is None
    assert status == UNKNOWN
    assert is_valid is False

    val, status, is_valid = validate_delivery(np.nan)
    assert val is None
    assert status == UNKNOWN
    assert is_valid is False

    # Screener filter must reject missing delivery
    assert is_delivery_acceptable(None, min_threshold=20.0) is False
    assert is_delivery_acceptable(np.nan, min_threshold=20.0) is False

    # Zero delivery passes validity check as float 0.0, but fails minimum threshold
    val, status, is_valid = validate_delivery(0.0)
    assert val == 0.0
    assert status == VALID
    assert is_valid is True
    assert is_delivery_acceptable(0.0, min_threshold=20.0) is False

    # Valid delivery above threshold
    val, status, is_valid = validate_delivery(42.8)
    assert val == 42.8
    assert status == VALID
    assert is_valid is True
    assert is_delivery_acceptable(42.8, min_threshold=20.0) is True

    # Impossible delivery (> 100 or < 0)
    val, status, is_valid = validate_delivery(105.0)
    assert val is None
    assert status == INVALID
    assert is_valid is False

    # Recovery from traded and delivered qty
    val, status, is_valid = validate_delivery(None, delivered_qty=2500, traded_qty=10000)
    assert val == 25.0
    assert status == VALID
    assert is_valid is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. OHLC Physics Validator
# ─────────────────────────────────────────────────────────────────────────────

def test_ohlc_physics_valid_normal():
    # Standard valid equity candle
    record = {
        "symbol": "RELIANCE.NS",
        "open": 2500.0,
        "high": 2550.0,
        "low": 2480.0,
        "close": 2530.0,
        "volume": 1200000,
    }
    is_valid, errors = validate_ohlcv_record(record)
    assert is_valid is True
    assert len(errors) == 0

    # Circuit limit (Open == High == Low == Close)
    circuit_record = {
        "Open": 100.0,
        "High": 100.0,
        "Low": 100.0,
        "Close": 100.0,
        "Volume": 5000,
    }
    is_valid, errors = validate_ohlcv_record(circuit_record)
    assert is_valid is True
    assert len(errors) == 0


def test_ohlc_physics_violations():
    # Negative / Zero prices
    record_zero = {"open": 0, "high": 100, "low": 0, "close": 50}
    is_valid, errors = validate_ohlcv_record(record_zero)
    assert is_valid is False
    assert any("Open price (0" in e for e in errors)
    assert any("Low price (0" in e for e in errors)

    # High < Low
    record_inverted = {"open": 100, "high": 90, "low": 110, "close": 95}
    is_valid, errors = validate_ohlcv_record(record_inverted)
    assert is_valid is False
    assert any("High (90.0) < Low (110.0)" in e for e in errors)

    # Open outside [Low, High]
    record_open_out = {"open": 120, "high": 110, "low": 90, "close": 100}
    is_valid, errors = validate_ohlcv_record(record_open_out)
    assert is_valid is False
    assert any("Open (120.0) is outside" in e for e in errors)

    # Close outside [Low, High]
    record_close_out = {"open": 100, "high": 110, "low": 90, "close": 85}
    is_valid, errors = validate_ohlcv_record(record_close_out)
    assert is_valid is False
    assert any("Close (85.0) is outside" in e for e in errors)

    # Negative volume
    record_neg_vol = {"open": 100, "high": 110, "low": 90, "close": 105, "volume": -10}
    is_valid, errors = validate_ohlcv_record(record_neg_vol)
    assert is_valid is False
    assert any("Volume (-10.0) < 0" in e for e in errors)


# ─────────────────────────────────────────────────────────────────────────────
# 5. AUROPHARMA Bug Simulation & Permanent Fix
# ─────────────────────────────────────────────────────────────────────────────

def test_auropharma_bug_simulation():
    """
    Simulation of the AUROPHARMA data corruption bug:
      - ₹0 Open, High, Low
      - ₹0 EMA
      - ₹0 52-Week Range
      - Mismatched reported change of +3.50% when real close/prev_close was +0.68%
      - Missing delivery
    """
    corrupt_auropharma = {
        "symbol": "AUROPHARMA.NS",
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "close": 1006.8,
        "prev_close": 1000.0,
        "change_pct": 3.50,       # Corrupted reported change
        "high_52w": 0.0,          # Corrupted 52w high
        "low_52w": 0.0,           # Corrupted 52w low
        "ema20": 0.0,             # Corrupted ₹0 EMA
        "delivery_pct": None,     # Missing delivery
        "volume": 850000,
    }

    # 1. OHLC validator catches the zero Open/High/Low immediately
    is_valid_ohlc, ohlc_errors = validate_ohlcv_record(corrupt_auropharma)
    assert is_valid_ohlc is False
    assert any("INVALID_OHLC" in e for e in ohlc_errors)

    # 2. Price change validator catches reported +3.50% vs actual +0.68%
    expected_chg, is_chg_valid, chg_status = validate_price_change(
        close=corrupt_auropharma["close"],
        prev_close=corrupt_auropharma["prev_close"],
        reported_change_pct=corrupt_auropharma["change_pct"]
    )
    assert abs(expected_chg - 0.68) < 0.01
    assert is_chg_valid is False
    assert chg_status == "CHANGE_MISMATCH"

    # 3. 52-Week Range validator rejects impossible ₹0 values and sets them to None
    range_res = validate_52w_range(
        high_52w=corrupt_auropharma["high_52w"],
        low_52w=corrupt_auropharma["low_52w"],
        close=corrupt_auropharma["close"]
    )
    assert range_res["is_valid"] is False
    assert range_res["high_52w"] is None   # NEVER 0!
    assert range_res["low_52w"] is None    # NEVER 0!
    assert range_res["status"] == INVALID

    # 4. Data Quality Score must fail hard for this corrupted record
    dq_score = compute_data_quality_score(corrupt_auropharma)
    assert dq_score < 40.0  # Fails quality threshold

    # 5. validate_and_sanitize_stock_record permanently repairs/sanitizes the record
    sanitized = validate_and_sanitize_stock_record(corrupt_auropharma)
    assert sanitized["data_status"] == INVALID
    assert sanitized["change_pct"] == 0.68  # Bogus 3.50% replaced with true 0.68%
    assert sanitized["high_52w"] is None    # Never kept as 0
    assert sanitized["low_52w"] is None     # Never kept as 0
    assert sanitized["ema20"] is None       # Never kept as 0
    assert sanitized["delivery_pct"] is None
    assert sanitized["delivery_status"] == UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# 6. 52-Week Range Validator & Independent Calculator
# ─────────────────────────────────────────────────────────────────────────────

def test_52w_range_healing_from_history():
    # When reported is ₹0 or missing, but historical DataFrame is supplied
    dates = pd.date_range("2025-01-01", periods=100)
    df_history = pd.DataFrame({
        "Date": dates,
        "High": np.linspace(800, 1250, 100),
        "Low": np.linspace(650, 950, 100),
        "Close": np.linspace(700, 1200, 100),
    })

    # Reported values are 0.0 (corrupt)
    res = validate_52w_range(
        high_52w=0.0,
        low_52w=0.0,
        close=1200.0,
        df_history=df_history
    )

    assert res["is_valid"] is True
    assert res["status"] == VALID
    assert res["source"] == "CALCULATED"
    assert res["high_52w"] == 1250.0
    assert res["low_52w"] == 650.0
    assert res["pct_from_52w_high"] == round(((1200.0 - 1250.0) / 1250.0) * 100.0, 2)


def test_52w_range_valid_reported():
    res = validate_52w_range(high_52w=1500.0, low_52w=1000.0, close=1250.0)
    assert res["is_valid"] is True
    assert res["source"] == "REPORTED"
    assert res["high_52w"] == 1500.0
    assert res["low_52w"] == 1000.0
    assert res["pct_from_52w_high"] == round(((1250.0 - 1500.0) / 1500.0) * 100.0, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Price Change Recalculation & Tolerance
# ─────────────────────────────────────────────────────────────────────────────

def test_price_change_tolerance():
    # Exact match
    exp, valid, code = validate_price_change(close=105.0, prev_close=100.0, reported_change_pct=5.0)
    assert valid is True
    assert exp == 5.0
    assert code == VALID

    # Within tolerance 0.15% (e.g. slight rounding in data feed)
    exp, valid, code = validate_price_change(close=105.08, prev_close=100.0, reported_change_pct=5.0)
    assert valid is True  # diff is 0.08 <= 0.15

    # Out of tolerance (e.g. reported is 2.50% when real is 5.0%)
    exp, valid, code = validate_price_change(close=105.0, prev_close=100.0, reported_change_pct=2.50)
    assert valid is False
    assert code == "CHANGE_MISMATCH"

    # Missing prev_close or close <= 0
    exp, valid, code = validate_price_change(close=105.0, prev_close=0.0, reported_change_pct=2.50)
    assert valid is False
    assert code == "INVALID_PREV_CLOSE"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Data Quality Score Computation
# ─────────────────────────────────────────────────────────────────────────────

def test_data_quality_score_clean_record():
    clean_record = {
        "symbol": "TCS.NS",
        "open": 3500.0,
        "high": 3550.0,
        "low": 3480.0,
        "close": 3520.0,
        "prev_close": 3500.0,
        "change_pct": 0.5714,
        "volume": 2500000,
        "delivery_pct": 52.4,
        "high_52w": 4200.0,
        "low_52w": 3300.0,
        "ema20": 3490.0,
        "ema50": 3450.0,
        "ema200": 3380.0,
        "rsi": 58.5,
        "atr": 45.0,
    }
    score = compute_data_quality_score(clean_record)
    assert score == 100.0


def test_data_quality_score_missing_delivery_partial():
    # If delivery is missing, it receives 0 delivery pts (15 pts deduction)
    partial_record = {
        "symbol": "INFY.NS",
        "open": 1600.0,
        "high": 1620.0,
        "low": 1590.0,
        "close": 1610.0,
        "prev_close": 1600.0,
        "change_pct": 0.625,
        "volume": 1500000,
        "delivery_pct": None,  # Missing
        "high_52w": 1900.0,
        "low_52w": 1350.0,
        "ema20": 1595.0,
        "rsi": 52.0,
    }
    score = compute_data_quality_score(partial_record)
    assert 80.0 <= score <= 85.0


# ─────────────────────────────────────────────────────────────────────────────
# 9. Validation Errors Table & Provenance Summary
# ─────────────────────────────────────────────────────────────────────────────

def test_validation_errors_db_provenance():
    # Use in-memory SQLite database
    conn = sqlite3.connect(":memory:")
    init_validation_db(conn)

    run_id = "RUN_PIPELINE_20260914"

    # Record 3 distinct errors
    id1 = record_validation_error(
        run_id=run_id,
        symbol="AUROPHARMA.NS",
        field="OHLC",
        error_type="INVALID_OHLC",
        expected="Open, High, Low, Close > 0",
        actual="Open price (0.0) <= 0",
        severity="CRITICAL",
        conn=conn,
    )
    assert id1 > 0

    id2 = record_validation_error(
        run_id=run_id,
        symbol="AUROPHARMA.NS",
        field="change_pct",
        error_type="CHANGE_MISMATCH",
        expected=0.68,
        actual=3.50,
        severity="ERROR",
        conn=conn,
    )
    assert id2 > id1

    id3 = record_validation_error(
        run_id=run_id,
        symbol="ZOMATO.NS",
        field="delivery_pct",
        error_type="MISSING_DELIVERY",
        expected="delivery_pct >= 0",
        actual=None,
        severity="WARNING",
        conn=conn,
    )
    assert id3 > id2

    # Fetch summary
    summary = get_run_validation_summary(run_id=run_id, conn=conn)

    assert summary["run_id"] == run_id
    assert summary["total_errors"] == 3
    assert summary["symbols_affected"] == 2
    assert summary["symbols"] == ["AUROPHARMA.NS", "ZOMATO.NS"]

    assert summary["by_severity"]["CRITICAL"] == 1
    assert summary["by_severity"]["ERROR"] == 1
    assert summary["by_severity"]["WARNING"] == 1

    assert summary["by_error_type"]["INVALID_OHLC"] == 1
    assert summary["by_error_type"]["CHANGE_MISMATCH"] == 1
    assert summary["by_error_type"]["MISSING_DELIVERY"] == 1

    assert len(summary["errors"]) == 3
