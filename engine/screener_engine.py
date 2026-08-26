"""
Universal Stock Screener Engine.

Combines metrics across all system layers:
  1. Technical Indicators (RSI, MACD, Moving Averages, Bollinger, ATR, 52W Range, Volume Surge)
  2. Fundamentals & Valuation (PE, PB, ROE, ROCE, Market Cap, Sales/Profit Growth)
  3. Governance & Quality Scores (Pledge %, Insider Trend)
  4. Relative Strength (RS Score vs Nifty)
  5. AI Composite Prediction Layer (Composite Score /100, Action, Target, R:R, EV %)

Usage:
    from engine.screener_engine import filter_universe, ScreenerFilter

    filters = ScreenerFilter(
        min_pe=10.0,
        max_pe=30.0,
        min_roe=15.0,
        min_rsi=40.0,
        max_rsi=65.0,
        above_50dma=True,
        min_score=60.0
    )

    results = filter_universe(filters)
    for res in results:
        print(res['symbol'], res['score'], res['action'], res['rsi'], res['pe'])
"""

import sys
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.universe import EQUITY_UNIVERSE
from engine.indicators import compute_indicators, IndicatorResult, compute_all
from data.screener import fetch_screener_data, ScreenerData
from engine.fundamental import compute_fundamental_score
from engine.governance import compute_governance_score
from engine.valuation import compute_valuation_score
from engine.relative_strength import compute_rs_score
from engine.expected_return import compute_expected_return

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Screener Filter Options
# ─────────────────────────────────────────────

@dataclass
class ScreenerFilter:
    # ── Fundamental Filters ──────────────────
    min_market_cap_cr: Optional[float] = None
    max_market_cap_cr: Optional[float] = None
    min_pe: Optional[float] = None
    max_pe: Optional[float] = None
    min_pb: Optional[float] = None
    max_pb: Optional[float] = None
    min_roe: Optional[float] = None
    min_roce: Optional[float] = None
    max_debt_to_equity: Optional[float] = None
    min_sales_growth_3yr: Optional[float] = None
    min_profit_growth_3yr: Optional[float] = None
    max_pledge_pct: Optional[float] = None

    # ── Technical Filters ────────────────────
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    rsi_zone: Optional[str] = None           # OVERSOLD / NEUTRAL / OVERBOUGHT
    macd_bullish_only: bool = False
    macd_crossover_only: bool = False
    above_20dma: Optional[bool] = None
    above_50dma: Optional[bool] = None
    above_200dma: Optional[bool] = None
    min_volume_ratio: Optional[float] = None  # e.g., 1.5x 20D average
    min_delivery_pct: Optional[float] = None  # Delivery % from Bhavcopy
    max_pct_from_52w_high: Optional[float] = None  # e.g. -5.0 means within 5% of 52W high
    is_breakout_only: bool = False
    is_near_breakout_only: bool = False
    golden_cross_only: bool = False
    bollinger_squeeze_only: bool = False
    oversold_bounce_only: bool = False

    # ── AI Score & Action Filters ────────────
    min_score: Optional[float] = None         # Min composite AI score (0-100)
    min_fundamental_score: Optional[float] = None
    min_governance_score: Optional[float] = None
    min_rs_score: Optional[float] = None      # Relative Strength score (0-100)
    actions: Optional[list[str]] = None       # e.g. ["BUY_NOW", "WATCH"]
    min_expected_return_pct: Optional[float] = None # Min EV %
    min_rr_ratio: Optional[float] = None      # Min Risk:Reward ratio (e.g., 2.0 for 1:2)

    # ── Categorical & Sector Filters ─────────
    sector: Optional[str] = None
    symbols: Optional[list[str]] = None


# ─────────────────────────────────────────────
# Core Screener Evaluator
# ─────────────────────────────────────────────

