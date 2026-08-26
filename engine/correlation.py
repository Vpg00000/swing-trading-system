"""
Correlation/concentration check -- per DESIGN.md's risk controls section:
"Correlation/concentration check before adding a position (no hidden
sector-stacking, e.g. 3 bank stocks = 1 concentrated bet)" and the hard cap
"single sector <=20%".

Free-data proxy: GICS sector (via yfinance's `Ticker.info["sector"]`) is
used as the concentration grouping, since real pairwise price-correlation
would need a paid factor model to be reliable -- sector membership is the
concrete, observable version of "these aren't actually independent bets"
that DESIGN.md's own example (3 bank stocks) describes.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MAX_SECTOR_PCT = 0.20  # DESIGN.md hard cap: single sector <=20% of capital

_info_cache: dict[str, dict] = {}


@dataclass
class SectorExposure:
    sector: str
    total_inr: float
    pct_of_capital: float
    symbols: list[str]


def _get_info(symbol: str) -> dict:
    """Cached lookup -- yfinance's `.info` is a slow full-profile fetch, so
    avoid re-hitting it for the same symbol within a run. Shared by sector
    and industry lookups so each symbol costs one fetch, not two."""
    if symbol not in _info_cache:
        try:
            _info_cache[symbol] = yf.Ticker(symbol).info
        except Exception:
            _info_cache[symbol] = {}
    return _info_cache[symbol]


def get_sector(symbol: str) -> str:
    return _get_info(symbol).get("sector") or "Unknown"


def get_industry(symbol: str) -> str:
    return _get_info(symbol).get("industry") or "Unknown"


def compute_sector_exposure(positions: list[dict], capital_inr: float) -> list[SectorExposure]:
    """positions: [{"symbol": ..., "value_inr": ...}, ...]"""
    by_sector: dict[str, list[dict]] = {}
    for p in positions:
        sector = get_sector(p["symbol"])
        by_sector.setdefault(sector, []).append(p)

    exposures = []
    for sector, rows in by_sector.items():
        total = sum(r["value_inr"] for r in rows)
        exposures.append(SectorExposure(
            sector=sector,
            total_inr=total,
            pct_of_capital=total / capital_inr,
            symbols=[r["symbol"] for r in rows],
        ))
    exposures.sort(key=lambda e: e.pct_of_capital, reverse=True)
    return exposures


def concentration_flags(positions: list[dict], capital_inr: float) -> list[SectorExposure]:
    """Sectors already over the 20% hard cap, given current holdings."""
    return [e for e in compute_sector_exposure(positions, capital_inr) if e.pct_of_capital > MAX_SECTOR_PCT]


def check_new_position(symbol: str, size_inr: float, existing_positions: list[dict],
                        capital_inr: float) -> str | None:
    """
    Returns a warning string if adding this position would push its sector
    over the 20% cap (hidden sector-stacking), else None.
    """
    sector = get_sector(symbol)
    same_sector_inr = sum(
        p["value_inr"] for p in existing_positions if get_sector(p["symbol"]) == sector
    )
    projected_pct = (same_sector_inr + size_inr) / capital_inr
    if projected_pct > MAX_SECTOR_PCT:
        same_sector_symbols = [p["symbol"] for p in existing_positions if get_sector(p["symbol"]) == sector]
        stack_note = f" (already holding {', '.join(same_sector_symbols)})" if same_sector_symbols else ""
        return (f"{symbol} is {sector} -- adding would bring sector exposure to "
                f"{projected_pct:.0%}, over the {MAX_SECTOR_PCT:.0%} cap{stack_note}")
    return None


if __name__ == "__main__":
    demo_positions = [
        {"symbol": "HDFCBANK.NS", "value_inr": 300_000},
        {"symbol": "ICICIBANK.NS", "value_inr": 300_000},
        {"symbol": "RELIANCE.NS", "value_inr": 500_000},
    ]
    capital = 1_00_00_000

    print("-- Sector exposure --")
    for e in compute_sector_exposure(demo_positions, capital):
        print(f"  {e.sector:<20} {e.pct_of_capital:>6.1%}  ₹{e.total_inr/1e5:.1f}L  {e.symbols}")

    print("\n-- Concentration flags (>20% cap) --")
    flags = concentration_flags(demo_positions, capital)
    if not flags:
        print("  none")
    for f in flags:
        print(f"  {f.sector} at {f.pct_of_capital:.0%}")

    print("\n-- Hypothetical new position check --")
    warning = check_new_position("KOTAKBANK.NS", 200_000, demo_positions, capital)
    print(f"  {warning or 'OK, no sector-stacking concern'}")
