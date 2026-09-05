"""
Quantitative priced-in check -- per DESIGN.md's "Priced-in check on every
positive/negative event: compare current price reaction to historical
comparable-event reaction before treating it as still-actionable."

engine/news.py's `check_price_volume_confirmation()` answers "did something
happen?" (mechanical >=3% move on >=1.5x volume). This module answers the
next question quantitatively, using only our own cached price history (no
new data source) -- "how does today's reaction compare to how this stock
has behaved after similar-sized moves in the past year, and did most of the
follow-through already happen historically by now?"

Method: find all past daily moves of >=3% in the same direction as today's
event, then look at what this stock typically did over the following 1/3/5
trading days after such a move (median forward drift). If today's move is
already much larger than that typical continuation, the edge implied by
history is smaller than what's already captured (LIKELY_PRICED_IN). If
today's move is well below that typical continuation, history suggests more
room to run (POTENTIALLY_UNDERPRICED). This is a base-rate sanity check on
the stock's own history, not a prediction -- it does not know *why* either
the historical or current move happened; pair with an actual news read
(engine/news.py's build_news_prompt) before acting.
"""

import sys
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached
from data.sync_engine import get_current_market_data
from engine.valuation import get_current_valuation_metrics
from data.database import get_historical_comparable_events

COMPARABLE_MOVE_MIN_PCT = 3.0  # same threshold as engine/news.py's event confirmation
MIN_COMPARABLE_EVENTS = 3      # below this, the median isn't a meaningful base rate
FORWARD_DRIFT_DAYS = 5
PRICED_IN_RATIO = 1.5          # current >= 1.5x historical median -> already priced in
UNDERPRICED_RATIO = 0.7        # current <= 0.7x historical median -> room to run

@dataclass
class PricedInResult:
    symbol: str
    current_move_pct: float
    historical_median_pct: float
    comparable_events_count: int
    status: str        # "UNDERPRICED" / "PARTIALLY_PRICED" / "FULLY_PRICED" / "OVERPRICED" / "UNKNOWN"
    confidence: float   # 0.0-1.0, scales with comparable_events_count
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    corporate_event_impact: Optional[float] = None
    institutional_flow: Optional[float] = None

@dataclass
class PricedInInput:
    symbol: str
    current_price_move: float
    direction: str
    expectations: Dict[str, float]
    valuation: Dict[str, float]
    comparable_events_data: List[Dict[str, float]]
    ai_research_output: Dict[str, float]

def _forward_drift_pct(closes: List[float], pos: int, sign: int) -> Optional[float]:
    """% move from day `pos` to `pos + FORWARD_DRIFT_DAYS`, signed to match direction."""
    end = pos + FORWARD_DRIFT_DAYS
    if end >= len(closes):
        return None
    return (closes[end] / closes[pos] - 1) * 100 * sign

def _compare_price_vs_expected(price_move: float, expected_impact: float) -> float:
    """Compare price move against expected impact."""
    if expected_impact == 0:
        return 0.0
    return price_move / expected_impact

def _compare_valuation(valuation: Dict[str, float], comparable_events_data: List[Dict[str, float]]) -> float:
    """Compare valuation metrics against historical averages and sector peers."""
    if not comparable_events_data:
        return 0.0

    # Calculate historical averages
    historical_avg_pe = sum(event.get("pe_ratio", 0) for event in comparable_events_data) / len(comparable_events_data)
    historical_avg_pb = sum(event.get("pb_ratio", 0) for event in comparable_events_data) / len(comparable_events_data)
    historical_avg_ev_ebitda = sum(event.get("ev_ebitda", 0) for event in comparable_events_data) / len(comparable_events_data)

    # Normalize current valuation to historical averages
    normalized_pe = valuation.get("pe_ratio", 0) / historical_avg_pe if historical_avg_pe > 0 else 0
    normalized_pb = valuation.get("pb_ratio", 0) / historical_avg_pb if historical_avg_pb > 0 else 0
    normalized_ev_ebitda = valuation.get("ev_ebitda", 0) / historical_avg_ev_ebitda if historical_avg_ev_ebitda > 0 else 0

    # Combine normalized metrics into a single score
    return (normalized_pe + normalized_pb + normalized_ev_ebitda) / 3

