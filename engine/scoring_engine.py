"""
engine/scoring_engine.py — Transparent Scoring Engine & Indicator Integrity Module.

Adheres strictly to:
- Rules 1–4:
    Rule 1: Indicator warm-up / data integrity (never return 0 for uncomputed indicators; return None/UNKNOWN).
    Rule 2: Boundary validation (RSI strictly 0-100, ATR >= 0).
    Rule 3: Missing-Component Normalization: UNKNOWN ≠ PASS and UNKNOWN ≠ FAIL.
            Never assign 0 and never award unearned points for missing data.
            final_score = (sum_of_available_points / sum_of_available_max_weights) * 100.
    Rule 4: Provenance: Target and Stop-Loss tags must explicitly be marked source="MODEL_GENERATED".
- Tasks 161–180 (Phases 10 & 11):
    Tasks 161–174: Indicator warm-up checking:
      - Price history < 200 bars => EMA200 is None (UNKNOWN), NEVER 0!
      - Price history < 50 bars => EMA50 is None (UNKNOWN), NEVER 0!
      - Price history < 14 bars => RSI and ATR are None (UNKNOWN), NEVER 0!
    Tasks 175–179: Missing-Component Normalization & Transparent Breakdown:
      - Configurable weights: Trend (20), Momentum (20), Volume (20), Delivery (15), Fundamentals (15), Risk/Reward (10).
      - Strategy Versioning (default "Strategy v3.2").
      - Explicit Data Coverage % exposed.
    Task 180: Classification & Determinism:
      - BUY_NOW (score >= 80 and coverage >= 70%)
      - BUY (score >= 65)
      - WATCH (score >= 50)
      - HOLD (score >= 40)
      - EXIT (< 40)
      - 100% deterministic and reproducible output with cryptographic SHA-256 fingerprint.
"""

import math
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Union, List, Tuple
from datetime import datetime, timezone

try:
    import pandas as pd
    import numpy as np
except ImportError:
    pd = None
    np = None

# ============================================================================
# 1. INDICATOR INTEGRITY MODULE (Rules 1–2, Tasks 161–174)
# ============================================================================

MIN_BARS_EMA200 = 200
MIN_BARS_EMA50 = 50
MIN_BARS_RSI = 14
MIN_BARS_ATR = 14


def check_warmup(bars_count: int, indicator_name: str) -> bool:
    """
    Checks whether sufficient bar history exists to calculate the given indicator.
    Returns True if warm-up requirement is met, False otherwise.
    """
    name = indicator_name.upper()
    if "200" in name:
        return bars_count >= MIN_BARS_EMA200
    if "50" in name:
        return bars_count >= MIN_BARS_EMA50
    if "RSI" in name:
        return bars_count >= MIN_BARS_RSI
    if "ATR" in name:
        return bars_count >= MIN_BARS_ATR
    return True


def validate_rsi(rsi: Optional[Union[float, int]], strict: bool = False) -> Optional[float]:
    """
    Validates RSI value strictly between 0.0 and 100.0.
    Returns sanitized float or None. If strict=True, raises ValueError on invalid bound.
    """
    if rsi is None:
        return None
    try:
        val = float(rsi)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"Invalid RSI numeric value: {rsi}")
        return None

    if math.isnan(val) or math.isinf(val):
        if strict:
            raise ValueError(f"RSI cannot be NaN or Inf: {rsi}")
        return None

    if 0.0 <= val <= 100.0:
        return round(val, 2)
    else:
        if strict:
            raise ValueError(f"RSI boundary violation: {val} is not strictly between 0 and 100")
        return None


