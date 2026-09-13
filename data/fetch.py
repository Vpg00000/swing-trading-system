"""
Daily EOD data fetch for the swing trading system.

Pulls OHLCV history for the equity universe plus Nifty index / India VIX
using free yfinance data. Sufficient for regime/momentum/event-confirmation
logic since those operate on daily closes, not intraday ticks.
"""

import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.universe import EQUITY_UNIVERSE, NIFTY_INDEX, INDIA_VIX

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

LOOKBACK_PERIOD = "1y"  # enough history for 200-DMA, 6mo momentum, ATR(14)


def fetch_symbol(symbol: str, period: str = LOOKBACK_PERIOD) -> pd.DataFrame:
    """Fetch daily OHLCV for one symbol. Returns empty DataFrame on failure."""
    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
        if df.empty:
            print(f"  [warn] no data returned for {symbol}")
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception as exc:
        print(f"  [warn] failed to fetch {symbol}: {exc}")
        return pd.DataFrame()


def fetch_universe(symbols: list[str], sleep_sec: float = 0.3) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV for a list of symbols, writing each to a local cache CSV."""
    out = {}
    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] fetching {sym}...")
        df = fetch_symbol(sym)
        if not df.empty:
            out[sym] = df
            df.to_csv(CACHE_DIR / f"{sym.replace('.', '_').replace('^', '')}.csv")
        time.sleep(sleep_sec)  # be polite to the free data endpoint
    return out


def fetch_regime_inputs() -> dict[str, pd.DataFrame]:
    """Fetch the Nifty index and India VIX series used for regime detection."""
    return {
        "nifty": fetch_symbol(NIFTY_INDEX),
        "vix": fetch_symbol(INDIA_VIX),
    }


def load_cached(symbol: str) -> pd.DataFrame:
    """Load a previously cached symbol from disk without re-fetching."""
    sym_clean = symbol.replace('.', '_').replace('^', '').strip()
    path = CACHE_DIR / f"{sym_clean}.csv"
    if not path.exists():
        if not sym_clean.endswith("_NS"):
            alt_path = CACHE_DIR / f"{sym_clean}_NS.csv"
            if alt_path.exists():
                path = alt_path
        elif sym_clean.endswith("_NS"):
            alt_path = CACHE_DIR / f"{sym_clean[:-3]}.csv"
            if alt_path.exists():
                path = alt_path
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df


def load_cached_adjusted(symbol: str, corporate_actions: Optional[List[Dict[str, Any]]] = None) -> pd.DataFrame:
    """
    Load cached daily OHLCV data with corporate action adjustments (splits, bonuses, dividends).
    Applies reverse chronological adjustments to historical price bars prior to the ex-date.
    Formula from CODE_REVIEW_COMPREHENSIVE.md:
        SPLIT: divide prior prices by split ratio, multiply prior volume by split ratio.
        BONUS: divide prior prices by (1 + bonus_ratio), multiply volume by (1 + bonus_ratio).
    """
    df = load_cached(symbol)
    if df.empty or not corporate_actions:
        return df

    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # Sort actions reverse chronologically by date
    sorted_actions = sorted(corporate_actions, key=lambda a: pd.to_datetime(a.get("date", "1970-01-01")), reverse=True)

    for action in sorted_actions:
        action_date = pd.to_datetime(action.get("date"))
        action_type = str(action.get("type", "")).upper()
        mask = df.index < action_date

        if action_type == "SPLIT":
            ratio = float(action.get("ratio", action.get("split_ratio", 2.0)))
            if ratio > 0:
                for col in ["Open", "High", "Low", "Close"]:
                    if col in df.columns:
                        df.loc[mask, col] = df.loc[mask, col] / ratio
                if "Volume" in df.columns:
                    df.loc[mask, "Volume"] = df.loc[mask, "Volume"] * ratio

        elif action_type == "BONUS":
            bonus_ratio = float(action.get("bonus_ratio", action.get("ratio", 1.0)))
            if bonus_ratio > 0:
                factor = 1.0 + bonus_ratio
                for col in ["Open", "High", "Low", "Close"]:
                    if col in df.columns:
                        df.loc[mask, col] = df.loc[mask, col] / factor
                if "Volume" in df.columns:
                    df.loc[mask, "Volume"] = df.loc[mask, "Volume"] * factor

        elif action_type == "DIVIDEND":
            div_amount = float(action.get("amount", 0.0))
            if div_amount > 0:
                for col in ["Open", "High", "Low", "Close"]:
                    if col in df.columns:
                        df.loc[mask, col] = np.maximum(0.01, df.loc[mask, col] - div_amount)

    return df


if __name__ == "__main__":
    print("Fetching regime inputs (Nifty, India VIX)...")
    regime = fetch_regime_inputs()
    for name, df in regime.items():
        if not df.empty:
            df.to_csv(CACHE_DIR / f"{name}.csv")
            print(f"  {name}: {len(df)} rows, latest close {df['Close'].iloc[-1]:.2f}")
        else:
            print(f"  {name}: FAILED to fetch")

    print(f"\nFetching equity universe ({len(EQUITY_UNIVERSE)} symbols)...")
    universe_data = fetch_universe(EQUITY_UNIVERSE)
    print(f"\nDone. Successfully fetched {len(universe_data)}/{len(EQUITY_UNIVERSE)} symbols.")