def evaluate_symbol_for_screener(
    symbol: str,
    filters: ScreenerFilter,
    tech_cache: Optional[dict[str, IndicatorResult]] = None
) -> Optional[dict[str, Any]]:
    """
    Evaluates one symbol against the provided filters.
    Returns a enriched result dictionary if all filters pass, otherwise None.
    """
    # 1. Technical Indicators
    if tech_cache and symbol in tech_cache:
        tech = tech_cache[symbol]
    else:
        tech = compute_indicators(symbol)

    if not tech.sufficient_data and tech.data_rows < 30:
        return None

    # Technical Checks
    if filters.min_rsi is not None and tech.rsi < filters.min_rsi:
        return None
    if filters.max_rsi is not None and tech.rsi > filters.max_rsi:
        return None
    if filters.rsi_zone is not None and tech.rsi_zone != filters.rsi_zone:
        return None
    if filters.macd_bullish_only and not tech.macd_bullish:
        return None
    if filters.macd_crossover_only and not tech.macd_crossover_bullish:
        return None
    if filters.above_20dma is not None and tech.above_20dma != filters.above_20dma:
        return None
    if filters.above_50dma is not None and tech.above_50dma != filters.above_50dma:
        return None
    if filters.above_200dma is not None and tech.above_200dma != filters.above_200dma:
        return None
    if filters.min_volume_ratio is not None and tech.volume_ratio < filters.min_volume_ratio:
        return None
    if filters.max_pct_from_52w_high is not None and tech.pct_from_52w_high < filters.max_pct_from_52w_high:
        return None
    if filters.is_breakout_only and not tech.is_breakout:
        return None
    if filters.is_near_breakout_only and not tech.is_near_breakout:
        return None
    if filters.golden_cross_only and not tech.golden_cross:
        return None
    if filters.bollinger_squeeze_only and not tech.bb_squeeze:
        return None
    if filters.oversold_bounce_only and not tech.oversold_bounce:
        return None

    # 2. Fundamentals
    fund = fetch_screener_data(symbol)

    mcap = fund.market_cap_cr or 0.0
    if filters.min_market_cap_cr is not None and mcap < filters.min_market_cap_cr:
        return None
    if filters.max_market_cap_cr is not None and mcap > filters.max_market_cap_cr:
        return None

    pe = fund.pe_ratio or 0.0
    if filters.min_pe is not None and pe < filters.min_pe:
        return None
    if filters.max_pe is not None and (pe <= 0 or pe > filters.max_pe):
        return None

    pb = fund.pb_ratio or 0.0
    if filters.min_pb is not None and pb < filters.min_pb:
        return None
    if filters.max_pb is not None and pb > filters.max_pb:
        return None

    roe = fund.roe or 0.0
    if filters.min_roe is not None and roe < filters.min_roe:
        return None

    roce = fund.roce or 0.0
    if filters.min_roce is not None and roce < filters.min_roce:
        return None

    de = fund.debt_to_equity or 0.0
    if filters.max_debt_to_equity is not None and de > filters.max_debt_to_equity:
        return None

    pledge = fund.promoter_holding_pct or 0.0
    if filters.max_pledge_pct is not None and pledge > filters.max_pledge_pct:
        return None

    # 3. AI & Sub-Engine Scores
    fund_score_obj = compute_fundamental_score(fund)
    fund_score = fund_score_obj.total_score if hasattr(fund_score_obj, "total_score") else 50.0

    gov_score_obj = compute_governance_score(symbol, pledged_pct=fund.promoter_holding_pct, promoter_pct=fund.promoter_holding_pct)
    gov_score = gov_score_obj.total_100 if hasattr(gov_score_obj, "total_100") else 50.0

    val_score_obj = compute_valuation_score(fund)
    val_score = val_score_obj.total_100 if hasattr(val_score_obj, "total_100") else 50.0

    rs_obj = compute_rs_score(symbol)
    rs_score = rs_obj.score_100 if hasattr(rs_obj, "score_100") else 50.0

    if filters.min_fundamental_score is not None and fund_score < filters.min_fundamental_score:
        return None
    if filters.min_governance_score is not None and gov_score < filters.min_governance_score:
        return None
    if filters.min_rs_score is not None and rs_score < filters.min_rs_score:
        return None

    # Composite AI Score calculation
    # Composite formula: Tech (20) + RS (20) + Fund (20) + Gov (15) + Val (15) + Trend (10)
    tech_score = 100.0 if tech.signal == "BULLISH" else (60.0 if tech.signal == "NEUTRAL" else 20.0)
    trend_score = 100.0 if "UP" in tech.trend else (50.0 if tech.trend == "NEUTRAL" else 10.0)

    composite_score = round(
        0.20 * tech_score +
        0.20 * rs_score +
        0.20 * fund_score +
        0.15 * gov_score +
        0.15 * val_score +
        0.10 * trend_score,
        1
    )

    if filters.min_score is not None and composite_score < filters.min_score:
        return None

    # Determine Action & Recommendation
    if composite_score >= 70 and tech.above_50dma:
        action = "BUY_NOW"
    elif composite_score >= 55:
        action = "WATCH"
    elif composite_score <= 40:
        action = "EXIT"
    else:
        action = "HOLD"

    if filters.actions and action not in filters.actions:
        return None

    # Target & R:R via Expected Return engine
    stop_loss_val = round(tech.close - 2.0 * tech.atr, 2) if tech.atr > 0 else round(tech.close * 0.95, 2)
    exp_ret = compute_expected_return(
        symbol=symbol,
        current_price=tech.close,
        atr=tech.atr,
        stop_price=stop_loss_val,
        composite_score=composite_score
    )

    target_price = getattr(exp_ret, "target_price", round(tech.close * 1.10, 2))
    stop_loss = getattr(exp_ret, "stop_price", stop_loss_val)
    rr_ratio = getattr(exp_ret, "risk_reward", 2.0)
    ev_pct = getattr(exp_ret, "expected_value_pct", 3.5)

    if filters.min_expected_return_pct is not None and ev_pct < filters.min_expected_return_pct:
        return None
    if filters.min_rr_ratio is not None and rr_ratio < filters.min_rr_ratio:
        return None

    # Return structured result enriched for screener table & API
    return {
        "symbol": symbol,
        "name": symbol.replace(".NS", ""),
        "sector": "Equity",
        "market_cap_cr": mcap,
        "close": tech.close,
        "change_pct": tech.change_pct,
        "volume": tech.volume,
        "volume_ratio": tech.volume_ratio,
        "rsi": tech.rsi,
        "macd_bullish": tech.macd_bullish,
        "above_50dma": tech.above_50dma,
        "above_200dma": tech.above_200dma,
        "pct_from_52w_high": tech.pct_from_52w_high,
        "pe": pe,
        "pb": pb,
        "roe": roe,
        "roce": roce,
        "rs_score": rs_score,
        "fundamental_score": fund_score,
        "governance_score": gov_score,
        "valuation_score": val_score,
        "composite_score": composite_score,
        "action": action,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "rr_ratio": rr_ratio,
        "ev_pct": ev_pct,
        "trend": tech.trend,
        "signal": tech.signal,
    }


