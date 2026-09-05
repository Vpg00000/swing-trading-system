"""
engine/governance.py — Governance & Risk Score engine (Module 14).

Produces a GovernanceScore /5 (for composite) and /100 (for analysis).
Uses existing data already fetched by other modules — no new API calls.

Inputs used:
  - Promoter pledge % (from data/institutional/pledge.py or screener)
  - Promoter holding % (from screener or shareholding)
  - FII/DII ownership changes (from shareholding — proxy for institutional confidence)
  - Any SEBI action flags (manual or from news engine)
  - Credit rating changes (not fetched — manual flag)

Score starts at 100 and deductions are applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


def _to_float(val: object) -> Optional[float]:
    """Safely convert value to float, returning None for invalid/NaN/Inf values."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


@dataclass
class GovernanceScore:
    symbol: str
    total_100: float        # /100
    total_5: float          # /5 for composite
    deductions: list[str]   # list of applied deductions with reasons
    pledged_pct: Optional[float]
    promoter_pct: Optional[float]
    status: str             # 'SCORED', 'PARTIAL_DATA', 'DATA_UNAVAILABLE'
    missing: list[str] = field(default_factory=list)


def compute_governance_score(
    symbol: str,
    pledged_pct: Optional[float],            # from pledge.py or screener
    promoter_pct: Optional[float],           # % of shares held by promoters
    fii_qoq_change: Optional[float] = None, # +ve = buying, -ve = selling
    has_sebi_action: bool = False,           # manual flag
    auditor_qualified: bool = False,         # qualified audit report flag
    promoter_share_sold: bool = False,       # insider selling flag (from bulk/block)
    credit_rating_downgrade: bool = False,   # credit rating downgrade flag
    rpt_high_risk: bool = False,            # related party transaction high risk flag
    auditor_score: Optional[float] = None,   # auditor quality score (0-100)
) -> GovernanceScore:
    """
    Compute governance/risk score starting from 100 with deductions.

    Deductions:
      Pledge ≥50%      : -30  (existential risk)
      Pledge 20-50%    : -15
      Pledge 1-20%     : -5
      SEBI action      : -20
      Audit qualified  : -15
      Promoter sold    : -10
      Credit downgrade : -10
      Promoter < 15%   : -5  (skin in game concern)
      FII sold >3% QoQ : -5  (institutional exit)
      RPT high risk    : -15 (related party transactions)
      Auditor score<50 : -10 (low auditor quality)
    """
    score = 100.0
    deductions: list[str] = []
    missing: list[str] = []

    pledged_val = _to_float(pledged_pct)
    promoter_val = _to_float(promoter_pct)
    fii_val = _to_float(fii_qoq_change)
    audit_val = _to_float(auditor_score)

    # ── Pledge deductions ─────────────────────────────────────────────────────
    if pledged_val is None:
        missing.append("pledge_pct")
        # We can't assess this risk — don't deduct but flag
    elif pledged_val >= 50.0:
        score -= 30.0
        deductions.append(f"pledge {pledged_val:.1f}% (CRITICAL -30)")
    elif pledged_val >= 20.0:
        score -= 15.0
        deductions.append(f"pledge {pledged_val:.1f}% (HIGH -15)")
    elif pledged_val > 0.0:
        score -= 5.0
        deductions.append(f"pledge {pledged_val:.1f}% (LOW -5)")

    # ── Promoter holding concern ───────────────────────────────────────────────
    if promoter_val is not None:
        if promoter_val < 15.0:
            score -= 5.0
            deductions.append(f"low promoter holding {promoter_val:.1f}% (-5)")
    else:
        missing.append("promoter_pct")

    # ── FII selling signal ────────────────────────────────────────────────────
    if fii_val is not None and fii_val < -3.0:
        score -= 5.0
        deductions.append(f"FII sold {abs(fii_val):.1f}% QoQ (-5)")

    # ── SEBI action (manual flag) ─────────────────────────────────────────────
    if bool(has_sebi_action):
        score -= 20.0
        deductions.append("SEBI regulatory action (-20)")

    # ── Audit qualification ───────────────────────────────────────────────────
    if bool(auditor_qualified):
        score -= 15.0
        deductions.append("qualified audit report (-15)")

    # ── Promoter selling ──────────────────────────────────────────────────────
    if bool(promoter_share_sold):
        score -= 10.0
        deductions.append("promoter/insider shares sold (-10)")

    # ── Credit rating downgrade ───────────────────────────────────────────────
    if bool(credit_rating_downgrade):
        score -= 10.0
        deductions.append("credit rating downgrade (-10)")

    # ── Related party transaction risk ───────────────────────────────────────
    if bool(rpt_high_risk):
        score -= 15.0
        deductions.append("high related-party transactions risk (-15)")

    # ── Auditor quality score ─────────────────────────────────────────────────
    if audit_val is not None and audit_val < 50.0:
        score -= 10.0
        deductions.append(f"low auditor quality score {audit_val:.1f} (-10)")

    score = max(0.0, min(100.0, score))
    total_100 = round(score, 1)
    total_5 = round((total_100 / 100.0) * 5.0, 2)

    if len(missing) >= 2:
        status = "DATA_UNAVAILABLE"
    elif len(missing) > 0:
        status = "PARTIAL_DATA"
    else:
        status = "SCORED"

    return GovernanceScore(
        symbol=symbol,
        total_100=total_100,
        total_5=total_5,
        deductions=deductions,
        pledged_pct=pledged_val,
        promoter_pct=promoter_val,
        status=status,
        missing=missing,
    )


