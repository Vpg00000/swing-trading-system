"""
NSE FII / DII Trading Activity Collector.

Fetches daily FII (Foreign Institutional Investors) and DII (Domestic Institutional Investors)
buy/sell totals from official NSE endpoints:
  - https://www.nseindia.com/api/fiidiiTradeReact (Live daily totals)

Stores historical series in data/cache/fii_dii_history.json and SQLite database to populate:
  1. Market Regime Score (FII/DII flow signal)
  2. ScanX-equivalent FII/DII Insights Page

Usage:
    python data/fii_dii.py                     # fetch today's data & update history
    from data.fii_dii import get_fii_dii_history, update_fii_dii_cache, get_fii_dii_summary
"""

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

HISTORY_FILE = CACHE_DIR / "fii_dii_history.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/reports/fii-dii",
}


def _clean_val(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        cleaned = str(val).replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _parse_nse_date(dt_raw: Optional[str]) -> str:
    if not dt_raw:
        return date.today().strftime("%Y-%m-%d")
    s = str(dt_raw).strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date.today().strftime("%Y-%m-%d")


def _get_nse_session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update(_HEADERS)
    try:
        sess.get("https://www.nseindia.com", timeout=10)
    except Exception as e:
        log.warning(f"NSE homepage cookie fetch failed: {e}")
    return sess


def fetch_live_fii_dii() -> List[Dict[str, Any]]:
    """
    Fetches daily FII/DII activity from NSE API.
    Returns list of dicts: [ {category: 'FII/FPI', buyValue: X, sellValue: Y, netValue: Z, date: 'DD-MMM-YYYY'}, ... ]
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    sess = _get_nse_session()
    try:
        resp = sess.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            log.info(f"Fetched live FII/DII data: {len(data)} records")
            return data
        return []
    except Exception as exc:
        log.warning(f"Failed to fetch FII/DII live data from NSE: {exc}")
        return []


def load_history() -> List[Dict[str, Any]]:
    """
    Load historical FII/DII series from cache JSON or SQLite database.
    Guarantees ZERO synthetic or mock data generation.
    """
    if HISTORY_FILE.exists():
        try:
            records = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(records, list) and len(records) > 0:
                return records
        except Exception as exc:
            log.warning(f"Failed to load FII/DII history from {HISTORY_FILE}: {exc}")

    # Fallback to database if available
    try:
        from data.database import query_fii_dii_history
        db_records = query_fii_dii_history(days=100)
        if db_records:
            return db_records
    except Exception:
        pass

    return []


def save_history(records: List[Dict[str, Any]]) -> None:
    """Save updated history series to cache file and SQLite database."""
    try:
        HISTORY_FILE.write_text(json.dumps(records, indent=2), encoding="utf-8")
        log.info(f"Saved FII/DII history ({len(records)} records) → {HISTORY_FILE.name}")
    except Exception as exc:
        log.error(f"Failed to save FII/DII history file: {exc}")

    try:
        from data.database import upsert_fii_dii_history
        upsert_fii_dii_history(records)
    except Exception as exc:
        log.warning(f"Failed to save FII/DII history to database: {exc}")


def update_fii_dii_cache() -> List[Dict[str, Any]]:
    """
    Fetch today's FII/DII data, merge into historical series, save to file/DB, and return full history.
    """
    history = load_history()
    live = fetch_live_fii_dii()

    if not live:
        return history

    history_map = {r["date"]: dict(r) for r in history}
    records_by_date: Dict[str, Dict[str, Any]] = {}

    for item in live:
        cat = str(item.get("category", "")).upper()
        raw_date = item.get("date") or item.get("dateStr")
        dt_str = _parse_nse_date(raw_date)

        if dt_str not in records_by_date:
            records_by_date[dt_str] = {
                "date": dt_str,
                "fii_buy": 0.0,
                "fii_sell": 0.0,
                "fii_net": 0.0,
                "dii_buy": 0.0,
                "dii_sell": 0.0,
                "dii_net": 0.0,
                "total_net": 0.0
            }

        rec = records_by_date[dt_str]
        buy = _clean_val(item.get("buyValue"))
        sell = _clean_val(item.get("sellValue"))
        net = _clean_val(item.get("netValue"))

        if "FII" in cat or "FPI" in cat:
            rec["fii_buy"] = buy
            rec["fii_sell"] = sell
            rec["fii_net"] = net
        elif "DII" in cat:
            rec["dii_buy"] = buy
            rec["dii_sell"] = sell
            rec["dii_net"] = net

    for dt_str, rec in records_by_date.items():
        rec["total_net"] = round(rec["fii_net"] + rec["dii_net"], 2)
        if dt_str in history_map:
            history_map[dt_str].update(rec)
        else:
            history_map[dt_str] = rec

    sorted_history = sorted(list(history_map.values()), key=lambda x: x["date"])
    save_history(sorted_history)
    return sorted_history


def get_fii_dii_history(days: int = 30) -> List[Dict[str, Any]]:
    """Get last N days of FII/DII flow records for charts."""
    history = load_history()
    if not history:
        history = update_fii_dii_cache()
    return history[-days:] if history else []


def get_fii_dii_summary() -> Dict[str, Any]:
    """
    Computes real-time institutional flow summary from latest available data.
    """
    history = load_history()
    if not history:
        history = update_fii_dii_cache()

    if not history:
        return {
            "date": date.today().strftime("%Y-%m-%d"),
            "fii_buy": 0.0,
            "fii_sell": 0.0,
            "fii_net": 0.0,
            "dii_buy": 0.0,
            "dii_sell": 0.0,
            "dii_net": 0.0,
            "total_net": 0.0,
            "cum_5d_fii": 0.0,
            "cum_5d_dii": 0.0,
            "cum_5d_total": 0.0,
            "signal": "NO_DATA",
            "records_count": 0
        }

    latest = history[-1]
    recent_5 = history[-5:]

    cum_fii = sum(r.get("fii_net", 0.0) for r in recent_5)
    cum_dii = sum(r.get("dii_net", 0.0) for r in recent_5)
    cum_total = cum_fii + cum_dii

    fii_net = latest.get("fii_net", 0.0)
    dii_net = latest.get("dii_net", 0.0)

    if fii_net > 0 and dii_net > 0:
        signal = "INSTITUTIONAL_CO_BUYING"
    elif fii_net < 0 and dii_net < 0:
        signal = "INSTITUTIONAL_CO_SELLING"
    elif fii_net > 1000:
        signal = "HEAVY_FII_INFLOW"
    elif fii_net < -1000:
        signal = "HEAVY_FII_OUTFLOW"
    elif fii_net > 0 and dii_net < 0:
        signal = "FII_BUY_DII_SELL"
    elif fii_net < 0 and dii_net > 0:
        signal = "DII_SUPPORT_FII_SELL"
    else:
        signal = "NEUTRAL"

    return {
        "date": latest.get("date"),
        "fii_buy": latest.get("fii_buy", 0.0),
        "fii_sell": latest.get("fii_sell", 0.0),
        "fii_net": fii_net,
        "dii_buy": latest.get("dii_buy", 0.0),
        "dii_sell": latest.get("dii_sell", 0.0),
        "dii_net": dii_net,
        "total_net": latest.get("total_net", round(fii_net + dii_net, 2)),
        "cum_5d_fii": round(cum_fii, 2),
        "cum_5d_dii": round(cum_dii, 2),
        "cum_5d_total": round(cum_total, 2),
        "signal": signal,
        "records_count": len(history)
    }


if __name__ == "__main__":
    print("Fetching live FII/DII market activity from NSE...\n")
    hist = update_fii_dii_cache()
    print(f"\nFII/DII History ({len(hist)} days recorded):\n")
    print(f"  {'Date':<12} {'FII Net (Cr)':>14} {'DII Net (Cr)':>14} {'Total Flow':>14}")
    print("  " + "─" * 58)
    for r in hist[-10:]:
        fii = r.get("fii_net", 0.0)
        dii = r.get("dii_net", 0.0)
        total = r.get("total_net", fii + dii)
        print(f"  {r['date']:<12} {fii:>+14.2f} {dii:>+14.2f} {total:>+14.2f}")
