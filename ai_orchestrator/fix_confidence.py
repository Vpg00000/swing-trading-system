"""
Fix Confidence Score Calculator — evaluates holistic confidence for proposed AI repairs:

    Confidence Score =
        0.30 * Root Cause Score
      + 0.25 * Test Pass Rate
      + 0.20 * AI Agreement Index
      + 0.15 * Fix Memory Similarity
      - 0.10 * Downstream Regression Risk

Thresholds:
    >= 95%  → High Confidence (Auto-patch candidate)
    90–94%  → Medium-High Confidence (Human Review Required)
    < 75%   → Low Confidence (Reject / Require Manual Investigation)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FixConfidenceResult:
    score: float           # 0.0 to 1.0
    percentage: float      # 0.0 to 100.0%
    action_recommendation: str  # "AUTO_PATCH" | "HUMAN_REVIEW" | "REJECT"
    breakdown: dict


class FixConfidenceCalculator:

    @staticmethod
    def calculate(
        root_cause_score: float,        # 0.0 to 1.0
        test_pass_rate: float,          # 0.0 to 1.0
        ai_agreement_score: float,      # 0.0 to 1.0
        fix_memory_similarity: float,   # 0.0 to 1.0
        regression_risk_score: float,   # 0.0 (no risk) to 1.0 (high risk)
    ) -> FixConfidenceResult:

        raw_score = (
            0.30 * root_cause_score
            + 0.25 * test_pass_rate
            + 0.20 * ai_agreement_score
            + 0.15 * fix_memory_similarity
            - 0.10 * regression_risk_score
        )

        score = max(0.0, min(1.0, raw_score))
        pct = round(score * 100, 1)

        if pct >= 95.0:
            rec = "AUTO_PATCH"
        elif pct >= 90.0:
            rec = "HUMAN_REVIEW"
        else:
            rec = "REJECT"

        return FixConfidenceResult(
            score=score,
            percentage=pct,
            action_recommendation=rec,
            breakdown={
                "root_cause_score": round(root_cause_score, 2),
                "test_pass_rate": round(test_pass_rate, 2),
                "ai_agreement_score": round(ai_agreement_score, 2),
                "fix_memory_similarity": round(fix_memory_similarity, 2),
                "regression_risk_score": round(regression_risk_score, 2),
            },
        )
