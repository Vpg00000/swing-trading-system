"""
Momentum ranking + ATR-based position sizing/stop calculation.
See DESIGN.md "Momentum ranking" and "Position sizing and stops" sections.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached
from config.universe import EQUITY_UNIVERSE, MIN_AVG_DAILY_TURNOVER_INR

TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
ATR_WINDOW = 14
STOP_ATR_MULTIPLE = 2.0
RISK_PER_TRADE_PCT = 0.0075  # 0.75% of capital risked per position


@dataclass
class Candidate:
    symbol: str
    close: float
    momentum_score: float
    ret_3m: float
    ret_6m: float
    avg_daily_turnover_inr: float
    atr: float
    stop_distance_pct: float
    stop_price: float
    position_size_inr: float
    vol_weighted_score: float = 0.0
    beta_adjusted_size_inr: float = 0.0


def compute_atr(df: pd.DataFrame, window: int = ATR_WINDOW) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1])


def momentum_score(df: pd.DataFrame) -> tuple[float, float, float]:
    close = df["Close"]
    if len(close) < TRADING_DAYS_6M + 1:
        return np.nan, np.nan, np.nan
    ret_3m = close.iloc[-1] / close.iloc[-TRADING_DAYS_3M] - 1
    ret_6m = close.iloc[-1] / close.iloc[-TRADING_DAYS_6M] - 1
    score = 0.4 * ret_3m + 0.6 * ret_6m
    return score, ret_3m, ret_6m


def compute_volume_weighted_momentum(df: pd.DataFrame) -> tuple[float, float, float, float]:
    """
    Calculates 3M/6M blended momentum scaled by 20-DMA volume confirmation factor.
    Returns: (vol_weighted_score, raw_score, ret_3m, ret_6m)
    Formula:
      raw_score = 0.4 * ret_3m + 0.6 * ret_6m
      vol_ratio = recent_volume / 20_day_avg_volume
      vol_factor = max(0.6, min(1.8, 0.8 + 0.4 * vol_ratio))
      vol_weighted_score = raw_score * vol_factor
    """
    raw_score, ret_3m, ret_6m = momentum_score(df)
    if np.isnan(raw_score):
        return np.nan, np.nan, np.nan, np.nan

    if "Volume" in df.columns and len(df["Volume"]) >= 20:
        vol_20ma = float(df["Volume"].tail(20).mean())
        recent_vol = float(df["Volume"].iloc[-1])
        vol_ratio = (recent_vol / vol_20ma) if vol_20ma > 0 else 1.0
        vol_factor = max(0.6, min(1.8, 0.8 + 0.4 * vol_ratio))
        vol_weighted_score = raw_score * vol_factor
    else:
        vol_weighted_score = raw_score

    return float(vol_weighted_score), float(raw_score), float(ret_3m), float(ret_6m)


def relative_strength_within_sector(
    symbol: str,
    sector_symbols: list[str],
    lookback_days: int = TRADING_DAYS_3M
) -> dict[str, Any]:
    """
    Computes relative strength ranking and percentile of symbol within its sector peers.
    Higher percentile (80-100) indicates the stock is a sector leader.
    """
    peer_returns = {}
    for sym in sector_symbols:
        df = load_cached(sym)
        if df.empty or len(df) < lookback_days + 1 or "Close" not in df.columns:
            continue
        c = df["Close"]
        ret = float((c.iloc[-1] / c.iloc[-lookback_days]) - 1.0)
        peer_returns[sym] = ret

    if not peer_returns or symbol not in peer_returns:
        return {
            "symbol": symbol,
            "percentile_rank": 50.0,
            "rank": 1,
            "total_peers": len(peer_returns),
            "symbol_return": 0.0,
            "is_sector_leader": False
        }

    sorted_peers = sorted(peer_returns.items(), key=lambda x: x[1], reverse=True)
    rank = next(idx + 1 for idx, (s, _) in enumerate(sorted_peers) if s == symbol)
    total_peers = len(sorted_peers)
    percentile = round(((total_peers - rank) / max(1, total_peers - 1)) * 100.0, 1) if total_peers > 1 else 100.0

    return {
        "symbol": symbol,
        "percentile_rank": percentile,
        "rank": rank,
        "total_peers": total_peers,
        "symbol_return": round(peer_returns[symbol] * 100.0, 2),
        "is_sector_leader": percentile >= 75.0
    }


def calculate_beta_adjusted_size(
    base_position_size: float,
    beta: float,
    target_beta: float = 1.0,
    min_scale: float = 0.5,
    max_scale: float = 1.5
) -> float:
    """
    Calculates beta-adjusted position size to equalize volatility risk across portfolio positions.
    High beta stocks (>1.5) get downscaled; low beta stocks (<0.8) get upscaled.
    """
    if beta <= 0 or np.isnan(beta):
        return base_position_size
    scale = target_beta / beta
    clipped_scale = max(min_scale, min(max_scale, scale))
    return round(base_position_size * clipped_scale, 2)


def evaluate_universe(capital_inr: float, symbols: list[str] = None) -> list[Candidate]:
    symbols = symbols or EQUITY_UNIVERSE
    risk_budget = capital_inr * RISK_PER_TRADE_PCT
    candidates = []

    for sym in symbols:
        df = load_cached(sym)
        if df.empty or len(df) < TRADING_DAYS_6M + 1:
            continue

        avg_turnover = float((df["Close"] * df["Volume"]).tail(20).mean())
        if avg_turnover < MIN_AVG_DAILY_TURNOVER_INR:
            continue  # liquidity filter

        vol_score, score, ret_3m, ret_6m = compute_volume_weighted_momentum(df)
        if np.isnan(score):
            continue

        atr = compute_atr(df)
        close = float(df["Close"].iloc[-1])
        if atr <= 0 or close <= 0:
            continue

        stop_distance_pct = (STOP_ATR_MULTIPLE * atr) / close
        stop_price = close - STOP_ATR_MULTIPLE * atr
        position_size = risk_budget / stop_distance_pct

        candidates.append(Candidate(
            symbol=sym,
            close=close,
            momentum_score=score,
            ret_3m=ret_3m,
            ret_6m=ret_6m,
            avg_daily_turnover_inr=avg_turnover,
            atr=atr,
            stop_distance_pct=stop_distance_pct,
            stop_price=stop_price,
            position_size_inr=position_size,
            vol_weighted_score=vol_score,
            beta_adjusted_size_inr=position_size,
        ))

    candidates.sort(key=lambda c: c.momentum_score, reverse=True)
    return candidates


def compute_atr_adaptive(df: pd.DataFrame, base_window: int = 14, vix: Optional[float] = None) -> float:
    """
    Computes volatility-smoothed ATR. Uses longer lookback windows (21, 30 days)
    during high volatility regimes (VIX > 25) to prevent whipsaw stop-outs,
    and tighter multiplier in low volatility (VIX < 12).
    """
    atr_14 = compute_atr(df, base_window)
    atr_21 = compute_atr(df, 21) if len(df) >= 22 else atr_14
    atr_30 = compute_atr(df, 30) if len(df) >= 31 else atr_21

    if vix is None:
        try:
            from config.universe import INDIA_VIX
            vix_df = load_cached(INDIA_VIX)
            if not vix_df.empty and "Close" in vix_df.columns:
                vix = float(vix_df["Close"].iloc[-1])
            else:
                vix = 15.0
        except Exception:
            vix = 15.0

    if vix > 25.0:
        return round((atr_21 + atr_30) / 2.0, 2)
    elif vix < 12.0:
        return round(atr_14 * 0.9, 2)
    else:
        return round(atr_14, 2)


def score_with_earnings_forward(candidate: Candidate, days_to_earnings: Optional[int] = None) -> float:
    """
    Reduces momentum confidence score for stocks with imminent earnings announcements
    (where binary event variance dominates momentum factor).
    """
    if days_to_earnings is None:
        days_to_earnings = getattr(candidate, "days_to_earnings", None)

    if days_to_earnings is None:
        return candidate.momentum_score

    if days_to_earnings < 7:
        return round(candidate.momentum_score * 0.60, 4)
    elif days_to_earnings < 14:
        return round(candidate.momentum_score * 0.75, 4)
    elif days_to_earnings < 21:
        return round(candidate.momentum_score * 0.85, 4)
    else:
        return round(candidate.momentum_score, 4)


def filter_earnings_candidates(
    ranked: list[Candidate],
    earnings_lookup: Optional[dict[str, int]] = None,
    min_days: int = 7,
    max_days: int = 45
) -> list[Candidate]:
    """
    Filters out candidates with scheduled earnings inside the event window
    to eliminate binary event shock risk.
    """
    if not earnings_lookup:
        return ranked

    filtered = []
    for c in ranked:
        days = earnings_lookup.get(c.symbol)
        if days is not None and min_days <= days <= max_days:
            continue
        filtered.append(c)
    return filtered


def rebalance_momentum_portfolio(
    current_holdings: dict[str, float],
    ranked_candidates: list[Candidate],
    target_count: int = 6,
    max_turnover_pct: float = 0.20,
    total_portfolio_value: Optional[float] = None
) -> dict[str, Any]:
    """
    Active weekly momentum portfolio rebalancer with turnover constraints.
    Rebalances capital across top ranked momentum candidates while capping turnover
    to control transaction drag and slippage.
    """
    current_symbols = set(current_holdings.keys())
    curr_val = total_portfolio_value if total_portfolio_value is not None else sum(current_holdings.values())
    if curr_val <= 0:
        curr_val = sum(c.position_size_inr for c in ranked_candidates[:target_count])

    top_candidates = ranked_candidates[:target_count]
    target_symbols = {c.symbol for c in top_candidates}
    target_slot_val = curr_val / max(1, target_count)

    raw_targets: dict[str, float] = {}
    for c in top_candidates:
        raw_targets[c.symbol] = target_slot_val

    # Calculate raw turnover required
    all_syms = current_symbols | set(raw_targets.keys())
    raw_turnover_inr = sum(abs(raw_targets.get(s, 0.0) - current_holdings.get(s, 0.0)) for s in all_syms) / 2.0
    raw_turnover_pct = raw_turnover_inr / curr_val if curr_val > 0 else 0.0

    if raw_turnover_pct > max_turnover_pct and curr_val > 0:
        # Scale towards target using hybrid turnover cap
        scale = (max_turnover_pct * curr_val) / max(1.0, raw_turnover_inr)
        adjusted_targets: dict[str, float] = {}
        for s in all_syms:
            cur = current_holdings.get(s, 0.0)
            tar = raw_targets.get(s, 0.0)
            new_val = cur + (tar - cur) * min(1.0, scale)
            if new_val > 100.0:  # prune negligible amounts
                adjusted_targets[s] = round(new_val, 2)
        effective_targets = adjusted_targets
        turnover_inr = sum(abs(effective_targets.get(s, 0.0) - current_holdings.get(s, 0.0)) for s in all_syms) / 2.0
        turnover_pct = turnover_inr / curr_val
    else:
        effective_targets = {k: round(v, 2) for k, v in raw_targets.items()}
        turnover_inr = raw_turnover_inr
        turnover_pct = raw_turnover_pct

    exits = [s for s in current_symbols if s not in effective_targets]
    entries = [s for s in effective_targets if s not in current_symbols]
    rebalanced_syms = list(effective_targets.keys())

    # Transaction cost model: 20 bps on total traded volume (buys + sells)
    est_cost_inr = round(turnover_inr * 2.0 * 0.0020, 2)

    return {
        "status": "SUCCESS",
        "portfolio_value_inr": round(curr_val, 2),
        "target_holdings": effective_targets,
        "turnover_inr": round(turnover_inr, 2),
        "turnover_pct": round(turnover_pct * 100.0, 2),
        "max_turnover_pct": round(max_turnover_pct * 100.0, 2),
        "turnover_capped": raw_turnover_pct > max_turnover_pct,
        "estimated_cost_inr": est_cost_inr,
        "rebalanced_symbols": rebalanced_syms,
        "entries": entries,
        "exits": exits
    }


if __name__ == "__main__":
    CAPITAL = 1_00_00_000  # Rs 1 crore
    ranked = evaluate_universe(CAPITAL)
    print(f"{len(ranked)} candidates passed the liquidity filter.\n")
    print(f"{'Symbol':<16}{'Close':>10}{'3M%':>8}{'6M%':>8}{'ATR':>8}{'Stop':>10}{'Size(Rs L)':>12}")
    for c in ranked[:15]:
        print(f"{c.symbol:<16}{c.close:>10.1f}{c.ret_3m*100:>7.1f}%{c.ret_6m*100:>7.1f}%"
              f"{c.atr:>8.1f}{c.stop_price:>10.1f}{c.position_size_inr/1e5:>12.2f}")
