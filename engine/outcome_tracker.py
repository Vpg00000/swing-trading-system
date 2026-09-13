"""
Outcome Tracker for Signal Predictions.
"""
import logging
from typing import List, Dict, Any
from data.database import get_connection, init_db

log = logging.getLogger(__name__)

def record_prediction_outcome(outcome: dict) -> int:
    """Store prediction outcome"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO prediction_outcomes (
                symbol, date, open_price, gap_pct, price_5m, price_15m, price_30m,
                high_price, low_price, close_price, volume_day, mfe_pct, mae_pct,
                actual_return_1d, actual_return_5d, direction_predicted, direction_actual,
                direction_correct, predicted_reason, reason_correct, classification
            ) VALUES (
                :symbol, :date, :open_price, :gap_pct, :price_5m, :price_15m, :price_30m,
                :high_price, :low_price, :close_price, :volume_day, :mfe_pct, :mae_pct,
                :actual_return_1d, :actual_return_5d, :direction_predicted, :direction_actual,
                :direction_correct, :predicted_reason, :reason_correct, :classification
            )
            ON CONFLICT(symbol, date) DO UPDATE SET
                open_price=excluded.open_price,
                gap_pct=excluded.gap_pct,
                price_5m=excluded.price_5m,
                price_15m=excluded.price_15m,
                price_30m=excluded.price_30m,
                high_price=excluded.high_price,
                low_price=excluded.low_price,
                close_price=excluded.close_price,
                volume_day=excluded.volume_day,
                mfe_pct=excluded.mfe_pct,
                mae_pct=excluded.mae_pct,
                actual_return_1d=excluded.actual_return_1d,
                actual_return_5d=excluded.actual_return_5d,
                direction_predicted=excluded.direction_predicted,
                direction_actual=excluded.direction_actual,
                direction_correct=excluded.direction_correct,
                predicted_reason=excluded.predicted_reason,
                reason_correct=excluded.reason_correct,
                classification=excluded.classification
        """, {
            "symbol": outcome.get("symbol"),
            "date": outcome.get("date"),
            "open_price": outcome.get("open_price"),
            "gap_pct": outcome.get("gap_pct"),
            "price_5m": outcome.get("price_5m"),
            "price_15m": outcome.get("price_15m"),
            "price_30m": outcome.get("price_30m"),
            "high_price": outcome.get("high_price"),
            "low_price": outcome.get("low_price"),
            "close_price": outcome.get("close_price"),
            "volume_day": outcome.get("volume_day"),
            "mfe_pct": outcome.get("mfe_pct"),
            "mae_pct": outcome.get("mae_pct"),
            "actual_return_1d": outcome.get("actual_return_1d"),
            "actual_return_5d": outcome.get("actual_return_5d"),
            "direction_predicted": outcome.get("direction_predicted"),
            "direction_actual": outcome.get("direction_actual"),
            "direction_correct": outcome.get("direction_correct"),
            "predicted_reason": outcome.get("predicted_reason"),
            "reason_correct": outcome.get("reason_correct"),
            "classification": outcome.get("classification"),
        })
        conn.commit()
        return cursor.rowcount

def compute_mfe_mae(symbol: str, entry_price: float, high: float, low: float) -> dict:
    """Calculate MFE/MAE"""
    if entry_price <= 0:
        return {"mfe_pct": 0.0, "mae_pct": 0.0}
    
    mfe_pct = ((high - entry_price) / entry_price) * 100
    mae_pct = ((low - entry_price) / entry_price) * 100
    
    return {
        "mfe_pct": round(mfe_pct, 2),
        "mae_pct": round(mae_pct, 2)
    }

def evaluate_direction_accuracy(predicted: str, actual_return: float) -> dict:
    """Classify as WIN/SCRATCH/LOSS"""
    result = "LOSS"
    if predicted == "BULLISH":
        if actual_return > 1.0:
            result = "WIN"
        elif actual_return >= -0.5:
            result = "SCRATCH"
    elif predicted == "BEARISH":
        if actual_return < -1.0:
            result = "WIN"
        elif actual_return <= 0.5:
            result = "SCRATCH"
            
    is_correct = 1 if result == "WIN" else 0
    return {
        "result": result,
        "direction_correct": is_correct
    }

def classify_prediction_quadrant(direction_correct: bool, reason_correct: bool) -> str:
    """TRUE_ALPHA/LUCKY_BETA/FAILED_CATALYST/TOTAL_MISS"""
    if direction_correct and reason_correct:
        return "TRUE_ALPHA"
    elif direction_correct and not reason_correct:
        return "LUCKY_BETA"
    elif not direction_correct and reason_correct:
        return "FAILED_CATALYST"
    else:
        return "TOTAL_MISS"

def get_rolling_accuracy(days: int = 30) -> dict:
    """Rolling directional hit rate and reason hit rate"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(direction_correct) as correct_direction,
                SUM(reason_correct) as correct_reason
            FROM prediction_outcomes
            WHERE date >= date('now', ?)
        """, (f"-{days} days",))
        row = cursor.fetchone()
        if row and row["total"] and row["total"] > 0:
            total = row["total"]
            return {
                "total_predictions": total,
                "directional_hit_rate": round((row["correct_direction"] or 0) / total * 100, 2),
                "reason_hit_rate": round((row["correct_reason"] or 0) / total * 100, 2)
            }
        return {"total_predictions": 0, "directional_hit_rate": 0.0, "reason_hit_rate": 0.0}

def get_prediction_vs_reality(date: str) -> List[dict]:
    """Side-by-side comparison"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, direction_predicted, direction_actual, 
                   predicted_reason, classification, actual_return_1d, actual_return_5d
            FROM prediction_outcomes
            WHERE date = ?
        """, (date,))
        return [dict(row) for row in cursor.fetchall()]
