"""
Real, tradeable ETF universe for the Phase 2 gold/silver/equity-index sleeve.

AMFI's NAVAll.txt (see data/amfi.py) identifies which schemes are gold /
silver / equity ETFs and gives their NAV, but it does NOT give the NSE
ticker symbol needed to actually place a trade -- ETFs are bought/sold on
the exchange like a stock, not subscribed to like a mutual fund.

Source for the missing link: the official NSE ETF security list
(archives.nseindia.com/content/equities/eq_etfseclist.csv), saved to
config/nse_etf_list.csv. It carries the same ISIN as AMFI, so we join on
ISIN rather than guessing tickers from fund names -- guessing would risk
recommending a symbol that doesn't exist or belongs to a different fund.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data.amfi import fetch_and_parse, FundRecord

NSE_ETF_LIST_PATH = Path(__file__).resolve().parent.parent / "config" / "nse_etf_list.csv"
LIQUIDITY_LOOKBACK_DAYS = "5d"


@dataclass
class ETFListing:
    ticker: str  # NSE symbol, e.g. "GOLDBEES" -- append ".NS" for yfinance
    underlying: str
    scheme_name: str
    isin: str
    nav: float
    nav_date: str
    sleeve: str


def load_nse_etf_list() -> pd.DataFrame:
    df = pd.read_csv(NSE_ETF_LIST_PATH, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    return df


def build_etf_universe(amfi_records: list[FundRecord] | None = None) -> list[ETFListing]:
    """
    Join AMFI's gold_etf/silver_etf/equity_etf sleeve records to real NSE
    tickers via ISIN. Records with no ISIN match on NSE's list are dropped
    silently -- most of those are FOF (fund-of-funds) wrappers that are
    bought via mutual fund platforms, not exchange tickers, so they belong
    in the AMFI-only fund view, not here.
    """
    if amfi_records is None:
        amfi_records = fetch_and_parse()

    nse_df = load_nse_etf_list()
    isin_to_ticker = dict(zip(nse_df["ISINNumber"], nse_df["Symbol"]))
    isin_to_underlying = dict(zip(nse_df["ISINNumber"], nse_df["Underlying"]))

    listings = []
    seen_tickers = set()
    for r in amfi_records:
        if r.sleeve not in ("gold_etf", "silver_etf", "equity_etf"):
            continue
        if not r.isin or r.isin not in isin_to_ticker:
            continue
        ticker = isin_to_ticker[r.isin]
        if ticker in seen_tickers:
            continue  # AMFI can list the same ISIN multiple times (IDCW/growth NAV rows)
        seen_tickers.add(ticker)
        listings.append(ETFListing(
            ticker=ticker,
            underlying=isin_to_underlying.get(r.isin, ""),
            scheme_name=r.scheme_name,
            isin=r.isin,
            nav=r.nav,
            nav_date=r.date,
            sleeve=r.sleeve,
        ))
    return listings


def get_etf_tickers(sleeve: str, amfi_records: list[FundRecord] | None = None) -> list[str]:
    """Convenience: just the yfinance-ready .NS tickers for a sleeve."""
    listings = build_etf_universe(amfi_records)
    return [f"{l.ticker}.NS" for l in listings if l.sleeve == sleeve]


def most_liquid_etf(listings: list[ETFListing], sleeve: str) -> ETFListing | None:
    """
    Same underlying benchmark, different AMC -- pick the one that's actually
    liquid enough to trade at size. AMFI lists dozens of near-identical gold
    ETFs (GOLDBEES, GOLD1, SETFGOLD, ...); NAV alone can't tell them apart,
    but real average daily turnover can (confirmed: GOLDBEES trades at
    ~10-40x the turnover of most competing gold ETFs).
    """
    rows = [l for l in listings if l.sleeve == sleeve]
    if not rows:
        return None

    best, best_turnover = None, -1.0
    for l in rows:
        hist = yf.Ticker(f"{l.ticker}.NS").history(period=LIQUIDITY_LOOKBACK_DAYS)
        if hist.empty:
            continue
        turnover = float((hist["Close"] * hist["Volume"]).mean())
        if turnover > best_turnover:
            best, best_turnover = l, turnover
    return best or rows[0]


if __name__ == "__main__":
    print("Fetching AMFI data and joining to NSE ETF tickers...")
    universe = build_etf_universe()
    print(f"\n{len(universe)} ETFs matched to real NSE tickers.\n")

    for sleeve in ["gold_etf", "silver_etf", "equity_etf"]:
        rows = [l for l in universe if l.sleeve == sleeve]
        print(f"-- {sleeve} ({len(rows)}) --")
        for l in rows[:10]:
            print(f"  {l.ticker:<14} {l.scheme_name:<45} NAV {l.nav:>10.2f} ({l.nav_date})")
        print()
