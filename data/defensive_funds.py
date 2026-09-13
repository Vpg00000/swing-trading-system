"""
Liquid / Overnight / Arbitrage fund selection -- the Phase 2 "cash-equivalent
parking" and "tax-efficient cash parking" sleeves (see DESIGN.md).

AMFI's NAVAll.txt has no expense-ratio or AUM field, so fund quality here is
judged the only way the free daily NAV file allows: trailing NAV return
over a lookback window, which for these near-zero-volatility categories is
dominated by expense ratio and yield -- a reasonable free-data proxy for
"which fund is actually compounding fastest net of costs" without needing a
paid data source.

Uses AMFI's historical-NAV report endpoint (DownloadNAVHistoryReport_Po.aspx)
to pull a past date for the trailing-return comparison, in addition to the
live NAVAll.txt for the current date (data/amfi.py).
"""

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.amfi import fetch_and_parse, filter_direct_growth, get_sleeve_candidates, FundRecord

HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
LOOKBACK_DAYS = 30


@dataclass
class FundReturn:
    scheme_name: str
    isin: str
    nav_now: float
    nav_past: float
    trailing_return_pct: float
    sleeve: str


def _fetch_historical_navs(as_of: datetime) -> dict[str, float]:
    """
    Returns {isin: nav} for the most recent trading day at or before as_of,
    using AMFI's history endpoint. Most funds don't publish a NAV on
    weekends/market holidays, so we request a window ending at as_of and,
    per ISIN, keep whichever date in that window is closest to (but not
    after) the target -- this is what "trailing N-day return as of the
    nearest trading day" means in practice.
    """
    date_str = as_of.strftime("%d-%b-%Y")
    range_start = (as_of - timedelta(days=7)).strftime("%d-%b-%Y")
    resp = requests.get(HISTORY_URL, params={"frmdt": range_start, "todt": date_str}, timeout=30)
    resp.raise_for_status()

    isin_to_nav: dict[str, float] = {}
    isin_to_date: dict[str, datetime] = {}
    for line in resp.text.splitlines():
        line = line.strip()
        if ";" not in line or line.startswith("Scheme Code"):
            continue
        parts = line.split(";")
        if len(parts) < 8:
            continue
        # Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;NAV;Date
        try:
            row_date = datetime.strptime(parts[7].strip(), "%d-%b-%Y")
        except ValueError:
            continue
        if row_date > as_of:
            continue
        isin_payout = parts[4].strip()
        isin_reinvest = parts[5].strip()
        isin = isin_payout if isin_payout not in ("", "-") else isin_reinvest
        if isin in ("", "-"):
            continue
        try:
            nav = float(parts[6])
        except ValueError:
            continue
        if isin not in isin_to_date or row_date > isin_to_date[isin]:
            isin_to_date[isin] = row_date
            isin_to_nav[isin] = nav
    return isin_to_nav


def rank_defensive_funds(sleeve: str, lookback_days: int = LOOKBACK_DAYS) -> list[FundReturn]:
    """
    Rank Direct-Plan/Growth funds in a defensive sleeve (liquid_fund,
    overnight_fund, arbitrage_fund) by trailing NAV return, highest first.
    """
    current_records = fetch_and_parse()
    candidates = get_sleeve_candidates(current_records, sleeve)
    current_by_isin = {r.isin: r for r in candidates if r.isin}

    past_date = datetime.now() - timedelta(days=lookback_days)
    past_navs = _fetch_historical_navs(past_date)

    results = []
    for isin, r in current_by_isin.items():
        if isin not in past_navs or past_navs[isin] <= 0:
            continue
        ret_pct = (r.nav / past_navs[isin] - 1) * 100
        results.append(FundReturn(
            scheme_name=r.scheme_name,
            isin=isin,
            nav_now=r.nav,
            nav_past=past_navs[isin],
            trailing_return_pct=round(ret_pct, 3),
            sleeve=sleeve,
        ))

    results.sort(key=lambda f: f.trailing_return_pct, reverse=True)
    return results


if __name__ == "__main__":
    for sleeve in ["liquid_fund", "overnight_fund", "arbitrage_fund"]:
        print(f"\n-- Top 5 {sleeve} by {LOOKBACK_DAYS}-day trailing return --")
        ranked = rank_defensive_funds(sleeve)
        for f in ranked[:5]:
            print(f"  {f.scheme_name:<50} {f.trailing_return_pct:+.3f}% "
                  f"(NAV {f.nav_past:.4f} -> {f.nav_now:.4f})")
