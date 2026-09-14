"""
Data Validation & Integrity Engine for Indian Equities.

Fulfills Phase 6 (Tasks 84–113) of the Clean-Slate Full-Market Pipeline.
Permanently resolves data integrity anomalies including the AUROPHARMA bug:
  - ₹0 Open/High/Low
  - ₹0 EMA and indicators
  - ₹0 52-Week range
  - Mismatched reported % change vs actual Close / Prev Close

Core Invariants (Non-negotiable Rules):
  1. N/A ≠ 0: Never replace missing prices/indicators with 0.
  2. NULL ≠ 0: Keep missing fields as None/NULL.
  3. UNKNOWN ≠ PASS: Unknown conditions must NEVER evaluate to True.
  4. Missing delivery must be delivery_pct = None, status UNKNOWN (never 0 and never passing delivery checks).
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "system.db"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Data Status Enum & Top-Level Constants
# ─────────────────────────────────────────────────────────────────────────────

class DataStatus(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"
    STALE = "STALE"
    CALCULATION_FAILED = "CALCULATION_FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


VALID = DataStatus.VALID.value
MISSING = DataStatus.MISSING.value
UNKNOWN = DataStatus.UNKNOWN.value
INVALID = DataStatus.INVALID.value
STALE = DataStatus.STALE.value
CALCULATION_FAILED = DataStatus.CALCULATION_FAILED.value
NOT_APPLICABLE = DataStatus.NOT_APPLICABLE.value


# ─────────────────────────────────────────────────────────────────────────────
# 2. Database Initialization & Validation Errors Provenance
# ─────────────────────────────────────────────────────────────────────────────

def get_db_connection(conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
    """Get active connection or create connection to system.db."""
    if conn is not None:
        return conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    return c


def init_validation_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Ensure the validation_errors table and indexes exist."""
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS validation_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                field TEXT,
                error_type TEXT NOT NULL,
                expected TEXT,
                actual TEXT,
                severity TEXT DEFAULT 'ERROR',  -- WARNING, ERROR, CRITICAL
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_validation_errors_run ON validation_errors(run_id);
            CREATE INDEX IF NOT EXISTS idx_validation_errors_sym ON validation_errors(symbol);
            CREATE INDEX IF NOT EXISTS idx_validation_errors_type ON validation_errors(error_type);
        """)
        conn.commit()
    finally:
        if close_after:
            conn.close()


def record_validation_error(
    run_id: str,
    symbol: str,
    field: str,
    error_type: str,
    expected: Any,
    actual: Any,
    severity: str = "ERROR",
    conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Persists a data integrity violation into validation_errors table for provenance.
    Severity can be: 'WARNING', 'ERROR', 'CRITICAL'.
    """
    def _to_str(val: Any) -> str:
        if val is None:
            return "None"
        if isinstance(val, (dict, list)):
            try:
                return json.dumps(val)
            except Exception:
                return str(val)
        return str(val)

    exp_str = _to_str(expected)
    act_str = _to_str(actual)

    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO validation_errors (run_id, symbol, field, error_type, expected, actual, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, symbol, field, error_type, exp_str, act_str, severity.upper())
            )
            conn.commit()
            inserted_id = cursor.lastrowid or 0
        except sqlite3.OperationalError:
            # Table might be missing in a fresh DB connection
            init_validation_db(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO validation_errors (run_id, symbol, field, error_type, expected, actual, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, symbol, field, error_type, exp_str, act_str, severity.upper())
            )
            conn.commit()
            inserted_id = cursor.lastrowid or 0

        log.warning(
            f"[{severity.upper()}] Validation error recorded for {symbol} field='{field}' "
            f"type='{error_type}' expected='{exp_str}' actual='{act_str}' (run_id={run_id})"
        )
        return inserted_id
    finally:
        if close_after:
            conn.close()


