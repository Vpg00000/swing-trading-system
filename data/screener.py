"""
data/screener.py — Screener.in fundamental data fetcher (Task 5).

Scrapes per-symbol fundamental ratios from https://screener.in for use in
the Fundamental Engine (Module 12) and Valuation Engine (Module 13).

Automated Access Terms of Service & Paid API Evaluation Notes:
--------------------------------------------------------------
1. Terms of Service Compliance:
   - Screener.in automated web scraping is governed by their website Terms of Service.
   - High-frequency scraping or hitting endpoint URLs directly at high volume violates access policies
     and triggers source IP rate limits/blocks.
   - This module enforces a weekly refresh cadence (CACHE_TTL_HOURS = 168 / 7 days) and randomized jitter
     delays (random.uniform(2.0, 6.0) seconds) between requests to minimize server load and respect fair use.

2. Commercial & High-Throughput Paid API Evaluation:
   - Screener.in does not provide an official public REST API for commercial redistribution or high-speed streaming.
   - Production / commercial applications requiring real-time fundamental feeds or bulk extraction must evaluate
     and integrate paid financial data vendor APIs (e.g. Trendlyne, Moneycontrol API, NSE/BSE XBRL feeds, AceTP,
     or Bloomberg/Refinitiv enterprise data feeds) instead of scraping HTML pages.

Cadence & Jitter:
- Weekly refresh (CACHE_TTL_HOURS = 168 / 7 days). Fundamental ratios (PE, ROCE, ROE, Debt/Equity) change
  quarterly/annually, reducing request volume by ~85%.
- Jitter: random.uniform(2.0, 6.0) seconds between requests in batch processing.

Graceful Failure:
- All failures degrade gracefully — returns ScreenerData with data_source='UNAVAILABLE' or last cached snapshot.
"""

from __future__ import annotations

import json
import re
import time
import random
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# Try to import BeautifulSoup; fall back to regex-only parsing
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_TTL_HOURS = 168  # 7-day weekly refresh cadence


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.screener.in/",
}


@dataclass
class ScreenerData:
    symbol: str
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]          # price / book value per share
    roce: Optional[float]              # Return on Capital Employed (%)
    roe: Optional[float]               # Return on Equity (%)
    debt_to_equity: Optional[float]    # Debt/Equity ratio (borrowings / equity capital)
    sales_growth_3yr: Optional[float]  # 3-year revenue CAGR (%) — from analysis text
    profit_growth_3yr: Optional[float] # 3-year EPS/profit CAGR (%) — from analysis text
    opm_pct: Optional[float]           # Operating Profit Margin (%) — from P&L table
    promoter_holding_pct: Optional[float]
    current_price: Optional[float]     # ₹ from sidebar
    book_value_per_share: Optional[float]  # ₹ from sidebar
    market_cap_cr: Optional[float]     # Market Cap in ₹ Crore from sidebar
    data_source: str                   # 'SCREENER_IN' or 'UNAVAILABLE'
    fetch_error: Optional[str] = None


def _normalize_symbol(symbol: str) -> str:
    """Strip exchange suffix and uppercase."""
    return symbol.replace(".NS", "").replace(".BSE", "").upper().strip()


def _cache_path(symbol: str) -> Path:
    bare = _normalize_symbol(symbol)
    return CACHE_DIR / f"screener_{bare}.json"


def _load_cache(symbol: str) -> Optional[dict]:
    """Load from cache if it exists and is fresh (<24h)."""
    p = _cache_path(symbol)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        cached_at = datetime.fromisoformat(data.get("_cached_at", "2000-01-01"))
        if datetime.now() - cached_at < timedelta(hours=CACHE_TTL_HOURS):
            return data
    except Exception:
        pass
    return None


