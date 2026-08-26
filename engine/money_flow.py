"""
Money Flow Score -- combines the four institutional data/institutional/
modules (insider, bulk_block, pledge, shareholding) into a single /20 score
per symbol, per ROADMAP.md's money-flow module and the approved plan's
scoring split:
  Insider score     /8
  Bulk/block score  /4
  Pledge score      /4
  Ownership score   /4

This module only combines already-fetched data (callers run the four
data/institutional/*.py lookups themselves, since each has a different
fetch cost/frequency -- insider and bulk/block are near-daily, pledge and
shareholding are per-symbol/quarterly per those modules' own docstrings).
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.institutional.insider import InsiderTrade
from data.institutional.bulk_block import BulkBlockDeal
from data.institutional.pledge import PledgeData
from data.institutional.shareholding import OwnershipSnapshot

_PROMOTER_CATEGORIES = {"Promoters", "Promoter Group"}
_STRATEGIC_BUYER_MARKERS = ("MUTUAL FUND", "INSURANCE", "LIFE", "PENSION")

INSIDER_MAX = 8
BULK_BLOCK_MAX = 4
PLEDGE_MAX = 4
OWNERSHIP_MAX = 4


@dataclass
class MoneyFlowScore:
    symbol: str
    insider_score: float    # -8..+8, clamped to +-INSIDER_MAX
    bulk_block_score: float  # -4..+4
    pledge_score: float      # -4..0 (pledge is a risk flag, never a positive)
    ownership_score: float   # -4..+4
    total_score: float       # -20..+20 (not 0..20 -- negative flow is a real signal, not a floor)
    notes: list[str]
    insider_status: str
    bulk_block_status: str
    pledge_status: str
    ownership_status: str


def _score_insider(trades: list[InsiderTrade] | None) -> tuple[float, list[str]]:
    if not trades:
        return 0.0, []

    promoter_trades = [t for t in trades if t.person_category in _PROMOTER_CATEGORIES]
    promoter_buys = [t for t in promoter_trades if t.transaction_type == "Buy"]
    promoter_sells = [t for t in promoter_trades if t.transaction_type == "Sell"]

    score = 0.0
    notes = []
    if promoter_buys:
        score += 4
        notes.append(f"{len(promoter_buys)} promoter open-market buy(s)")
    distinct_buyers = {t.person_name for t in promoter_buys}
    if len(distinct_buyers) > 1:
        score += 3
        notes.append(f"{len(distinct_buyers)} distinct insiders buying")
    if promoter_sells:
        score -= 3
        notes.append(f"{len(promoter_sells)} promoter sale(s)")
    if len(promoter_sells) > 1:
        score -= 4
        notes.append("repeated promoter selling")

    return max(-INSIDER_MAX, min(INSIDER_MAX, score)), notes


def _score_bulk_block(deals: list[BulkBlockDeal] | None) -> tuple[float, list[str]]:
    if not deals:
        return 0.0, []

    score = 0.0
    notes = []
    for d in deals:
        is_strategic = any(marker in d.client_name.upper() for marker in _STRATEGIC_BUYER_MARKERS)
        if is_strategic and d.buy_sell == "BUY":
            score += 2
        elif d.buy_sell == "SELL" and is_strategic:
            score -= 1  # institutional exit, milder flag than a promoter exit
    buy_value = sum(d.value_inr for d in deals if d.buy_sell == "BUY")
    sell_value = sum(d.value_inr for d in deals if d.buy_sell == "SELL")
    if buy_value > sell_value * 1.5:
        notes.append("net bulk/block buying pressure")
    elif sell_value > buy_value * 1.5:
        notes.append("net bulk/block selling pressure")

    return max(-BULK_BLOCK_MAX, min(BULK_BLOCK_MAX, score)), notes


def _score_pledge(pledge: PledgeData | None) -> tuple[float, list[str]]:
    if pledge is None or not pledge.has_pledge:
        return 0.0, []

    if pledge.pledged_pct >= 50:
        return -PLEDGE_MAX, [f"promoter pledge {pledge.pledged_pct:.1f}% -- high, hard risk flag"]
    if pledge.pledged_pct >= 20:
        return -PLEDGE_MAX * 0.5, [f"promoter pledge {pledge.pledged_pct:.1f}% -- elevated"]
    return -PLEDGE_MAX * 0.25, [f"promoter pledge {pledge.pledged_pct:.1f}% -- present, moderate"]


def _score_ownership(snap: OwnershipSnapshot | None) -> tuple[float, list[str]]:
    if snap is None:
        return 0.0, []

    fii_chg = snap.fii_pct - snap.prev_fii_pct if snap.prev_fii_pct is not None else 0.0
    dii_chg = snap.dii_pct - snap.prev_dii_pct if snap.prev_dii_pct is not None else 0.0

    if snap.prev_fii_pct is not None and snap.prev_dii_pct is not None:
        details = (f"FII {snap.fii_pct:.1f}% (was {snap.prev_fii_pct:.1f}%, {fii_chg:+.1f}%), "
                   f"DII {snap.dii_pct:.1f}% (was {snap.prev_dii_pct:.1f}%, {dii_chg:+.1f}%)")
    else:
        details = f"FII {snap.fii_pct:.1f}%, DII {snap.dii_pct:.1f}%"

    if snap.accumulation_signal == "ACCUMULATION":
        return OWNERSHIP_MAX, [f"FII+DII accumulation QoQ: {details}"]
    if snap.accumulation_signal == "DISTRIBUTION":
        return -OWNERSHIP_MAX, [f"FII+DII distribution QoQ: {details}"]
    return 0.0, []


def compute_money_flow_score(symbol: str, insider_trades: list[InsiderTrade] | None,
                              bulk_deals: list[BulkBlockDeal] | None,
                              pledge: PledgeData | None,
                              ownership: OwnershipSnapshot | None) -> MoneyFlowScore:
    insider_score, insider_notes = _score_insider(insider_trades)
    bulk_block_score, bulk_notes = _score_bulk_block(bulk_deals)
    pledge_score, pledge_notes = _score_pledge(pledge)
    ownership_score, ownership_notes = _score_ownership(ownership)

    total = insider_score + bulk_block_score + pledge_score + ownership_score
    notes = insider_notes + bulk_notes + pledge_notes + ownership_notes

    # Compute status string fields
    if insider_trades is None:
        insider_status = "DATA_UNAVAILABLE"
    elif not insider_trades:
        insider_status = "NO_ACTIVITY"
    elif insider_score > 0:
        insider_status = "BUYING"
    elif insider_score < 0:
        insider_status = "SELLING"
    else:
        insider_status = "NEUTRAL"

    if bulk_deals is None:
        bulk_block_status = "DATA_UNAVAILABLE"
    elif not bulk_deals:
        bulk_block_status = "NO_ACTIVITY"
    elif bulk_block_score > 0:
        bulk_block_status = "BUYING"
    elif bulk_block_score < 0:
        bulk_block_status = "SELLING"
    else:
        bulk_block_status = "NEUTRAL"

    if pledge is None:
        pledge_status = "DATA_UNAVAILABLE"
    elif not pledge.has_pledge:
        pledge_status = "NO_ACTIVITY"
    else:
        pledge_status = "FLAGGED"

    if ownership is None:
        ownership_status = "DATA_UNAVAILABLE"
    elif ownership.accumulation_signal == "ACCUMULATION":
        ownership_status = "ACCUMULATION"
    elif ownership.accumulation_signal == "DISTRIBUTION":
        ownership_status = "DISTRIBUTION"
    else:
        ownership_status = "NEUTRAL"

    return MoneyFlowScore(
        symbol=symbol,
        insider_score=insider_score,
        bulk_block_score=bulk_block_score,
        pledge_score=pledge_score,
        ownership_score=ownership_score,
        total_score=round(total, 1),
        notes=notes,
        insider_status=insider_status,
        bulk_block_status=bulk_block_status,
        pledge_status=pledge_status,
        ownership_status=ownership_status,
    )


if __name__ == "__main__":
    from data.institutional.insider import insider_trades_for_universe
    from data.institutional.bulk_block import bulk_block_deals_for_universe
    from data.institutional.pledge import pledge_status_for_symbols
    from data.institutional.shareholding import shareholding_for_symbols

    demo_symbols = ["RELIANCE", "MWL"]

    print("Fetching money-flow inputs for demo symbols (per-symbol lookups, kept short)...")
    all_insider = insider_trades_for_universe(demo_symbols, lookback_days=180)
    all_bulk_block = bulk_block_deals_for_universe(demo_symbols)
    pledges = {p.symbol: p for p in pledge_status_for_symbols(demo_symbols)}
    ownerships = {o.symbol: o for o in shareholding_for_symbols(demo_symbols)}

    print("\n-- Money Flow Scores --")
    for sym in demo_symbols:
        sym_insider = [t for t in all_insider if t.symbol == sym]
        sym_bulk_block = [d for d in all_bulk_block if d.symbol == sym]
        score = compute_money_flow_score(sym, sym_insider, sym_bulk_block,
                                          pledges.get(sym), ownerships.get(sym))
        print(f"\n  {score.symbol} -- total {score.total_score:+.1f}/20 "
              f"(insider {score.insider_score:+.1f}/8, bulk/block {score.bulk_block_score:+.1f}/4, "
              f"pledge {score.pledge_score:+.1f}/4, ownership {score.ownership_score:+.1f}/4)")
        for n in score.notes:
            print(f"    - {n}")
