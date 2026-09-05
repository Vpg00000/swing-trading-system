import os
from typing import Dict, Optional
from pydantic import BaseModel, ValidationError
from engine.priced_in import priced_in_analysis

class ExpectedImpact(BaseModel):
    magnitude: float
    direction: str
    timeframe: str
    confidence: float

class AIArticle(BaseModel):
    what_happened: str
    why_now: str
    source_credibility: str
    fundamental_significance: str
    input_evidence: Dict[str, str]
    expected_impact: Optional[ExpectedImpact] = None
    comparable_event_context: Optional[Dict] = None
    suggested_comparable_event_ids: Optional[list] = None
    priced_in_state: Optional[Dict] = None

ResearchOutputSchema = AIArticle

def calculate_dynamic_weights(regime_status: str, priced_in_data: Optional[Dict] = None) -> Dict:
    if not regime_status or regime_status.upper() not in ["BULL", "BEAR", "NEUTRAL", "SIDEWAYS"]:
        raise ValueError(f"Invalid regime status: {regime_status}")

    bull_weight = float(os.getenv('DANH_BULL_WEIGHT', '0.35'))
    bear_weight = float(os.getenv('DANH_BEAR_WEIGHT', '0.40'))
    if priced_in_data is None:
        priced_in_data = priced_in_analysis(None, None, None, None)
    if "BULL" in regime_status.upper():
        article = {
            "what_happened": "Bull market conditions identified",
            "why_now": "High momentum and positive trends",
            "source_credibility": "Historical data and expert opinions",
            "fundamental_significance": "Strong economic indicators",
            "input_evidence": {},
            "priced_in_state": priced_in_data
        }
    elif "BEAR" in regime_status.upper():
        article = {
            "what_happened": "Bear market conditions identified",
            "why_now": "Weak momentum and negative trends",
            "source_credibility": "Historical data and expert opinions",
            "fundamental_significance": "Weak economic indicators",
            "input_evidence": {},
            "priced_in_state": priced_in_data
        }
    else:
        article = {
            "what_happened": "Neutral market conditions identified",
            "why_now": "Balanced momentum and trends",
            "source_credibility": "Historical data and expert opinions",
            "fundamental_significance": "Mixed economic indicators",
            "input_evidence": {},
            "priced_in_state": priced_in_data
        }
    # Validate with Pydantic model
    validated = AIArticle(**article)
    return article