def validate_atr(atr: Optional[Union[float, int]], strict: bool = False) -> Optional[float]:
    """
    Validates ATR value >= 0.0.
    Returns sanitized float or None. If strict=True, raises ValueError on negative ATR.
    """
    if atr is None:
        return None
    try:
        val = float(atr)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"Invalid ATR numeric value: {atr}")
        return None

    if math.isnan(val) or math.isinf(val):
        if strict:
            raise ValueError(f"ATR cannot be NaN or Inf: {atr}")
        return None

    if val >= 0.0:
        return round(val, 4)
    else:
        if strict:
            raise ValueError(f"ATR boundary violation: {val} must be >= 0")
        return None


def validate_indicator_warmup(
    bars_count: int,
    indicators: Dict[str, Any],
    strict_boundaries: bool = False
) -> Dict[str, Any]:
    """
    Applies indicator warm-up checking and boundary validation:
    - If price history < 200 bars, EMA200 is None (UNKNOWN), NEVER 0!
    - If price history < 50 bars, EMA50 is None, NEVER 0!
    - If price history < 14 bars, RSI and ATR are None, NEVER 0!
    - RSI strictly between 0 and 100.
    - ATR >= 0.
    """
    result = dict(indicators)
    result["bars_count"] = bars_count

    # EMA 200
    if bars_count < MIN_BARS_EMA200:
        result["ema200"] = None
        result["sma200"] = None
    elif "ema200" in result and result["ema200"] is not None:
        try:
            val = float(result["ema200"])
            result["ema200"] = val if not math.isnan(val) else None
        except (TypeError, ValueError):
            result["ema200"] = None

    # EMA 50
    if bars_count < MIN_BARS_EMA50:
        result["ema50"] = None
        result["sma50"] = None
    elif "ema50" in result and result["ema50"] is not None:
        try:
            val = float(result["ema50"])
            result["ema50"] = val if not math.isnan(val) else None
        except (TypeError, ValueError):
            result["ema50"] = None

    # RSI & ATR (14 bars)
    if bars_count < MIN_BARS_RSI:
        result["rsi"] = None
    elif "rsi" in result:
        result["rsi"] = validate_rsi(result["rsi"], strict=strict_boundaries)

    if bars_count < MIN_BARS_ATR:
        result["atr"] = None
    elif "atr" in result:
        result["atr"] = validate_atr(result["atr"], strict=strict_boundaries)

    return result


