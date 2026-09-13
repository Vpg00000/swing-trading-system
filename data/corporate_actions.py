"""
Corporate action / earnings (board-meeting) calendar -- per DESIGN.md's
morning check-in ("corporate-action/earnings calendar check") and risk
controls ("Weekend/pre-event gap-risk flag: Budget, RBI policy, Fed meeting,
earnings").

Source: NSE's own corporate-filings API (nseindia.com/api/...), queried
market-wide over a forward date window rather than per-symbol -- one request
covers the whole universe instead of one round-trip per stock. No login/
session cookie is required for these two endpoints (confirmed empirically);
if NSE's WAF starts requiring one, the fallback is a GET to nseindia.com
first to harvest cookies into the same requests.Session before calling the
API.

Two endpoints:
  - corporates-corporateActions: dividends, splits, bonus, rights, buybacks
    (ex-date is the gap-risk date -- price mechanically drops).
  - corporate-board-meetings: board meeting intimations, mostly "Financial
    Results" purpose -- NSE's free equivalent of an earnings calendar (this
    is the meeting-intimation date, not always confirmed results date, so
    treat as a heads-up window rather than a guaranteed announcement day).
"""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.nse_client import nse_session, nse_get

DEFAULT_LOOKAHEAD_DAYS = 21  # ~3 weeks forward, covers weekly rebalance + next check-in


@dataclass
class CorporateAction:
    symbol: str
    ex_date: str
    purpose: str  # e.g. "Dividend", "Bonus 1:1", "Stock Split", "Buy Back"


@dataclass
class BoardMeeting:
    symbol: str
    meeting_date: str
    purpose: str  # e.g. "Financial Results"


def fetch_corporate_actions(from_date: datetime, to_date: datetime,
                             session: requests.Session | None = None) -> list[CorporateAction]:
    s = session or nse_session()
    data = nse_get(s, "corporates-corporateActions", {
        "index": "equities",
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }, referer="https://www.nseindia.com/companies-listing/corporate-filings-actions")
    if not isinstance(data, list):
        return []
    return [
        CorporateAction(symbol=r.get("symbol", ""), ex_date=r.get("exDate", ""),
                         purpose=r.get("subject", ""))
        for r in data
    ]


def fetch_board_meetings(from_date: datetime, to_date: datetime,
                          session: requests.Session | None = None) -> list[BoardMeeting]:
    s = session or nse_session()
    data = nse_get(s, "corporate-board-meetings", {
        "index": "equities",
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
    }, referer="https://www.nseindia.com/companies-listing/corporate-filings-board-meetings")
    if not isinstance(data, list):
        return []
    return [
        BoardMeeting(symbol=r.get("bm_symbol", ""), meeting_date=r.get("bm_date", ""),
                     purpose=r.get("bm_purpose", ""))
        for r in data
    ]


def upcoming_events_for_universe(symbols: list[str], lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS
                                  ) -> tuple[list[CorporateAction], list[BoardMeeting]]:
    """
    Fetches the market-wide calendar once, then filters to the given universe
    (bare symbols, no ".NS" suffix -- NSE's own symbol convention) -- one
    round-trip covers any universe size instead of one call per stock.
    """
    symbol_set = {s.replace(".NS", "").upper() for s in symbols}
    today = datetime.now()
    horizon = today + timedelta(days=lookahead_days)

    session = nse_session()
    actions = fetch_corporate_actions(today, horizon, session)
    meetings = fetch_board_meetings(today, horizon, session)

    relevant_actions = [a for a in actions if a.symbol.upper() in symbol_set]
    relevant_meetings = [m for m in meetings if m.symbol.upper() in symbol_set]
    return relevant_actions, relevant_meetings


if __name__ == "__main__":
    from config.universe import EQUITY_UNIVERSE

    print(f"-- Corporate actions / board meetings, next {DEFAULT_LOOKAHEAD_DAYS} days --")
    actions, meetings = upcoming_events_for_universe(EQUITY_UNIVERSE)

    print(f"\n{len(actions)} corporate action(s) (dividend/split/bonus/rights/buyback):")
    for a in actions[:20]:
        print(f"  {a.symbol:<16} {a.ex_date:<12} {a.purpose}")

    print(f"\n{len(meetings)} board meeting(s) (mostly quarterly results):")
    for m in meetings[:20]:
        print(f"  {m.symbol:<16} {m.meeting_date:<12} {m.purpose}")
