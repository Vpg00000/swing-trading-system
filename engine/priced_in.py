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
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached

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
    status: str        # "LIKELY_PRICED_IN" / "PARTIALLY_PRICED_IN" / "POTENTIALLY_UNDERPRICED" / "INSUFFICIENT_DATA"
    confidence: float   # 0.0-1.0, scales with comparable_events_count


def _forward_drift_pct(closes, pos: int, sign: int) -> float | None:
    """% move from day `pos` to `pos + FORWARD_DRIFT_DAYS`, signed to match direction."""
    end = pos + FORWARD_DRIFT_DAYS
    if end >= len(closes):
        return None
    return (closes[end] / closes[pos] - 1) * 100 * sign


def assess_priced_in(symbol: str, current_move_pct: float, direction: str) -> PricedInResult:
    sign = 1 if direction == "up" else -1
    df = load_cached(symbol)

    if df.empty or len(df) < 30:
        return PricedInResult(symbol, current_move_pct, 0.0, 0, "INSUFFICIENT_DATA", 0.0)

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
        return PricedInResult(symbol, current_move_pct, 0.0, len(drifts),
                               "INSUFFICIENT_DATA", 0.0)

    median_drift = statistics.median(drifts)
    current_abs = abs(current_move_pct)
    median_abs = abs(median_drift)

    if median_abs == 0:
        status = "INSUFFICIENT_DATA"
    elif current_abs >= PRICED_IN_RATIO * median_abs:
        status = "LIKELY_PRICED_IN"
    elif current_abs <= UNDERPRICED_RATIO * median_abs:
        status = "POTENTIALLY_UNDERPRICED"
    else:
        status = "PARTIALLY_PRICED_IN"

    confidence = min(1.0, len(drifts) / 10)

    return PricedInResult(symbol, current_move_pct, round(median_drift, 2),
                           len(drifts), status, round(confidence, 2))


if __name__ == "__main__":
    from engine.news import scan_for_price_volume_events
    from config.universe import EQUITY_UNIVERSE

    print("Scanning cached universe for price+volume confirmed moves, then")
    print("assessing each against its own historical comparable-event drift...\n")
    hits = scan_for_price_volume_events(EQUITY_UNIVERSE)
    if not hits:
        print("No qualifying moves in the current cached data.")
    for h in hits:
        result = assess_priced_in(h["symbol"], h["move_pct"], h["direction"])
        print(f"  {result.symbol:<16} move {result.current_move_pct:+6.1f}%  "
              f"hist. median 5D-fwd drift {result.historical_median_pct:+6.1f}% "
              f"(n={result.comparable_events_count}, conf={result.confidence:.2f})  "
              f"-- {result.status}")