def compute_indicators_with_integrity(df: Any, strict_boundaries: bool = False) -> Dict[str, Any]:
    """
    Computes technical indicators from an OHLCV DataFrame enforcing all integrity rules.
    If DataFrame is empty or None, all warm-up indicators are None (NEVER 0).
    """
    if df is None or (hasattr(df, "empty") and df.empty):
        return {
            "bars_count": 0,
            "close": None,
            "ema200": None,
            "ema50": None,
            "rsi": None,
            "atr": None,
            "integrity_notes": ["Empty or missing price series"]
        }

    bars_count = len(df)
    close = df["Close"]
    last_close = float(close.iloc[-1]) if not close.empty else None

    # EMA200
    ema200 = None
    if bars_count >= MIN_BARS_EMA200:
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])

    # EMA50
    ema50 = None
    if bars_count >= MIN_BARS_EMA50:
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])

    # RSI (14)
    rsi = None
    if bars_count >= MIN_BARS_RSI:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        if avg_loss == 0 or math.isnan(avg_loss):
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100.0 - (100.0 / (1.0 + rs)), 2)
        rsi = validate_rsi(rsi, strict=strict_boundaries)

    # ATR (14)
    atr = None
    if bars_count >= MIN_BARS_ATR and "High" in df.columns and "Low" in df.columns:
        high = df["High"]
        low = df["Low"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr_val = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        atr = validate_atr(round(float(atr_val), 4), strict=strict_boundaries)

    return {
        "bars_count": bars_count,
        "close": last_close,
        "ema200": ema200,
        "ema50": ema50,
        "rsi": rsi,
        "atr": atr,
    }


class IndicatorIntegrityValidator:
    """Encapsulates all integrity and boundary validations."""

    @staticmethod
    def check_warmup(bars_count: int, indicator_name: str) -> bool:
        return check_warmup(bars_count, indicator_name)

    @staticmethod
    def validate_rsi(rsi: Optional[Union[float, int]], strict: bool = False) -> Optional[float]:
        return validate_rsi(rsi, strict)

    @staticmethod
    def validate_atr(atr: Optional[Union[float, int]], strict: bool = False) -> Optional[float]:
        return validate_atr(atr, strict)

    @staticmethod
    def validate(bars_count: int, indicators: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
        return validate_indicator_warmup(bars_count, indicators, strict_boundaries=strict)


# ============================================================================
# 2. 100-POINT TRANSPARENT SCORING ENGINE (Rules 3–4, Tasks 175–180)
# ============================================================================

DEFAULT_WEIGHTS = {
    "trend": 20.0,
    "momentum": 20.0,
    "volume": 20.0,
    "delivery": 15.0,
    "fundamentals": 15.0,
    "risk_reward": 10.0,
}

STRATEGY_VERSION = "Strategy v3.2"


@dataclass
class FactorScore:
    """Individual factor score with transparent points earned / max points."""
    name: str
    points_earned: Optional[float]  # None indicates UNKNOWN (missing component)
    max_points: float
    weight: float
    status: str  # "AVAILABLE" or "UNKNOWN"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "points_earned": self.points_earned,
            "max_points": self.max_points,
            "weight": self.weight,
            "status": self.status,
            "details": self.details,
        }


@dataclass
class TargetStopLoss:
    """Model-generated target, stop loss, and risk/reward ratio with explicit provenance."""
    target_price: Optional[float]
    stop_loss: Optional[float]
    rr_ratio: Optional[float]
    source: str = "MODEL_GENERATED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "rr_ratio": self.rr_ratio,
            "source": self.source,
        }


@dataclass
class TransparentScoreResult:
    """
    Transparent Opportunity Score result adhering to:
    - 100-point normalized scoring
    - Missing-Component Normalization
    - Strategy versioning
    - Explicit Data Coverage %
    - MODEL_GENERATED Target and Stop-Loss
    - Deterministic SHA-256 fingerprint
    """
    symbol: str
    final_score: float
    coverage_pct: float
    classification: str
    strategy_version: str
    breakdown: Dict[str, FactorScore]
    available_points: float
    available_max_weights: float
    total_max_weights: float
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    rr_ratio: Optional[float] = None
    source: str = "MODEL_GENERATED"
    targets_and_stops: Optional[TargetStopLoss] = None
    metrics_used: Dict[str, Any] = field(default_factory=dict)
    deterministic_hash: str = ""
    timestamp: str = ""

    @property
    def action(self) -> str:
        """Alias for classification."""
        return self.classification

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "final_score": self.final_score,
            "coverage_pct": self.coverage_pct,
            "classification": self.classification,
            "action": self.classification,
            "strategy_version": self.strategy_version,
            "available_points": self.available_points,
            "available_max_weights": self.available_max_weights,
            "total_max_weights": self.total_max_weights,
            "breakdown": {k: v.to_dict() for k, v in self.breakdown.items()},
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "rr_ratio": self.rr_ratio,
            "source": self.source,
            "targets_and_stops": self.targets_and_stops.to_dict() if self.targets_and_stops else {
                "target_price": self.target_price,
                "stop_loss": self.stop_loss,
                "rr_ratio": self.rr_ratio,
                "source": self.source,
            },
            "metrics_used": self.metrics_used,
            "deterministic_hash": self.deterministic_hash,
            "timestamp": self.timestamp,
        }

    def as_dict(self) -> Dict[str, Any]:
        return self.to_dict()