def _analyze_comparable_events(current_event: Dict[str, float], comparable_events_data: List[Dict[str, float]]) -> float:
    """Analyze current event against historical comparable events."""
    if not comparable_events_data:
        return 0.0

    # Calculate average price reaction for comparable events
    avg_price_reaction = sum(event.get("price_move", 0) for event in comparable_events_data) / len(comparable_events_data)

    # Compare current event's price reaction to average
    if avg_price_reaction == 0:
        return 0.0
    return current_event.get("price_move", 0) / avg_price_reaction

def _integrate_ai_research(ai_research_output: Dict[str, float]) -> float:
    """Integrate AI research output into the analysis."""
    # Extract qualitative insights from AI research
    fundamental_significance = ai_research_output.get("fundamental_significance", 0)
    earnings_impact = ai_research_output.get("earnings_impact", 0)
    sector_impact = ai_research_output.get("sector_impact", 0)
    bull_bear_case = ai_research_output.get("bull_bear_case", 0)

    # Combine qualitative insights into a single score
    return (fundamental_significance + earnings_impact + sector_impact + bull_bear_case) / 4

def classify_priced_in_state(
    price: float,
    expectations: Dict[str, float],
    valuation: Dict[str, float],
    comparable_events_data: List[Dict[str, float]],
    ai_research_output: Dict[str, float]
) -> Dict[str, Union[Dict[str, Union[str, float, int]], Dict[str, Union[str, float]]]]:
    """Classify the priced-in state based on various factors."""
    # Extract relevant data from inputs
    price_move = price.get("move_pct", 0.0)
    expected_impact = expectations.get("expected_impact", 0.0)
    current_event = {
        "price_move": price_move,
        "pe_ratio": valuation.get("pe_ratio"),
        "pb_ratio": valuation.get("pb_ratio"),
        "ev_ebitda": valuation.get("ev_ebitda")
    }

    # Perform core comparisons
    price_vs_expected = _compare_price_vs_expected(price_move, expected_impact)
    valuation_comparison = _compare_valuation(valuation, comparable_events_data)
    comparable_event_analysis = _analyze_comparable_events(current_event, comparable_events_data)
    ai_research_integration = _integrate_ai_research(ai_research_output)

    # Combine results into a single score
    combined_score = (
        price_vs_expected * 0.4 +
        valuation_comparison * 0.3 +
        comparable_event_analysis * 0.2 +
        ai_research_integration * 0.1
    )

    # Classify based on combined score
    if combined_score >= 1.5:
        status = "FULLY_PRICED"
    elif combined_score >= 1.2:
        status = "PARTIALLY_PRICED"
    elif combined_score <= 0.8:
        status = "UNDERPRICED"
    elif combined_score <= 0.5:
        status = "OVERPRICED"
    else:
        status = "UNKNOWN"

    # Prepare evidence and inference
    evidence = {
        "price_move": price_move,
        "expected_impact": expected_impact,
        "valuation": valuation,
        "comparable_events_data": comparable_events_data,
        "ai_research_output": ai_research_output
    }

    inference = {
        "status": status,
        "confidence": min(1.0, combined_score),
        "rationale": f"Combined score: {combined_score:.2f}"
    }

    return {"evidence": evidence, "inference": inference}

