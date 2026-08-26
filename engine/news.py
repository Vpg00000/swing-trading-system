"""
Tiered news/event research layer.

This module is intentionally NOT a pure script -- confirming whether news is
material, whether it's already priced in, and how comparable past events
played out requires judgment (an LLM reading and reasoning), not just an
API call. This file defines the structure/tiers and a price+volume
confirmation check; the actual news reading/summarizing step is meant to be
run by an AI assistant (e.g. Claude, via web search) each morning, using the
`build_news_prompt()` output below as its brief, then feeding results back
via `EventFlag` objects.

See DESIGN.md "Event-driven satellite" and "News/research layer" sections.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached

# Source tiers, per DESIGN.md -- Tier 3 must never independently trigger a
# flagged candidate; it can only add color to a Tier 1/2-confirmed event.
TIER_1_SOURCES = ["NSE announcements", "BSE announcements", "company exchange filings",
                   "RBI", "SEBI", "Government of India / ministry releases"]
TIER_2_SOURCES = ["Reuters", "Bloomberg", "Economic Times", "Mint", "Business Standard"]
TIER_3_SOURCES = ["social media", "forums", "unverified analyst notes"]

EVENT_CONFIRM_MIN_PRICE_MOVE_PCT = 3.0
EVENT_CONFIRM_MIN_VOLUME_MULTIPLE = 1.5
VOLUME_LOOKBACK_DAYS = 20


@dataclass
class EventFlag:
    symbol: str
    headline: str
    source_tier: int  # 1, 2, or 3
    event_date: str
    reported_price_move_pct: float | None = None
    confirmed: bool = False
    priced_in_assessment: str = ""  # e.g. "Reaction (+4.5%) already close to
                                     # historical median (+5%) for this event
                                     # type -- residual edge likely small."
    still_actionable: bool = False
    notes: str = ""


def check_price_volume_confirmation(symbol: str) -> dict:
    """
    Mechanical part of event confirmation: does yesterday's price/volume
    action actually meet the bar (>=3% move on >=1.5x avg volume)?
    This does NOT know *why* the stock moved -- pair with an actual news
    read (Tier 1/2 source) before treating a hit here as a real event.
    """
    df = load_cached(symbol)
    if df.empty or len(df) < VOLUME_LOOKBACK_DAYS + 1:
        return {"symbol": symbol, "confirmed": False, "reason": "insufficient data"}

    last_close = df["Close"].iloc[-1]
    prev_close = df["Close"].iloc[-2]
    move_pct = (last_close / prev_close - 1) * 100

    avg_volume = df["Volume"].iloc[-(VOLUME_LOOKBACK_DAYS + 1):-1].mean()
    last_volume = df["Volume"].iloc[-1]
    volume_multiple = last_volume / avg_volume if avg_volume > 0 else 0

    confirmed = (
        abs(move_pct) >= EVENT_CONFIRM_MIN_PRICE_MOVE_PCT
        and volume_multiple >= EVENT_CONFIRM_MIN_VOLUME_MULTIPLE
    )

    return {
        "symbol": symbol,
        "move_pct": round(move_pct, 2),
        "volume_multiple": round(volume_multiple, 2),
        "confirmed": confirmed,
        "direction": "up" if move_pct > 0 else "down",
    }


def scan_for_price_volume_events(symbols: list[str]) -> list[dict]:
    """Run the mechanical confirmation check across a symbol list."""
    results = []
    for sym in symbols:
        r = check_price_volume_confirmation(sym)
        if r.get("confirmed"):
            results.append(r)
    return results


def build_news_prompt(symbols_with_moves: list[dict]) -> str:
    """
    Produces the brief an AI assistant should use each morning to actually
    research and judge the news behind flagged price/volume moves. This is
    NOT executed here -- it's meant to be handed to Claude (or run via
    WebSearch/WebFetch tools) as the next manual/scheduled step.
    """
    lines = [
        "Research the news/event behind each of these confirmed price+volume",
        "moves (>=3% move on >=1.5x average volume) from yesterday's session.",
        "",
        "For each stock:",
        "1. What happened? (search NSE/BSE filings, Tier-1 sources first)",
        "2. Economic significance -- is this a real fundamental change or noise?",
        "3. How does the current price reaction compare to the historical median",
        "   reaction for comparable past events on this stock/sector? Has the",
        "   move already priced in most of the expected effect?",
        "4. Is this still actionable at the current price, or has the edge",
        "   already been captured by the initial move?",
        "5. Classify source: Tier 1 (official filing/regulator), Tier 2",
        "   (Reuters/Bloomberg/quality media), or Tier 3 (social/forum) --",
        "   Tier 3 alone must NOT be treated as confirmation.",
        "",
        "Stocks with confirmed price+volume moves:",
    ]
    for r in symbols_with_moves:
        lines.append(
            f"  - {r['symbol']}: {r['move_pct']:+.1f}% on {r['volume_multiple']:.1f}x "
            f"avg volume ({r['direction']})"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config.universe import EQUITY_UNIVERSE

    print("Scanning cached universe for price+volume confirmed moves...")
    hits = scan_for_price_volume_events(EQUITY_UNIVERSE)
    print(f"\n{len(hits)} symbols show a confirmed >=3% move on >=1.5x volume:\n")
    for r in hits:
        print(f"  {r['symbol']:<16} {r['move_pct']:+6.1f}%  vol {r['volume_multiple']:.1f}x  ({r['direction']})")

    if hits:
        print("\n--- Next step: hand this prompt to an AI research pass ---\n")
        print(build_news_prompt(hits))
    else:
        print("\nNo qualifying moves in the current cached data.")