def governance_from_money_flow(
    symbol: str,
    money_flow_result,      # MoneyFlowResult from engine/money_flow.py
    screener_data=None,     # ScreenerData from data/screener.py (optional)
) -> GovernanceScore:
    """
    Convenience wrapper that builds GovernanceScore from existing data
    already fetched by the money flow and screener pipelines.

    Parameters:
        money_flow_result: engine.money_flow.MoneyFlowResult
        screener_data:     data.screener.ScreenerData (optional)
    """
    pledged_pct = getattr(money_flow_result, "pledged_pct", None) if money_flow_result else None
    if pledged_pct is None and isinstance(screener_data, dict):
        pledged_pct = screener_data.get("pledged_pct") or screener_data.get("promoter_pledged_pct")
    elif pledged_pct is None and screener_data is not None:
        pledged_pct = getattr(screener_data, "pledged_pct", getattr(screener_data, "promoter_pledged_pct", None))

    promoter_pct = None
    if isinstance(screener_data, dict):
        promoter_pct = screener_data.get("promoter_holding_pct") or screener_data.get("promoter_holding")
    elif screener_data is not None:
        promoter_pct = getattr(screener_data, "promoter_holding_pct", getattr(screener_data, "promoter_holding", None))

    # FII QoQ from ownership_snapshot if available
    ownership = getattr(money_flow_result, "_ownership_snapshot", None) if money_flow_result else None
    fii_qoq = None
    if ownership is not None:
        if isinstance(ownership, dict):
            curr = ownership.get("fii_pct")
            prev = ownership.get("prev_fii_pct")
        else:
            curr = getattr(ownership, "fii_pct", None)
            prev = getattr(ownership, "prev_fii_pct", None)
        curr_f = _to_float(curr)
        prev_f = _to_float(prev)
        if curr_f is not None and prev_f is not None:
            fii_qoq = curr_f - prev_f

    # Insider selling: if insider_score < 0, promoters are selling
    promoter_sold = False
    insider_score = getattr(money_flow_result, "insider_score", None) if money_flow_result else None
    insider_score_f = _to_float(insider_score)
    if insider_score_f is not None and insider_score_f < 0:
        promoter_sold = True

    return compute_governance_score(
        symbol=symbol,
        pledged_pct=pledged_pct,
        promoter_pct=promoter_pct,
        fii_qoq_change=fii_qoq,
        has_sebi_action=False,  # not automated; manual override
        auditor_qualified=False,
        promoter_share_sold=promoter_sold,
        credit_rating_downgrade=False,
    )


if __name__ == "__main__":
    # Quick self-test with hand-crafted values
    tests = [
        ("CLEAN_CO", 0.0, 55.0, 2.0, False, False, False, False),
        ("PLEDGED_CO", 35.0, 60.0, -5.0, False, False, True, False),
        ("RISKY_CO", 60.0, 12.0, -8.0, True, True, True, True),
    ]
    for args in tests:
        gs = compute_governance_score(*args)
        print(f"=== {gs.symbol} ===")
        print(f"  Governance Score: {gs.total_100}/100 → {gs.total_5}/5")
        print(f"  Pledge:           {gs.pledged_pct}%")
        for d in gs.deductions:
            print(f"  ⚠  {d}")
        print()