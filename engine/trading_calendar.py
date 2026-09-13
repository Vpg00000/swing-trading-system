"""
NSE / BSE Trading Calendar & Business Day Helper
Handles weekend detection, Indian market holiday skipping, next trading day calculation,
and target exit date calculation.
"""

from __future__ import annotations
import datetime
from typing import Set

# Indian Stock Exchange (NSE/BSE) Standard Official Trading Holidays for 2025-2026
NSE_HOLIDAYS: Set[str] = {
    "2026-01-26",  # Republic Day
    "2026-03-06",  # Holi
    "2026-03-20",  # Id-Ul-Fitr (Ramzan Id)
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-27",  # Bakri Id
    "2026-06-25",  # Muharram
    "2026-08-15",  # Independence Day
    "2026-08-26",  # Milad-un-Nabi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-08",  # Diwali Laxmi Pujan
    "2026-11-09",  # Diwali Balipratipada
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
}


def is_trading_day(dt: datetime.date) -> bool:
    """Return True if dt is a valid NSE/BSE trading day (Mon-Fri and not an official holiday)."""
    if dt.weekday() in (5, 6):  # Saturday=5, Sunday=6
        return False
    date_str = dt.strftime("%Y-%m-%d")
    if date_str in NSE_HOLIDAYS:
        return False
    return True


def get_previous_trading_day(dt: datetime.date) -> datetime.date:
    """Return the most recent valid trading day on or before dt."""
    curr = dt
    while not is_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr


def get_next_trading_day(dt: datetime.date) -> datetime.date:
    """Return the next valid trading day on or strictly after dt."""
    curr = dt
    while not is_trading_day(curr):
        curr += datetime.timedelta(days=1)
    return curr


def add_trading_days(start_date: datetime.date, num_trading_days: int) -> datetime.date:
    """Add N trading days to start_date, automatically skipping weekends and NSE holidays."""
    curr = start_date
    added = 0
    while added < num_trading_days:
        curr += datetime.timedelta(days=1)
        if is_trading_day(curr):
            added += 1
    return curr


def get_trade_lifecycle_dates(
    reference_dt: datetime.date | None = None,
    holding_period_days: int = 15,
    now_dt: datetime.datetime | None = None,
) -> dict:
    """
    Computes exact market-aware trade schedule:
    - recommendation_date: Date when recommendation was generated (e.g. today)
    - purchase_date: Next market open trading day (skips weekend & holidays)
      - If run on weekend/holiday -> Next trading day (e.g. Monday 2026-09-07)
      - If run on weekday after market hours (>= 15:30 IST) -> Next trading day
      - If run on weekday during market hours (< 15:30 IST) -> Today
    - expected_sell_date: purchase_date + N trading days
    """
    if now_dt is None:
        now_dt = datetime.datetime.now()
    if reference_dt is None:
        reference_dt = now_dt.date()

    rec_date = reference_dt

    is_today_trading = is_trading_day(reference_dt)
    time_now = now_dt.time()
    market_close_time = datetime.time(15, 30)

    if is_today_trading and time_now < market_close_time:
        purch_date = reference_dt
    else:
        # Weekend, holiday, or past market close -> Next market open day
        purch_date = get_next_trading_day(reference_dt + datetime.timedelta(days=1))

    exp_sell_date = add_trading_days(purch_date, holding_period_days)

    return {
        "recommendation_date": rec_date.strftime("%Y-%m-%d"),
        "purchase_date": purch_date.strftime("%Y-%m-%d"),
        "expected_sell_date": exp_sell_date.strftime("%Y-%m-%d"),
        "holding_trading_days": holding_period_days,
        "is_weekend": reference_dt.weekday() in (5, 6),
    }

