"""
AMFI mutual fund NAV data fetch + category classification.

Source: portal.amfiindia.com/spages/NAVAll.txt -- the official, free, daily
NAV file covering every registered Indian mutual fund scheme. This is the
authoritative source (not a scraped/guessed list).

Categories relevant to the Phase 2 defensive/passive sleeve (see DESIGN.md):
  - index funds / equity ETFs   -> passive equity beta, low cost
  - Gold ETF / Silver ETF       -> commodity hedge
  - Liquid Fund / Overnight Fund -> true cash-equivalent parking
  - Arbitrage Fund              -> tax-efficient (equity-taxed) cash parking
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
NAV_HISTORY_DIR = Path(__file__).resolve().parent / "nav_history"
NAV_HISTORY_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# Category keywords -> our internal sleeve label, checked in order against
# the "Open Ended Schemes(...)" header lines in the AMFI file. Order matters:
# more specific patterns must come before generic ones. Note "Index Funds -
# Debt Funds" / "Index Funds - Hybrid Fund" / "Other Scheme - Index Funds"
# (the latter holds Gilt/SDL debt-index funds per AMFI's own file) are
# deliberately NOT matched into index_fund -- only the equity index category
# belongs in the passive-equity-beta sleeve described in DESIGN.md.
CATEGORY_MAP = [
    ("Gold ETF", "gold_etf"),
    ("Silver ETF", "silver_etf"),
    ("Equity ETF", "equity_etf"),
    ("Liquid Fund", "liquid_fund"),
    ("Overnight Fund", "overnight_fund"),
    ("Arbitrage Fund", "arbitrage_fund"),
    ("Index Funds - Equity", "index_fund"),
]

# AMFI's own category headers are unreliable for ETFs -- e.g. "Aditya Birla
# Sun Life Gold ETF" is filed under the "Equity ETF" header, not "Gold ETF".
# So gold/silver identification always happens by scheme *name* first,
# checked before any header-based classification, regardless of bucket.
GOLD_SILVER_NAME_MAP = [
    ("gold etf", "gold_etf"),
    ("gold exchange traded", "gold_etf"),
    ("silver etf", "silver_etf"),
    ("silver exchange traded", "silver_etf"),
]

# AMFI also dumps most well-known exchange-listed equity ETFs (NIFTYBEES,
# BANKBEES etc.) into a single messy legacy bucket -- "Other Scheme - Other
# ETFs" -- alongside debt/gilt/liquid-rate ETFs that don't belong in any of
# our sleeves. Within that bucket only, classify remaining (non-gold/silver)
# rows by name: debt/gilt/liquid-rate patterns are checked first so they
# fall through to "other" rather than being misclassified as equity_etf.
OTHER_ETF_BUCKET_HEADER = "other scheme - other  etfs"
OTHER_ETF_NAME_MAP = [
    ("gilt etf", "other"),
    ("liquid etf", "other"),
    ("1d rate", "other"),
    ("nifty", "equity_etf"),
    ("sensex", "equity_etf"),
    ("bse ", "equity_etf"),
]


@dataclass
class FundRecord:
    scheme_code: str
    isin: str
    scheme_name: str
    plan: str
    option: str
    nav: float
    date: str
    category_header: str
    sleeve: str


def _classify(category_header: str, scheme_name: str) -> str:
    name_lower = scheme_name.lower()
    for keyword, sleeve in GOLD_SILVER_NAME_MAP:
        if keyword in name_lower:
            return sleeve

    header_lower = category_header.lower()
    if OTHER_ETF_BUCKET_HEADER in header_lower:
        for keyword, sleeve in OTHER_ETF_NAME_MAP:
            if keyword in name_lower:
                return sleeve
        return "other"
    for keyword, sleeve in CATEGORY_MAP:
        if keyword.lower() in header_lower:
            return sleeve
    return "other"


def fetch_and_parse() -> list[FundRecord]:
    resp = requests.get(AMFI_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text

    raw_path = CACHE_DIR / "amfi_navall_raw.txt"
    raw_path.write_text(text)

    records = []
    current_category = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("Open Ended Schemes(") or line.startswith("Close Ended Schemes(") \
                or line.startswith("Interval Fund Schemes("):
            current_category = line
            continue
        if line.startswith("Scheme Code"):
            continue  # header row
        if ";" not in line:
            continue  # AMC name line, no delimiter

        parts = line.split(";")
        if len(parts) < 8:
            continue
        scheme_code, isin_payout, isin_growth, scheme_name, plan, option, nav_str, date_str = parts[:8]
        try:
            nav = float(nav_str)
        except ValueError:
            continue  # NAV not available for this row

        isin_payout = isin_payout.strip()
        isin_growth = isin_growth.strip()
        isin = isin_payout if isin_payout not in ("", "-") else isin_growth

        records.append(FundRecord(
            scheme_code=scheme_code.strip(),
            isin=isin if isin not in ("", "-") else "",
            scheme_name=scheme_name.strip(),
            plan=plan.strip(),
            option=option.strip(),
            nav=nav,
            date=date_str.strip(),
            category_header=current_category,
            sleeve=_classify(current_category, scheme_name),
        ))
    return records


def save_daily_snapshot(records: list[FundRecord]) -> Path:
    """Append today's NAVs to a running history file, one row per scheme_code."""
    df = pd.DataFrame([r.__dict__ for r in records])
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = NAV_HISTORY_DIR / f"navall_{today}.csv"
    df.to_csv(out_path, index=False)
    return out_path


ETF_SLEEVES = {"gold_etf", "silver_etf", "equity_etf"}


def filter_direct_growth(records: list[FundRecord]) -> list[FundRecord]:
    """
    Keep only Direct Plan / Growth option rows -- lowest cost (no distributor
    commission) and NAV reflects total return without dividend distortion.
    This is the correct default for a systematic momentum/ranking approach.

    Exchange-traded funds (gold/silver/equity ETF sleeves) are exempt from
    this Direct/Growth check: they trade as a single listed unit on the
    exchange with no distributor-plan split, so AMFI lists plan/option as
    blank for most of them -- that's not a data gap, it's just how ETFs work.
    """
    out = []
    for r in records:
        if r.sleeve in ETF_SLEEVES:
            out.append(r)
            continue
        if "direct" not in r.plan.lower():
            continue
        if "growth" not in r.option.lower() and "bonus" not in r.option.lower():
            continue
        out.append(r)
    return out


def get_sleeve_candidates(records: list[FundRecord], sleeve: str) -> list[FundRecord]:
    return [r for r in filter_direct_growth(records) if r.sleeve == sleeve]


if __name__ == "__main__":
    print("Fetching AMFI NAV data...")
    records = fetch_and_parse()
    print(f"Parsed {len(records)} fund/plan/option rows.")

    path = save_daily_snapshot(records)
    print(f"Saved daily snapshot to {path}")

    direct_growth = filter_direct_growth(records)
    print(f"\n{len(direct_growth)} Direct-Plan/Growth rows.")

    for sleeve in ["gold_etf", "silver_etf", "equity_etf", "liquid_fund",
                   "overnight_fund", "arbitrage_fund", "index_fund"]:
        candidates = get_sleeve_candidates(records, sleeve)
        print(f"\n-- {sleeve} ({len(candidates)} funds) --")
        for r in candidates[:5]:
            print(f"  {r.scheme_name} | {r.plan} {r.option} | NAV {r.nav} ({r.date})")
