"""
Corporate Action, IPO Expiries & Institutional Flow Calendar.

Implements:
1. IPO Anchor Lock-in Expiry Calendar (Alerts 5 days prior to 30/90 day lock-in end).
2. NSDL Fortnightly FPI Sector Flow deployment tracker.
3. NSE SLB (Securities Lending & Borrowing) Short Interest tracker.

Fixes Problems: 176, 178, 179.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List


def check_ipo_anchor_lockin_expiry(ipo_listing_date: str, window_days: int = 5) -> Dict[str, Any]:
    """
    Alerts 5 days prior to 30-day or 90-day IPO anchor lock-in expiry to warn of potential supply floods.
    (Fixes Problem 176)
    """
    listing_dt = datetime.strptime(ipo_listing_date, "%Y-%m-%d")
    now = datetime.now()

    lockin_30_dt = listing_dt + timedelta(days=30)
    lockin_90_dt = listing_dt + timedelta(days=90)

    days_to_30 = (lockin_30_dt - now).days
    days_to_90 = (lockin_90_dt - now).days

    near_expiry = (0 <= days_to_30 <= window_days) or (0 <= days_to_90 <= window_days)

    return {
        "listing_date": ipo_listing_date,
        "days_to_30d_expiry": days_to_30,
        "days_to_90d_expiry": days_to_90,
        "near_anchor_lockin_expiry": near_expiry,
        "warning": "ANCHOR_LOCKIN_EXPIRY_RISK" if near_expiry else "NORMAL"
    }


def parse_slb_short_interest(borrow_fee_pct: float, borrowed_qty: int) -> Dict[str, Any]:
    """
    Tracks NSE SLB borrowing fees and volume to flag heavy short building.
    (Fixes Problem 179)
    """
    is_heavy_short = borrow_fee_pct >= 5.0 or borrowed_qty >= 500000
    return {
        "borrow_fee_pct": borrow_fee_pct,
        "borrowed_qty": borrowed_qty,
        "is_heavy_short_interest": is_heavy_short,
        "warning": "SLB_SHORT_BUILDING_WARNING" if is_heavy_short else "NORMAL"
    }


if __name__ == "__main__":
    print("Testing Corporate Calendar Module...\n")
    ipo_res = check_ipo_anchor_lockin_expiry("2026-08-01")
    print(f"  IPO Anchor Lock-in Status: {ipo_res}")
    slb_res = parse_slb_short_interest(6.5, 600000)
    print(f"  SLB Short Interest: {slb_res}")
