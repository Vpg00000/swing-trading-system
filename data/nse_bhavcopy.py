"""
NSE Bhavcopy downloader — official EOD price + delivery data.

Downloads daily Bhavcopy CSV from NSE archives, parses OHLCV plus
Traded/Delivered/Delivery-% columns that yfinance never provides.

Saves in same format as data/fetch.py (Date,Open,High,Low,Close,Volume)
so all existing engine modules continue to work unchanged.
Also saves an extended cache (Date,...,Delivered,Delivery_Pct) for the
Top Deliveries screener and delivery-% filter.

Usage:
    python data/nse_bhavcopy.py                 # fetch today's Bhavcopy
    python data/nse_bhavcopy.py --date 2026-08-23
"""

import io
import sys
import time
import zipfile
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.universe import EQUITY_UNIVERSE

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DELIVERY_CACHE_DIR = CACHE_DIR / "delivery"
DELIVERY_CACHE_DIR.mkdir(exist_ok=True)

# NSE Bhavcopy archive URLs
# cm = Capital Market (equities)
_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)
_BHAVCOPY_ZIP_URL = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES/{yyyy}/{mmm}/"
    "cm{ddMMMyyyy}bhav.csv.zip"
)

# NSE requires a browser-like User-Agent or it rejects requests
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

_MONTH_MAP = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAY", 6: "JUN", 7: "JUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


# ─────────────────────────────────────────────
# URL builders
# ─────────────────────────────────────────────

def _bhav_url_v1(d: date) -> str:
    """Flat CSV format used for recent dates."""
    return _BHAVCOPY_URL.format(ddmmyyyy=d.strftime("%d%m%Y"))


def _bhav_url_v2(d: date) -> str:
    """Zipped CM Bhavcopy from NSE archives (more reliable, older format)."""
    mmm = _MONTH_MAP[d.month]
    ddMMMyyyy = d.strftime("%d") + mmm + d.strftime("%Y")
    return _BHAVCOPY_ZIP_URL.format(
        yyyy=d.strftime("%Y"),
        mmm=mmm,
        ddMMMyyyy=ddMMMyyyy,
    )


# ─────────────────────────────────────────────
# Fetchers
# ─────────────────────────────────────────────

def _get(url: str, timeout: int = 20) -> requests.Response | None:
    """HTTP GET with NSE headers; returns None on failure."""
    try:
        sess = requests.Session()
        # NSE requires a session cookie — hit the homepage first
        sess.get("https://www.nseindia.com/", headers=_HEADERS, timeout=10)
        resp = sess.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as exc:
        log.debug(f"  GET failed {url}: {exc}")
        return None


def fetch_bhavcopy_df(target_date: date) -> pd.DataFrame:
    """
    Download NSE Bhavcopy for target_date.
    Returns a DataFrame with columns:
        SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY (volume),
        TOTALTRDVAL, TIMESTAMP, TOTALTRADES, ISIN,
        + DELIV_QTY, DELIV_PER (delivery columns, may be NaN if unavailable)
    Returns empty DataFrame on failure.
    """
    # Try v1 flat CSV first (works for very recent dates)
    resp = _get(_bhav_url_v1(target_date))
    if resp is not None:
        try:
            df = pd.read_csv(io.StringIO(resp.text))
            df.columns = [c.strip() for c in df.columns]
            log.info(f"  Bhavcopy v1: {len(df)} rows for {target_date}")
            return df
        except Exception:
            pass

    # Try v2 zipped archive
    resp = _get(_bhav_url_v2(target_date))
    if resp is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                name = z.namelist()[0]
                with z.open(name) as f:
                    df = pd.read_csv(f)
            df.columns = [c.strip() for c in df.columns]
            log.info(f"  Bhavcopy v2 (zip): {len(df)} rows for {target_date}")
            return df
        except Exception as exc:
            log.debug(f"  v2 zip parse failed: {exc}")

    if target_date >= date.today():
        log.info(f"  Bhavcopy for {target_date} not yet published by NSE (released post-market close ~18:00 IST). Utilizing latest cached EOD data.")
    else:
        log.warning(f"  Could not fetch Bhavcopy for {target_date}")
    return pd.DataFrame()


