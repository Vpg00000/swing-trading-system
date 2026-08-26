"""
Decision engine for the swing trading support system.
Computes a normalized composite score (/100) using the 10-component
architecture from the AI Market Intelligence diagram, and classifies
actions using a rich vocabulary.

New 10-component formula (matches diagram Module 19):
  Market Regime    /10  — from engine/regime.py RegimeResult
  Sector           /10  — from engine/sector_score.py SectorScore
  Catalyst         /15  — from engine/news.py + priced_in.py
  FII/DII/MF       /15  — from engine/money_flow.py (ownership_score component)
  Insider          /10  — from engine/money_flow.py (insider_score + bulk_block_score)
  Technical        /15  — from engine/relative_strength.py + engine/momentum.py
  Fundamental      /10  — from engine/fundamental.py FundamentalScore
  Cash Flow         /5  — from engine/fundamental.py (cashflow_score sub-component)
  Governance        /5  — from engine/governance.py GovernanceScore
  Valuation         /5  — from engine/valuation.py ValuationScore
  ──────────────────────
  TOTAL            /100

Action vocabulary (expanded from binary BUY/HOLD OFF):
  BUY_NOW | BUY_ON_PULLBACK | WAIT_FOR_BREAKOUT | WAIT_FOR_NEWS_CONFIRMATION
  WATCH | HOLD | REDUCE | EXIT | CASH | WAIT

Backward-compatible: old callers that used evaluate_decision() still work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DecisionResult:
    symbol: str
    overall_score: float
    # New 10-component breakdown
    regime_component: float       # /10
    sector_component: float       # /10
    catalyst_component: float     # /15
    fii_dii_component: float      # /15
    insider_component: float      # /10
    technical_component: float    # /15
    fundamental_component: float  # /10
    cashflow_component: float     # /5
    governance_component: float   # /5
    valuation_component: float    # /5
    suggested_action: str
    concerns: list[str]
    # Data quality flags
    missing_components: list[str]


def _regime_to_10(regime_state: str, regime_score: Optional[float] = None) -> float:
    """
    Convert regime state (or score /100) to a /10 component.
    If multi-factor regime_score is available, use it directly.
    Falls back to binary regime_state mapping.
    """
    if regime_score is not None:
        return (regime_score / 100.0) * 10.0

    mapping = {
        "RISK-ON":          9.0,
        "RISK-ON-CAUTIOUS": 6.5,
        "RISK-OFF":         3.0,
        "EMERGENCY":        0.5,
    }
    return mapping.get(regime_state, 5.0)


def _sector_to_10(sector_overall_score: Optional[float]) -> float:
    """Convert sector score /100 to /10."""
    if sector_overall_score is None:
        return 5.0  # neutral when unavailable
    return (sector_overall_score / 100.0) * 10.0


def _catalyst_to_15(
    news_flagged: bool,
    priced_in_status: Optional[str],
) -> float:
    """Map catalyst signal to /15."""
    if not news_flagged:
        return 7.5  # neutral, no catalyst

    if priced_in_status == "POTENTIALLY_UNDERPRICED":
        return 15.0
    elif priced_in_status == "PARTIALLY_PRICED_IN":
        return 10.0
    elif priced_in_status == "LIKELY_PRICED_IN":
        return 4.0
    else:  # INSUFFICIENT_DATA or None
        return 7.5  # flagged but unclear → neutral


def _money_flow_to_fii_dii_15(ownership_score: Optional[float]) -> float:
    """
    Map ownership_score (-4..+4) from MoneyFlowScore to /15.
    Mid-point (0) → 7.5, full buying (+4) → 15, full selling (-4) → 0.
    """
    if ownership_score is None:
        return 7.5  # neutral
    # ownership_score ranges -4 to +4 → map to 0-15
    score_15 = ((ownership_score + 4.0) / 8.0) * 15.0
    return max(0.0, min(15.0, score_15))


def _insider_to_10(
    insider_score: Optional[float],    # -8..+8 from money_flow
    bulk_block_score: Optional[float], # -4..+4 from money_flow
) -> float:
    """
    Combine insider + bulk/block signals → /10.
    Combined range: (-12..+12) → mapped to 0-10.
    """
    ins = insider_score if insider_score is not None else 0.0
    bbl = bulk_block_score if bulk_block_score is not None else 0.0
    combined = ins + bbl  # -12 to +12
    score_10 = ((combined + 12.0) / 24.0) * 10.0
    return max(0.0, min(10.0, score_10))


def _technical_to_15(
    momentum_pct: float,       # 0.0 to 1.0 (percentile rank in candidate list)
    rs_score_100: Optional[float] = None,  # RS score /100 from relative_strength.py
) -> float:
    """
    Combine momentum percentile rank and relative strength → /15.
    RS score (60% weight) + momentum percentile (40% weight).
    """
    # Momentum percentile → /100
    momentum_100 = momentum_pct * 100.0

    if rs_score_100 is not None:
        combined_100 = 0.6 * rs_score_100 + 0.4 * momentum_100
    else:
        combined_100 = momentum_100  # fall back to momentum only

    return (combined_100 / 100.0) * 15.0


def _fundamental_to_10(fundamental_score_100: Optional[float]) -> float:
    """Map FundamentalScore /100 → /10."""
    if fundamental_score_100 is None:
        return 5.0  # neutral when unavailable
    return (fundamental_score_100 / 100.0) * 10.0


def _cashflow_to_5(cashflow_score: Optional[float]) -> float:
    """
    Map cashflow sub-score from FundamentalScore → /5.
    cashflow_score is already /20 from fundamental.py; rescale to /5.
    """
    if cashflow_score is None:
        return 2.5  # neutral
    return (cashflow_score / 20.0) * 5.0


def _governance_to_5(governance_score_100: Optional[float]) -> float:
    """Map GovernanceScore /100 → /5."""
    if governance_score_100 is None:
        return 4.0  # assume clean when no data (not penalize unknown)
    return (governance_score_100 / 100.0) * 5.0


def _valuation_to_5(valuation_score_100: Optional[float]) -> float:
    """Map ValuationScore /100 → /5."""
    if valuation_score_100 is None:
        return 2.5  # neutral when unavailable
    return (valuation_score_100 / 100.0) * 5.0


def compute_composite_score(
    # Required
    regime_state: str,
    momentum_pct: float,
    # Optional new components
    regime_score: Optional[float] = None,          # /100 multi-factor regime score
    sector_overall_score: Optional[float] = None,  # /100 sector score
    news_flagged: bool = False,
    priced_in_status: Optional[str] = None,
    ownership_score: Optional[float] = None,       # -4..+4 from MoneyFlowScore
    insider_score: Optional[float] = None,         # -8..+8
    bulk_block_score: Optional[float] = None,      # -4..+4
    rs_score_100: Optional[float] = None,          # /100 RS score
    fundamental_score_100: Optional[float] = None, # /100
    cashflow_sub_score: Optional[float] = None,    # /20 sub-score from fundamental
    governance_score_100: Optional[float] = None,  # /100
    valuation_score_100: Optional[float] = None,   # /100
    # Risk flags (for concerns generation)
    stop_distance_pct: float = 0.0,
    pledged_pct: float = 0.0,
    has_upcoming_event: bool = False,
    sector_stacking_risk: bool = False,
) -> tuple[float, dict[str, float], list[str], list[str]]:
    """
    Computes the /100 composite score using the 10-component formula.

    Returns:
        (total_score, component_dict, concerns, missing_components)
    """
    concerns: list[str] = []
    missing: list[str] = []

    # ── 1. Market Regime /10 ─────────────────────────────────────────────────
    regime_10 = _regime_to_10(regime_state, regime_score)

    # ── 2. Sector /10 ────────────────────────────────────────────────────────
    sector_10 = _sector_to_10(sector_overall_score)
    if sector_overall_score is None:
        missing.append("sector_score")

    # ── 3. Catalyst /15 ──────────────────────────────────────────────────────
    catalyst_15 = _catalyst_to_15(news_flagged, priced_in_status)

    # ── 4. FII/DII/MF /15 ────────────────────────────────────────────────────
    fii_dii_15 = _money_flow_to_fii_dii_15(ownership_score)
    if ownership_score is None:
        missing.append("fii_dii_flow")

    # ── 5. Insider /10 ───────────────────────────────────────────────────────
    insider_10 = _insider_to_10(insider_score, bulk_block_score)
    if insider_score is None and bulk_block_score is None:
        missing.append("insider_flow")

    # ── 6. Technical /15 ─────────────────────────────────────────────────────
    technical_15 = _technical_to_15(momentum_pct, rs_score_100)
    if rs_score_100 is None:
        missing.append("rs_score")

    # ── 7. Fundamental /10 ───────────────────────────────────────────────────
    fundamental_10 = _fundamental_to_10(fundamental_score_100)
    if fundamental_score_100 is None:
        missing.append("fundamental_score")

    # ── 8. Cash Flow /5 ──────────────────────────────────────────────────────
    cashflow_5 = _cashflow_to_5(cashflow_sub_score)
    if cashflow_sub_score is None:
        missing.append("cashflow_score")

    # ── 9. Governance /5 ─────────────────────────────────────────────────────
    governance_5 = _governance_to_5(governance_score_100)
    if governance_score_100 is None:
        missing.append("governance_score")

    # ── 10. Valuation /5 ─────────────────────────────────────────────────────
    valuation_5 = _valuation_to_5(valuation_score_100)
    if valuation_score_100 is None:
        missing.append("valuation_score")

    # ── Risk Concerns (don't change score, just flag) ─────────────────────────
    if stop_distance_pct > 0.08:
        concerns.append(f"wide stop ({stop_distance_pct:.1%})")
    elif stop_distance_pct > 0.05:
        concerns.append(f"moderate stop ({stop_distance_pct:.1%})")

    if pledged_pct >= 50.0:
        concerns.append(f"CRITICAL: promoter pledge {pledged_pct:.1f}%")
    elif pledged_pct >= 20.0:
        concerns.append(f"elevated pledge {pledged_pct:.1f}%")
    elif pledged_pct > 0.0:
        concerns.append(f"pledge present {pledged_pct:.1f}%")

    if has_upcoming_event:
        concerns.append("corporate action/board meeting within 21 days")
    if sector_stacking_risk:
        concerns.append("sector-stacking risk (sector cap)")

    # ── Total ─────────────────────────────────────────────────────────────────
    total = (
        regime_10 + sector_10 + catalyst_15 + fii_dii_15 + insider_10
        + technical_15 + fundamental_10 + cashflow_5 + governance_5 + valuation_5
    )
    total = round(max(0.0, min(100.0, total)), 1)

    components = {
        "regime":      round(regime_10, 1),
        "sector":      round(sector_10, 1),
        "catalyst":    round(catalyst_15, 1),
        "fii_dii":     round(fii_dii_15, 1),
        "insider":     round(insider_10, 1),
        "technical":   round(technical_15, 1),
        "fundamental": round(fundamental_10, 1),
        "cashflow":    round(cashflow_5, 1),
        "governance":  round(governance_5, 1),
        "valuation":   round(valuation_5, 1),
    }

    return total, components, concerns, missing


def classify_action(
    symbol: str,
    rank: Optional[int],
    total_candidates: int,
    composite_score: float,
    is_held: bool,
    regime_state: str,
    news_flagged: bool,
    stop_distance_pct: float,
    pledged_pct: float,
    has_upcoming_event: bool,
    sector_stacking_risk: bool,
    sector_overall_score: Optional[float],
    concerns: list[str],
) -> str:
    """
    Classifies the suggested action using the rich vocabulary.
    """
    if is_held:
        if regime_state == "EMERGENCY":
            return "EXIT"
        if composite_score < 30.0:
            return "EXIT"
        if pledged_pct >= 50.0:
            return "EXIT"
        if rank is None or rank > 15:
            return "EXIT"
        if sector_stacking_risk:
            return "REDUCE"
        if regime_state == "RISK-OFF" and (rank or 99) > 8:
            return "REDUCE"
        if (rank or 99) > 10 and composite_score < 45.0:
            return "REDUCE"
        return "HOLD"

    else:
        # Not held
        if regime_state == "EMERGENCY":
            return "CASH"
        if regime_state == "RISK-OFF":
            if composite_score >= 75.0:
                return "WATCH"  # wait for regime improvement
            return "WAIT"
        if news_flagged and priced_in_status_unknown(rank, composite_score):
            return "WAIT_FOR_NEWS_CONFIRMATION"
        if sector_stacking_risk:
            return "WAIT"
        if (
            sector_overall_score is not None
            and sector_overall_score > 80.0
            and rank is not None and rank <= 3
            and stop_distance_pct < 0.04
        ):
            return "WAIT_FOR_BREAKOUT"
        if rank is not None and rank <= 8 and composite_score >= 65.0:
            if stop_distance_pct > 0.08:
                return "BUY_ON_PULLBACK"
            return "BUY_NOW"
        if rank is not None and rank <= 8 and composite_score >= 50.0:
            return "BUY_ON_PULLBACK"
        if (rank is not None and rank <= 15) or composite_score >= 40.0:
            return "WATCH"
        return "WAIT"


def priced_in_status_unknown(rank, score) -> bool:
    """Helper: treat news as uncertain when we lack confirmation."""
    return True  # conservative: always wait for news confirmation


def evaluate_decision(
    symbol: str,
    rank: Optional[int],
    total_candidates: int,
    momentum_pct: float,
    sector_overall_score: Optional[float],
    money_flow_total: Optional[float],      # legacy field — mapped to components below
    news_flagged: bool,
    priced_in_status: Optional[str],
    stop_distance_pct: float,
    pledged_pct: float,
    has_upcoming_event: bool,
    sector_stacking_risk: bool,
    is_held: bool,
    regime_state: str,
    # New optional inputs
    regime_score: Optional[float] = None,
    rs_score_100: Optional[float] = None,
    fundamental_score_100: Optional[float] = None,
    cashflow_sub_score: Optional[float] = None,
    governance_score_100: Optional[float] = None,
    valuation_score_100: Optional[float] = None,
    ownership_score: Optional[float] = None,
    insider_score: Optional[float] = None,
    bulk_block_score: Optional[float] = None,
) -> DecisionResult:
    """
    Runs the full decision loop for a symbol and returns a DecisionResult.
    Backward-compatible: old callers can pass money_flow_total and it will
    be decomposed into approximate ownership/insider splits.
    """
    # Legacy compatibility: decompose money_flow_total into components
    if money_flow_total is not None and ownership_score is None and insider_score is None:
        # money_flow_total is -20..+20. Split roughly 40% ownership, 60% insider+bulk
        ownership_score = money_flow_total * 0.4 / 5.0 * 4.0  # scale to -4..+4
        insider_score = money_flow_total * 0.6 / 5.0 * 8.0    # scale to -8..+8
        bulk_block_score = 0.0

    total, components, concerns, missing = compute_composite_score(
        regime_state=regime_state,
        momentum_pct=momentum_pct,
        regime_score=regime_score,
        sector_overall_score=sector_overall_score,
        news_flagged=news_flagged,
        priced_in_status=priced_in_status,
        ownership_score=ownership_score,
        insider_score=insider_score,
        bulk_block_score=bulk_block_score,
        rs_score_100=rs_score_100,
        fundamental_score_100=fundamental_score_100,
        cashflow_sub_score=cashflow_sub_score,
        governance_score_100=governance_score_100,
        valuation_score_100=valuation_score_100,
        stop_distance_pct=stop_distance_pct,
        pledged_pct=pledged_pct,
        has_upcoming_event=has_upcoming_event,
        sector_stacking_risk=sector_stacking_risk,
    )

    action = classify_action(
        symbol=symbol,
        rank=rank,
        total_candidates=total_candidates,
        composite_score=total,
        is_held=is_held,
        regime_state=regime_state,
        news_flagged=news_flagged,
        stop_distance_pct=stop_distance_pct,
        pledged_pct=pledged_pct,
        has_upcoming_event=has_upcoming_event,
        sector_stacking_risk=sector_stacking_risk,
        sector_overall_score=sector_overall_score,
        concerns=concerns,
    )

    return DecisionResult(
        symbol=symbol,
        overall_score=total,
        regime_component=components["regime"],
        sector_component=components["sector"],
        catalyst_component=components["catalyst"],
        fii_dii_component=components["fii_dii"],
        insider_component=components["insider"],
        technical_component=components["technical"],
        fundamental_component=components["fundamental"],
        cashflow_component=components["cashflow"],
        governance_component=components["governance"],
        valuation_component=components["valuation"],
        suggested_action=action,
        concerns=concerns,
        missing_components=missing,
    )
