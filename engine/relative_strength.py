"""
engine/relative_strength.py — Relative Strength Engine (Module 11).

Computes stock RS vs Nifty AND vs own sector index.
Produces a normalized RSScore /100 (used as input to Technical Score /15
in the composite score).

Methodology:
  RS vs Nifty  = stock_ret_Xm / nifty_ret_Xm  (ratio ≥1 = outperforming)
  RS vs Sector = stock_ret_Xm / sector_ret_Xm

Uses 3M and 6M windows (weighted 40/60 like the momentum score) and
maps the combined ratio to a 0-100 score via percentile ranking across
a batch of candidates. For single-symbol use, uses a direct map.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached

TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
NIFTY_KEY = "nifty"   # must match data/fetch.py cache naming convention

# Sector ETF yfinance tickers → cache keys
SECTOR_ETF_MAP: dict[str, str] = {
    "Technology":  "NIFTEIT.NS",
    "Pharma":      "NIFTYPHARMA.NS",
    "Banking":     "NIFTYBANK.NS",
    "Auto":        "NIFTYAUTO.NS",
    "Consumer":    "NIFTYFMCG.NS",
    "Energy":      "NIFTYENERGY.NS",
    "Metals":      "NIFTYMETAL.NS",
    "Infra":       "NIFTYINFRA.NS",
    "Realty":      "NIFTYREALTY.NS",
    "Telecom":     "NIFTYIT.NS",    # proxy
}


@dataclass
class RSScore:
    symbol: str
    rs_vs_nifty_3m: Optional[float]   # ratio: >1 outperforms, <1 underperforms
    rs_vs_nifty_6m: Optional[float]
    rs_vs_sector_3m: Optional[float]  # None if sector unknown/unavailable
    rs_vs_sector_6m: Optional[float]
    combined_rs_ratio: float           # weighted combined ratio
    rs_score_100: float                # normalized /100
    rs_score_15: float                 # /15 for composite technical score
    status: str                        # 'SCORED', 'NO_NIFTY_DATA', 'INSUFFICIENT_HISTORY'
    sector: Optional[str]


def _get_return(df: pd.DataFrame, window: int) -> Optional[float]:
    """Return the simple return over 'window' trading days. None if not enough data."""
    if df is None or df.empty or len(df) < window + 1:
        return None
    close = df["Close"]
    try:
        return float(close.iloc[-1]) / float(close.iloc[-window]) - 1
    except (IndexError, ZeroDivisionError):
        return None


def _rs_ratio(stock_ret: Optional[float], bench_ret: Optional[float]) -> Optional[float]:
    """
    Compute RS ratio. bench_ret==0 handled: return None.
    rs = (1 + stock_ret) / (1 + bench_ret) — standard RS ratio.
    """
    if stock_ret is None or bench_ret is None:
        return None
    denom = 1.0 + bench_ret
    if abs(denom) < 1e-6:
        return None
    return (1.0 + stock_ret) / denom


def _rs_ratio_to_score(ratio: Optional[float]) -> float:
    """
    Map an RS ratio to a 0-100 score.
    ratio = 1.0 → 50 (in-line with benchmark)
    ratio = 1.2 → ~80 (outperforming by 20%)
    ratio = 0.8 → ~25 (underperforming by 20%)
    """
    if ratio is None:
        return 50.0  # neutral when data unavailable
    # Smooth sigmoid-like mapping centred at 1.0
    # score = 50 + 50 * tanh(3 * (ratio - 1))
    import math
    val = 3.0 * (ratio - 1.0)
    score = 50.0 + 50.0 * math.tanh(val)
    return max(0.0, min(100.0, score))


def compute_rs_score(
    symbol: str,
    sector: Optional[str] = None,
) -> RSScore:
    """
    Compute RSScore for a single symbol.
    Loads cached OHLCV data from data/cache/ (yfinance EOD).
    """
    # Load stock data
    df_stock = load_cached(symbol)
    # Load Nifty benchmark
    df_nifty = load_cached(NIFTY_KEY)

    if df_stock is None or df_stock.empty:
        return RSScore(
            symbol=symbol,
            rs_vs_nifty_3m=None, rs_vs_nifty_6m=None,
            rs_vs_sector_3m=None, rs_vs_sector_6m=None,
            combined_rs_ratio=1.0,
            rs_score_100=50.0, rs_score_15=7.5,
            status="NO_STOCK_DATA", sector=sector,
        )

    if df_nifty is None or df_nifty.empty:
        return RSScore(
            symbol=symbol,
            rs_vs_nifty_3m=None, rs_vs_nifty_6m=None,
            rs_vs_sector_3m=None, rs_vs_sector_6m=None,
            combined_rs_ratio=1.0,
            rs_score_100=50.0, rs_score_15=7.5,
            status="NO_NIFTY_DATA", sector=sector,
        )

    # Stock returns
    stock_3m = _get_return(df_stock, TRADING_DAYS_3M)
    stock_6m = _get_return(df_stock, TRADING_DAYS_6M)

    if stock_3m is None and stock_6m is None:
        return RSScore(
            symbol=symbol,
            rs_vs_nifty_3m=None, rs_vs_nifty_6m=None,
            rs_vs_sector_3m=None, rs_vs_sector_6m=None,
            combined_rs_ratio=1.0,
            rs_score_100=50.0, rs_score_15=7.5,
            status="INSUFFICIENT_HISTORY", sector=sector,
        )

    # Nifty returns
    nifty_3m = _get_return(df_nifty, TRADING_DAYS_3M)
    nifty_6m = _get_return(df_nifty, TRADING_DAYS_6M)

    # RS ratios vs Nifty
    rs_n3 = _rs_ratio(stock_3m, nifty_3m)
    rs_n6 = _rs_ratio(stock_6m, nifty_6m)

    # Sector RS (optional)
    rs_s3 = rs_s6 = None
    if sector and sector in SECTOR_ETF_MAP:
        sector_ticker = SECTOR_ETF_MAP[sector]
        df_sector = load_cached(sector_ticker)
        if df_sector is not None and not df_sector.empty:
            sec_3m = _get_return(df_sector, TRADING_DAYS_3M)
            sec_6m = _get_return(df_sector, TRADING_DAYS_6M)
            rs_s3 = _rs_ratio(stock_3m, sec_3m)
            rs_s6 = _rs_ratio(stock_6m, sec_6m)

    # Combined RS: weight 3M=40%, 6M=60%, then average Nifty RS and Sector RS
    def weighted_ratio(r3, r6):
        if r3 is None and r6 is None:
            return None
        if r3 is None:
            return r6
        if r6 is None:
            return r3
        return 0.4 * r3 + 0.6 * r6

    nifty_combined = weighted_ratio(rs_n3, rs_n6)
    sector_combined = weighted_ratio(rs_s3, rs_s6)

    if nifty_combined is not None and sector_combined is not None:
        # Weight Nifty RS 60%, Sector RS 40%
        combined = 0.6 * nifty_combined + 0.4 * sector_combined
    elif nifty_combined is not None:
        combined = nifty_combined
    else:
        combined = 1.0  # neutral

    # Convert to score
    score_100 = _rs_ratio_to_score(combined)
    score_15 = round((score_100 / 100.0) * 15.0, 2)

    return RSScore(
        symbol=symbol,
        rs_vs_nifty_3m=round(rs_n3, 4) if rs_n3 is not None else None,
        rs_vs_nifty_6m=round(rs_n6, 4) if rs_n6 is not None else None,
        rs_vs_sector_3m=round(rs_s3, 4) if rs_s3 is not None else None,
        rs_vs_sector_6m=round(rs_s6, 4) if rs_s6 is not None else None,
        combined_rs_ratio=round(combined, 4),
        rs_score_100=round(score_100, 1),
        rs_score_15=score_15,
        status="SCORED",
        sector=sector,
    )


def compute_rs_batch(
    symbols: list[str],
    sector_map: Optional[dict[str, str]] = None,
) -> dict[str, RSScore]:
    """
    Compute RS scores for a list of symbols.
    sector_map: {symbol: sector_name} — optional
    Returns dict: symbol → RSScore
    """
    sector_map = sector_map or {}
    return {
        sym: compute_rs_score(sym, sector=sector_map.get(sym))
        for sym in symbols
    }


if __name__ == "__main__":
    test_syms = {
        "HFCL.NS": "Technology",
        "WELCORP.NS": "Metals",
        "RELIANCE.NS": "Energy",
    }
    for sym, sec in test_syms.items():
        rs = compute_rs_score(sym, sector=sec)
        print(f"=== {sym} (sector={sec}) ===")
        print(f"  RS Score:       {rs.rs_score_100}/100 → {rs.rs_score_15}/15 ({rs.status})")
        print(f"  RS vs Nifty 3M: {rs.rs_vs_nifty_3m}")
        print(f"  RS vs Nifty 6M: {rs.rs_vs_nifty_6m}")
        print(f"  RS vs Sector 3M:{rs.rs_vs_sector_3m}")
        print(f"  Combined ratio: {rs.combined_rs_ratio}")
        print()