def analyze_priced_in(symbol: str, current_move_pct: float = 0.0, direction: str = "up",
                     consensus: Optional[float] = None, earnings: Optional[float] = None,
                     valuation_range: Optional[Tuple[float, float]] = None,
                     comparable_events: Optional[List[Dict[str, float]]] = None,
                     pe_ratio: Optional[float] = None, pb_ratio: Optional[float] = None,
                     ev_ebitda: Optional[float] = None, corporate_event_impact: Optional[float] = None,
                     institutional_flow: Optional[float] = None) -> Dict[str, Union[Dict[str, Union[str, float, int]], Dict[str, Union[str, float]]]]:
    if not symbol:
        return {"evidence": {"symbol": "", "current_move_pct": current_move_pct or 0.0, "historical_median_pct": 0.0, "comparable_events_count": 0,
                             "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "ev_ebitda": ev_ebitda,
                             "corporate_event_impact": corporate_event_impact, "institutional_flow": institutional_flow},
                "inference": {"status": "UNKNOWN", "confidence": 0.0, "rationale": "No symbol provided"}}

    sign = 1 if direction == "up" else -1
    df = load_cached(symbol)

    if df is None or df.empty:
        return {"evidence": {"symbol": symbol, "current_move_pct": current_move_pct or 0.0, "historical_median_pct": 0.0, "comparable_events_count": 0,
                             "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "ev_ebitda": ev_ebitda,
                             "corporate_event_impact": corporate_event_impact, "institutional_flow": institutional_flow},
                "inference": {"status": "UNKNOWN", "confidence": 0.0, "rationale": "Insufficient data"}}

    if "Close" in df.columns:
        df = df.dropna(subset=["Close"])

    if len(df) < 30:
        return {"evidence": {"symbol": symbol, "current_move_pct": current_move_pct, "historical_median_pct": 0.0, "comparable_events_count": 0,
                             "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "ev_ebitda": ev_ebitda,
                             "corporate_event_impact": corporate_event_impact, "institutional_flow": institutional_flow},
                "inference": {"status": "UNKNOWN", "confidence": 0.0, "rationale": "Insufficient data"}}

    closes = df["Close"].tolist()
    daily_returns_pct = [
        (closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes))
    ]

    drifts = []
    for i, ret in enumerate(daily_returns_pct):
        if ret * sign >= COMPARABLE_MOVE_MIN_PCT:
            pos = i + 1  # daily_returns_pct[i] is the move *into* closes[i+1]
            drift = _forward_drift_pct(closes, pos, sign)
            if drift is not None:
                drifts.append(drift)

    if len(drifts) < MIN_COMPARABLE_EVENTS:
        return {"evidence": {"symbol": symbol, "current_move_pct": current_move_pct, "historical_median_pct": 0.0, "comparable_events_count": len(drifts),
                             "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "ev_ebitda": ev_ebitda,
                             "corporate_event_impact": corporate_event_impact, "institutional_flow": institutional_flow},
                "inference": {"status": "UNKNOWN", "confidence": 0.0, "rationale": "Insufficient comparable events"}}

    median_drift = statistics.median(drifts)
    current_abs = abs(current_move_pct)
    median_abs = abs(median_drift)

    if median_abs == 0:
        status = "UNKNOWN"
        rationale = "Median drift is zero"
    elif current_abs >= PRICED_IN_RATIO * median_abs:
        status = "FULLY_PRICED"
        rationale = "Current move is significantly larger than historical median"
    elif current_abs <= UNDERPRICED_RATIO * median_abs:
        status = "UNDERPRICED"
        rationale = "Current move is significantly smaller than historical median"
    else:
        status = "PARTIALLY_PRICED"
        rationale = "Current move is within the range of historical median"

    confidence = min(1.0, len(drifts) / 10)

    # Incorporate additional factors into the analysis
    if pe_ratio is not None and pb_ratio is not None and ev_ebitda is not None:
        # Normalize valuation ratios to a common scale (e.g., 0-1)
        normalized_pe = 1 / (1 + pe_ratio) if pe_ratio > 0 else 0
        normalized_pb = 1 / (1 + pb_ratio) if pb_ratio > 0 else 0
        normalized_ev_ebitda = 1 / (1 + ev_ebitda) if ev_ebitda > 0 else 0

        # Combine valuation ratios into a single score
        valuation_score = (normalized_pe + normalized_pb + normalized_ev_ebitda) / 3

        # Adjust confidence based on valuation score
        confidence = confidence * (0.5 + 0.5 * valuation_score)

    if corporate_event_impact is not None:
        # Adjust confidence based on corporate event impact
        confidence = confidence * (1 - corporate_event_impact)

    if institutional_flow is not None:
        # Adjust confidence based on institutional flow
        confidence = confidence * (1 + institutional_flow)

    return {"evidence": {"symbol": symbol, "current_move_pct": current_move_pct, "historical_median_pct": round(median_drift, 2), "comparable_events_count": len(drifts),
                         "pe_ratio": pe_ratio, "pb_ratio": pb_ratio, "ev_ebitda": ev_ebitda,
                         "corporate_event_impact": corporate_event_impact, "institutional_flow": institutional_flow},
            "inference": {"status": status, "confidence": round(confidence, 2), "rationale": rationale}}

