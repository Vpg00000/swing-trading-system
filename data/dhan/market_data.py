"""
Dhan live market data -- stub layer, see data/dhan/client.py for why this
degrades to None/empty rather than raising when credentials aren't set up
yet. Once active, this is the eventual replacement for report.py's "prior-
day close, not live" disclaimer (DESIGN.md's Phase 1 data source note).
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from data.dhan.client import DhanClient
from data.dhan.instruments import symbol_to_security_id
from data.dhan.errors import DhanError

def get_ltp(symbols: list[str], client: DhanClient | None = None) -> dict[str, float]:
    """Last-traded-price per symbol using Dhan Market Quote API."""
    client = client or DhanClient()
    if not client.is_active():
        raise DhanError("Dhan client is not active")

    sec_to_sym = {}
    instruments = []
    for sym in symbols:
        sec_id = symbol_to_security_id(sym, client)
        if sec_id:
            sec_to_sym[str(sec_id)] = sym
            sec_to_sym[sym] = sym
            instruments.append(("NSE_EQ", sec_id))
            
    if not instruments:
        raise ValueError("No valid instruments provided")

    try:
        response = client.sdk.get_ltp(instruments)
    except Exception as e:
        raise DhanError(f"Failed to fetch LTP: {e}")

    if not isinstance(response, dict) or response.get("status") != "success":
        raise ValueError(f"Invalid response: {response}")

    data = response.get("data", {})
    nse_eq_data = data.get("NSE_EQ", {})
    
    result = {}
    for sec_id, info in nse_eq_data.items():
        sym = sec_to_sym.get(str(sec_id)) or sec_to_sym.get(sec_id)
        if sym and isinstance(info, dict) and "last_price" in info:
            result[sym] = float(info["last_price"])
            
    return result


def get_ohlc(symbol: str, interval: str, from_date, to_date, client: DhanClient | None = None):
    """Historical OHLC candles from Dhan historical API."""
    client = client or DhanClient()
    if not client.is_active():
        raise DhanError("Dhan client is not active")

    sec_id = symbol_to_security_id(symbol, client)
    if not sec_id:
        raise ValueError("Invalid instrument symbol")

    # Format dates to YYYY-MM-DD
    f_date = from_date.strftime("%Y-%m-%d") if isinstance(from_date, (date, datetime)) else str(from_date)
    t_date = to_date.strftime("%Y-%m-%d") if isinstance(to_date, (date, datetime)) else str(to_date)
    
    try:
        return client.sdk.historical_daily_data(
            security_id=sec_id,
            exchange_segment="NSE_EQ",
            instrument_type="EQUITY",
            from_date=f_date,
            to_date=t_date
        )
    except Exception as e:
        raise DhanError(f"Failed to fetch OHLC data: {e}")