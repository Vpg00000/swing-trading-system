"""
Sector scoring -- relative strength, breadth, and commodity tilt, derived
entirely from data already fetched by data/fetch.py and data/global_macro.py
(no new source, per ROADMAP.md: "derived from existing data"). Feeds
DESIGN.md's "Future-demand scenario module" (commodity/geopolitical ->
sector-tilt) and the sector-tilt input to momentum ranking.

Sector grouping reuses engine/correlation.py's get_sector() (yfinance GICS
`sector` field) -- the same free-data proxy already used for the
concentration/hard-cap check, so a stock's sector label is consistent
across both risk-control and scoring use.

Commodity tilt is a deliberately coarse static mapping (GICS sector ->
tailwind/headwind on a Brent/Copper move), not a granular per-industry
model -- a genuinely precise commodity-exposure map (e.g. which specific
paint/tyre/aviation names are crude-sensitive) would need per-industry
data finer than yfinance's broad sector field offers for free.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached
from config.universe import EQUITY_UNIVERSE
from engine.correlation import get_sector

RETURN_WINDOW_DAYS = 20
DMA_SHORT = 20
DMA_LONG = 50
COMMODITY_MOVE_THRESHOLD_PCT = 1.0  # min Brent/Copper daily move to count as a tilt signal

# Coarse GICS-sector -> commodity-tilt mapping. Crude up = tailwind for
# Energy producers, headwind for crude-consuming Industrials/Consumer
# Cyclical (aviation/logistics/paints/tyres sit inside these broad
# buckets). Copper up = tailwind for Basic Materials (copper producers).
_CRUDE_TAILWIND_SECTORS = {"Energy"}
_CRUDE_HEADWIND_SECTORS = {"Industrials", "Consumer Cyclical"}
_COPPER_TAILWIND_SECTORS = {"Basic Materials"}


@dataclass
class SectorScore:
    sector: str
    return_20d: float          # %, average of constituent 20-day returns
    rs_vs_nifty: float         # %, return_20d - Nifty's own 20-day return
    breadth_above_20dma: float  # %, share of constituents above their 20DMA
    breadth_above_50dma: float  # %, share of constituents above their 50DMA
    commodity_impact: str       # "TAILWIND" / "HEADWIND" / "NEUTRAL"
    overall_score: float        # 0-100


def _return_over(df, window: int) -> float | None:
    close = df["Close"]
    if len(close) < window + 1:
        return None
    return float(close.iloc[-1] / close.iloc[-window - 1] - 1)


def _above_dma(df, window: int) -> bool | None:
    close = df["Close"]
    if len(close) < window:
        return None
    dma = close.tail(window).mean()
    return bool(close.iloc[-1] > dma)


def compute_commodity_impact(sector: str, macro: dict) -> str:
    commodities = {q.name: q.change_pct for q in macro.get("commodities", [])}
    brent_chg = commodities.get("Brent Crude", 0.0)
    copper_chg = commodities.get("Copper", 0.0)

    if sector in _CRUDE_TAILWIND_SECTORS and brent_chg > COMMODITY_MOVE_THRESHOLD_PCT:
        return "TAILWIND"
    if sector in _CRUDE_HEADWIND_SECTORS and brent_chg > COMMODITY_MOVE_THRESHOLD_PCT:
        return "HEADWIND"
    if sector in _COPPER_TAILWIND_SECTORS and copper_chg > COMMODITY_MOVE_THRESHOLD_PCT:
        return "TAILWIND"
    return "NEUTRAL"


def compute_sector_scores(symbols: list[str] | None = None, macro: dict | None = None
                           ) -> list[SectorScore]:
    symbols = symbols or EQUITY_UNIVERSE
    macro = macro or {}

    nifty_df = load_cached("nifty")  # data/fetch.py's fetch_regime_inputs() cache name
    nifty_ret = _return_over(nifty_df, RETURN_WINDOW_DAYS) or 0.0

    by_sector: dict[str, list[str]] = {}
    for sym in symbols:
        sector = get_sector(sym)
        if sector == "Unknown":
            continue
        by_sector.setdefault(sector, []).append(sym)

    # First pass: gather raw values
    raw_sectors = []
    for sector, syms in by_sector.items():
        rets, above_20, above_50 = [], [], []
        for sym in syms:
            df = load_cached(sym)
            if df.empty:
                continue
            r = _return_over(df, RETURN_WINDOW_DAYS)
            if r is not None:
                rets.append(r)
            a20 = _above_dma(df, DMA_SHORT)
            if a20 is not None:
                above_20.append(a20)
            a50 = _above_dma(df, DMA_LONG)
            if a50 is not None:
                above_50.append(a50)

        if not rets:
            continue

        return_20d = sum(rets) / len(rets)
        rs_vs_nifty = return_20d - nifty_ret
        breadth20 = sum(above_20) / len(above_20) if above_20 else 0.0
        breadth50 = sum(above_50) / len(above_50) if above_50 else 0.0
        commodity_impact = compute_commodity_impact(sector, macro)

        raw_sectors.append({
            "sector": sector,
            "return_20d": return_20d,
            "rs_vs_nifty": rs_vs_nifty,
            "breadth20": breadth20,
            "breadth50": breadth50,
            "commodity_impact": commodity_impact
        })

    if not raw_sectors:
        return []

    # Sort raw sectors by rs_vs_nifty to compute percentile rank
    raw_sectors.sort(key=lambda x: x["rs_vs_nifty"])
    N = len(raw_sectors)

    scores = []
    for idx, item in enumerate(raw_sectors):
        # Percentile rank of RS
        if N > 1:
            rs_percentile = idx / (N - 1)
        else:
            rs_percentile = 1.0

        rs_component = rs_percentile * 100.0
        breadth_component = (item["breadth20"] + item["breadth50"]) / 2 * 100.0
        commodity_val = {
            "TAILWIND": 100.0,
            "HEADWIND": 0.0,
            "NEUTRAL": 50.0
        }[item["commodity_impact"]]

        overall = 0.5 * rs_component + 0.4 * breadth_component + 0.1 * commodity_val
        overall = max(0.0, min(100.0, overall))

        scores.append(SectorScore(
            sector=item["sector"],
            return_20d=round(item["return_20d"] * 100, 2),
            rs_vs_nifty=round(item["rs_vs_nifty"] * 100, 2),
            breadth_above_20dma=round(item["breadth20"] * 100, 1),
            breadth_above_50dma=round(item["breadth50"] * 100, 1),
            commodity_impact=item["commodity_impact"],
            overall_score=round(overall, 1),
        ))

    scores.sort(key=lambda s: s.overall_score, reverse=True)
    return scores


if __name__ == "__main__":
    from data.global_macro import fetch_all_macro

    print("Fetching macro context for commodity tilt...")
    macro = fetch_all_macro()

    print("\nComputing sector scores from cached price data...")
    scores = compute_sector_scores(macro=macro)

    print(f"\n{'Sector':<24}{'20D Ret':>9}{'RS vs Nifty':>13}{'>20DMA':>9}{'>50DMA':>9}"
          f"{'Commodity':>12}{'Score':>8}")
    for s in scores:
        print(f"{s.sector:<24}{s.return_20d:>8.2f}%{s.rs_vs_nifty:>12.2f}%"
              f"{s.breadth_above_20dma:>8.1f}%{s.breadth_above_50dma:>8.1f}%"
              f"{s.commodity_impact:>12}{s.overall_score:>8.1f}")
