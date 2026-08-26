"""
Phase 1 equity universe: Nifty 500 constituents, sourced from the official
NSE constituent list (archives.nseindia.com/content/indices/ind_nifty500list.csv)
saved to nifty500_symbols.txt. This is the real, current index membership --
not a hand-typed guess -- refresh that file periodically since index
constituents change.

The liquidity filter (MIN_AVG_DAILY_TURNOVER_INR) is what actually keeps
the universe safe to trade at size -- it excludes illiquid names even
though they're nominally "in the universe", rather than us pre-guessing
which 500 stocks are worth including.
"""

from pathlib import Path

_SYMBOLS_FILE = Path(__file__).resolve().parent / "nifty500_symbols.txt"

with open(_SYMBOLS_FILE) as f:
    NIFTY_500_SYMBOLS = [line.strip() for line in f if line.strip()]

SECTOR_ETFS = [
    "NIFTYBEES.NS",   # Nifty 50 ETF
    "JUNIORBEES.NS",  # Nifty Next 50 ETF
    "BANKBEES.NS",    # Bank sector ETF
    "ITBEES.NS",      # IT sector ETF
    "PHARMBEES.NS",   # Pharma sector ETF
    "GOLDBEES.NS",    # Gold ETF (defensive sleeve, Phase 2 mainly)
]

# Regime-detection reference instruments
NIFTY_INDEX = "^NSEI"
INDIA_VIX = "^INDIAVIX"

EQUITY_UNIVERSE = NIFTY_500_SYMBOLS + SECTOR_ETFS

# Minimum average daily traded value (Rupees) to pass the liquidity filter.
# This is what actually protects capital deployment at size -- keep this
# active even as the universe widens to Nifty 500.
MIN_AVG_DAILY_TURNOVER_INR = 50_00_00_000  # Rs 50 crore
