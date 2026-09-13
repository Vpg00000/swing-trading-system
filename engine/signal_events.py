"""
Signal Event Infrastructure for early-movement detection.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from data.database import get_connection, init_db

log = logging.getLogger(__name__)

def record_signal_event(event: dict) -> int:
    """Insert a signal event with dedup (ON CONFLICT DO UPDATE)"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signal_events (
                symbol, signal_id, signal_name, signal_group, direction,
                horizon, value, threshold, strength, confidence,
                first_detected_at, last_detected_at, data_timestamp,
                source, is_active, ttl_hours
            ) VALUES (
                :symbol, :signal_id, :signal_name, :signal_group, :direction,
                :horizon, :value, :threshold, :strength, :confidence,
                :first_detected_at, :last_detected_at, :data_timestamp,
                :source, :is_active, :ttl_hours
            )
            ON CONFLICT(symbol, signal_id, data_timestamp) DO UPDATE SET
                value=excluded.value,
                strength=excluded.strength,
                confidence=excluded.confidence,
                last_detected_at=excluded.last_detected_at,
                is_active=1
        """, {
            "symbol": event.get("symbol"),
            "signal_id": event.get("signal_id"),
            "signal_name": event.get("signal_name"),
            "signal_group": event.get("signal_group"),
            "direction": event.get("direction", "BULLISH"),
            "horizon": event.get("horizon", "CONFIRMATION"),
            "value": event.get("value"),
            "threshold": event.get("threshold"),
            "strength": event.get("strength", 50),
            "confidence": event.get("confidence", 0.5),
            "first_detected_at": event.get("first_detected_at", datetime.now().isoformat()),
            "last_detected_at": event.get("last_detected_at", datetime.now().isoformat()),
            "data_timestamp": event.get("data_timestamp"),
            "source": event.get("source", "ENGINE"),
            "is_active": event.get("is_active", 1),
            "ttl_hours": event.get("ttl_hours", 72)
        })
        conn.commit()
        return cursor.rowcount

def record_signal_events_batch(events: List[dict]) -> int:
    """Batch insert signal events."""
    if not events:
        return 0
    init_db()
    count = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for event in events:
            cursor.execute("""
                INSERT INTO signal_events (
                    symbol, signal_id, signal_name, signal_group, direction,
                    horizon, value, threshold, strength, confidence,
                    first_detected_at, last_detected_at, data_timestamp,
                    source, is_active, ttl_hours
                ) VALUES (
                    :symbol, :signal_id, :signal_name, :signal_group, :direction,
                    :horizon, :value, :threshold, :strength, :confidence,
                    :first_detected_at, :last_detected_at, :data_timestamp,
                    :source, :is_active, :ttl_hours
                )
                ON CONFLICT(symbol, signal_id, data_timestamp) DO UPDATE SET
                    value=excluded.value,
                    strength=excluded.strength,
                    confidence=excluded.confidence,
                    last_detected_at=excluded.last_detected_at,
                    is_active=1
            """, {
                "symbol": event.get("symbol"),
                "signal_id": event.get("signal_id"),
                "signal_name": event.get("signal_name"),
                "signal_group": event.get("signal_group"),
                "direction": event.get("direction", "BULLISH"),
                "horizon": event.get("horizon", "CONFIRMATION"),
                "value": event.get("value"),
                "threshold": event.get("threshold"),
                "strength": event.get("strength", 50),
                "confidence": event.get("confidence", 0.5),
                "first_detected_at": event.get("first_detected_at", datetime.now().isoformat()),
                "last_detected_at": event.get("last_detected_at", datetime.now().isoformat()),
                "data_timestamp": event.get("data_timestamp"),
                "source": event.get("source", "ENGINE"),
                "is_active": event.get("is_active", 1),
                "ttl_hours": event.get("ttl_hours", 72)
            })
            count += cursor.rowcount
        conn.commit()
    return count

def get_active_signals(symbol: str, hours: int = 72) -> List[dict]:
    """Get active (non-expired) signals for a symbol."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor.execute("""
            SELECT * FROM signal_events
            WHERE symbol = ? AND is_active = 1 AND last_detected_at >= ?
            ORDER BY last_detected_at DESC
        """, (symbol, cutoff))
        return [dict(row) for row in cursor.fetchall()]

def get_signal_chronology(symbol: str, limit: int = 50) -> List[dict]:
    """Time-ordered signal history for a symbol."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM signal_events
            WHERE symbol = ?
            ORDER BY first_detected_at DESC
            LIMIT ?
        """, (symbol, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_early_signals_count(symbol: str) -> int:
    """Count of active EARLY signals."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count FROM signal_events
            WHERE symbol = ? AND horizon = 'EARLY' AND is_active = 1
        """, (symbol,))
        row = cursor.fetchone()
        return row["count"] if row else 0

def get_signal_summary(symbol: str) -> dict:
    """Summary with counts by horizon (early/confirmation/late)."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT horizon, COUNT(*) as count FROM signal_events
            WHERE symbol = ? AND is_active = 1
            GROUP BY horizon
        """, (symbol,))
        rows = cursor.fetchall()
        summary = {"EARLY": 0, "CONFIRMATION": 0, "LATE": 0}
        for r in rows:
            if r["horizon"] in summary:
                summary[r["horizon"]] = r["count"]
        return summary

def expire_old_signals(ttl_hours: int = 72) -> int:
    """Deactivate expired signals."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
        cursor.execute("""
            UPDATE signal_events
            SET is_active = 0
            WHERE is_active = 1 AND last_detected_at < ?
        """, (cutoff,))
        conn.commit()
        return cursor.rowcount

def get_universe_signal_heatmap(limit: int = 50) -> List[dict]:
    """Top stocks by active early signal count."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, COUNT(*) as early_count FROM signal_events
            WHERE horizon = 'EARLY' AND is_active = 1
            GROUP BY symbol
            ORDER BY early_count DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

def compute_signal_decay(first_detected_at: str, ttl_hours: int = 72) -> float:
    """Returns confidence decay factor 0.0-1.0"""
    try:
        first_detected = datetime.fromisoformat(first_detected_at)
        age_hours = (datetime.now() - first_detected).total_seconds() / 3600.0
        if age_hours <= 0:
            return 1.0
        if age_hours >= ttl_hours:
            return 0.0
        # Linear decay
        return 1.0 - (age_hours / ttl_hours)
    except Exception as e:
        log.error(f"Error computing decay: {e}")
        return 0.0
