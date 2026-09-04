"""
Symbol <-> Dhan security-id mapping -- stub layer, see data/dhan/client.py.
Dhan's API addresses instruments by an internal security-id, not by the
NSE trading symbol used everywhere else in this codebase (config/universe.py,
data/fetch.py, etc.) -- this module is where that mapping will live once
Dhan's instrument master CSV is fetched and cached, so the rest of the
system keeps working with plain NSE symbols throughout.
"""

import os
import sys
import requests
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from data.dhan.client import DhanClient

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "dhan_scrip_master.csv"
_mapping_cache: dict[str, str] = {}


def _load_mapping():
    global _mapping_cache
    if _mapping_cache:
        return

    if not CSV_PATH.exists():
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        CSV_PATH.write_bytes(resp.content)

    cols = ["SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_SMST_SECURITY_ID", "SEM_TRADING_SYMBOL"]
    df = pd.read_csv(CSV_PATH, usecols=cols, low_memory=False)
    
    # Filter to NSE equities
    df_nse = df[(df["SEM_EXM_EXCH_ID"] == "NSE") & (df["SEM_SEGMENT"] == "E")]
    _mapping_cache = dict(zip(df_nse["SEM_TRADING_SYMBOL"].astype(str), df_nse["SEM_SMST_SECURITY_ID"].astype(str)))


def symbol_to_security_id(symbol: str, client: DhanClient | None = None) -> str | None:
    """Look up internal security ID for a symbol, downloading scrip master if needed."""
    bare = symbol.replace(".NS", "").upper()
    try:
        _load_mapping()
        return _mapping_cache.get(bare, bare)
    except Exception:
        return bare


if __name__ == "__main__":
    print("symbol_to_security_id('RELIANCE.NS') ->", symbol_to_security_id("RELIANCE.NS"))
    print("symbol_to_security_id('HFCL') ->", symbol_to_security_id("HFCL"))
