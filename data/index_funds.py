"""
Broad-market passive index fund selection -- the passive slice carved out
of the core equity budget (see DESIGN.md "Capital allocation"; the equity
budget itself is regime-sized in engine/regime.py).

AMFI's index_fund sleeve (data/amfi.py) contains ~45 funds tracking dozens
of different benchmarks -- Nifty 50, Nifty Next 50, sector indices
(banking/auto/IT), factor indices (momentum/quality/low-vol), and
market-cap slices (midcap/smallcap). Only the broad Nifty 50 / Nifty 500
funds are a genuine passive substitute for single-stock momentum risk;
sector/thematic/factor index funds are their own concentrated bet and
don't belong in a "reduce single-stock risk" sleeve.

Selection within the broad-market group uses the same trailing-NAV-return
proxy as data/defensive_funds.py: funds tracking the same benchmark should
have near-identical gross returns, so higher trailing return net of that
mostly reflects lower expense ratio / tighter tracking, which is the real
signal AMFI's free NAV file lets us observe.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.amfi import fetch_and_parse, get_sleeve_candidates
from data.defensive_funds import rank_defensive_funds, FundReturn

# Scheme-name substrings that identify a genuinely broad-market passive
# fund. Deliberately excludes "Next 50", "Midcap", "Smallcap", "Equal
# Weight", sector names (Bank/Auto/IT/PSU/Infrastructure/Defence/etc.), and
# factor tilts (Momentum/Quality/Value/Low Volatility/Alpha) -- those are
# concentrated bets, not passive beta.
BROAD_MARKET_NAME_MARKERS = [
    "nifty 50 index",
    "nifty50 index",
    "nifty total market index",
    "nifty 500 index",
    "nifty500 index",
    "sensex index",
]
BROAD_MARKET_EXCLUDE_MARKERS = [
    "next 50", "equal weight", "value 50", "shariah", "momentum",
    "quality", "low vol", "alpha", "midcap", "smallcap", "total market index fund",
]


def _is_broad_market(scheme_name: str) -> bool:
    name = scheme_name.lower()
    if not any(marker in name for marker in BROAD_MARKET_NAME_MARKERS):
        return False
    if any(marker in name for marker in BROAD_MARKET_EXCLUDE_MARKERS):
        return False
    return True


def rank_broad_market_index_funds(lookback_days: int = 30) -> list[FundReturn]:
    """Ranks broad Nifty 50/Sensex index funds by trailing NAV return."""
    ranked = rank_defensive_funds("index_fund", lookback_days=lookback_days)
    return [f for f in ranked if _is_broad_market(f.scheme_name)]


if __name__ == "__main__":
    print("-- Broad-market (Nifty 50 / Sensex) index funds, by 30-day trailing return --")
    ranked = rank_broad_market_index_funds()
    for f in ranked:
        print(f"  {f.scheme_name:<40} {f.trailing_return_pct:+.3f}% "
              f"(NAV {f.nav_past:.4f} -> {f.nav_now:.4f})")

    print("\n-- Everything else in the index_fund sleeve (sector/factor/cap-slice, excluded) --")
    all_records = fetch_and_parse()
    all_index = get_sleeve_candidates(all_records, "index_fund")
    excluded_names = {f.scheme_name for f in ranked}
    for r in all_index:
        if r.scheme_name not in excluded_names:
            print(f"  {r.scheme_name}")
