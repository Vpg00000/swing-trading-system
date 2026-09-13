"""
Global macro / cross-asset context -- forex, commodities, global rates,
crypto, and Nifty sectoral indices, per DESIGN.md's "Future-demand scenario
module" (commodity/geopolitical tracking feeding sector-tilt) and the
market-regime research framework's "Global markets" stage.

Data-input only: these feed regime/sector/catalyst scoring context (e.g. a
crude spike flags paint/tyre margin risk; a weak Rupee flags IT/pharma
exporter tailwind). This module does NOT enable trading any of these
assets -- DESIGN.md explicitly excludes retail forex speculation (FEMA)
and direct crude ownership (no retail vehicle in India); crypto stays
buy-and-hold-only per DESIGN.md, this module just prices it for context.

All tickers resolve live via yfinance -- no local cache, since this is a
handful of calls, cheap to always refetch fresh at report time.
"""

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore", category=FutureWarning)

# (display name, yfinance ticker) -- grouped by category for report layout.
FOREX_TICKERS = [
    ("USD/INR", "INR=X"),
    ("DXY (Dollar Index)", "DX-Y.NYB"),
    ("EUR/USD", "EURUSD=X"),
    ("GBP/USD", "GBPUSD=X"),
]
COMMODITY_TICKERS = [
    ("Brent Crude", "BZ=F"),
    ("WTI Crude", "CL=F"),
    ("Natural Gas", "NG=F"),
    ("Gold", "GC=F"),
    ("Silver", "SI=F"),
    ("Copper", "HG=F"),
]
GLOBAL_RATES_TICKERS = [
    ("US 10Y Yield", "^TNX"),
]
GLOBAL_EQUITY_TICKERS = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Nikkei 225", "^N225"),
    ("Hang Seng", "^HSI"),
]
CRYPTO_TICKERS = [
    ("Bitcoin (INR)", "BTC-INR"),
    ("Ethereum (INR)", "ETH-INR"),
]
NIFTY_SECTOR_INDEX_TICKERS = [
    ("Nifty Bank", "^NSEBANK"),
    ("Nifty IT", "^CNXIT"),
    ("Nifty Auto", "^CNXAUTO"),
    ("Nifty Pharma", "^CNXPHARMA"),
    ("Nifty FMCG", "^CNXFMCG"),
    ("Nifty Metal", "^CNXMETAL"),
]


@dataclass
class MacroQuote:
    name: str
    ticker: str
    last: float
    change_pct: float  # vs previous close in the pulled window


from concurrent.futures import ThreadPoolExecutor

def _fetch_quote(name: str, ticker: str) -> MacroQuote | None:
    try:
        hist = yf.Ticker(ticker).history(period="5d", timeout=5)
        if hist.empty or len(hist) < 2:
            return None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        change_pct = (last / prev - 1) * 100 if prev else 0.0
        return MacroQuote(name=name, ticker=ticker, last=last, change_pct=change_pct)
    except Exception:
        return None


def fetch_group(tickers: list[tuple[str, str]]) -> list[MacroQuote]:
    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as executor:
        results = list(executor.map(lambda item: _fetch_quote(item[0], item[1]), tickers))
    return [q for q in results if q is not None]


def fetch_all_macro() -> dict[str, list[MacroQuote]]:
    all_tickers = (
        FOREX_TICKERS +
        COMMODITY_TICKERS +
        GLOBAL_RATES_TICKERS +
        GLOBAL_EQUITY_TICKERS +
        CRYPTO_TICKERS +
        NIFTY_SECTOR_INDEX_TICKERS
    )
    
    quote_map = {}
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(_fetch_quote, name, ticker): (name, ticker) for name, ticker in all_tickers}
        for future in futures:
            name, ticker = futures[future]
            try:
                q = future.result()
                if q is not None:
                    quote_map[ticker] = q
            except Exception:
                pass

    return {
        "forex": [quote_map[t] for _, t in FOREX_TICKERS if t in quote_map],
        "commodities": [quote_map[t] for _, t in COMMODITY_TICKERS if t in quote_map],
        "global_rates": [quote_map[t] for _, t in GLOBAL_RATES_TICKERS if t in quote_map],
        "global_equity": [quote_map[t] for _, t in GLOBAL_EQUITY_TICKERS if t in quote_map],
        "crypto": [quote_map[t] for _, t in CRYPTO_TICKERS if t in quote_map],
        "nifty_sectors": [quote_map[t] for _, t in NIFTY_SECTOR_INDEX_TICKERS if t in quote_map],
    }


if __name__ == "__main__":
    groups = fetch_all_macro()
    for label, quotes in groups.items():
        print(f"\n-- {label.replace('_', ' ').upper()} --")
        for q in quotes:
            print(f"  {q.name:<22} {q.last:>12,.2f}  {q.change_pct:+.2f}%")
