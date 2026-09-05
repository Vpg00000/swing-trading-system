"""
NSE/BSE Best Execution Smart Order Router (TASK-042).

Implements:
1. Level-2 order book depth analysis for NSE vs BSE exchanges.
2. Volume-Weighted Average Price (VWAP) and effective fill price calculation across order book levels.
3. Bid-Ask spread & liquidity depth metrics.
4. Dynamic exchange selection maximizing execution price savings.
5. Audit trail evidence comparing quote vs expected execution.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class Level2Level:
    """Represents a single level of bid or ask depth in Level-2 order book."""
    def __init__(self, price: float, quantity: int, orders: int = 1):
        self.price = float(price)
        self.quantity = int(quantity)
        self.orders = int(orders)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "price": self.price,
            "quantity": self.quantity,
            "orders": self.orders
        }


class Level2Depth:
    """Represents Level-2 order book depth with bids and asks."""
    def __init__(self, bids: List[Dict[str, Any]], asks: List[Dict[str, Any]], timestamp: Optional[str] = None):
        self.bids = [Level2Level(**b) if isinstance(b, dict) else b for b in bids]
        # Ensure bids sorted descending by price
        self.bids.sort(key=lambda x: x.price, reverse=True)

        self.asks = [Level2Level(**a) if isinstance(a, dict) else a for a in asks]
        # Ensure asks sorted ascending by price
        self.asks.sort(key=lambda x: x.price)

        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def get_best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    def get_best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    def get_spread(self) -> Optional[float]:
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is not None and ask is not None:
            return ask - bid
        return None

    def get_mid_price(self) -> Optional[float]:
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return None


def calculate_effective_execution_price(
    depth: Level2Depth,
    transaction_type: str,
    quantity: int
) -> Dict[str, Any]:
    """
    Calculates expected effective fill price (VWAP) across Level-2 order book depth
    for a given order quantity.
    """
    tx = transaction_type.upper()
    levels = depth.asks if tx == "BUY" else depth.bids

    if not levels:
        return {
            "effective_price": 0.0,
            "filled_quantity": 0,
            "unfilled_quantity": quantity,
            "market_impact_bps": 9999.0,
            "levels_used": 0,
            "total_cost": 0.0
        }

    remaining_qty = quantity
    total_cost = 0.0
    filled_qty = 0
    levels_used = 0

    best_price = levels[0].price

    for lvl in levels:
        if remaining_qty <= 0:
            break
        levels_used += 1
        qty_take = min(remaining_qty, lvl.quantity)
        total_cost += qty_take * lvl.price
        filled_qty += qty_take
        remaining_qty -= qty_take

    if filled_qty == 0:
        effective_price = best_price
    else:
        effective_price = total_cost / filled_qty

    # Calculate market impact in basis points relative to best bid/ask
    if best_price > 0:
        if tx == "BUY":
            impact_bps = ((effective_price - best_price) / best_price) * 10000.0
        else:
            impact_bps = ((best_price - effective_price) / best_price) * 10000.0
    else:
        impact_bps = 0.0

    return {
        "effective_price": effective_price,
        "filled_quantity": filled_qty,
        "unfilled_quantity": remaining_qty,
        "market_impact_bps": round(impact_bps, 2),
        "levels_used": levels_used,
        "total_cost": round(total_cost, 2)
    }


class SmartOrderRouter:
    """
    Smart Order Router selecting optimal exchange (NSE vs BSE)
    based on Level-2 bid-ask spread and order book depth.
    """

    def evaluate_exchanges(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        nse_depth: Level2Depth,
        bse_depth: Level2Depth
    ) -> Dict[str, Any]:
        """
        Evaluates execution quotes and order book depth on NSE and BSE,
        returning optimal exchange selection with detailed comparison evidence.
        """
        tx = transaction_type.upper()
        quantity = int(quantity)

        # 1. NSE Evaluation
        nse_mid = nse_depth.get_mid_price() or 0.0
        nse_spread = nse_depth.get_spread() or 0.0
        nse_spread_bps = ((nse_spread / nse_mid) * 10000.0) if nse_mid > 0 else 0.0
        nse_exec = calculate_effective_execution_price(nse_depth, tx, quantity)

        # 2. BSE Evaluation
        bse_mid = bse_depth.get_mid_price() or 0.0
        bse_spread = bse_depth.get_spread() or 0.0
        bse_spread_bps = ((bse_spread / bse_mid) * 10000.0) if bse_mid > 0 else 0.0
        bse_exec = calculate_effective_execution_price(bse_depth, tx, quantity)

        nse_metrics = {
            "exchange": "NSE",
            "best_bid": nse_depth.get_best_bid(),
            "best_ask": nse_depth.get_best_ask(),
            "mid_price": round(nse_mid, 2),
            "spread": round(nse_spread, 2),
            "spread_bps": round(nse_spread_bps, 2),
            "effective_price": round(nse_exec["effective_price"], 2),
            "market_impact_bps": nse_exec["market_impact_bps"],
            "filled_quantity": nse_exec["filled_quantity"],
            "total_cost": nse_exec["total_cost"]
        }

        bse_metrics = {
            "exchange": "BSE",
            "best_bid": bse_depth.get_best_bid(),
            "best_ask": bse_depth.get_best_ask(),
            "mid_price": round(bse_mid, 2),
            "spread": round(bse_spread, 2),
            "spread_bps": round(bse_spread_bps, 2),
            "effective_price": round(bse_exec["effective_price"], 2),
            "market_impact_bps": bse_exec["market_impact_bps"],
            "filled_quantity": bse_exec["filled_quantity"],
            "total_cost": bse_exec["total_cost"]
        }

        # 3. Dynamic Routing Decision Logic
        # For BUY: lower effective_price is better
        # For SELL: higher effective_price is better
        selected_exchange = "NSE"
        reason = ""
        price_diff = bse_metrics["effective_price"] - nse_metrics["effective_price"]

        # Calculate basis point savings relative to mid price
        base_mid = nse_mid or bse_mid or 1.0

        if tx == "BUY":
            if nse_metrics["effective_price"] < bse_metrics["effective_price"]:
                selected_exchange = "NSE"
                price_savings_bps = (abs(price_diff) / base_mid) * 10000.0
                reason = f"NSE offers lower buy execution price ({nse_metrics['effective_price']:.2f} vs BSE {bse_metrics['effective_price']:.2f})"
            elif bse_metrics["effective_price"] < nse_metrics["effective_price"]:
                selected_exchange = "BSE"
                price_savings_bps = (abs(price_diff) / base_mid) * 10000.0
                reason = f"BSE offers lower buy execution price ({bse_metrics['effective_price']:.2f} vs NSE {nse_metrics['effective_price']:.2f})"
            else:
                # TIE breaker: tighter spread or higher fill quantity
                if nse_metrics["spread_bps"] <= bse_metrics["spread_bps"]:
                    selected_exchange = "NSE"
                    reason = "Equal execution price; NSE selected due to tighter spread"
                else:
                    selected_exchange = "BSE"
                    reason = "Equal execution price; BSE selected due to tighter spread"
                price_savings_bps = 0.0
        else: # SELL
            if nse_metrics["effective_price"] > bse_metrics["effective_price"]:
                selected_exchange = "NSE"
                price_savings_bps = (abs(price_diff) / base_mid) * 10000.0
                reason = f"NSE offers higher sell execution price ({nse_metrics['effective_price']:.2f} vs BSE {bse_metrics['effective_price']:.2f})"
            elif bse_metrics["effective_price"] > nse_metrics["effective_price"]:
                selected_exchange = "BSE"
                price_savings_bps = (abs(price_diff) / base_mid) * 10000.0
                reason = f"BSE offers higher sell execution price ({bse_metrics['effective_price']:.2f} vs NSE {nse_metrics['effective_price']:.2f})"
            else:
                if nse_metrics["spread_bps"] <= bse_metrics["spread_bps"]:
                    selected_exchange = "NSE"
                    reason = "Equal execution price; NSE selected due to tighter spread"
                else:
                    selected_exchange = "BSE"
                    reason = "Equal execution price; BSE selected due to tighter spread"
                price_savings_bps = 0.0

        spread_delta = round(abs(nse_metrics["spread"] - bse_metrics["spread"]), 2)

        evidence = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "transaction_type": tx,
            "requested_quantity": quantity,
            "selected_exchange": selected_exchange,
            "reason": reason,
            "spread_delta": spread_delta,
            "price_savings_bps": round(price_savings_bps, 2),
            "nse": nse_metrics,
            "bse": bse_metrics
        }

        log.info(f"[SOR] Evaluated {symbol} {tx} qty={quantity} -> Selected {selected_exchange}. {reason}")

        return {
            "selected_exchange": selected_exchange,
            "reason": reason,
            "spread_delta": spread_delta,
            "price_savings_bps": round(price_savings_bps, 2),
            "nse_metrics": nse_metrics,
            "bse_metrics": bse_metrics,
            "evidence": evidence
        }


# Global Singleton Router
_SMART_ROUTER = SmartOrderRouter()


def get_smart_router() -> SmartOrderRouter:
    return _SMART_ROUTER


def route_smart_order(
    symbol: str,
    transaction_type: str,
    quantity: int,
    nse_depth: Dict[str, Any],
    bse_depth: Dict[str, Any]
) -> Dict[str, Any]:
    """Convenience helper function for smart order routing."""
    router = get_smart_router()
    nse_l2 = Level2Depth(**nse_depth)
    bse_l2 = Level2Depth(**bse_depth)
    return router.evaluate_exchanges(symbol, transaction_type, quantity, nse_l2, bse_l2)