class TransparentScoringEngine:
    """
    100-Point Transparent Opportunity Scoring Engine.

    Configurable weights:
      Trend: 20
      Momentum: 20
      Volume: 20
      Delivery: 15
      Fundamentals: 15
      Risk/Reward: 10
      Total: 100

    Strategy Version: 'Strategy v3.2'
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        strategy_version: str = STRATEGY_VERSION,
    ):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)
        self.strategy_version = strategy_version
        self.total_max_weight = sum(self.weights.values())

    def classify(self, score: float, coverage_pct: float) -> str:
        """
        Classification rules:
        - BUY_NOW: score >= 80 and coverage >= 70%
        - BUY: score >= 65
        - WATCH: score >= 50
        - HOLD: score >= 40
        - EXIT: < 40
        """
        if score >= 80.0 and coverage_pct >= 70.0:
            return "BUY_NOW"
        elif score >= 65.0:
            return "BUY"
        elif score >= 50.0:
            return "WATCH"
        elif score >= 40.0:
            return "HOLD"
        else:
            return "EXIT"

    def compute_targets_and_stops(
        self,
        close: Optional[float],
        atr: Optional[float] = None,
        stop_loss: Optional[float] = None,
        target_price: Optional[float] = None,
        rr_ratio: Optional[float] = None,
    ) -> TargetStopLoss:
        """
        Calculates ATR-based targets and stop losses tagged explicitly as MODEL_GENERATED.
        """
        if stop_loss is not None and target_price is not None:
            calc_rr = rr_ratio
            if calc_rr is None and close is not None and close > stop_loss:
                risk = close - stop_loss
                reward = target_price - close
                calc_rr = round(reward / risk, 2) if risk > 0 else 2.2
            return TargetStopLoss(
                target_price=round(float(target_price), 2),
                stop_loss=round(float(stop_loss), 2),
                rr_ratio=calc_rr if calc_rr is not None else 2.2,
                source="MODEL_GENERATED",
            )

        if close is not None and close > 0:
            if atr is not None and atr > 0:
                sl = round(max(0.01, close - (2.0 * atr)), 2)
                risk = close - sl
                tp = round(close + (2.2 * risk), 2)
                return TargetStopLoss(
                    target_price=tp,
                    stop_loss=sl,
                    rr_ratio=2.2,
                    source="MODEL_GENERATED",
                )
            else:
                sl = round(close * 0.95, 2)
                risk = close - sl
                tp = round(close + (2.2 * risk), 2)
                return TargetStopLoss(
                    target_price=tp,
                    stop_loss=sl,
                    rr_ratio=2.2,
                    source="MODEL_GENERATED",
                )

        return TargetStopLoss(
            target_price=None,
            stop_loss=None,
            rr_ratio=None,
            source="MODEL_GENERATED",
        )

    def _normalize_component_input(
        self,
        comp_name: str,
        val: Any,
        max_points: float,
    ) -> FactorScore:
        """
        Parses direct component input into a FactorScore.
        If val is None or marked UNKNOWN: points_earned is None, status is UNKNOWN.
        """
        if val is None or val == "UNKNOWN":
            return FactorScore(
                name=comp_name,
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Missing or uncomputed data"},
            )

        if isinstance(val, dict):
            status = val.get("status", "AVAILABLE")
            if status == "UNKNOWN" or (val.get("points_earned") is None and "score" not in val):
                return FactorScore(
                    name=comp_name,
                    points_earned=None,
                    max_points=max_points,
                    weight=max_points,
                    status="UNKNOWN",
                    details=val,
                )
            if "points_earned" in val and val["points_earned"] is not None:
                pts = float(val["points_earned"])
            elif "score" in val and val["score"] is not None:
                s = float(val["score"])
                pts = (s / 100.0 * max_points) if s > 1.0 else (s * max_points)
            else:
                pts = 0.0
            earned = round(max(0.0, min(max_points, pts)), 2)
            return FactorScore(
                name=comp_name,
                points_earned=earned,
                max_points=max_points,
                weight=max_points,
                status="AVAILABLE",
                details=val,
            )

        if isinstance(val, (int, float)):
            v = float(val)
            if 0.0 < v <= 1.0 and max_points > 1.0 and v <= (max_points / 100.0):
                earned = round(v * max_points, 2)
            else:
                earned = round(max(0.0, min(max_points, v)), 2)

            return FactorScore(
                name=comp_name,
                points_earned=earned,
                max_points=max_points,
                weight=max_points,
                status="AVAILABLE",
                details={"input": val},
            )

        return FactorScore(
            name=comp_name,
            points_earned=None,
            max_points=max_points,
            weight=max_points,
            status="UNKNOWN",
            details={"input": str(val)},
        )

    def _evaluate_trend_factor(
        self,
        close: Optional[float],
        ema50: Optional[float],
        ema200: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """Evaluates Trend factor (max 20 points)."""
        if ema50 is None and ema200 is None:
            return FactorScore(
                name="trend",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Neither EMA50 nor EMA200 available (insufficient warm-up)"},
            )

        if close is None or close <= 0:
            return FactorScore(
                name="trend",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Missing close price"},
            )

        if ema50 is not None and ema200 is not None:
            if close >= ema50 and close >= ema200:
                pts = max_points
                desc = "Strong Uptrend: Above EMA50 & EMA200"
            elif close >= ema50 and close < ema200:
                pts = max_points * 0.60
                desc = "Pullback / Recovery: Above EMA50, Below EMA200"
            elif close < ema50 and close >= ema200:
                pts = max_points * 0.50
                desc = "Consolidation: Below EMA50, Above EMA200"
            else:
                pts = max_points * 0.20
                desc = "Downtrend: Below EMA50 & EMA200"
        else:
            if close >= ema50:
                pts = max_points * 0.75
                desc = "Short-term Uptrend: Above EMA50 (EMA200 warming up)"
            else:
                pts = max_points * 0.25
                desc = "Short-term Downtrend: Below EMA50 (EMA200 warming up)"

        return FactorScore(
            name="trend",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "close": close, "ema50": ema50, "ema200": ema200},
        )

    def _evaluate_momentum_factor(
        self,
        rsi: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """Evaluates Momentum factor (max 20 points)."""
        if rsi is None:
            return FactorScore(
                name="momentum",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "RSI unavailable (insufficient warm-up < 14 bars)"},
            )

        if 55.0 <= rsi <= 70.0:
            pts = max_points
            desc = "Prime Bullish Momentum Zone (55-70)"
        elif 50.0 <= rsi < 55.0:
            pts = max_points * 0.80
            desc = "Mild Bullish Momentum (50-55)"
        elif 70.0 < rsi <= 80.0:
            pts = max_points * 0.70
            desc = "Strong Overbought Expansion (70-80)"
        elif 35.0 <= rsi < 50.0:
            pts = max_points * 0.50
            desc = "Neutral/Weak Momentum (35-50)"
        elif 30.0 <= rsi < 35.0:
            pts = max_points * 0.40
            desc = "Potential Oversold Bounce (30-35)"
        else:
            pts = max_points * 0.20
            desc = "Extreme reading (<30 or >80)"

        return FactorScore(
            name="momentum",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "rsi": rsi},
        )

    def _evaluate_volume_factor(
        self,
        volume_ratio: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """Evaluates Volume factor (max 20 points)."""
        if volume_ratio is None:
            return FactorScore(
                name="volume",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Volume ratio unavailable"},
            )

        if volume_ratio >= 2.0:
            pts = max_points
            desc = "High Volume Surge (>= 2.0x 20D avg)"
        elif volume_ratio >= 1.5:
            pts = max_points * 0.80
            desc = "Above Average Volume (1.5x - 2.0x)"
        elif volume_ratio >= 1.0:
            pts = max_points * 0.60
            desc = "Average Volume (1.0x - 1.5x)"
        elif volume_ratio >= 0.7:
            pts = max_points * 0.40
            desc = "Below Average Volume (0.7x - 1.0x)"
        else:
            pts = max_points * 0.20
            desc = "Dry Volume (< 0.7x)"

        return FactorScore(
            name="volume",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "volume_ratio": volume_ratio},
        )

    def _evaluate_delivery_factor(
        self,
        delivery_pct: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """
        Evaluates Delivery factor (max 15 points).
        Rule 3: UNKNOWN ≠ PASS and UNKNOWN ≠ FAIL.
        If delivery is None (UNKNOWN), do NOT assign 0 and do NOT award unearned points.
        """
        if delivery_pct is None:
            return FactorScore(
                name="delivery",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Delivery data unavailable (UNKNOWN ≠ PASS and UNKNOWN ≠ FAIL)"},
            )

        if delivery_pct >= 55.0:
            pts = max_points
            desc = "Institutional Accumulation (>= 55% delivery)"
        elif delivery_pct >= 45.0:
            pts = max_points * 0.80
            desc = "Strong Delivery (45% - 55%)"
        elif delivery_pct >= 35.0:
            pts = max_points * 0.60
            desc = "Moderate Delivery (35% - 45%)"
        elif delivery_pct >= 25.0:
            pts = max_points * 0.40
            desc = "Average Delivery (25% - 35%)"
        else:
            pts = max_points * 0.20
            desc = "Speculative Turnover (< 25% delivery)"

        return FactorScore(
            name="delivery",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "delivery_pct": delivery_pct},
        )

    def _evaluate_fundamentals_factor(
        self,
        roe: Optional[float],
        pe: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """Evaluates Fundamentals factor (max 15 points)."""
        if roe is None and pe is None:
            return FactorScore(
                name="fundamentals",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Fundamental metrics unavailable"},
            )

        r = roe if roe is not None else 12.0
        p = pe if pe is not None else 25.0

        if r >= 18.0 and p <= 30.0:
            pts = max_points
            desc = "High Quality at Reasonable Price (ROE >= 18%, PE <= 30)"
        elif r >= 12.0 and p <= 45.0:
            pts = max_points * 0.75
            desc = "Solid Quality Fundamentals (ROE >= 12%, PE <= 45)"
        elif r >= 8.0:
            pts = max_points * 0.50
            desc = "Average Fundamentals"
        else:
            pts = max_points * 0.25
            desc = "Weak Fundamentals / High Valuation"

        return FactorScore(
            name="fundamentals",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "roe": roe, "pe": pe},
        )

    def _evaluate_risk_reward_factor(
        self,
        rr_ratio: Optional[float],
        max_points: float,
    ) -> FactorScore:
        """Evaluates Risk/Reward factor (max 10 points)."""
        if rr_ratio is None:
            return FactorScore(
                name="risk_reward",
                points_earned=None,
                max_points=max_points,
                weight=max_points,
                status="UNKNOWN",
                details={"reason": "Risk/Reward ratio unavailable"},
            )

        if rr_ratio >= 3.0:
            pts = max_points
            desc = "Exceptional Asymmetric R:R (>= 3.0:1)"
        elif rr_ratio >= 2.5:
            pts = max_points * 0.85
            desc = "Strong R:R (2.5:1 - 3.0:1)"
        elif rr_ratio >= 2.0:
            pts = max_points * 0.70
            desc = "Standard Swing R:R (2.0:1 - 2.5:1)"
        elif rr_ratio >= 1.5:
            pts = max_points * 0.50
            desc = "Marginal R:R (1.5:1 - 2.0:1)"
        else:
            pts = max_points * 0.20
            desc = "Unfavorable R:R (< 1.5:1)"

        return FactorScore(
            name="risk_reward",
            points_earned=round(pts, 2),
            max_points=max_points,
            weight=max_points,
            status="AVAILABLE",
            details={"description": desc, "rr_ratio": rr_ratio},
        )

    def score(
        self,
        symbol: str,
        trend: Any = None,
        momentum: Any = None,
        volume: Any = None,
        delivery: Any = None,
        fundamentals: Any = None,
        risk_reward: Any = None,
        raw_metrics: Optional[Dict[str, Any]] = None,
        strategy_version: Optional[str] = None,
        timestamp: Optional[str] = None,
        **kwargs: Any,
    ) -> TransparentScoreResult:
        """
        Computes 100-point transparent opportunity score with missing-component normalization.
        Can accept direct component scores or raw metrics.
        """
        ver = strategy_version or self.strategy_version
        metrics = dict(raw_metrics or {})
        metrics.update(kwargs)

        # Run indicator integrity validator if bar count is provided
        bars_count = metrics.get("bars_count")
        if bars_count is not None:
            metrics = validate_indicator_warmup(bars_count, metrics)

        factors: Dict[str, FactorScore] = {}

        # 1. Trend (20 pts)
        if trend is not None or "trend" in kwargs:
            val = trend if trend is not None else kwargs["trend"]
            factors["trend"] = self._normalize_component_input("trend", val, self.weights["trend"])
        else:
            factors["trend"] = self._evaluate_trend_factor(
                close=metrics.get("close"),
                ema50=metrics.get("ema50"),
                ema200=metrics.get("ema200"),
                max_points=self.weights["trend"],
            )

        # 2. Momentum (20 pts)
        if momentum is not None or "momentum" in kwargs:
            val = momentum if momentum is not None else kwargs["momentum"]
            factors["momentum"] = self._normalize_component_input("momentum", val, self.weights["momentum"])
        else:
            factors["momentum"] = self._evaluate_momentum_factor(
                rsi=metrics.get("rsi"),
                max_points=self.weights["momentum"],
            )

        # 3. Volume (20 pts)
        if volume is not None or "volume" in kwargs:
            val = volume if volume is not None else kwargs["volume"]
            factors["volume"] = self._normalize_component_input("volume", val, self.weights["volume"])
        else:
            factors["volume"] = self._evaluate_volume_factor(
                volume_ratio=metrics.get("volume_ratio"),
                max_points=self.weights["volume"],
            )

        # 4. Delivery (15 pts)
        if delivery is not None or "delivery" in kwargs:
            val = delivery if delivery is not None else kwargs["delivery"]
            factors["delivery"] = self._normalize_component_input("delivery", val, self.weights["delivery"])
        else:
            factors["delivery"] = self._evaluate_delivery_factor(
                delivery_pct=metrics.get("delivery_pct"),
                max_points=self.weights["delivery"],
            )

        # 5. Fundamentals (15 pts)
        if fundamentals is not None or "fundamentals" in kwargs:
            val = fundamentals if fundamentals is not None else kwargs["fundamentals"]
            factors["fundamentals"] = self._normalize_component_input("fundamentals", val, self.weights["fundamentals"])
        else:
            factors["fundamentals"] = self._evaluate_fundamentals_factor(
                roe=metrics.get("roe"),
                pe=metrics.get("pe"),
                max_points=self.weights["fundamentals"],
            )

        # 6. Risk/Reward (10 pts)
        if risk_reward is not None or "risk_reward" in kwargs:
            val = risk_reward if risk_reward is not None else kwargs["risk_reward"]
            factors["risk_reward"] = self._normalize_component_input("risk_reward", val, self.weights["risk_reward"])
        else:
            factors["risk_reward"] = self._evaluate_risk_reward_factor(
                rr_ratio=metrics.get("rr_ratio"),
                max_points=self.weights["risk_reward"],
            )

        # Missing-Component Normalization (Tasks 175–179)
        # UNKNOWN ≠ PASS and UNKNOWN ≠ FAIL.
        # final_score = (sum_of_available_points / sum_of_available_max_weights) * 100
        available_points = 0.0
        available_max_weights = 0.0

        for f_name, f_score in factors.items():
            if f_score.status == "AVAILABLE" and f_score.points_earned is not None:
                available_points += f_score.points_earned
                available_max_weights += f_score.max_points

        if available_max_weights > 0:
            final_score = round((available_points / available_max_weights) * 100.0, 2)
        else:
            final_score = 0.0

        coverage_pct = round(
            (available_max_weights / self.total_max_weight) * 100.0, 2
        ) if self.total_max_weight > 0 else 0.0

        classification = self.classify(final_score, coverage_pct)

        # Targets and Stop-Loss (Rule 4: source="MODEL_GENERATED")
        target_obj = self.compute_targets_and_stops(
            close=metrics.get("close"),
            atr=metrics.get("atr"),
            stop_loss=metrics.get("stop_loss"),
            target_price=metrics.get("target_price"),
            rr_ratio=metrics.get("rr_ratio"),
        )

        ts_str = timestamp or datetime.now(timezone.utc).isoformat()

        # Deterministic SHA-256 fingerprint
        canonical_repr = {
            "symbol": symbol,
            "strategy_version": ver,
            "final_score": final_score,
            "coverage_pct": coverage_pct,
            "classification": classification,
            "available_points": available_points,
            "available_max_weights": available_max_weights,
            "breakdown": {k: v.to_dict() for k, v in sorted(factors.items())},
            "targets_and_stops": target_obj.to_dict(),
        }
        canonical_json = json.dumps(canonical_repr, sort_keys=True)
        fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

        return TransparentScoreResult(
            symbol=symbol,
            final_score=final_score,
            coverage_pct=coverage_pct,
            classification=classification,
            strategy_version=ver,
            breakdown=factors,
            available_points=round(available_points, 2),
            available_max_weights=round(available_max_weights, 2),
            total_max_weights=round(self.total_max_weight, 2),
            target_price=target_obj.target_price,
            stop_loss=target_obj.stop_loss,
            rr_ratio=target_obj.rr_ratio,
            source="MODEL_GENERATED",
            targets_and_stops=target_obj,
            metrics_used=metrics,
            deterministic_hash=fingerprint,
            timestamp=ts_str,
        )

    def score_stock(self, symbol: str, **kwargs: Any) -> TransparentScoreResult:
        """Convenience method to score a stock from keyword arguments."""
        return self.score(symbol=symbol, **kwargs)


# ============================================================================
# 3. PUBLIC MODULE-LEVEL INTERFACE
# ============================================================================

_default_engine = TransparentScoringEngine()


def calculate_transparent_score(
    symbol: str,
    trend: Any = None,
    momentum: Any = None,
    volume: Any = None,
    delivery: Any = None,
    fundamentals: Any = None,
    risk_reward: Any = None,
    raw_metrics: Optional[Dict[str, Any]] = None,
    strategy_version: str = STRATEGY_VERSION,
    weights: Optional[Dict[str, float]] = None,
    **kwargs: Any,
) -> TransparentScoreResult:
    """
    Public API computing a 100-point transparent opportunity score.
    """
    if weights:
        engine = TransparentScoringEngine(weights=weights, strategy_version=strategy_version)
    else:
        engine = _default_engine if strategy_version == STRATEGY_VERSION else TransparentScoringEngine(strategy_version=strategy_version)

    return engine.score(
        symbol=symbol,
        trend=trend,
        momentum=momentum,
        volume=volume,
        delivery=delivery,
        fundamentals=fundamentals,
        risk_reward=risk_reward,
        raw_metrics=raw_metrics,
        strategy_version=strategy_version,
        **kwargs,
    )


def score_stock(symbol: str, **kwargs: Any) -> TransparentScoreResult:
    """Public helper matching parallel_analyzer and screener conventions."""
    return calculate_transparent_score(symbol=symbol, **kwargs)