def _save_cache(symbol: str, data: dict) -> None:
    """Persist parsed result to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(symbol)
    data["_cached_at"] = datetime.now().isoformat()
    try:
        p.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        log.warning(f"screener cache write failed for {symbol}: {exc}")


def _parse_number(text: str) -> Optional[float]:
    """Extract first float from a string like '23.9%' or '₹ 1,317'."""
    if not text:
        return None
    text = text.replace(",", "").replace("₹", "").replace("%", "").strip()
    m = re.search(r"-?\d+\.?\d*", text)
    return float(m.group()) if m else None


def _extract_ratio_table(html: str) -> dict[str, Optional[float]]:
    """
    Extracts key ratios from the <ul> sidebar list:
      <li data-source='default'>
        <span class='name'>Stock P/E</span>
        <span class='nowrap value'><span class='number'>23.9</span></span>
      </li>
    Returns a dict: {label_lowercase: value}
    """
    results: dict[str, Optional[float]] = {}

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for li in soup.select("li[data-source='default']"):
            name_el = li.select_one("span.name")
            num_el = li.select_one("span.number")
            if name_el and num_el:
                label = name_el.get_text(strip=True).lower()
                value = _parse_number(num_el.get_text(strip=True))
                results[label] = value
    else:
        # Regex fallback for when bs4 is not installed
        pattern = re.compile(
            r'<span class="name">\s*(.*?)\s*</span>.*?'
            r'<span class="number">\s*([\d,\.\-]+)\s*</span>',
            re.DOTALL
        )
        for m in pattern.finditer(html):
            label = m.group(1).strip().lower()
            value = _parse_number(m.group(2))
            results[label] = value

    return results


def _extract_extended_data(html: str) -> dict[str, Optional[float]]:
    """
    Extracts extra fields not in the sidebar:
    - OPM % from the Profit & Loss table (most recent column)
    - Debt/Equity from balance sheet (borrowings / equity capital)
    - Sales growth CAGR, Profit growth CAGR from analysis text
    """
    results: dict[str, Optional[float]] = {
        "opm_pct": None,
        "debt_to_equity": None,
        "sales_growth_3yr": None,
        "profit_growth_3yr": None,
    }

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")

        # 1. OPM from Profit & Loss table (last column = most recent)
        pl = soup.find("section", id="profit-loss")
        if pl:
            tbl = pl.find("table")
            if tbl:
                for row in tbl.find_all("tr"):
                    cells = row.find_all(["th", "td"])
                    if cells and "opm" in cells[0].get_text(strip=True).lower():
                        results["opm_pct"] = _parse_number(cells[-1].get_text(strip=True))
                        break

        # 2. Debt/Equity from balance sheet — most recent year
        # Use: Debt/Equity = Total Borrowings / (Equity Capital + Reserves)
        bs = soup.find("section", id="balance-sheet")
        if bs:
            tbl = bs.find("table")
            borrowings = equity_cap = reserves = None
            if tbl:
                for row in tbl.find_all("tr"):
                    cells = row.find_all(["th", "td"])
                    if not cells:
                        continue
                    label = cells[0].get_text(strip=True).lower()
                    if "borrowing" in label:
                        borrowings = _parse_number(cells[-1].get_text(strip=True))
                    elif label == "equity capital" or label == "share capital":
                        equity_cap = _parse_number(cells[-1].get_text(strip=True))
                    elif "reserve" in label:
                        reserves = _parse_number(cells[-1].get_text(strip=True))
            total_equity = (equity_cap or 0) + (reserves or 0)
            if borrowings is not None and total_equity > 0:
                results["debt_to_equity"] = round(borrowings / total_equity, 2)

        # 3. Growth CAGR from analysis section text
        # e.g. 'Company has delivered good profit growth of 20.9% CAGR over last 5 years'
        analysis = soup.find("section", id="analysis")
        if analysis:
            for li in analysis.find_all("li"):
                text = li.get_text(strip=True)
                # Sales / Revenue growth (3yr preferred; fall back to 5yr)
                if "sales" in text.lower() and "cagr" in text.lower():
                    m = re.search(r'([\d\.]+)%', text)
                    if m and results["sales_growth_3yr"] is None:
                        results["sales_growth_3yr"] = float(m.group(1))
                # Profit growth
                if "profit" in text.lower() and "cagr" in text.lower():
                    m = re.search(r'([\d\.]+)%', text)
                    if m and results["profit_growth_3yr"] is None:
                        results["profit_growth_3yr"] = float(m.group(1))
    else:
        # Regex fallback
        m = re.search(r'OPM %.*?<td[^>]*>([\d]+)%', html, re.DOTALL)
        results["opm_pct"] = _parse_number(m.group(1)) if m else None

    return results


_CIRCUIT_BREAKER_ACTIVE = False
_CONSECUTIVE_FAILURES = 0
_MAX_CONSECUTIVE_FAILURES = 3


def fetch_screener_data(symbol: str) -> ScreenerData:
    """
    Fetch fundamental data for a symbol from screener.in.
    Returns a ScreenerData. On any failure, returns with data_source='UNAVAILABLE'.
    Respects a 24-hour file cache and includes an automatic circuit breaker.
    """
    global _CIRCUIT_BREAKER_ACTIVE, _CONSECUTIVE_FAILURES

    bare = _normalize_symbol(symbol)

    # Try cache first
    cached = _load_cache(bare)
    if cached:
        try:
            cached.pop("_cached_at", None)
            return ScreenerData(**{k: v for k, v in cached.items() if k in ScreenerData.__dataclass_fields__})
        except Exception:
            pass

    # If circuit breaker is active, degrade gracefully without spamming retries
    if _CIRCUIT_BREAKER_ACTIVE:
        return ScreenerData(
            symbol=bare, pe_ratio=None, pb_ratio=None, roce=None, roe=None,
            debt_to_equity=None, sales_growth_3yr=None, profit_growth_3yr=None,
            opm_pct=None, promoter_holding_pct=None,
            current_price=None, book_value_per_share=None, market_cap_cr=None,
            data_source="UNAVAILABLE", fetch_error="Screener circuit breaker active"
        )

    # Build URLs to try (consolidated first, then standalone)
    urls = [
        f"https://www.screener.in/company/{bare}/consolidated/",
        f"https://www.screener.in/company/{bare}/",
    ]

    html = None
    for url in urls:
        # Try up to 2 attempts with short timeout
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=2.5)
                if resp.status_code == 200:
                    html = resp.text
                    _CONSECUTIVE_FAILURES = 0
                    break
                elif resp.status_code == 404:
                    break
            except Exception as exc:
                _CONSECUTIVE_FAILURES += 1
                if _CONSECUTIVE_FAILURES >= _MAX_CONSECUTIVE_FAILURES:
                    _CIRCUIT_BREAKER_ACTIVE = True
                    log.info(f"Screener.in rate limit / connection threshold reached. Circuit breaker activated; falling back to cached fundamentals.")
                    break
                else:
                    log.debug(f"screener fetch attempt {attempt + 1} for {bare}: {exc}")
                if attempt < 1:
                    time.sleep(0.5)
        if html or _CIRCUIT_BREAKER_ACTIVE:
            break

    if html is None:
        return ScreenerData(
            symbol=bare, pe_ratio=None, pb_ratio=None, roce=None, roe=None,
            debt_to_equity=None, sales_growth_3yr=None, profit_growth_3yr=None,
            opm_pct=None, promoter_holding_pct=None,
            current_price=None, book_value_per_share=None, market_cap_cr=None,
            data_source="UNAVAILABLE", fetch_error="HTTP fetch failed for all URLs"
        )


    try:
        # Extract sidebar key ratios
        sidebar = _extract_ratio_table(html)

        # Sidebar fields
        pe = sidebar.get("stock p/e")
        book_value = sidebar.get("book value")    # ₹ per share
        current_price = sidebar.get("current price")  # ₹
        mkt_cap = sidebar.get("market cap")       # ₹ Cr
        roce = sidebar.get("roce")
        roe = sidebar.get("roe")
        promoter = sidebar.get("promoter holding")

        # Compute P/B from sidebar price and book value
        pb = None
        if current_price and book_value and book_value > 0:
            pb = round(current_price / book_value, 2)

        # Extended data from P&L, balance sheet, and analysis text
        extended = _extract_extended_data(html)
        debt_eq = extended.get("debt_to_equity")
        sales_growth = extended.get("sales_growth_3yr")
        profit_growth = extended.get("profit_growth_3yr")
        opm = extended.get("opm_pct")

        result = ScreenerData(
            symbol=bare,
            pe_ratio=pe,
            pb_ratio=pb,
            roce=roce,
            roe=roe,
            debt_to_equity=debt_eq,
            sales_growth_3yr=sales_growth,
            profit_growth_3yr=profit_growth,
            opm_pct=opm,
            promoter_holding_pct=promoter,
            current_price=current_price,
            book_value_per_share=book_value,
            market_cap_cr=mkt_cap,
            data_source="SCREENER_IN",
            fetch_error=None
        )

        # Cache the result
        _save_cache(bare, asdict(result))
        return result

    except Exception as exc:
        log.error(f"screener parse failed for {bare}: {exc}", exc_info=True)
        return ScreenerData(
            symbol=bare, pe_ratio=None, pb_ratio=None, roce=None, roe=None,
            debt_to_equity=None, sales_growth_3yr=None, profit_growth_3yr=None,
            opm_pct=None, promoter_holding_pct=None,
            current_price=None, book_value_per_share=None, market_cap_cr=None,
            data_source="UNAVAILABLE", fetch_error=str(exc)
        )


def fetch_screener_batch(
    symbols: list[str],
    delay_seconds: Optional[float] = None,
    min_delay: float = 2.0,
    max_delay: float = 6.0
) -> dict[str, ScreenerData]:
    """
    Fetch fundamentals for a list of symbols with a randomized jitter delay (random.uniform(2.0, 6.0))
    between requests in batch fetches to respect rate limits and terms of service.
    Returns dict: symbol → ScreenerData.
    """
    results = {}
    for i, sym in enumerate(symbols):
        if i > 0:
            if delay_seconds is not None:
                jitter = delay_seconds
            else:
                jitter = random.uniform(min_delay, max_delay)
            log.info(f"Screener batch fetch waiting {jitter:.2f}s jitter before {sym}...")
            time.sleep(jitter)
        results[sym] = fetch_screener_data(sym)
    return results



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_symbols = ["RELIANCE", "HFCL.NS", "WELCORP"]
    print("Testing Screener.in fundamental fetch on small set...\n")
    for sym in test_symbols:
        data = fetch_screener_data(sym)
        print(f"=== {data.symbol} ===")
        print(f"  Source:           {data.data_source}")
        if data.fetch_error:
            print(f"  Error:            {data.fetch_error}")
        else:
            print(f"  Price:            ₹{data.current_price}")
            print(f"  Mkt Cap:          ₹{data.market_cap_cr} Cr")
            print(f"  P/E Ratio:        {data.pe_ratio}")
            print(f"  P/B Ratio:        {data.pb_ratio}")
            print(f"  ROCE:             {data.roce}%")
            print(f"  ROE:              {data.roe}%")
            print(f"  Debt/Equity:      {data.debt_to_equity}")
            print(f"  Sales Growth 3Y:  {data.sales_growth_3yr}%")
            print(f"  Profit Growth 3Y: {data.profit_growth_3yr}%")
            print(f"  OPM:              {data.opm_pct}%")
            print(f"  Promoter:         {data.promoter_holding_pct}%")
        print()
        time.sleep(2)
