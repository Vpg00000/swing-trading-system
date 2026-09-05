"""
Execution Fill Rate Tracker & Basis-Point Slippage Calculator (TASK-044).

Implements:
1. Exact basis point (bps) execution slippage calculation vs benchmark price.
2. Order fill rate percentage tracking (executed / requested quantity).
3. Market impact cost quantification (INR).
4. Aggregate summary metrics and slippage report generation.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


def calculate_slippage_bps(
    transaction_type: str,
    benchmark_price: float,
    actual_fill_price: float
) -> float:
    """
    Calculates execution slippage in basis points (bps).
    
    Formula:
    - BUY:  ((actual_fill_price - benchmark_price) / benchmark_price) * 10000.0
            Positive value = adverse slippage (paid higher price).
            Negative value = price improvement (paid lower price).
    - SELL: ((benchmark_price - actual_fill_price) / benchmark_price) * 10000.0
            Positive value = adverse slippage (received lower price).
            Negative value = price improvement (received higher price).
    """
    tx = transaction_type.upper()
    b_price = float(benchmark_price)
    f_price = float(actual_fill_price)

    if b_price <= 0:
        return 0.0

    if tx == "BUY":
        bps = ((f_price - b_price) / b_price) * 10000.0
    else:  # SELL
        bps = ((b_price - f_price) / b_price) * 10000.0

    return round(bps, 2)


class ExecutionRecord:
    """Represents a logged execution for slippage tracking."""

    def __init__(
        self,
        order_id: str,
        symbol: str,
        transaction_type: str,
        requested_quantity: int,
        executed_quantity: int,
        benchmark_price: float,
        actual_fill_price: float,
        broker: str = "dhan",
        exchange: str = "NSE",
        record_id: Optional[str] = None,
        timestamp: Optional[str] = None
    ):
        self.record_id = record_id or f"SLIP-{uuid.uuid4().hex[:8].upper()}"
        self.order_id = order_id
        self.symbol = symbol.upper()
        self.transaction_type = transaction_type.upper()
        self.requested_quantity = int(requested_quantity)
        self.executed_quantity = int(executed_quantity)
        self.benchmark_price = float(benchmark_price)
        self.actual_fill_price = float(actual_fill_price)
        self.broker = broker.lower()
        self.exchange = exchange.upper()
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

        # Derived calculations
        self.slippage_bps = calculate_slippage_bps(
            self.transaction_type,
            self.benchmark_price,
            self.actual_fill_price
        )
        
        if self.requested_quantity > 0:
            self.fill_rate_pct = round((self.executed_quantity / self.requested_quantity) * 100.0, 2)
        else:
            self.fill_rate_pct = 0.0

        self.price_delta = round(abs(self.actual_fill_price - self.benchmark_price), 2)
        self.market_impact_cost = round(self.price_delta * self.executed_quantity, 2)
        self.is_adverse = self.slippage_bps > 0.0
        self.is_favorable = self.slippage_bps < 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "order_id": self.order_id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "transaction_type": self.transaction_type,
            "requested_quantity": self.requested_quantity,
            "executed_quantity": self.executed_quantity,
            "fill_rate_pct": self.fill_rate_pct,
            "benchmark_price": self.benchmark_price,
            "actual_fill_price": self.actual_fill_price,
            "price_delta": self.price_delta,
            "slippage_bps": self.slippage_bps,
            "market_impact_cost": self.market_impact_cost,
            "is_adverse": self.is_adverse,
            "is_favorable": self.is_favorable,
            "broker": self.broker,
            "exchange": self.exchange
        }


class SlippageTracker:
    """
    Tracks order fills, execution slippage in basis points, and market impact cost.
    """

    def __init__(self):
        self._history: List[ExecutionRecord] = []

    def record_execution(
        self,
        order_id: str,
        symbol: str,
        transaction_type: str,
        requested_quantity: int,
        executed_quantity: int,
        benchmark_price: float,
        actual_fill_price: float,
        broker: str = "dhan",
        exchange: str = "NSE"
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            order_id=order_id,
            symbol=symbol,
            transaction_type=transaction_type,
            requested_quantity=requested_quantity,
            executed_quantity=executed_quantity,
            benchmark_price=benchmark_price,
            actual_fill_price=actual_fill_price,
            broker=broker,
            exchange=exchange
        )
        self._history.append(record)
        log.info(
            f"[SLIPPAGE] Recorded fill {order_id} ({symbol} {transaction_type}): "
            f"Fill={actual_fill_price} vs Bench={benchmark_price} -> Slippage={record.slippage_bps:.2f} bps, Fill Rate={record.fill_rate_pct}%"
        )
        return record

    def get_execution_history(
        self,
        symbol: Optional[str] = None,
        broker: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        history = self._history
        if symbol:
            history = [r for r in history if r.symbol == symbol.upper()]
        if broker:
            history = [r for r in history if r.broker == broker.lower()]
        return [r.to_dict() for r in history]

    def calculate_stats(
        self,
        symbol: Optional[str] = None,
        broker: Optional[str] = None
    ) -> Dict[str, Any]:
        records = self._history
        if symbol:
            records = [r for r in records if r.symbol == symbol.upper()]
        if broker:
            records = [r for r in records if r.broker == broker.lower()]

        if not records:
            return {
                "total_orders": 0,
                "avg_slippage_bps": 0.0,
                "max_adverse_slippage_bps": 0.0,
                "best_favorable_slippage_bps": 0.0,
                "avg_fill_rate_pct": 0.0,
                "total_market_impact_cost": 0.0,
                "adverse_fills_count": 0,
                "favorable_fills_count": 0,
                "zero_slippage_count": 0
            }

        slippage_values = [r.slippage_bps for r in records]
        fill_rates = [r.fill_rate_pct for r in records]
        impact_costs = [r.market_impact_cost for r in records]

        adverse_count = sum(1 for r in records if r.is_adverse)
        favorable_count = sum(1 for r in records if r.is_favorable)
        zero_count = len(records) - adverse_count - favorable_count

        return {
            "total_orders": len(records),
            "avg_slippage_bps": round(sum(slippage_values) / len(slippage_values), 2),
            "max_adverse_slippage_bps": round(max(slippage_values), 2),
            "best_favorable_slippage_bps": round(min(slippage_values), 2),
            "avg_fill_rate_pct": round(sum(fill_rates) / len(fill_rates), 2),
            "total_market_impact_cost": round(sum(impact_costs), 2),
            "adverse_fills_count": adverse_count,
            "favorable_fills_count": favorable_count,
            "zero_slippage_count": zero_count
        }

    def generate_slippage_report(self) -> Dict[str, Any]:
        overall_stats = self.calculate_stats()
        
        # Group by broker
        brokers = set(r.broker for r in self._history)
        broker_breakdown = {b: self.calculate_stats(broker=b) for b in brokers}

        # Group by symbol
        symbols = set(r.symbol for r in self._history)
        symbol_breakdown = {s: self.calculate_stats(symbol=s) for s in symbols}

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_summary": overall_stats,
            "broker_breakdown": broker_breakdown,
            "symbol_breakdown": symbol_breakdown,
            "total_records_logged": len(self._history)
        }

    def reset(self):
        self._history.clear()


# Global Singleton Instance
_SLIPPAGE_TRACKER = SlippageTracker()


def get_slippage_tracker() -> SlippageTracker:
    return _SLIPPAGE_TRACKER


def reset_slippage_tracker():
    global _SLIPPAGE_TRACKER
    _SLIPPAGE_TRACKER = SlippageTracker()
