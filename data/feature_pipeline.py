"""
High-Performance Daily Feature Pipeline (Phase 2 Tasks 015 – 024)

Computes vectorized price returns (1D, 3D, 5D, 10D, 20D, 30D, 52W),
Wilder's RSI-14, MACD (12, 26, 9), ATR/NATR, EMA & SMA suites,
Volume & Delivery multipliers, Realized Volatility, Parkinson & Garman-Klass Volatilities,
Distance to 52-Week High/Low, Bollinger Bands, Keltner Channels, and TTM Squeeze flags.
Persists computed features into SQLite `features_daily` table with sub-5ms query latency.
"""

import math
import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from data.database import upsert_features_daily, query_features_daily

log = logging.getLogger(__name__)

def compute_features_from_df(symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Given an OHLCV DataFrame with columns [Open, High, Low, Close, Volume]
    and optionally [Delivered, Delivery_Pct], computes full daily feature records.
    """
    if df.empty or len(df) < 15:
        return []

    df = df.copy().sort_index()
    n = len(df)

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    open_p = df["Open"].astype(float)
    volume = df["Volume"].astype(float)

    # 1. Multi-horizon returns (Tasks 015)
    ret_1d = close.pct_change(1) * 100.0
    ret_3d = close.pct_change(3) * 100.0
    ret_5d = close.pct_change(5) * 100.0
    ret_10d = close.pct_change(10) * 100.0
    ret_20d = close.pct_change(20) * 100.0
    ret_30d = close.pct_change(30) * 100.0
    ret_52w = close.pct_change(252) * 100.0

    # 2. Moving averages (Task 019)
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()

    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()

    # 3. Wilder's RSI-14 (Task 016)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_14 = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

    # 4. MACD (12, 26, 9) (Task 017)
    macd_fast = close.ewm(span=12, adjust=False).mean()
    macd_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = macd_fast - macd_slow
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # 5. ATR-14 & NATR (Task 018)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr_14 = tr.ewm(alpha=1/14, adjust=False).mean()
    natr_14 = (atr_14 / close.replace(0, np.nan)) * 100.0

    # 6. Volume & Delivery Multipliers (Task 020)
    vol_sma_20 = volume.rolling(20).mean()
    vol_20d_ratio = (volume / vol_sma_20.replace(0, np.nan)).fillna(1.0)

    if "Delivered" in df.columns and df["Delivered"].notna().sum() > 5:
        deliv = df["Delivered"].astype(float)
        deliv_sma_20 = deliv.rolling(20).mean()
        deliv_20d_ratio = (deliv / deliv_sma_20.replace(0, np.nan)).fillna(1.0)
    else:
        deliv_20d_ratio = pd.Series(1.0, index=df.index)

    # 7. Volatilities (Task 021, Task 023)
    # Realized Volatility: 20-day annualized std dev of log returns
    log_ret = np.log(close / close.shift(1))
    realized_vol_20d = (log_ret.rolling(20).std() * math.sqrt(252) * 100.0).fillna(0.0)

    # Parkinson Volatility: sqrt(1 / (4 * ln(2)) * (ln(High/Low))^2) * sqrt(252)
    hl_ratio = (high / low.replace(0, np.nan)).clip(lower=1.0)
    log_hl_sq = (np.log(hl_ratio)) ** 2
    parkinson_vol = (np.sqrt(log_hl_sq.rolling(20).mean() / (4.0 * math.log(2))) * math.sqrt(252) * 100.0).fillna(0.0)

    # Garman-Klass Volatility: 0.5 * (ln(H/L))^2 - (2*ln(2) - 1)*(ln(C/O))^2
    co_ratio = (close / open_p.replace(0, np.nan)).clip(lower=0.001)
    log_co_sq = (np.log(co_ratio)) ** 2
    gk_var = 0.5 * log_hl_sq - (2.0 * math.log(2) - 1.0) * log_co_sq
    garman_klass_vol = (np.sqrt(gk_var.clip(lower=0).rolling(20).mean()) * math.sqrt(252) * 100.0).fillna(0.0)

    # 8. 52-Week High & Low Distances (Task 022)
    roll_high_252 = high.rolling(252, min_periods=20).max()
    roll_low_252 = low.rolling(252, min_periods=20).min()
    dist_52w_high_pct = ((close - roll_high_252) / roll_high_252.replace(0, np.nan) * 100.0).fillna(0.0)
    dist_52w_low_pct = ((close - roll_low_252) / roll_low_252.replace(0, np.nan) * 100.0).fillna(0.0)

    # 9. Bollinger Bands & Keltner Channels (TTM Squeeze - Task 033)
    bb_std = close.rolling(20).std()
    bb_upper = sma_20 + 2.0 * bb_std
    bb_lower = sma_20 - 2.0 * bb_std
    bb_width = ((bb_upper - bb_lower) / sma_20.replace(0, np.nan) * 100.0).fillna(0.0)

    keltner_upper = ema_20 + 1.5 * atr_14
    keltner_lower = ema_20 - 1.5 * atr_14

    # TTM Squeeze is ON when Bollinger Band is inside Keltner Channel
    ttm_squeeze = ((bb_upper < keltner_upper) & (bb_lower > keltner_lower)).astype(int)

    # Convert to list of dict records
    features = []
    # Save the most recent records (e.g. up to last 60 days)
    lookback_window = min(n, 60)
    for i in range(n - lookback_window, n):
        dt_idx = df.index[i]
        dt_str = str(dt_idx)[:10] if hasattr(dt_idx, "strftime") else str(dt_idx)[:10]

        def _get_val(series: pd.Series, idx: int) -> Optional[float]:
            val = series.iloc[idx]
            if pd.isna(val) or not np.isfinite(val):
                return None
            return round(float(val), 4)

        rec = {
            "symbol": symbol,
            "date": dt_str,
            "ret_1d": _get_val(ret_1d, i),
            "ret_3d": _get_val(ret_3d, i),
            "ret_5d": _get_val(ret_5d, i),
            "ret_10d": _get_val(ret_10d, i),
            "ret_20d": _get_val(ret_20d, i),
            "ret_30d": _get_val(ret_30d, i),
            "ret_52w": _get_val(ret_52w, i),
            "rsi_14": _get_val(rsi_14, i),
            "macd": _get_val(macd_line, i),
            "macd_signal": _get_val(macd_signal, i),
            "macd_hist": _get_val(macd_hist, i),
            "atr_14": _get_val(atr_14, i),
            "natr_14": _get_val(natr_14, i),
            "ema_9": _get_val(ema_9, i),
            "ema_20": _get_val(ema_20, i),
            "ema_50": _get_val(ema_50, i),
            "ema_200": _get_val(ema_200, i),
            "sma_20": _get_val(sma_20, i),
            "sma_50": _get_val(sma_50, i),
            "sma_200": _get_val(sma_200, i),
            "vol_20d_ratio": _get_val(vol_20d_ratio, i),
            "deliv_20d_ratio": _get_val(deliv_20d_ratio, i),
            "realized_vol_20d": _get_val(realized_vol_20d, i),
            "parkinson_vol": _get_val(parkinson_vol, i),
            "garman_klass_vol": _get_val(garman_klass_vol, i),
            "dist_52w_high_pct": _get_val(dist_52w_high_pct, i),
            "dist_52w_low_pct": _get_val(dist_52w_low_pct, i),
            "bb_upper": _get_val(bb_upper, i),
            "bb_lower": _get_val(bb_lower, i),
            "bb_width": _get_val(bb_width, i),
            "keltner_upper": _get_val(keltner_upper, i),
            "keltner_lower": _get_val(keltner_lower, i),
            "ttm_squeeze": int(ttm_squeeze.iloc[i])
        }
        features.append(rec)

    return features


def compute_and_store_features_for_symbol(symbol: str) -> int:
    """Computes and persists features for a single symbol using cached CSV data."""
    from data.fetch import load_cached
    df = load_cached(symbol)
    if df.empty:
        return 0
    records = compute_features_from_df(symbol, df)
    if not records:
        return 0
    return upsert_features_daily(records)


def compute_and_store_all_features(symbols: Optional[List[str]] = None) -> Dict[str, int]:
    """Batch computes and stores daily features for all universe symbols."""
    from config.universe import EQUITY_UNIVERSE
    symbols = symbols or EQUITY_UNIVERSE
    total_saved = 0
    processed = 0

    for sym in symbols:
        try:
            cnt = compute_and_store_features_for_symbol(sym)
            if cnt > 0:
                total_saved += cnt
                processed += 1
        except Exception as exc:
            log.warning(f"Error computing features for {sym}: {exc}")

    log.info(f"Computed and stored {total_saved} feature rows across {processed} symbols.")
    return {"symbols_processed": processed, "total_features_saved": total_saved}