def fetch_delivery_bhavcopy(target_date: date) -> pd.DataFrame:
    """
    NSE also publishes a 'security-wise delivery data' file that has
    Traded Qty + Delivered Qty + Delivery % per symbol.
    URL: https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv
    This is the same v1 URL which includes delivery columns for recent dates.
    Returns DataFrame with: SYMBOL, TRADED_QTY, DELIV_QTY, DELIV_PER
    """
    resp = _get(_bhav_url_v1(target_date))
    if resp is None:
        return pd.DataFrame()
    try:
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]

        # Column names vary: look for delivery-related columns
        col_map = {}
        for c in df.columns:
            cl = c.upper().strip()
            if "DELIV_PER" in cl or "DELIVERY_PER" in cl:
                col_map[c] = "DELIV_PER"
            elif "DELIV_QTY" in cl or "DELIVERY_QTY" in cl:
                col_map[c] = "DELIV_QTY"
            elif "TOTTRDQTY" in cl or "TOTAL_TRADED_QTY" in cl or "TRADED_QTY" in cl:
                col_map[c] = "TRADED_QTY"
            elif "SYMBOL" in cl:
                col_map[c] = "SYMBOL"

        if "SYMBOL" not in col_map.values():
            return pd.DataFrame()

        df = df.rename(columns=col_map)
        keep = [c for c in ["SYMBOL", "TRADED_QTY", "DELIV_QTY", "DELIV_PER"] if c in df.columns]
        return df[keep].copy()
    except Exception as exc:
        log.debug(f"  Delivery parse failed: {exc}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# Parser — convert raw Bhavcopy to OHLCV
# ─────────────────────────────────────────────

def _parse_bhavcopy(raw: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """
    Convert raw Bhavcopy into a per-symbol OHLCV DataFrame.
    Filters to EQ series only (excludes BE/BZ/SM/ST/etc.).
    Returns DataFrame indexed by SYMBOL with columns:
        Date, Open, High, Low, Close, Volume, Traded, Delivered, Delivery_Pct
    """
    if raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    df.columns = [c.strip().upper() for c in df.columns]

    # Filter equity series only
    series_col = next((c for c in df.columns if "SERIES" in c), None)
    if series_col:
        df = df[df[series_col].str.strip().isin(["EQ", "BE", "BZ"])]

    # Find column names (they vary slightly between formats)
    def _find(candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    sym_col   = _find(["SYMBOL", "SCRIP_CD"])
    open_col  = _find(["OPEN", "OPEN_PRICE", "PREV_CL_PR"])  # fallback prev close
    high_col  = _find(["HIGH", "HIGH_PRICE"])
    low_col   = _find(["LOW", "LOW_PRICE"])
    close_col = _find(["CLOSE", "CLOSE_PRICE", "LAST"])
    vol_col   = _find(["TOTTRDQTY", "TOTAL_TRADED_QTY", "TTL_TRD_QNTY", "QTY_TRD"])
    del_qty   = _find(["DELIV_QTY", "DELIV_QTY"])
    del_pct   = _find(["DELIV_PER", "DELIVERY_PER"])

    if not all([sym_col, close_col]):
        log.warning("  Could not identify required columns in Bhavcopy")
        return pd.DataFrame()

    rows = []
    for _, row in df.iterrows():
        sym = str(row[sym_col]).strip()
        try:
            rec = {
                "Date":         pd.Timestamp(target_date),
                "Symbol":       sym,
                "Open":         float(row[open_col])  if open_col  else float(row[close_col]),
                "High":         float(row[high_col])  if high_col  else float(row[close_col]),
                "Low":          float(row[low_col])   if low_col   else float(row[close_col]),
                "Close":        float(row[close_col]),
                "Volume":       int(float(row[vol_col])) if vol_col else 0,
                "Delivered":    int(float(row[del_qty])) if del_qty and pd.notna(row.get(del_qty)) else None,
                "Delivery_Pct": float(row[del_pct])      if del_pct and pd.notna(row.get(del_pct)) else None,
            }
            rows.append(rec)
        except (ValueError, TypeError):
            continue

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows).set_index("Symbol")
    return result


# ─────────────────────────────────────────────
# Cache updater — merge into existing CSV files
# ─────────────────────────────────────────────

def _cache_path(symbol: str) -> Path:
    """Same naming convention as data/fetch.py."""
    return CACHE_DIR / f"{symbol.replace('.', '_').replace('^', '')}.csv"


def _delivery_cache_path(target_date: date) -> Path:
    return DELIVERY_CACHE_DIR / f"delivery_{target_date.isoformat()}.csv"


def update_cache_from_bhavcopy(target_date: date, symbols: list[str] | None = None) -> dict:
    """
    Download Bhavcopy for target_date, merge new row into each symbol's
    existing cache CSV, and return a status dict.

    symbols: list of NSE symbols WITHOUT .NS suffix (e.g. 'RELIANCE', 'HDFCBANK')
    If None, uses EQUITY_UNIVERSE stripped of '.NS'.
    """
    if symbols is None:
        symbols = [s.replace(".NS", "") for s in EQUITY_UNIVERSE]

    raw = fetch_bhavcopy_df(target_date)
    if raw.empty:
        return {"status": "FAILED", "date": str(target_date), "rows": 0}

    parsed = _parse_bhavcopy(raw, target_date)
    if parsed.empty:
        return {"status": "FAILED", "date": str(target_date), "rows": 0}

    # Save full delivery data for Top Deliveries insight
    delivery_path = _delivery_cache_path(target_date)
    del_cols = [c for c in ["Date", "Volume", "Delivered", "Delivery_Pct"] if c in parsed.columns]
    if del_cols:
        parsed[del_cols].to_csv(delivery_path)
        log.info(f"  Saved delivery data → {delivery_path.name}")

    updated = 0
    for sym in symbols:
        # Bhavcopy uses bare NSE symbol (no .NS suffix)
        nse_sym = sym.replace(".NS", "")
        if nse_sym not in parsed.index:
            continue

        row = parsed.loc[nse_sym]
        new_row = pd.DataFrame({
            "Open":   [row["Open"]],
            "High":   [row["High"]],
            "Low":    [row["Low"]],
            "Close":  [row["Close"]],
            "Volume": [row["Volume"]],
        }, index=[row["Date"]])

        cache_path = _cache_path(sym + ".NS")
        if cache_path.exists():
            existing = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            # Remove any existing row for this date then append
            existing = existing[existing.index.date != target_date]
            merged = pd.concat([existing, new_row]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
        else:
            merged = new_row

        merged.to_csv(cache_path)
        updated += 1

    log.info(f"  Updated {updated}/{len(symbols)} symbol caches from Bhavcopy {target_date}")
    return {"status": "OK", "date": str(target_date), "rows": len(parsed), "updated": updated}


# ─────────────────────────────────────────────
# Top Deliveries — for dashboard insight
# ─────────────────────────────────────────────

def get_top_deliveries(target_date: date | None = None, top_n: int = 50) -> list[dict]:
    """
    Return top stocks by delivery % for target_date.
    Reads from delivery cache if available, else fetches live.

    Returns list of dicts:
        {symbol, close, change_pct, traded_qty, delivered_qty, delivery_pct}
    sorted by delivery_pct descending.
    """
    if target_date is None:
        target_date = date.today()

    # Try cached delivery file first
    cache_path = _delivery_cache_path(target_date)
    if cache_path.exists():
        df = pd.read_csv(cache_path, index_col=0)
    else:
        raw = fetch_bhavcopy_df(target_date)
        if raw.empty:
            return []
        parsed = _parse_bhavcopy(raw, target_date)
        df = parsed

    if df.empty:
        return []

    results = []
    for sym, row in df.iterrows():
        if pd.isna(row.get("Delivery_Pct")) or row.get("Delivery_Pct", 0) <= 0:
            continue
        results.append({
            "symbol":       str(sym),
            "close":        round(float(row.get("Close", 0)), 2),
            "traded_qty":   int(row.get("Volume", 0)),
            "delivered_qty":int(row.get("Delivered", 0) or 0),
            "delivery_pct": round(float(row.get("Delivery_Pct", 0)), 2),
        })

    results.sort(key=lambda x: x["delivery_pct"], reverse=True)
    return results[:top_n]


# ─────────────────────────────────────────────
# Backfill helper — fill missing trading days
# ─────────────────────────────────────────────

def backfill_missing(days_back: int = 5, symbols: list[str] | None = None):
    """Try to fetch Bhavcopy for last N calendar days (skipping weekends)."""
    today = date.today()
    filled = 0
    for delta in range(1, days_back + 5):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:  # skip Sat/Sun
            continue
        if filled >= days_back:
            break
        log.info(f"Backfilling {d}...")
        result = update_cache_from_bhavcopy(d, symbols)
        if result["status"] == "OK":
            filled += 1
        time.sleep(1)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download NSE Bhavcopy")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--backfill", type=int, default=0, help="Backfill N trading days")
    args = parser.parse_args()

    if args.backfill:
        log.info(f"Backfilling {args.backfill} trading days...")
        backfill_missing(args.backfill)
    else:
        target = date.fromisoformat(args.date) if args.date else date.today()
        log.info(f"Downloading NSE Bhavcopy for {target}...")
        result = update_cache_from_bhavcopy(target)
        print(f"\nResult: {result}")

        # Show top deliveries
        top = get_top_deliveries(target, top_n=10)
        if top:
            print(f"\nTop 10 Delivery Stocks ({target}):")
            print(f"  {'Symbol':<16} {'Close':>8} {'Traded':>12} {'Delivery%':>10}")
            for r in top:
                print(f"  {r['symbol']:<16} {r['close']:>8.2f} {r['traded_qty']:>12,} {r['delivery_pct']:>9.1f}%")
