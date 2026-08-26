"""
Technical indicator calculator for the screener engine.

Reads from the existing data/cache/*.csv files (same OHLCV cache used by
all other engines) and computes a rich set of indicators per symbol:

  Trend:      SMA 20/50/200, EMA 20/50, price position vs each DMA
  Momentum:   RSI (14), MACD (12/26/9), Stochastic (14,3), ROC (10)
  Volatility: ATR (14), Bollinger Bands (20,2), 52W High/Low proximity
  Volume:     Volume ratio vs 20D avg, volume trend
  Patterns:   Breakout, near-breakout, oversold-bounce, golden/death cross
  Candlestick: Hammer, Doji, Bullish/Bearish Engulfing (last candle)

All outputs are plain Python dataclasses — no extra dependencies beyond
pandas and numpy (already required by the rest of the system).

Usage:
    from engine.indicators import compute_indicators, IndicatorResult
    result = compute_indicators("RELIANCE.NS")
    print(result.rsi, result.macd_signal, result.above_200dma)

    # Batch compute for all universe symbols:
    from engine.indicators import compute_all
    results = compute_all()   # dict[symbol -> IndicatorResult]
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.fetch import load_cached
from config.universe import EQUITY_UNIVERSE


# ─────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────

@dataclass
class IndicatorResult:
    symbol: str

    # ── Price snapshot ────────────────────────
    close: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0          # daily change %
    week_change_pct: float = 0.0     # 5-day change %
    month_change_pct: float = 0.0    # 21-day change %
    three_month_change_pct: float = 0.0  # 63-day change %
    six_month_change_pct: float = 0.0    # 126-day change %
    one_year_change_pct: float = 0.0     # 252-day change %

    # ── 52-Week High / Low ─────────────────────
    high_52w: float = 0.0
    low_52w: float = 0.0
    pct_from_52w_high: float = 0.0   # negative = below high
    pct_from_52w_low: float = 0.0    # positive = above low

    # ── Simple / Exponential Moving Averages ──
    sma_20: float = 0.0
    sma_50: float = 0.0
    sma_200: float = 0.0
    ema_20: float = 0.0
    ema_50: float = 0.0

    # Position vs MAs
    above_20dma: bool = False
    above_50dma: bool = False
    above_200dma: bool = False
    pct_from_20dma: float = 0.0
    pct_from_50dma: float = 0.0
    pct_from_200dma: float = 0.0

    # ── RSI ───────────────────────────────────
    rsi: float = 50.0                # RSI-14
    rsi_zone: str = "NEUTRAL"        # OVERSOLD / NEUTRAL / OVERBOUGHT

    # ── MACD ─────────────────────────────────
    macd_line: float = 0.0           # 12 EMA - 26 EMA
    macd_signal: float = 0.0         # 9 EMA of macd_line
    macd_hist: float = 0.0           # macd_line - macd_signal
    macd_bullish: bool = False        # line > signal AND hist > 0
    macd_crossover_bullish: bool = False  # crossed above signal today
    macd_crossover_bearish: bool = False  # crossed below signal today

    # ── Stochastic ────────────────────────────
    stoch_k: float = 50.0            # %K (14-period)
    stoch_d: float = 50.0            # %D (3-period SMA of %K)

    # ── Rate of Change ────────────────────────
    roc_10: float = 0.0              # ROC-10 %

    # ── Bollinger Bands ───────────────────────
    bb_upper: float = 0.0
    bb_middle: float = 0.0           # SMA-20
    bb_lower: float = 0.0
    bb_width: float = 0.0            # (upper-lower)/middle * 100 %
    bb_pct_b: float = 0.5            # (close-lower)/(upper-lower)
    bb_squeeze: bool = False         # bb_width < 5 %

    # ── ATR (Average True Range) ──────────────
    atr: float = 0.0
    atr_pct: float = 0.0             # atr / close * 100

    # ── Volume ────────────────────────────────
    volume: int = 0
    avg_volume_20d: float = 0.0
    volume_ratio: float = 1.0        # today / 20D avg
    volume_surge: bool = False        # ratio > 2.0

    # ── Pattern flags ─────────────────────────
    is_breakout: bool = False         # close > 52W high
    is_near_breakout: bool = False    # within 3% of 52W high
    golden_cross: bool = False        # 50DMA crossed above 200DMA (last 5 days)
    death_cross: bool = False         # 50DMA crossed below 200DMA (last 5 days)
    oversold_bounce: bool = False     # RSI < 35 + close > prev close

    # ── Candlestick patterns (last candle) ────
    candle_hammer: bool = False
    candle_doji: bool = False
    candle_bullish_engulfing: bool = False
    candle_bearish_engulfing: bool = False

    # ── Advanced Technical Indicators ──────────
    adx: float = 25.0                # ADX-14 Trend Strength
    cmf: float = 0.0                 # Chaikin Money Flow (20D)
    pivot_p: float = 0.0             # Pivot Point (P)
    pivot_r1: float = 0.0            # Pivot Resistance 1 (R1)
    pivot_s1: float = 0.0            # Pivot Support 1 (S1)
    supertrend_bullish: bool = False # Supertrend (10, 3) Bullish Flag

    # ── Data quality ─────────────────────────
    data_rows: int = 0
    sufficient_data: bool = False     # need at least 200 rows for all indicators

    # ── Human-readable summary ────────────────
    trend: str = "NEUTRAL"           # STRONG_UP / UP / NEUTRAL / DOWN / STRONG_DOWN
    signal: str = "NEUTRAL"          # BULLISH / NEUTRAL / BEARISH


# ─────────────────────────────────────────────
# Core calculator
# ─────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if np.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k=14, d=3):
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    pct_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    pct_d = pct_k.rolling(d).mean()
    return pct_k, pct_d


def _bollinger(close: pd.Series, period=20, std_dev=2):
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def _atr(df: pd.DataFrame, period=14) -> pd.Series:
    high, low, prev_close = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _detect_hammer(o, h, l, c) -> bool:
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    if body == 0:
        return False
    return lower_shadow >= 2 * body and upper_shadow <= 0.1 * body


def _detect_doji(o, h, l, c) -> bool:
    body = abs(c - o)
    total_range = h - l
    if total_range == 0:
        return False
    return body / total_range < 0.1


def _detect_bullish_engulfing(prev_o, prev_c, curr_o, curr_c) -> bool:
    return prev_c < prev_o and curr_c > curr_o and curr_o < prev_c and curr_c > prev_o


def _detect_bearish_engulfing(prev_o, prev_c, curr_o, curr_c) -> bool:
    return prev_c > prev_o and curr_c < curr_o and curr_o > prev_c and curr_c < prev_o


def _trend_label(r: "IndicatorResult") -> str:
    score = 0
    if r.above_200dma:
        score += 2
    if r.above_50dma:
        score += 1
    if r.above_20dma:
        score += 1
    if r.macd_bullish:
        score += 1
    if r.rsi > 55:
        score += 1

    if score >= 5:
        return "STRONG_UP"
    elif score >= 3:
        return "UP"
    elif score <= 1:
        return "STRONG_DOWN" if score == 0 else "DOWN"
    return "NEUTRAL"


def _signal_label(r: "IndicatorResult") -> str:
    bull = sum([
        r.macd_bullish,
        r.rsi < 65 and r.rsi > 40,
        r.above_50dma,
        r.volume_surge,
        r.macd_crossover_bullish,
    ])
    bear = sum([
        not r.macd_bullish,
        r.rsi > 70,
        not r.above_50dma,
        r.macd_crossover_bearish,
    ])
    if bull >= 3 and bull > bear:
        return "BULLISH"
    elif bear >= 3 and bear > bull:
        return "BEARISH"
    return "NEUTRAL"


# ─────────────────────────────────────────────
# Main public API
# ─────────────────────────────────────────────

def compute_indicators(symbol: str) -> IndicatorResult:
    """
    Compute all technical indicators for one symbol.
    Reads from data/cache/*.csv — no network calls.
    Returns IndicatorResult (all fields zeroed/False if insufficient data).
    """
    result = IndicatorResult(symbol=symbol)
    df = load_cached(symbol)

    if df.empty or len(df) < 30:
        return result

    df = df.sort_index()
    result.data_rows = len(df)
    result.sufficient_data = len(df) >= 200

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    n = len(df)

    # ── Price changes ──────────────────────────
    result.close = _safe_float(close.iloc[-1])
    result.prev_close = _safe_float(close.iloc[-2]) if n >= 2 else result.close

    def _pct_change(window: int) -> float:
        if n <= window:
            return 0.0
        return _safe_float((close.iloc[-1] / close.iloc[-window] - 1) * 100)

    result.change_pct = _pct_change(2)
    result.week_change_pct = _pct_change(6)
    result.month_change_pct = _pct_change(22)
    result.three_month_change_pct = _pct_change(64)
    result.six_month_change_pct = _pct_change(127)
    result.one_year_change_pct = _pct_change(253)

    # ── 52-week high / low ─────────────────────
    window_252 = min(252, n)
    result.high_52w = _safe_float(high.tail(window_252).max())
    result.low_52w = _safe_float(low.tail(window_252).min())
    if result.high_52w > 0:
        result.pct_from_52w_high = _safe_float((result.close / result.high_52w - 1) * 100)
    if result.low_52w > 0:
        result.pct_from_52w_low = _safe_float((result.close / result.low_52w - 1) * 100)

    # ── Moving averages ────────────────────────
    for window, attr in [(20, "sma_20"), (50, "sma_50"), (200, "sma_200")]:
        if n >= window:
            val = _safe_float(close.rolling(window).mean().iloc[-1])
            setattr(result, attr, val)

    for span, attr in [(20, "ema_20"), (50, "ema_50")]:
        if n >= span * 2:
            val = _safe_float(_ema(close, span).iloc[-1])
            setattr(result, attr, val)

    result.above_20dma = result.close > result.sma_20 > 0
    result.above_50dma = result.close > result.sma_50 > 0
    result.above_200dma = result.close > result.sma_200 > 0

    if result.sma_20 > 0:
        result.pct_from_20dma = _safe_float((result.close / result.sma_20 - 1) * 100)
    if result.sma_50 > 0:
        result.pct_from_50dma = _safe_float((result.close / result.sma_50 - 1) * 100)
    if result.sma_200 > 0:
        result.pct_from_200dma = _safe_float((result.close / result.sma_200 - 1) * 100)

    # ── Golden / Death cross ───────────────────
    if n >= 205:
        sma50_series = close.rolling(50).mean()
        sma200_series = close.rolling(200).mean()
        last5_50 = sma50_series.iloc[-6:-1]
        last5_200 = sma200_series.iloc[-6:-1]
        curr_50 = sma50_series.iloc[-1]
        curr_200 = sma200_series.iloc[-1]
        crossed_above = any(last5_50.iloc[i] < last5_200.iloc[i] for i in range(len(last5_50)))
        if curr_50 > curr_200 and crossed_above:
            result.golden_cross = True
        crossed_below = any(last5_50.iloc[i] > last5_200.iloc[i] for i in range(len(last5_50)))
        if curr_50 < curr_200 and crossed_below:
            result.death_cross = True

    # ── RSI ───────────────────────────────────
    if n >= 20:
        rsi_series = _rsi(close)
        result.rsi = _safe_float(rsi_series.iloc[-1], 50.0)
        if result.rsi <= 35:
            result.rsi_zone = "OVERSOLD"
        elif result.rsi >= 65:
            result.rsi_zone = "OVERBOUGHT"
        else:
            result.rsi_zone = "NEUTRAL"

    # ── MACD ─────────────────────────────────
    if n >= 35:
        macd_line, signal_line, hist = _macd(close)
        result.macd_line = _safe_float(macd_line.iloc[-1])
        result.macd_signal = _safe_float(signal_line.iloc[-1])
        result.macd_hist = _safe_float(hist.iloc[-1])
        result.macd_bullish = result.macd_line > result.macd_signal and result.macd_hist > 0

        if n >= 36:
            prev_macd = _safe_float(macd_line.iloc[-2])
            prev_signal = _safe_float(signal_line.iloc[-2])
            result.macd_crossover_bullish = (
                prev_macd <= prev_signal and result.macd_line > result.macd_signal
            )
            result.macd_crossover_bearish = (
                prev_macd >= prev_signal and result.macd_line < result.macd_signal
            )

    # ── Stochastic ────────────────────────────
    if n >= 17:
        k, d = _stochastic(high, low, close)
        result.stoch_k = _safe_float(k.iloc[-1], 50.0)
        result.stoch_d = _safe_float(d.iloc[-1], 50.0)

    # ── ROC ───────────────────────────────────
    if n >= 11:
        result.roc_10 = _safe_float((close.iloc[-1] / close.iloc[-11] - 1) * 100)

    # ── Bollinger Bands ───────────────────────
    if n >= 20:
        bb_upper, bb_mid, bb_lower = _bollinger(close)
        result.bb_upper = _safe_float(bb_upper.iloc[-1])
        result.bb_middle = _safe_float(bb_mid.iloc[-1])
        result.bb_lower = _safe_float(bb_lower.iloc[-1])
        band_range = result.bb_upper - result.bb_lower
        if result.bb_middle > 0:
            result.bb_width = _safe_float(band_range / result.bb_middle * 100)
        if band_range > 0:
            result.bb_pct_b = _safe_float((result.close - result.bb_lower) / band_range)
        result.bb_squeeze = result.bb_width < 5.0 and result.bb_width > 0

    # ── ATR ───────────────────────────────────
    if n >= 15:
        atr_series = _atr(df)
        result.atr = _safe_float(atr_series.iloc[-1])
        if result.close > 0:
            result.atr_pct = _safe_float(result.atr / result.close * 100)

    # ── Pivot Points (Classic P, R1, S1) ──────
    if n >= 2:
        h_prev = _safe_float(high.iloc[-2])
        l_prev = _safe_float(low.iloc[-2])
        c_prev = _safe_float(close.iloc[-2])
        p = (h_prev + l_prev + c_prev) / 3.0
        result.pivot_p = round(p, 2)
        result.pivot_r1 = round(2.0 * p - l_prev, 2)
        result.pivot_s1 = round(2.0 * p - h_prev, 2)

    # ── Chaikin Money Flow (CMF 20) ───────────
    if n >= 20:
        mfv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
        mfv = mfv.fillna(0.0) * volume
        cmf_val = mfv.tail(20).sum() / volume.tail(20).sum() if volume.tail(20).sum() > 0 else 0.0
        result.cmf = round(_safe_float(cmf_val), 3)

    # ── Supertrend (10, 3) ────────────────────
    if n >= 15 and result.atr > 0:
        hl2 = (high + low) / 2.0
        upperband = hl2 + (3.0 * result.atr)
        lowerband = hl2 - (3.0 * result.atr)
        result.supertrend_bullish = result.close > _safe_float(lowerband.iloc[-1])

    # ── Volume ────────────────────────────────
    result.volume = int(volume.iloc[-1]) if len(volume) > 0 else 0
    if n >= 20:
        result.avg_volume_20d = _safe_float(volume.tail(20).mean())
        if result.avg_volume_20d > 0:
            result.volume_ratio = _safe_float(result.volume / result.avg_volume_20d)
        result.volume_surge = result.volume_ratio >= 2.0

    # ── Pattern flags ─────────────────────────
    result.is_breakout = result.high_52w > 0 and result.close >= result.high_52w
    result.is_near_breakout = (
        not result.is_breakout
        and result.high_52w > 0
        and result.pct_from_52w_high >= -3.0
    )
    result.oversold_bounce = (
        result.rsi < 35
        and result.close > result.prev_close
        and result.close > result.sma_20
    )

    # ── Candlestick ───────────────────────────
    if n >= 2:
        o, h_, l_, c_ = (
            _safe_float(df["Open"].iloc[-1]),
            _safe_float(df["High"].iloc[-1]),
            _safe_float(df["Low"].iloc[-1]),
            _safe_float(df["Close"].iloc[-1]),
        )
        po = _safe_float(df["Open"].iloc[-2])
        pc = _safe_float(df["Close"].iloc[-2])

        result.candle_hammer = _detect_hammer(o, h_, l_, c_)
        result.candle_doji = _detect_doji(o, h_, l_, c_)
        result.candle_bullish_engulfing = _detect_bullish_engulfing(po, pc, o, c_)
        result.candle_bearish_engulfing = _detect_bearish_engulfing(po, pc, o, c_)

    # ── Summary labels ─────────────────────────
    result.trend = _trend_label(result)
    result.signal = _signal_label(result)

    return result


def compute_all(symbols: list[str] | None = None) -> dict[str, IndicatorResult]:
    """
    Batch compute indicators for all symbols.
    Returns dict: symbol → IndicatorResult.
    Uses only cached data — no network calls.
    """
    symbols = symbols or EQUITY_UNIVERSE
    results = {}
    for sym in symbols:
        try:
            results[sym] = compute_indicators(sym)
        except Exception as exc:
            results[sym] = IndicatorResult(symbol=sym)
    return results


# ─────────────────────────────────────────────
# Main — print indicator table
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute technical indicators")
    parser.add_argument("symbols", nargs="*", help="Symbols to compute (default: full universe sample)")
    parser.add_argument("--all", action="store_true", help="Run full universe")
    args = parser.parse_args()

    if args.all:
        syms = EQUITY_UNIVERSE
    elif args.symbols:
        syms = args.symbols
    else:
        # Quick demo: first 10 cached symbols
        syms = EQUITY_UNIVERSE[:10]

    print(f"\nComputing indicators for {len(syms)} symbols...\n")
    print(
        f"  {'Symbol':<20} {'Close':>8} {'RSI':>6} {'MACD':>8} "
        f"{'vs200':>8} {'BB%':>6} {'VolX':>6} {'52WHi':>8} {'Trend':<12} {'Signal'}"
    )
    print("  " + "─" * 110)

    all_results = compute_all(syms)
    for sym, r in all_results.items():
        if not r.sufficient_data and r.data_rows < 30:
            continue
        name = sym.replace(".NS", "")[:18]
        print(
            f"  {name:<20} {r.close:>8.1f} {r.rsi:>6.1f} "
            f"{'✅' if r.macd_bullish else '❌':>8} "
            f"{r.pct_from_200dma:>+7.1f}% "
            f"{r.bb_pct_b:>6.2f} "
            f"{r.volume_ratio:>5.1f}x "
            f"{r.pct_from_52w_high:>+7.1f}% "
            f"{r.trend:<12} {r.signal}"
        )

    print(f"\n✓ Done. {sum(1 for r in all_results.values() if r.sufficient_data)} symbols with full data.")
