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

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GovernanceScore:
    symbol: str
    total_100: float        # /100
    total_5: float          # /5 for composite
    deductions: list[str]   # list of applied deductions with reasons
    pledged_pct: Optional[float]
    promoter_pct: Optional[float]
    status: str             # 'SCORED', 'PARTIAL_DATA', 'DATA_UNAVAILABLE'


def compute_governance_score(
    symbol: str,
    pledged_pct: Optional[float],            # from pledge.py or screener
    promoter_pct: Optional[float],           # % of shares held by promoters
    fii_qoq_change: Optional[float] = None, # +ve = buying, -ve = selling
    has_sebi_action: bool = False,           # manual flag
    auditor_qualified: bool = False,         # qualified audit report flag
    promoter_share_sold: bool = False,       # insider selling flag (from bulk/block)
    credit_rating_downgrade: bool = False,   # credit rating downgrade flag
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
    """
    score = 100.0
    deductions: list[str] = []
    missing: list[str] = []

    # ── Pledge deductions ─────────────────────────────────────────────────────
    if pledged_pct is None:
        missing.append("pledge_pct")
        # We can't assess this risk — don't deduct but flag
    elif pledged_pct >= 50.0:
        score -= 30.0
        deductions.append(f"pledge {pledged_pct:.1f}% (CRITICAL -30)")
    elif pledged_pct >= 20.0:
        score -= 15.0
        deductions.append(f"pledge {pledged_pct:.1f}% (HIGH -15)")
    elif pledged_pct > 0.0:
        score -= 5.0
        deductions.append(f"pledge {pledged_pct:.1f}% (LOW -5)")

    # ── Promoter holding concern ───────────────────────────────────────────────
    if promoter_pct is not None:
        if promoter_pct < 15.0:
            score -= 5.0
            deductions.append(f"low promoter holding {promoter_pct:.1f}% (-5)")
    else:
        missing.append("promoter_pct")

    # ── FII selling signal ────────────────────────────────────────────────────
    if fii_qoq_change is not None and fii_qoq_change < -3.0:
        score -= 5.0
        deductions.append(f"FII sold {abs(fii_qoq_change):.1f}% QoQ (-5)")

    # ── SEBI action (manual flag) ─────────────────────────────────────────────
    if has_sebi_action:
        score -= 20.0
        deductions.append("SEBI regulatory action (-20)")

    # ── Audit qualification ───────────────────────────────────────────────────
    if auditor_qualified:
        score -= 15.0
        deductions.append("qualified audit report (-15)")

    # ── Promoter selling ──────────────────────────────────────────────────────
    if promoter_share_sold:
        score -= 10.0
        deductions.append("promoter/insider shares sold (-10)")

    # ── Credit rating downgrade ───────────────────────────────────────────────
    if credit_rating_downgrade:
        score -= 10.0
        deductions.append("credit rating downgrade (-10)")

    score = max(0.0, min(100.0, score))
    total_100 = round(score, 1)
    total_5 = round((total_100 / 100.0) * 5.0, 2)

    if len(missing) >= 2:
        status = "PARTIAL_DATA"
    elif total_100 == 100.0 and not deductions:
        status = "SCORED"  # Clean bill
    else:
        status = "SCORED"

    return GovernanceScore(
        symbol=symbol,
        total_100=total_100,
        total_5=total_5,
        deductions=deductions,
        pledged_pct=pledged_pct,
        promoter_pct=promoter_pct,
        status=status,
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
    pledged_pct = getattr(money_flow_result, "pledged_pct", None)
    promoter_pct = (
        screener_data.promoter_holding_pct
        if screener_data and screener_data.data_source == "SCREENER_IN"
        else None
    )

    # FII QoQ from ownership_snapshot if available
    ownership = getattr(money_flow_result, "_ownership_snapshot", None)
    fii_qoq = None
    if ownership is not None:
        curr = getattr(ownership, "fii_pct", None)
        prev = getattr(ownership, "prev_fii_pct", None)
        if curr is not None and prev is not None:
            fii_qoq = curr - prev

    # Insider selling: if insider_score < 0, promoters are selling
    promoter_sold = False
    insider_score = getattr(money_flow_result, "insider_score", None)
    if insider_score is not None and insider_score < 0:
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
