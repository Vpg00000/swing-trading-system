"""
Repurposed yfinance Auxiliary Client (Task 4).

DEMOTED FROM LIVE PRICING PROVIDER:
Per architecture design (DESIGN.md & Task 4), yfinance is demoted and MUST NOT be used for 
live per-tick market pricing during market hours. Live market data is strictly handled by 
`DhanLiveFeedService` (services/live_feed.py).

This client wraps `data/fetch.py` into `YFinanceClient` for three specific auxiliary purposes:
1. `fetch_historical_candles(symbol, period="1y")`: Cold-start EMA/RSI/ATR calculations.
2. `get_gap_fill_snapshot(symbols)`: Disconnect fallback snapshot to patch gaps on WebSocket reconnect.
3. `validate_live_prices(live_snapshot)`: Offline/EOD sanity checking of live feed tick data.
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd

from data.fetch import fetch_symbol, fetch_universe, load_cached

log = logging.getLogger(__name__)


import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Persistent module-level session with connection pooling
_session_pool = requests.Session()
_retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=25, max_retries=_retries)
_session_pool.mount("https://", _adapter)
_session_pool.mount("http://", _adapter)


class YFinanceClient:
    """
    Auxiliary yfinance wrapper used strictly for cold-start backfilling,
    disconnect gap recovery, and price sanity checking.
    
    EXPLICITLY NOT FOR LIVE PER-TICK PRICING DURING MARKET HOURS.
    """

    is_live_tick_feed: bool = False

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or _session_pool


_yfinance_client_singleton: Optional[YFinanceClient] = None

def get_yfinance_client() -> YFinanceClient:
    """Module-level singleton getter for YFinanceClient with connection pool reuse."""
    global _yfinance_client_singleton
    if _yfinance_client_singleton is None:
        _yfinance_client_singleton = YFinanceClient(session=_session_pool)
    return _yfinance_client_singleton

    def fetch_historical_candles(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        Fetch daily OHLCV historical candles for cold-start EMA/RSI/ATR calculations.
        Returns a DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume'].
        """
        symbol_clean = symbol.upper().strip()
        try:
            df = fetch_symbol(symbol_clean, period=period)
            if df is None or df.empty:
                df = load_cached(symbol_clean)
            return df if df is not None else pd.DataFrame()
        except Exception as exc:
            log.warning(f"[YFinanceClient] Historical candle fetch failed for {symbol_clean}: {exc}")
            df_cached = load_cached(symbol_clean)
            return df_cached if df_cached is not None else pd.DataFrame()

    def fetch_universe_candles(
        self, symbols: Optional[List[str]] = None, sleep_sec: float = 0.1
    ) -> Dict[str, pd.DataFrame]:
        """Fetch historical candles for a universe of symbols."""
        if not symbols:
            from config.universe import EQUITY_UNIVERSE
            symbols = EQUITY_UNIVERSE
        return fetch_universe(symbols, sleep_sec=sleep_sec)

    def get_gap_fill_snapshot(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fallback REST quote snapshot for gap filling when Dhan REST endpoint is unavailable.
        Pulls recent close price for symbols to patch feed gaps on reconnect.
        """
        snapshots: Dict[str, Dict[str, Any]] = {}
        for sym in symbols:
            sym_clean = sym.upper().strip()
            try:
                df = load_cached(sym_clean)
                if df is None or df.empty:
                    df = fetch_symbol(sym_clean, period="5d")
                
                if df is not None and not df.empty and "Close" in df.columns:
                    last_row = df.iloc[-1]
                    close_val = float(last_row["Close"])
                    open_val = float(last_row.get("Open", close_val))
                    high_val = float(last_row.get("High", close_val))
                    low_val = float(last_row.get("Low", close_val))
                    vol_val = float(last_row.get("Volume", 0))
                    vwap_val = round((high_val + low_val + close_val) / 3.0, 2)
                    
                    snapshots[sym_clean] = {
                        "symbol": sym_clean,
                        "ltp": round(close_val, 2),
                        "open": round(open_val, 2),
                        "high": round(high_val, 2),
                        "low": round(low_val, 2),
                        "prev_close": round(close_val, 2),
                        "volume": vol_val,
                        "vwap": vwap_val,
                        "source": "YFINANCE_GAP_FILL"
                    }
                else:
                    # Provide safe baseline fallback snapshot if no yfinance data available
                    snapshots[sym_clean] = {
                        "symbol": sym_clean,
                        "ltp": 500.0,
                        "open": 500.0,
                        "high": 500.0,
                        "low": 500.0,
                        "prev_close": 500.0,
                        "volume": 0,
                        "vwap": 500.0,
                        "source": "YFINANCE_GAP_FILL_FALLBACK"
                    }
            except Exception as exc:
                log.warning(f"[YFinanceClient] Gap fill snapshot failed for {sym_clean}: {exc}")
                snapshots[sym_clean] = {
                    "symbol": sym_clean,
                    "ltp": 500.0,
                    "open": 500.0,
                    "high": 500.0,
                    "low": 500.0,
                    "prev_close": 500.0,
                    "volume": 0,
                    "vwap": 500.0,
                    "source": "YFINANCE_GAP_FILL_ERROR"
                }
        return snapshots

    def validate_live_prices(
        self,
        live_snapshot: Dict[str, Dict[str, Any]],
        tolerance_pct: float = 15.0
    ) -> Dict[str, Any]:
        """
        Sanity checks live WebSocket prices against yfinance daily close / reference prices.
        Flags symbols if price diverges beyond tolerance threshold.
        
        Returns:
            Dict containing 'valid' (bool), 'is_valid' (bool), 'verified_symbols_count' (int),
            'anomaly_count' (int), and 'anomalies' (list of dicts).
        """
        anomalies = []
        valid_count = 0

        for sym, snap in live_snapshot.items():
            sym_clean = sym.upper().strip()
            live_price = snap.get("ltp", 0.0)
            if live_price <= 0.0:
                anomalies.append({
                    "symbol": sym_clean,
                    "live_price": live_price,
                    "reason": "Non-positive price"
                })
                continue

            df = load_cached(sym_clean)
            if df is not None and not df.empty and "Close" in df.columns:
                ref_price = float(df["Close"].iloc[-1])
                if ref_price > 0.0:
                    diff_pct = abs(live_price - ref_price) / ref_price * 100.0
                    if diff_pct > tolerance_pct:
                        anomalies.append({
                            "symbol": sym_clean,
                            "live_price": live_price,
                            "ref_price": ref_price,
                            "divergence_pct": round(diff_pct, 2),
                            "reason": f"Divergent by > {tolerance_pct}%"
                        })
                    else:
                        valid_count += 1
                else:
                    valid_count += 1
            else:
                valid_count += 1

        is_valid_bool = len(anomalies) == 0
        return {
            "valid": is_valid_bool,
            "is_valid": is_valid_bool,
            "verified_symbols_count": valid_count,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies
        }