def get_run_validation_summary(
    run_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Retrieves the aggregate validation summary for a given pipeline run_id.
    """
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True

    try:
        init_validation_db(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, run_id, symbol, field, error_type, expected, actual, severity, created_at
            FROM validation_errors
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,)
        )
        rows = cursor.fetchall()

        by_severity: Dict[str, int] = {"CRITICAL": 0, "ERROR": 0, "WARNING": 0}
        by_error_type: Dict[str, int] = {}
        symbols_set = set()
        error_records = []

        for r in rows:
            keys = r.keys() if hasattr(r, "keys") else []
            sev = (r["severity"] if "severity" in keys else r[7] or "ERROR").upper()
            err_type = r["error_type"] if "error_type" in keys else r[4]
            sym = r["symbol"] if "symbol" in keys else r[2]

            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_error_type[err_type] = by_error_type.get(err_type, 0) + 1
            symbols_set.add(sym)

            error_records.append({
                "id": r["id"] if "id" in keys else r[0],
                "run_id": r["run_id"] if "run_id" in keys else r[1],
                "symbol": sym,
                "field": r["field"] if "field" in keys else r[3],
                "error_type": err_type,
                "expected": r["expected"] if "expected" in keys else r[5],
                "actual": r["actual"] if "actual" in keys else r[6],
                "severity": sev,
                "created_at": r["created_at"] if "created_at" in keys else r[8],
            })

        return {
            "run_id": run_id,
            "total_errors": len(rows),
            "by_severity": by_severity,
            "by_error_type": by_error_type,
            "symbols_affected": len(symbols_set),
            "symbols": sorted(list(symbols_set)),
            "errors": error_records,
        }
    finally:
        if close_after:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Non-negotiable Rules & Helpers (N/A ≠ 0, NULL ≠ 0, UNKNOWN ≠ PASS)
# ─────────────────────────────────────────────────────────────────────────────

def is_null_or_na(val: Any) -> bool:
    """Check if value is None, NaN, pd.NA, or empty string."""
    if val is None:
        return True
    if isinstance(val, (float, np.floating)) and math.isnan(val):
        return True
    if pd.isna(val):
        return True
    if isinstance(val, str) and val.strip() in ("", "None", "NULL", "nan", "NaN", "N/A"):
        return True
    return False


def clean_missing_indicator(val: Any) -> Optional[float]:
    """
    Non-negotiable Rule: N/A ≠ 0, NULL ≠ 0.
    Never replace missing prices/indicators with 0.
    If value is 0.0 or None or NaN, returns None (missing).
    """
    if is_null_or_na(val):
        return None
    try:
        f = float(val)
        if math.isnan(f) or f == 0.0:
            return None
        return f
    except (ValueError, TypeError):
        return None


def evaluate_condition(
    value: Any,
    status: Union[str, DataStatus] = VALID,
    op: str = ">=",
    threshold: float = 0.0
) -> bool:
    """
    Non-negotiable Rule: UNKNOWN ≠ PASS.
    Unknown conditions or missing values must NEVER evaluate to True.
    """
    status_str = status.value if isinstance(status, DataStatus) else str(status)
    if status_str in (UNKNOWN, MISSING, INVALID, CALCULATION_FAILED, NOT_APPLICABLE):
        return False
    if is_null_or_na(value):
        return False

    try:
        f_val = float(value)
        if op == ">=":
            return f_val >= threshold
        elif op == ">":
            return f_val > threshold
        elif op == "<=":
            return f_val <= threshold
        elif op == "<":
            return f_val < threshold
        elif op == "==":
            return f_val == threshold
        elif op == "!=":
            return f_val != threshold
        else:
            return False
    except (ValueError, TypeError):
        return False


def validate_delivery(
    delivery_pct: Any,
    delivered_qty: Any = None,
    traded_qty: Any = None
) -> Tuple[Optional[float], str, bool]:
    """
    Delivery data validator.
    Non-negotiable Rule:
      Missing delivery must be delivery_pct = None, status UNKNOWN
      (never 0 and never passing delivery checks).
    Returns (delivery_pct, status, is_valid)
    """
    if is_null_or_na(delivery_pct):
        # Attempt recovery if delivered_qty and traded_qty are provided
        if not is_null_or_na(delivered_qty) and not is_null_or_na(traded_qty):
            try:
                d_qty = float(delivered_qty)
                t_qty = float(traded_qty)
                if t_qty > 0 and d_qty >= 0:
                    calc = (d_qty / t_qty) * 100.0
                    if 0.0 <= calc <= 100.0:
                        return round(calc, 2), VALID, True
                    else:
                        return None, INVALID, False
            except (ValueError, TypeError):
                pass
        # Missing delivery: MUST NOT default to 0. Must be None and UNKNOWN.
        return None, UNKNOWN, False

    try:
        val = float(delivery_pct)
        if math.isnan(val):
            return None, UNKNOWN, False
        if val < 0.0 or val > 100.0:
            return None, INVALID, False
        return round(val, 2), VALID, True
    except (ValueError, TypeError):
        return None, UNKNOWN, False


def is_delivery_acceptable(
    delivery_pct: Optional[float],
    min_threshold: float = 20.0
) -> bool:
    """
    Ensures missing delivery (None / UNKNOWN) never passes the screener filter.
    """
    if delivery_pct is None or is_null_or_na(delivery_pct):
        return False
    try:
        return float(delivery_pct) >= min_threshold
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 4. OHLC Physics Validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_ohlcv_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates standard OHLC physics for Indian equities:
      - Open > 0, High > 0, Low > 0, Close > 0
      - Low <= Open <= High
      - Low <= Close <= High
      - High >= Low
      - Detect zero/negative prices immediately and flag as INVALID_OHLC.

    Returns:
      (is_valid: bool, errors: List[str])
    """
    errors: List[str] = []
    if not isinstance(record, dict) or not record:
        return False, ["INVALID_OHLC: Empty or non-dictionary record"]

    rec_lower = {str(k).strip().lower(): v for k, v in record.items()}

    def _extract_price(field_names: List[str]) -> Tuple[Optional[float], bool]:
        for fn in field_names:
            if fn in rec_lower and not is_null_or_na(rec_lower[fn]):
                try:
                    val = float(rec_lower[fn])
                    if not math.isnan(val):
                        return val, True
                except (ValueError, TypeError):
                    return None, False
        return None, False

    open_p, has_o = _extract_price(["open", "open_price", "o"])
    high_p, has_h = _extract_price(["high", "high_price", "h"])
    low_p, has_l = _extract_price(["low", "low_price", "l"])
    close_p, has_c = _extract_price(["close", "close_price", "c", "ltp"])

    # Check presence
    if not has_o or open_p is None:
        errors.append("INVALID_OHLC: Missing or non-numeric Open price")
    if not has_h or high_p is None:
        errors.append("INVALID_OHLC: Missing or non-numeric High price")
    if not has_l or low_p is None:
        errors.append("INVALID_OHLC: Missing or non-numeric Low price")
    if not has_c or close_p is None:
        errors.append("INVALID_OHLC: Missing or non-numeric Close price")

    if errors:
        return False, errors

    # Check strictly positive price physics (prevents AUROPHARMA ₹0 bug)
    if open_p <= 0.0:
        errors.append(f"INVALID_OHLC: Open price ({open_p}) <= 0")
    if high_p <= 0.0:
        errors.append(f"INVALID_OHLC: High price ({high_p}) <= 0")
    if low_p <= 0.0:
        errors.append(f"INVALID_OHLC: Low price ({low_p}) <= 0")
    if close_p <= 0.0:
        errors.append(f"INVALID_OHLC: Close price ({close_p}) <= 0")

    # If any price is non-positive, bound checks are invalid
    if errors:
        return False, errors

    # Check bounds
    if high_p < low_p:
        errors.append(f"INVALID_OHLC: High ({high_p}) < Low ({low_p})")

    # Allow tiny epsilon for floating point equality
    eps = 1e-5
    if open_p < (low_p - eps) or open_p > (high_p + eps):
        errors.append(
            f"INVALID_OHLC: Open ({open_p}) is outside [Low ({low_p}), High ({high_p})]"
        )

    if close_p < (low_p - eps) or close_p > (high_p + eps):
        errors.append(
            f"INVALID_OHLC: Close ({close_p}) is outside [Low ({low_p}), High ({high_p})]"
        )

    # Volume check if present
    vol, has_v = _extract_price(["volume", "vol", "v", "traded_qty"])
    if has_v and vol is not None:
        if vol < 0:
            errors.append(f"INVALID_OHLC: Volume ({vol}) < 0")

    return len(errors) == 0, errors


# ─────────────────────────────────────────────────────────────────────────────
# 5. Percentage Change Recalculation & Mismatch Detector
# ─────────────────────────────────────────────────────────────────────────────

def validate_price_change(
    close: float,
    prev_close: float,
    reported_change_pct: float,
    tolerance: float = 0.15
) -> Tuple[float, bool, str]:
    """
    Calculates expected_change = ((close - prev_close) / prev_close) * 100.
    Detects discrepancies where reported change differs from actual close vs prev_close
    by more than tolerance (default 0.15%).
    Permanently stops AUROPHARMA bug where reported was +3.50% when real was +0.68%.

    Returns:
      (expected_change: float, is_valid: bool, status_message: str)
    """
    if is_null_or_na(close) or is_null_or_na(prev_close):
        return 0.0, False, "MISSING_DATA"

    try:
        c = float(close)
        pc = float(prev_close)
    except (ValueError, TypeError):
        return 0.0, False, "INVALID_NUMERIC_PRICE"

    if pc <= 0.0:
        return 0.0, False, "INVALID_PREV_CLOSE"

    expected_change = round(((c - pc) / pc) * 100.0, 4)

    if is_null_or_na(reported_change_pct):
        return expected_change, False, "MISSING_REPORTED_CHANGE"

    try:
        rep = float(reported_change_pct)
    except (ValueError, TypeError):
        return expected_change, False, "INVALID_REPORTED_CHANGE"

    diff = abs(expected_change - rep)
    if diff > tolerance:
        return expected_change, False, "CHANGE_MISMATCH"

    return expected_change, True, VALID


# ─────────────────────────────────────────────────────────────────────────────
# 6. 52-Week Range Validator & Independent Calculator
# ─────────────────────────────────────────────────────────────────────────────

def validate_52w_range(
    high_52w: Any,
    low_52w: Any,
    close: Optional[float] = None,
    df_history: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Validates reported 52-week High/Low and independently calculates from df_history
    if reported values are missing, zero, or corrupt.
    Prevents impossible zero values (AUROPHARMA ₹0 52W range bug).

    Returns:
      {
        "high_52w": Optional[float],
        "low_52w": Optional[float],
        "is_valid": bool,
        "status": str,
        "pct_from_52w_high": Optional[float],
        "pct_from_52w_low": Optional[float],
        "source": str,  # "REPORTED" | "CALCULATED" | "NONE"
        "errors": List[str]
      }
    """
    errors: List[str] = []
    calc_high: Optional[float] = None
    calc_low: Optional[float] = None

    # Step 1: Calculate from history if available
    if df_history is not None and isinstance(df_history, pd.DataFrame) and not df_history.empty:
        col_map = {c.lower(): c for c in df_history.columns}
        h_col = col_map.get("high")
        l_col = col_map.get("low")
        if h_col and l_col:
            # Last 252 trading sessions (~ 1 calendar year)
            window_df = df_history.tail(252)
            try:
                s_high = pd.to_numeric(window_df[h_col], errors="coerce").dropna()
                s_low = pd.to_numeric(window_df[l_col], errors="coerce").dropna()
                if not s_high.empty and not s_low.empty:
                    c_h = float(s_high.max())
                    c_l = float(s_low.min())
                    if c_h > 0 and c_l > 0 and c_h >= c_l:
                        calc_high = round(c_h, 2)
                        calc_low = round(c_l, 2)
            except Exception as exc:
                log.debug(f"History calculation exception: {exc}")

    # Step 2: Validate reported values
    rep_high: Optional[float] = None
    rep_low: Optional[float] = None

    if not is_null_or_na(high_52w):
        try:
            h = float(high_52w)
            if h > 0.0:
                rep_high = h
        except (ValueError, TypeError):
            pass

    if not is_null_or_na(low_52w):
        try:
            l = float(low_52w)
            if l > 0.0:
                rep_low = l
        except (ValueError, TypeError):
            pass

    resolved_high: Optional[float] = None
    resolved_low: Optional[float] = None
    source = "NONE"
    is_valid = False
    status = INVALID

    # Check if reported is valid
    if rep_high is not None and rep_low is not None and rep_high >= rep_low:
        resolved_high = rep_high
        resolved_low = rep_low
        source = "REPORTED"
        is_valid = True
        status = VALID
    elif calc_high is not None and calc_low is not None:
        # Auto-heal from historical series
        resolved_high = calc_high
        resolved_low = calc_low
        source = "CALCULATED"
        is_valid = True
        status = VALID
        errors.append("HEALED_52W_RANGE: Substituted invalid reported 52W range with calculated values")
    else:
        # Zero or missing 52w range cannot be accepted! Must be None (never 0)
        resolved_high = None
        resolved_low = None
        source = "NONE"
        is_valid = False
        status = INVALID
        errors.append("INVALID_52W_RANGE: 52-week high/low values <= 0 or missing")

    # Step 3: Check consistency with current Close price if available
    pct_high: Optional[float] = None
    pct_low: Optional[float] = None

    if close is not None and not is_null_or_na(close):
        try:
            c_val = float(close)
            if c_val > 0 and resolved_high is not None and resolved_low is not None:
                if c_val > resolved_high:
                    errors.append(f"WARNING_52W_RANGE: Close ({c_val}) > 52W High ({resolved_high}); updating high")
                    resolved_high = c_val
                elif c_val < resolved_low:
                    errors.append(f"WARNING_52W_RANGE: Close ({c_val}) < 52W Low ({resolved_low}); updating low")
                    resolved_low = c_val

                pct_high = round(((c_val - resolved_high) / resolved_high) * 100.0, 2)
                pct_low = round(((c_val - resolved_low) / resolved_low) * 100.0, 2)
        except (ValueError, TypeError):
            pass

    return {
        "high_52w": resolved_high,
        "low_52w": resolved_low,
        "is_valid": is_valid,
        "status": status,
        "pct_from_52w_high": pct_high,
        "pct_from_52w_low": pct_low,
        "source": source,
        "errors": errors,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Data Quality Score Calculator
# ─────────────────────────────────────────────────────────────────────────────

def compute_data_quality_score(record: Dict[str, Any]) -> float:
    """
    Computes a comprehensive Data Quality & Integrity Score from 0.0 to 100.0.
    Evaluates:
      1. OHLC Physics Integrity (30 pts)
      2. Price Change & Prev-Close Consistency (15 pts)
      3. Volume & Traded Activity (15 pts)
      4. Delivery Data Integrity (15 pts)
      5. 52-Week Range Validity (15 pts)
      6. Indicators / Technical Health (10 pts)

    AUROPHARMA bug record (with 0s, bogus change) receives a low/failing score.
    """
    if not isinstance(record, dict) or not record:
        return 0.0

    score = 0.0
    rec_lower = {str(k).strip().lower(): v for k, v in record.items()}

    # 1. OHLC Physics (30 pts)
    ohlc_valid, _ = validate_ohlcv_record(record)
    if ohlc_valid:
        score += 30.0

    # 2. Price Change & Prev-Close Consistency (15 pts)
    c_val = rec_lower.get("close") or rec_lower.get("close_price") or rec_lower.get("ltp")
    pc_val = rec_lower.get("prev_close") or rec_lower.get("prevclose")
    chg_val = rec_lower.get("change_pct") or rec_lower.get("pchange") or rec_lower.get("change")

    if c_val is not None and pc_val is not None and not is_null_or_na(c_val) and not is_null_or_na(pc_val):
        _, is_chg_valid, code = validate_price_change(float(c_val), float(pc_val), float(chg_val) if chg_val is not None else 0.0)
        if is_chg_valid:
            score += 15.0
        elif code == "CHANGE_MISMATCH":
            # Discrepancy penalty
            score += 0.0
        else:
            score += 5.0
    elif c_val is not None and not is_null_or_na(c_val):
        try:
            if float(c_val) > 0:
                score += 8.0
        except (ValueError, TypeError):
            pass

    # 3. Volume & Activity (15 pts)
    v_val = rec_lower.get("volume") or rec_lower.get("vol") or rec_lower.get("traded_qty")
    if v_val is not None and not is_null_or_na(v_val):
        try:
            vol_float = float(v_val)
            if vol_float > 0:
                score += 15.0
        except (ValueError, TypeError):
            pass

    # 4. Delivery Data Integrity (15 pts)
    deliv_p = rec_lower.get("delivery_pct") or rec_lower.get("delivery_percent")
    d_val, d_status, d_valid = validate_delivery(deliv_p)
    if d_valid and d_val is not None and d_val > 0.0:
        score += 15.0
    # Missing delivery awards 0 pts (N/A ≠ 0)

    # 5. 52-Week Range Validity (15 pts)
    h52 = rec_lower.get("high_52w") or rec_lower.get("high52") or rec_lower.get("fiftytwo_week_high")
    l52 = rec_lower.get("low_52w") or rec_lower.get("low52") or rec_lower.get("fiftytwo_week_low")
    res_52 = validate_52w_range(h52, l52, close=float(c_val) if c_val is not None and not is_null_or_na(c_val) else None)
    if res_52["is_valid"] and res_52["high_52w"] is not None and res_52["low_52w"] is not None:
        score += 15.0

    # 6. Indicators & Health (10 pts)
    indicators = [
        rec_lower.get("ema20"),
        rec_lower.get("ema50"),
        rec_lower.get("ema200"),
        rec_lower.get("rsi"),
        rec_lower.get("atr"),
    ]
    present_indicators = [ind for ind in indicators if ind is not None and not is_null_or_na(ind)]
    if present_indicators:
        bogus_count = sum(1 for ind in present_indicators if float(ind) == 0.0)
        if bogus_count == 0:
            score += 10.0
        else:
            score += max(0.0, 10.0 - (bogus_count * 2.5))
    else:
        # If no indicators provided in raw record, neutral partial score
        score += 5.0

    return min(100.0, max(0.0, round(score, 1)))


# ─────────────────────────────────────────────────────────────────────────────
# 8. Full Record Pipeline Validator & Sanitizer
# ─────────────────────────────────────────────────────────────────────────────

def validate_and_sanitize_stock_record(
    record: Dict[str, Any],
    run_id: Optional[str] = None,
    df_history: Optional[pd.DataFrame] = None,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Validates and sanitizes a complete equity record before ingestion or scoring.
    Enforces all non-negotiable rules:
      - N/A ≠ 0
      - NULL ≠ 0
      - UNKNOWN ≠ PASS
      - Missing delivery -> None, UNKNOWN
      - Fixes AUROPHARMA bug (zero OHLC, bogus change %, zero EMA, zero 52W)
    """
    sanitized = dict(record)
    symbol = sanitized.get("symbol", "UNKNOWN")
    rec_lower = {str(k).strip().lower(): k for k in sanitized.keys()}

    errors_list: List[str] = []

    # 1. OHLC Validation
    ohlc_valid, ohlc_errors = validate_ohlcv_record(sanitized)
    if not ohlc_valid:
        errors_list.extend(ohlc_errors)
        if run_id:
            for err in ohlc_errors:
                record_validation_error(
                    run_id=run_id,
                    symbol=symbol,
                    field="OHLC",
                    error_type="INVALID_OHLC",
                    expected="Open, High, Low, Close > 0 and Low <= Open/Close <= High",
                    actual=err,
                    severity="CRITICAL",
                    conn=conn
                )

    # 2. Percentage Change Recalculation
    c_key = rec_lower.get("close")
    pc_key = rec_lower.get("prev_close")
    chg_key = rec_lower.get("change_pct")

    c_val = sanitized.get(c_key) if c_key else None
    pc_val = sanitized.get(pc_key) if pc_key else None
    chg_val = sanitized.get(chg_key) if chg_key else None

    if c_val is not None and pc_val is not None:
        expected_chg, is_chg_valid, chg_status = validate_price_change(c_val, pc_val, chg_val)
        if not is_chg_valid:
            errors_list.append(f"CHANGE_MISMATCH: Reported {chg_val}% vs Expected {expected_chg}%")
            if run_id:
                record_validation_error(
                    run_id=run_id,
                    symbol=symbol,
                    field="change_pct",
                    error_type="CHANGE_MISMATCH",
                    expected=expected_chg,
                    actual=chg_val,
                    severity="ERROR",
                    conn=conn
                )
            # Permanently overwrite bogus change % with recalculated value
            if chg_key:
                sanitized[chg_key] = expected_chg
            else:
                sanitized["change_pct"] = expected_chg

    # 3. 52-Week Range Validation & Independent Calculation
    h52_key = rec_lower.get("high_52w")
    l52_key = rec_lower.get("low_52w")
    h52_val = sanitized.get(h52_key) if h52_key else None
    l52_val = sanitized.get(l52_key) if l52_key else None

    range_52 = validate_52w_range(h52_val, l52_val, close=c_val, df_history=df_history)
    if not range_52["is_valid"]:
        errors_list.extend(range_52["errors"])
        if run_id:
            record_validation_error(
                run_id=run_id,
                symbol=symbol,
                field="52w_range",
                error_type="INVALID_52W_RANGE",
                expected="high_52w > 0, low_52w > 0, high >= low",
                actual=f"high={h52_val}, low={l52_val}",
                severity="ERROR",
                conn=conn
            )
    sanitized["high_52w"] = range_52["high_52w"]
    sanitized["low_52w"] = range_52["low_52w"]
    sanitized["pct_from_52w_high"] = range_52["pct_from_52w_high"]
    sanitized["pct_from_52w_low"] = range_52["pct_from_52w_low"]

    # 4. Delivery Validation (Missing delivery = None / UNKNOWN, NEVER 0)
    deliv_key = rec_lower.get("delivery_pct")
    deliv_val = sanitized.get(deliv_key) if deliv_key else None
    clean_deliv, deliv_status, _ = validate_delivery(deliv_val)
    sanitized["delivery_pct"] = clean_deliv
    sanitized["delivery_status"] = deliv_status

    # 5. Indicator Cleanup (N/A ≠ 0, NULL ≠ 0)
    for ind_name in ["ema20", "ema50", "ema200", "rsi", "atr"]:
        k = rec_lower.get(ind_name)
        if k and sanitized.get(k) is not None:
            cleaned = clean_missing_indicator(sanitized[k])
            sanitized[k] = cleaned

    # 6. Data Quality Score
    quality_score = compute_data_quality_score(sanitized)
    sanitized["data_quality_score"] = quality_score
    sanitized["data_status"] = VALID if (ohlc_valid and quality_score >= 70.0) else (INVALID if not ohlc_valid else UNKNOWN)
    sanitized["validation_errors"] = errors_list

    return sanitized
