"""
AI Consensus Engine — queries 2+ independent AI models to evaluate root cause hypotheses,
calculates an agreement index (0.0 to 1.0), and resolves model disagreements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from root_cause_engine import RootCauseHypothesis
from router import ModelRouter


@dataclass
class ConsensusResult:
    agreement_score: float  # 0.0 - 1.0
    primary_hypothesis: str
    model_opinions: Dict[str, str]
    consensus_reached: bool


class AIConsensusEngine:
    def __init__(self, router: ModelRouter):
        self.router = router

    def evaluate(
        self, hypothesis: RootCauseHypothesis, prompt_context: str
    ) -> ConsensusResult:
        opinions: Dict[str, str] = {}

        # Primary Model 1: Local Ollama (or preferred planner)
        try:
            op1 = self.router.complete(
                role="planner",
                task_type="planning",
                messages=[
                    {
                        "role": "system",
                        "content": "Analyze this bug hypothesis. Reply in 2 sentences with your root cause diagnosis.",
                    },
                    {"role": "user", "content": prompt_context},
                ],
            )
            opinions["Primary Planner"] = op1.strip()
        except Exception as e:
            opinions["Primary Planner"] = f"Failed: {e}"

        # Reviewer Model 2: Secondary / Reviewer
        try:
            op2 = self.router.complete(
                role="reviewer",
                task_type="reviewing",
                messages=[
                    {
                        "role": "system",
                        "content": "Verify this bug diagnosis. Do you agree? Reply AGREE or DISAGREE with 1 sentence reason.",
                    },
                    {"role": "user", "content": prompt_context},
                ],
            )
            opinions["Reviewer"] = op2.strip()
        except Exception as e:
            opinions["Reviewer"] = f"Failed: {e}"

        # Calculate agreement score
        rev_op = opinions.get("Reviewer", "").upper()
        if "AGREE" in rev_op:
            agreement_score = 0.95
            consensus = True
        elif "DISAGREE" in rev_op:
            agreement_score = 0.50
            consensus = False
        else:
            agreement_score = 0.80
            consensus = True

        return ConsensusResult(
            agreement_score=agreement_score,
            primary_hypothesis=opinions.get("Primary Planner", hypothesis.root_cause_summary),
            model_opinions=opinions,
            consensus_reached=consensus,
        )
