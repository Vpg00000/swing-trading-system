"""
engine/indicator_calculator.py — Dynamic Technical Indicator Calculator.

Calculates technical indicators (EMA, RSI, MACD, Bollinger Bands) for any candle dataset.
"""

from typing import List, Dict, Any, Union, Optional
import pandas as pd
import numpy as np


def calculate_indicators(candles: Union[pd.DataFrame, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Calculates technical indicators (EMA 9/20/50/200, RSI 14, MACD 12/26/9, Bollinger Bands 20/2)
    from a given OHLCV dataset.

    Args:
        candles: DataFrame or list of dicts with 'close' / 'Close', 'high' / 'High', 'low' / 'Low', 'open' / 'Open', 'volume' / 'Volume'.

    Returns:
        Dict containing current indicator values and historic series.
    """
    if isinstance(candles, list):
        if not candles:
            return _empty_indicators_result()
        df = pd.DataFrame(candles)
    elif isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        return _empty_indicators_result()

    if df.empty:
        return _empty_indicators_result()

    # Normalize column names to title case
    col_map = {col: col.capitalize() for col in df.columns}
    df.rename(columns=col_map, inplace=True)

    if "Close" not in df.columns:
        return _empty_indicators_result()

    close = pd.to_numeric(df["Close"], errors="coerce").fillna(method="ffill").fillna(0.0)

    # 1. Exponential Moving Averages (EMA)
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean() if len(df) >= 50 else close.ewm(span=len(df), adjust=False).mean()

    # 2. Relative Strength Index (RSI 14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_14 = 100 - (100 / (1 + rs))
    rsi_14 = rsi_14.fillna(50.0)

    # 3. Moving Average Convergence Divergence (MACD 12, 26, 9)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal

    # 4. Bollinger Bands (20, 2 std)
    bb_middle = close.rolling(window=20, min_periods=1).mean()
    bb_std = close.rolling(window=20, min_periods=1).std().fillna(0.0)
    bb_upper = bb_middle + (bb_std * 2.0)
    bb_lower = bb_middle - (bb_std * 2.0)

    latest_close = float(close.iloc[-1])
    latest_ema9 = float(ema_9.iloc[-1])
    latest_ema20 = float(ema_20.iloc[-1])
    latest_ema50 = float(ema_50.iloc[-1])
    latest_ema200 = float(ema_200.iloc[-1])
    latest_rsi = float(rsi_14.iloc[-1])
    latest_macd = float(macd_line.iloc[-1])
    latest_signal = float(macd_signal.iloc[-1])
    latest_hist = float(macd_hist.iloc[-1])
    latest_bb_upper = float(bb_upper.iloc[-1])
    latest_bb_middle = float(bb_middle.iloc[-1])
    latest_bb_lower = float(bb_lower.iloc[-1])

    # Indicator signals analysis
    trend = "BULLISH" if latest_close > latest_ema20 else "BEARISH"
    rsi_status = "OVERBOUGHT" if latest_rsi >= 70 else ("OVERSOLD" if latest_rsi <= 30 else "NEUTRAL")
    macd_status = "BULLISH_CROSSOVER" if latest_hist > 0 else "BEARISH_CROSSOVER"

    return {
        "current": {
            "close": round(latest_close, 2),
            "ema9": round(latest_ema9, 2),
            "ema20": round(latest_ema20, 2),
            "ema50": round(latest_ema50, 2),
            "ema200": round(latest_ema200, 2),
            "rsi14": round(latest_rsi, 2),
            "macd": round(latest_macd, 2),
            "macd_signal": round(latest_signal, 2),
            "macd_histogram": round(latest_hist, 2),
            "bollinger_upper": round(latest_bb_upper, 2),
            "bollinger_middle": round(latest_bb_middle, 2),
            "bollinger_lower": round(latest_bb_lower, 2),
        },
        "signals": {
            "trend": trend,
            "rsi_status": rsi_status,
            "macd_status": macd_status,
            "bb_bandwidth_pct": round(((latest_bb_upper - latest_bb_lower) / max(1.0, latest_bb_middle)) * 100.0, 2),
        },
        "series": {
            "ema9": [round(x, 2) for x in ema_9.tail(30).tolist()],
            "ema20": [round(x, 2) for x in ema_20.tail(30).tolist()],
            "rsi14": [round(x, 2) for x in rsi_14.tail(30).tolist()],
            "macd": [round(x, 2) for x in macd_line.tail(30).tolist()],
            "macd_signal": [round(x, 2) for x in macd_signal.tail(30).tolist()],
        }
    }


def _empty_indicators_result() -> Dict[str, Any]:
    return {
        "current": {
            "close": 0.0, "ema9": 0.0, "ema20": 0.0, "ema50": 0.0, "ema200": 0.0,
            "rsi14": 50.0, "macd": 0.0, "macd_signal": 0.0, "macd_histogram": 0.0,
            "bollinger_upper": 0.0, "bollinger_middle": 0.0, "bollinger_lower": 0.0
        },
        "signals": {
            "trend": "NEUTRAL", "rsi_status": "NEUTRAL", "macd_status": "NEUTRAL", "bb_bandwidth_pct": 0.0
        },
        "series": {"ema9": [], "ema20": [], "rsi14": [], "macd": [], "macd_signal": []}
    }