def filter_universe(
    filters: ScreenerFilter,
    symbols: Optional[list[str]] = None,
    sort_by: str = "composite_score",
    ascending: bool = False
) -> list[dict[str, Any]]:
    """
    Filters the equity universe against the ScreenerFilter criteria.
    Returns sorted list of symbol result dicts.
    """
    target_symbols = symbols or filters.symbols or EQUITY_UNIVERSE
    log.info(f"Screening {len(target_symbols)} symbols...")

    # Batch compute indicators for performance
    tech_cache = compute_all(target_symbols)

    matched = []
    for sym in target_symbols:
        res = evaluate_symbol_for_screener(sym, filters, tech_cache=tech_cache)
        if res is not None:
            matched.append(res)

    # Sort results
    matched.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=not ascending)
    log.info(f"Screening complete: {len(matched)} / {len(target_symbols)} matched.")
    return matched


if __name__ == "__main__":
    print("Testing Screener Engine with a sample filter (Min Score: 60, RSI: 40-70, Above 50DMA)...")
    sample_filter = ScreenerFilter(
        min_score=60.0,
        min_rsi=40.0,
        max_rsi=70.0,
        above_50dma=True
    )
    results = filter_universe(sample_filter)
    print(f"\nFound {len(results)} matching stocks:\n")
    print(f"  {'Symbol':<16} {'Score':>6} {'Action':<10} {'Close':>8} {'RSI':>6} {'PE':>6} {'Target':>8} {'R:R':>6}")
    print("  " + "─" * 75)
    for r in results[:15]:
        print(
            f"  {r['symbol']:<16} {r['composite_score']:>6.1f} {r['action']:<10} "
            f"{r['close']:>8.1f} {r['rsi']:>6.1f} {r['pe']:>6.1f} {r['target_price']:>8.1f} 1:{r['rr_ratio']:>4.1f}"
        )
