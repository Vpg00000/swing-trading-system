"""
engine/orderbook_synthesizer.py — Dynamic Level 2 Order Book Synthesizer.

Generates realistic 5-level and 10-level bid/ask depth ladders for any stock symbol dynamically.
"""

import math
import random
from typing import Dict, Any, List, Optional


def synthesize_order_book(symbol: str, ltp: float, depth_levels: int = 5) -> Dict[str, Any]:
    """
    Synthesizes a realistic Level 2 depth ladder for a symbol based on LTP.

    Args:
        symbol: Stock ticker symbol (e.g. 'RELIANCE', 'TCS', 'INFY')
        ltp: Last traded price of the symbol
        depth_levels: Number of bid/ask levels (default 5)

    Returns:
        Dict containing bids, asks, total_bid_qty, total_ask_qty, spread, spread_pct, bid_ask_ratio
    """
    sym_clean = symbol.upper().strip()
    if ltp <= 0:
        ltp = 100.0

    # Tick size rules for Indian markets (₹0.05 minimum tick)
    tick_size = 0.05 if ltp < 10000 else 0.50
    spread_ticks = random.choice([1, 2, 3])
    spread = round(spread_ticks * tick_size, 2)

    best_bid = round(math.floor((ltp - (spread / 2)) / tick_size) * tick_size, 2)
    best_ask = round(best_bid + spread, 2)

    # Deterministic pseudo-random seed based on symbol & current hour to keep ladder stable yet dynamic
    seed_val = sum(ord(c) for c in sym_clean) + int(ltp)
    rng = random.Random(seed_val)

    bids: List[Dict[str, Any]] = []
    asks: List[Dict[str, Any]] = []

    total_bid_qty = 0
    total_ask_qty = 0

    base_qty = max(50, int((100000 / ltp) * rng.uniform(0.8, 1.5)))

    for i in range(depth_levels):
        # Bids step down
        bid_price = round(best_bid - (i * tick_size * rng.choice([1, 2])), 2)
        bid_qty = int(base_qty * (1 + (i * 0.15)) * rng.uniform(0.7, 1.4))
        bid_orders = rng.randint(2, 25 + i * 5)

        total_bid_qty += bid_qty
        bids.append({
            "level": i + 1,
            "price": bid_price,
            "quantity": bid_qty,
            "orders": bid_orders
        })

        # Asks step up
        ask_price = round(best_ask + (i * tick_size * rng.choice([1, 2])), 2)
        ask_qty = int(base_qty * (1 + (i * 0.15)) * rng.uniform(0.7, 1.4))
        ask_orders = rng.randint(2, 25 + i * 5)

        total_ask_qty += ask_qty
        asks.append({
            "level": i + 1,
            "price": ask_price,
            "quantity": ask_qty,
            "orders": ask_orders
        })

    bid_ask_ratio = round(total_bid_qty / max(1, total_ask_qty), 2)
    spread_pct = round((spread / max(0.01, ltp)) * 100.0, 3)
    imbalance_status = "BUY_PRESSURE" if bid_ask_ratio >= 1.2 else ("SELL_PRESSURE" if bid_ask_ratio <= 0.8 else "NEUTRAL")

    return {
        "symbol": sym_clean,
        "ltp": ltp,
        "depth_levels": depth_levels,
        "bids": bids,
        "asks": asks,
        "total_bid_quantity": total_bid_qty,
        "total_ask_quantity": total_ask_qty,
        "spread": spread,
        "spread_pct": spread_pct,
        "bid_ask_ratio": bid_ask_ratio,
        "imbalance_status": imbalance_status,
    }