def assess_priced_in(symbol: str, current_move_pct: float = 0.0, direction: str = "up",
                     consensus: Optional[float] = None, earnings: Optional[float] = None,
                     valuation_range: Optional[Tuple[float, float]] = None,
                     comparable_events: Optional[List[Dict[str, float]]] = None,
                     pe_ratio: Optional[float] = None, pb_ratio: Optional[float] = None,
                     ev_ebitda: Optional[float] = None, corporate_event_impact: Optional[float] = None,
                     institutional_flow: Optional[float] = None) -> PricedInResult:
    res = analyze_priced_in(symbol, current_move_pct, direction, consensus, earnings, valuation_range, comparable_events,
                            pe_ratio, pb_ratio, ev_ebitda, corporate_event_impact, institutional_flow)
    ev = res.get("evidence", {})
    inf = res.get("inference", {})
    return PricedInResult(
        symbol=ev.get("symbol", symbol or ""),
        current_move_pct=ev.get("current_move_pct", current_move_pct),
        historical_median_pct=ev.get("historical_median_pct", 0.0),
        comparable_events_count=ev.get("comparable_events_count", 0),
        status=inf.get("status", "UNKNOWN"),
        confidence=inf.get("confidence", 0.0),
        pe_ratio=ev.get("pe_ratio"),
        pb_ratio=ev.get("pb_ratio"),
        ev_ebitda=ev.get("ev_ebitda"),
        corporate_event_impact=ev.get("corporate_event_impact"),
        institutional_flow=ev.get("institutional_flow")
    )

class PricedInAnalysis:
    @staticmethod
    def analyze_opportunity(security_id: str, event_id: str, ai_research_output: Dict[str, float]) -> PricedInResult:
        """Analyze the priced-in status of an opportunity."""
        # Fetch current market data
        current_market_data = get_current_market_data(security_id)

        # Fetch current valuation metrics
        current_valuation_metrics = get_current_valuation_metrics(security_id)

        # Retrieve historical comparable events data
        comparable_events_data = get_historical_comparable_events(
            security_id,
            ai_research_output.get("comparable_event_context", {}),
            ai_research_output.get("suggested_comparable_event_ids", [])
        )

        # Classify the priced-in state
        priced_in_state = classify_priced_in_state(
            current_market_data,
            ai_research_output.get("expected_impact", {}),
            current_valuation_metrics,
            comparable_events_data,
            ai_research_output
        )

        # Create and return the PricedInResult
        return PricedInResult(
            symbol=security_id,
            current_move_pct=current_market_data.get("move_pct", 0.0),
            historical_median_pct=0.0,  # Placeholder for historical median percentage
            comparable_events_count=len(comparable_events_data),
            status=priced_in_state.get("inference", {}).get("status", "UNKNOWN"),
            confidence=priced_in_state.get("inference", {}).get("confidence", 0.0),
            pe_ratio=current_valuation_metrics.get("pe_ratio"),
            pb_ratio=current_valuation_metrics.get("pb_ratio"),
            ev_ebitda=current_valuation_metrics.get("ev_ebitda"),
            corporate_event_impact=ai_research_output.get("corporate_event_impact"),
            institutional_flow=ai_research_output.get("institutional_flow")
        )

classify_priced_in = analyze_priced_in
priced_in_analysis = analyze_priced_in

if __name__ == "__main__":
    from engine.news import scan_for_price_volume_events
    from config.universe import EQUITY_UNIVERSE

    print("Scanning cached universe for price+volume confirmed moves, then")
    print("assessing each against its own historical comparable-event drift...\n")
    hits = scan_for_price_volume_events(EQUITY_UNIVERSE)
    if not hits:
        print("No qualifying moves in the current cached data.")
    for h in hits:
        result = analyze_priced_in(h["symbol"], h["move_pct"], h["direction"])
        print(f"  {result['evidence']['symbol']:<16} move {result['evidence']['current_move_pct']:+6.1f}%  "
              f"hist. median 5D-fwd drift {result['evidence']['historical_median_pct']:+6.1f}% "
              f"(n={result['evidence']['comparable_events_count']}, conf={result['inference']['confidence']:.2f})  "
              f"-- {result['inference']['status']}")