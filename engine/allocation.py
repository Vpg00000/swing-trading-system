"""
Phase 2 capital allocation engine: combines the regime-driven equity budget
(Phase 1) with the defensive sleeve (gold/silver ETF, liquid/arbitrage
funds) into one full-portfolio recommendation. See DESIGN.md "Capital
allocation" table for the target shape this implements.

Allocation logic:
  - Equity budget = capital x regime.max_equity_exposure (Phase 1, unchanged).
  - Within the equity budget, a fixed slice (INDEX_FUND_EQUITY_SLICE_PCT)
    goes to a passive Nifty 50/Sensex index fund (data/index_funds.py)
    instead of individual momentum stock picks -- a risk-reduction carve-out
    within the existing equity %, not a new sleeve, per DESIGN.md's capital
    table (user-confirmed design choice).
  - Gold/Silver = a fixed hedge weight, independent of regime -- it's a
    portfolio diversifier, not a tactical bet, so it doesn't flex with the
    equity cap.
  - Cash floor = fixed minimum reserve, per DESIGN.md ("Cash 5%+ always
    allowed to be the answer").
  - Defensive (liquid/arbitrage) parking absorbs whatever capital regime
    keeps out of equities -- this is what makes a RISK-OFF/EMERGENCY regime
    concretely actionable: money leaving the equity budget doesn't sit idle
    in a bank account, it goes to work in low-risk yield instead.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.regime import classify_regime, RegimeResult
from data.amfi import fetch_and_parse
from data.etf_universe import build_etf_universe, most_liquid_etf
from data.defensive_funds import rank_defensive_funds, FundReturn
from data.index_funds import rank_broad_market_index_funds

GOLD_SILVER_TARGET_PCT = 0.10  # DESIGN.md: Gold/Silver ETF 10% of capital
CASH_FLOOR_PCT = 0.05  # DESIGN.md: Cash 5%+ always allowed to be the answer
GOLD_SILVER_SPLIT = 0.7  # within the 10% hedge, 70% gold / 30% silver

# Carve-out within the equity budget itself (not a new sleeve, per DESIGN.md
# capital table): a slice of the regime-sized equity exposure goes to a
# passive Nifty 50/Sensex index fund instead of 100% individual momentum
# stock picks, to reduce single-stock concentration risk without changing
# the overall target shape.
INDEX_FUND_EQUITY_SLICE_PCT = 0.25


@dataclass
class SleeveAllocation:
    sleeve: str
    target_pct: float
    target_inr: float
    top_pick: str  # ticker or scheme name
    top_pick_detail: str


@dataclass
class Phase2Allocation:
    capital_inr: float
    regime: RegimeResult
    equity_budget_inr: float
    momentum_equity_inr: float
    index_fund_inr: float
    gold_etf_inr: float
    silver_etf_inr: float
    liquid_arbitrage_inr: float
    cash_floor_inr: float
    sleeves: list[SleeveAllocation]


def _best_defensive_fund(ranked: list[FundReturn]) -> FundReturn | None:
    return ranked[0] if ranked else None


def build_phase2_allocation(capital_inr: float) -> Phase2Allocation:
    regime = classify_regime()

    equity_budget = capital_inr * regime.max_equity_exposure
    index_fund_inr = equity_budget * INDEX_FUND_EQUITY_SLICE_PCT
    momentum_equity_inr = equity_budget - index_fund_inr
    gold_silver_total = capital_inr * GOLD_SILVER_TARGET_PCT
    gold_inr = gold_silver_total * GOLD_SILVER_SPLIT
    silver_inr = gold_silver_total * (1 - GOLD_SILVER_SPLIT)
    cash_floor = capital_inr * CASH_FLOOR_PCT

    # Whatever's left after equity + gold/silver + cash floor goes to the
    # defensive (liquid/arbitrage) parking sleeve -- this is the "regime
    # de-risking has somewhere real to go" mechanism.
    liquid_arbitrage_inr = max(
        0.0, capital_inr - equity_budget - gold_silver_total - cash_floor
    )

    amfi_records = fetch_and_parse()
    etf_listings = build_etf_universe(amfi_records)
    gold_pick = most_liquid_etf(etf_listings, "gold_etf")
    silver_pick = most_liquid_etf(etf_listings, "silver_etf")
    liquid_ranked = rank_defensive_funds("liquid_fund")
    arbitrage_ranked = rank_defensive_funds("arbitrage_fund")
    liquid_pick = _best_defensive_fund(liquid_ranked)
    arbitrage_pick = _best_defensive_fund(arbitrage_ranked)
    index_fund_ranked = rank_broad_market_index_funds()
    index_fund_pick = index_fund_ranked[0] if index_fund_ranked else None

    sleeves = [
        SleeveAllocation(
            sleeve="Core momentum equity",
            target_pct=(momentum_equity_inr / capital_inr),
            target_inr=momentum_equity_inr,
            top_pick="(see daily momentum ranking)",
            top_pick_detail=f"regime={regime.regime}",
        ),
        SleeveAllocation(
            sleeve="Index fund (equity slice)",
            target_pct=(index_fund_inr / capital_inr),
            target_inr=index_fund_inr,
            top_pick=index_fund_pick.scheme_name if index_fund_pick else "N/A",
            top_pick_detail=(
                f"{index_fund_pick.trailing_return_pct:+.2f}%/30d"
                if index_fund_pick else "no data"
            ),
        ),
        SleeveAllocation(
            sleeve="Gold ETF",
            target_pct=GOLD_SILVER_TARGET_PCT * GOLD_SILVER_SPLIT,
            target_inr=gold_inr,
            top_pick=f"{gold_pick.ticker}.NS" if gold_pick else "N/A",
            top_pick_detail=f"{gold_pick.scheme_name} NAV {gold_pick.nav:.2f}" if gold_pick else "no data",
        ),
        SleeveAllocation(
            sleeve="Silver ETF",
            target_pct=GOLD_SILVER_TARGET_PCT * (1 - GOLD_SILVER_SPLIT),
            target_inr=silver_inr,
            top_pick=f"{silver_pick.ticker}.NS" if silver_pick else "N/A",
            top_pick_detail=f"{silver_pick.scheme_name} NAV {silver_pick.nav:.2f}" if silver_pick else "no data",
        ),
        SleeveAllocation(
            sleeve="Liquid/Arbitrage parking",
            target_pct=liquid_arbitrage_inr / capital_inr,
            target_inr=liquid_arbitrage_inr,
            top_pick=(arbitrage_pick.scheme_name if arbitrage_pick else
                      (liquid_pick.scheme_name if liquid_pick else "N/A")),
            top_pick_detail=(
                f"arbitrage {arbitrage_pick.trailing_return_pct:+.2f}%/30d"
                if arbitrage_pick else
                (f"liquid {liquid_pick.trailing_return_pct:+.2f}%/30d" if liquid_pick else "no data")
            ),
        ),
        SleeveAllocation(
            sleeve="Cash floor",
            target_pct=CASH_FLOOR_PCT,
            target_inr=cash_floor,
            top_pick="(uninvested)",
            top_pick_detail="always-available reserve per DESIGN.md",
        ),
    ]

    return Phase2Allocation(
        capital_inr=capital_inr,
        regime=regime,
        equity_budget_inr=equity_budget,
        momentum_equity_inr=momentum_equity_inr,
        index_fund_inr=index_fund_inr,
        gold_etf_inr=gold_inr,
        silver_etf_inr=silver_inr,
        liquid_arbitrage_inr=liquid_arbitrage_inr,
        cash_floor_inr=cash_floor,
        sleeves=sleeves,
    )


def classify_holding_sleeve(symbol: str) -> str:
    """Classifies a holding symbol into one of the Phase 2 sleeves."""
    sym_upper = symbol.upper()
    if sym_upper.endswith("BEES.NS") or sym_upper.endswith("BEES") or "GOLD" in sym_upper:
        if "SILVER" in sym_upper:
            return "Silver ETF"
        return "Gold ETF"
    elif "SILVER" in sym_upper:
        return "Silver ETF"
    elif "ARBITRAGE" in sym_upper or "LIQUID" in sym_upper or "PARKING" in sym_upper:
        return "Liquid/Arbitrage parking"
    elif "INDEX" in sym_upper or "NIFTY 50" in sym_upper or "SENSEX" in sym_upper:
        return "Index fund (equity slice)"
    elif sym_upper == "CASH" or sym_upper == "CASH_FLOOR":
        return "Cash floor"
    else:
        return "Core momentum equity"


def compute_portfolio_drift(portfolio: dict, alloc: Phase2Allocation) -> dict:
    """
    Computes drift between target allocation and actual holdings.
    Returns a dict mapping sleeve name to:
      {"target_pct": ..., "target_inr": ..., "actual_pct": ..., "actual_inr": ..., "drift_pct": ..., "drift_inr": ...}
    """
    capital = alloc.capital_inr
    actuals = {s.sleeve: 0.0 for s in alloc.sleeves}
    actuals["Cash floor"] = float(portfolio.get("cash_inr", 0.0))

    for h in portfolio.get("holdings", []):
        sleeve = h.get("sleeve") or classify_holding_sleeve(h["symbol"])
        if sleeve in actuals:
            actuals[sleeve] += float(h["value_inr"])
        else:
            actuals["Core momentum equity"] += float(h["value_inr"])

    drift_data = {}
    for s in alloc.sleeves:
        target_inr = s.target_inr
        target_pct = s.target_pct
        actual_inr = actuals[s.sleeve]
        actual_pct = actual_inr / capital if capital > 0 else 0.0
        drift_inr = actual_inr - target_inr
        drift_pct = actual_pct - target_pct

        drift_data[s.sleeve] = {
            "target_pct": target_pct,
            "target_inr": target_inr,
            "actual_pct": actual_pct,
            "actual_inr": actual_inr,
            "drift_pct": drift_pct,
            "drift_inr": drift_inr
        }

    return drift_data


if __name__ == "__main__":
    CAPITAL = 1_00_00_000  # Rs 1 crore
    alloc = build_phase2_allocation(CAPITAL)

    print(f"Regime: {alloc.regime.regime} (max equity exposure {alloc.regime.max_equity_exposure:.0%})")
    print(f"Capital: Rs{alloc.capital_inr/1e5:.1f}L\n")
    print(f"{'Sleeve':<32}{'Target %':>10}{'Target (Rs L)':>16}   Top pick")
    for s in alloc.sleeves:
        print(f"{s.sleeve:<32}{s.target_pct:>9.1%}{s.target_inr/1e5:>16.2f}   "
              f"{s.top_pick} -- {s.top_pick_detail}")
