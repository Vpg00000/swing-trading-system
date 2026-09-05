"""
Composite Opportunity Scoring Engine (TASK-017)

Combines technical, regime, flow, sector, fundamental, forensic, and priced-in
inputs into a 100-point composite opportunity score with a reproducible score breakdown.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Union
from engine.priced_in import PricedInResult

DEFAULT_WEIGHTS = {
    "technical": 20.0,
    "regime": 15.0,
    "flow": 15.0,
    "sector": 15.0,
    "fundamental": 15.0,
    "forensic": 10.0,
    "priced_in": 10.0,
}

@dataclass
class ScoreBreakdown:
    technical: float
    regime: float
    flow: float
    sector: float
    fundamental: float
    forensic: float
    priced_in: float

    def total(self) -> float:
        return round(
            self.technical +
            self.regime +
            self.flow +
            self.sector +
            self.fundamental +
            self.forensic +
            self.priced_in,
            2
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "technical": self.technical,
            "regime": self.regime,
            "flow": self.flow,
            "sector": self.sector,
            "fundamental": self.fundamental,
            "forensic": self.forensic,
            "priced_in": self.priced_in,
        }

    def as_dict(self) -> Dict[str, float]:
        return self.to_dict()

@dataclass
class OpportunityScoreResult:
    symbol: str
    total_score: float
    score_breakdown: ScoreBreakdown
    rank_grade: str
    confidence: float
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_score": self.total_score,
            "score_breakdown": self.score_breakdown.to_dict(),
            "rank_grade": self.rank_grade,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def _normalize_score_input(val: Union[float, int, str, Dict[str, Any], None], default_norm: float = 0.5) -> Tuple_Score_Conf:
    """Helper to convert various input types into (normalized_score 0.0..1.0, confidence 0.0..1.0)."""
    if val is None:
        return default_norm, 0.5

    if isinstance(val, (int, float)):
        v = float(val)
        if v > 1.0:
            # Assume 0..100 scale
            norm = max(0.0, min(1.0, v / 100.0))
        else:
            norm = max(0.0, min(1.0, v))
        return norm, 1.0

    if isinstance(val, str):
        v_upper = val.upper()
        if v_upper in ["BULLISH", "STRONG", "VERY_HIGH", "UNDERPRICED", "STRONG_BUY"]:
            return 1.0, 0.9
        elif v_upper in ["MODERATE_BULLISH", "BUY", "HIGH", "PARTIALLY_PRICED"]:
            return 0.75, 0.8
        elif v_upper in ["NEUTRAL", "HOLD", "UNKNOWN", "MEDIUM"]:
            return 0.5, 0.7
        elif v_upper in ["BEARISH", "WEAK", "LOW", "FULLY_PRICED"]:
            return 0.25, 0.8
        elif v_upper in ["VERY_BEARISH", "AVOID", "OVERPRICED", "FRAUD_RISK"]:
            return 0.0, 0.9
        return default_norm, 0.5

    if isinstance(val, dict):
        if "normalized_score" in val:
            conf = float(val.get("confidence", 1.0))
            return max(0.0, min(1.0, float(val["normalized_score"]))), conf
        if "score" in val:
            conf = float(val.get("confidence", 1.0))
            s = float(val["score"])
            norm = (s / 100.0) if s > 1.0 else s
            return max(0.0, min(1.0, norm)), conf

    return default_norm, 0.5

Tuple_Score_Conf = tuple  # type alias tuple[float, float]


def _normalize_priced_in(priced_in: Union[float, int, str, PricedInResult, Dict[str, Any], None]) -> tuple[float, float]:
    if priced_in is None:
        return 0.5, 0.5

    if isinstance(priced_in, PricedInResult):
        status_map = {
            "UNDERPRICED": 1.0,
            "PARTIALLY_PRICED": 0.65,
            "UNKNOWN": 0.5,
            "FULLY_PRICED": 0.2,
            "OVERPRICED": 0.0,
        }
        mult = status_map.get(priced_in.status, 0.5)
        conf = priced_in.confidence if priced_in.confidence is not None else 0.8
        return mult, conf

    if isinstance(priced_in, dict):
        status = priced_in.get("status") or priced_in.get("inference", {}).get("status", "UNKNOWN")
        conf = priced_in.get("confidence") or priced_in.get("inference", {}).get("confidence", 0.7)
        status_map = {
            "UNDERPRICED": 1.0,
            "PARTIALLY_PRICED": 0.65,
            "UNKNOWN": 0.5,
            "FULLY_PRICED": 0.2,
            "OVERPRICED": 0.0,
        }
        mult = status_map.get(status, 0.5)
        return mult, float(conf)

    return _normalize_score_input(priced_in)


def calculate_opportunity_score(
    symbol: str,
    technical: Union[float, int, str, Dict[str, Any], None] = None,
    regime: Union[float, int, str, Dict[str, Any], None] = None,
    flow: Union[float, int, str, Dict[str, Any], None] = None,
    sector: Union[float, int, str, Dict[str, Any], None] = None,
    fundamental: Union[float, int, str, Dict[str, Any], None] = None,
    forensic: Union[float, int, str, Dict[str, Any], None] = None,
    priced_in: Union[float, int, str, PricedInResult, Dict[str, Any], None] = None,
    weights: Optional[Dict[str, float]] = None,
) -> OpportunityScoreResult:
    """
    Computes a 100-point opportunity score for the given symbol across 7 sub-components.

    Parameters:
    - symbol: Stock ticker symbol (e.g. 'RELIANCE.NS')
    - technical, regime, flow, sector, fundamental, forensic, priced_in: component inputs
    - weights: optional dictionary overriding DEFAULT_WEIGHTS (must sum to 100 for 100-pt scale)
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update(weights)

    tech_norm, tech_conf = _normalize_score_input(technical)
    reg_norm, reg_conf = _normalize_score_input(regime)
    flow_norm, flow_conf = _normalize_score_input(flow)
    sec_norm, sec_conf = _normalize_score_input(sector)
    fund_norm, fund_conf = _normalize_score_input(fundamental)
    foren_norm, foren_conf = _normalize_score_input(forensic)
    pi_norm, pi_conf = _normalize_priced_in(priced_in)

    tech_pts = round(tech_norm * w["technical"], 2)
    reg_pts = round(reg_norm * w["regime"], 2)
    flow_pts = round(flow_norm * w["flow"], 2)
    sec_pts = round(sec_norm * w["sector"], 2)
    fund_pts = round(fund_norm * w["fundamental"], 2)
    foren_pts = round(foren_norm * w["forensic"], 2)
    pi_pts = round(pi_norm * w["priced_in"], 2)

    breakdown = ScoreBreakdown(
        technical=tech_pts,
        regime=reg_pts,
        flow=flow_pts,
        sector=sec_pts,
        fundamental=fund_pts,
        forensic=foren_pts,
        priced_in=pi_pts,
    )

    total_score = round(
        tech_pts + reg_pts + flow_pts + sec_pts + fund_pts + foren_pts + pi_pts, 2
    )

    # Grade classification
    if total_score >= 80.0:
        rank_grade = "STRONG_BUY"
    elif total_score >= 65.0:
        rank_grade = "BUY"
    elif total_score >= 50.0:
        rank_grade = "HOLD"
    elif total_score >= 35.0:
        rank_grade = "WEAK"
    else:
        rank_grade = "AVOID"

    avg_conf = round(
        (tech_conf + reg_conf + flow_conf + sec_conf + fund_conf + foren_conf + pi_conf) / 7.0,
        2
    )

    evidence = {
        "symbol": symbol,
        "weights": w,
        "normalized_scores": {
            "technical": tech_norm,
            "regime": reg_norm,
            "flow": flow_norm,
            "sector": sec_norm,
            "fundamental": fund_norm,
            "forensic": foren_norm,
            "priced_in": pi_norm,
        },
        "component_confidences": {
            "technical": tech_conf,
            "regime": reg_conf,
            "flow": flow_conf,
            "sector": sec_conf,
            "fundamental": fund_conf,
            "forensic": foren_conf,
            "priced_in": pi_conf,
        },
    }

    return OpportunityScoreResult(
        symbol=symbol,
        total_score=total_score,
        score_breakdown=breakdown,
        rank_grade=rank_grade,
        confidence=avg_conf,
        evidence=evidence,
    )


score_opportunity = calculate_opportunity_score


class CompositeOpportunityScorer:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS

    def score(
        self,
        symbol: str,
        technical: Union[float, int, str, Dict[str, Any], None] = None,
        regime: Union[float, int, str, Dict[str, Any], None] = None,
        flow: Union[float, int, str, Dict[str, Any], None] = None,
        sector: Union[float, int, str, Dict[str, Any], None] = None,
        fundamental: Union[float, int, str, Dict[str, Any], None] = None,
        forensic: Union[float, int, str, Dict[str, Any], None] = None,
        priced_in: Union[float, int, str, PricedInResult, Dict[str, Any], None] = None,
    ) -> OpportunityScoreResult:
        return calculate_opportunity_score(
            symbol=symbol,
            technical=technical,
            regime=regime,
            flow=flow,
            sector=sector,
            fundamental=fundamental,
            forensic=forensic,
            priced_in=priced_in,
            weights=self.weights,
        )
