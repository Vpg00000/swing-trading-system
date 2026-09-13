"""
Algorithmic Execution Engine & Smart Pacing Module (Phase 20).

Implements:
1. T-245: TWAP (Time-Weighted Average Price) slice order execution algorithm.
2. T-246: VWAP (Volume-Weighted Average Price) execution algorithm matching market volume curves.
3. T-247: Iceberg execution engine (splitting large order into hidden child orders).
4. T-248: Sniper execution engine (hidden order execution when ask/bid threshold is touched).
5. T-249: Implementation Shortfall benchmark tracking vs arrival price.
6. T-252: Automated order pacing to avoid triggering SEBI pattern alerts.
7. T-253: Algo parent-child order status visualization hierarchy & state machine.
"""

import time
import math
import random
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple


class AlgoType(str, Enum):
    TWAP = "TWAP"
    VWAP = "VWAP"
    ICEBERG = "ICEBERG"
    SNIPER = "SNIPER"


class AlgoStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    KILLED = "KILLED"


class ChildOrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class ChildOrder:
    slice_id: str
    parent_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: int
    price: float
    status: ChildOrderStatus = ChildOrderStatus.PENDING
    scheduled_time: float = 0.0
    fill_time: Optional[float] = None
    fill_price: float = 0.0
    slippage_bps: float = 0.0
    is_hidden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value if isinstance(self.status, Enum) else self.status
        return d


@dataclass
class ParentAlgoOrder:
    algo_id: str
    algo_type: AlgoType
    symbol: str
    side: str
    total_quantity: int
    arrival_price: float
    status: AlgoStatus = AlgoStatus.PENDING
    created_at: float = field(default_factory=time.time)
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    child_orders: List[ChildOrder] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    explicit_costs: float = 0.0
    implementation_shortfall_bps: float = 0.0
    total_slippage_bps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['algo_type'] = self.algo_type.value if isinstance(self.algo_type, Enum) else self.algo_type
        d['status'] = self.status.value if isinstance(self.status, Enum) else self.status
        d['child_orders'] = [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.child_orders]
        return d


def calculate_implementation_shortfall(
    side: str,
    arrival_price: float,
    avg_fill_price: float,
    filled_quantity: int,
    explicit_costs: float = 0.0
) -> Tuple[float, float]:
    """
    T-249: Implementation Shortfall benchmark tracking vs arrival price.
    Returns (IS_currency, IS_bps).
    Side: "BUY" -> loss if avg_fill > arrival
          "SELL" -> loss if avg_fill < arrival
    """
    if arrival_price <= 0 or filled_quantity <= 0:
        return 0.0, 0.0

    side_sign = 1.0 if side.upper() == "BUY" else -1.0
    execution_diff = (avg_fill_price - arrival_price) * side_sign
    is_currency = (execution_diff * filled_quantity) + explicit_costs
    is_bps = (is_currency / (arrival_price * filled_quantity)) * 10000.0
    return round(is_currency, 2), round(is_bps, 2)


def generate_twap_slices(
    parent_id: str,
    symbol: str,
    side: str,
    total_quantity: int,
    arrival_price: float,
    duration_seconds: int = 300,
    n_slices: int = 5
) -> List[ChildOrder]:
    """
    T-245: TWAP slice order generator.
    Splits parent order evenly across time slices with exact integer allocation.
    """
    if n_slices <= 0 or total_quantity <= 0:
        return []

    base_qty = total_quantity // n_slices
    remainder = total_quantity % n_slices
    interval = duration_seconds / float(n_slices)
    now = time.time()

    slices = []
    for i in range(n_slices):
        qty = base_qty + (1 if i < remainder else 0)
        if qty <= 0:
            continue
        slice_id = f"{parent_id}_TWAP_{i+1}"
        sched_time = now + (i * interval)
        slices.append(
            ChildOrder(
                slice_id=slice_id,
                parent_id=parent_id,
                symbol=symbol,
                side=side,
                quantity=qty,
                price=arrival_price,
                scheduled_time=sched_time
            )
        )
    return slices


def generate_vwap_slices(
    parent_id: str,
    symbol: str,
    side: str,
    total_quantity: int,
    arrival_price: float,
    volume_profile: Optional[List[float]] = None,
    duration_seconds: int = 300
) -> List[ChildOrder]:
    """
    T-246: VWAP slice order generator matching volume curve.
    Uses volume_profile (list of float weights) to weight slice quantities.
    """
    if total_quantity <= 0:
        return []

    if not volume_profile:
        # Default U-shaped intraday volume curve
        volume_profile = [0.25, 0.15, 0.10, 0.15, 0.35]

    total_weight = sum(volume_profile)
    if total_weight <= 0:
        weights = [1.0 / len(volume_profile)] * len(volume_profile)
    else:
        weights = [w / total_weight for w in volume_profile]

    n_slices = len(weights)
    interval = duration_seconds / float(n_slices)
    now = time.time()

    raw_qtys = [w * total_quantity for w in weights]
    int_qtys = [int(q) for q in raw_qtys]
    diff = total_quantity - sum(int_qtys)

    # Distribute integer remainder to slices with highest fractional residual
    residuals = [raw_qtys[i] - int_qtys[i] for i in range(n_slices)]
    sorted_res_indices = sorted(range(n_slices), key=lambda k: residuals[k], reverse=True)
    for i in range(diff):
        int_qtys[sorted_res_indices[i % n_slices]] += 1

    slices = []
    for i in range(n_slices):
        qty = int_qtys[i]
        if qty <= 0:
            continue
        slice_id = f"{parent_id}_VWAP_{i+1}"
        sched_time = now + (i * interval)
        slices.append(
            ChildOrder(
                slice_id=slice_id,
                parent_id=parent_id,
                symbol=symbol,
                side=side,
                quantity=qty,
                price=arrival_price,
                scheduled_time=sched_time
            )
        )
    return slices


def generate_iceberg_slice(
    parent_id: str,
    symbol: str,
    side: str,
    remaining_quantity: int,
    visible_quantity: int,
    arrival_price: float,
    slice_index: int = 1,
    variance_pct: float = 0.1
) -> Optional[ChildOrder]:
    """
    T-247: Iceberg slice generator (creates next visible child order with optional footprint variance).
    """
    if remaining_quantity <= 0 or visible_quantity <= 0:
        return None

    # Apply footprint noise variance (+/- variance_pct) to hide constant slice size
    var = 1.0 + random.uniform(-variance_pct, variance_pct)
    target_qty = int(round(visible_quantity * var))
    target_qty = max(1, min(remaining_quantity, target_qty))

    slice_id = f"{parent_id}_ICEBERG_{slice_index}"
    return ChildOrder(
        slice_id=slice_id,
        parent_id=parent_id,
        symbol=symbol,
        side=side,
        quantity=target_qty,
        price=arrival_price,
        scheduled_time=time.time(),
        is_hidden=True
    )


def evaluate_sniper_trigger(
    side: str,
    current_market_price: float,
    trigger_price: float
) -> bool:
    """
    T-248: Sniper execution engine trigger detector.
    Triggers execution when ask/bid threshold is touched.
    BUY: market price <= trigger_price
    SELL: market price >= trigger_price
    """
    if side.upper() == "BUY":
        return current_market_price <= trigger_price
    else:
        return current_market_price >= trigger_price


class OrderPacer:
    """
    T-252: Automated order pacing to avoid triggering SEBI pattern alerts.
    Enforces minimum delay, randomized jitter, and volume participation rate caps.
    """
    def __init__(self, min_delay_ms: int = 500, max_participation_pct: float = 0.10):
        self.min_delay_ms = min_delay_ms
        self.max_participation_pct = max_participation_pct
        self.last_order_time = 0.0

    def calculate_next_execution_time(self, current_time: float) -> float:
        """Adds randomized jitter (500ms - 1500ms) between order slices."""
        jitter_ms = random.randint(self.min_delay_ms, self.min_delay_ms * 3)
        delay_seconds = jitter_ms / 1000.0
        base_time = max(current_time, self.last_order_time)
        next_time = base_time + delay_seconds
        self.last_order_time = next_time
        return next_time

    def cap_slice_quantity(self, desired_qty: int, market_volume_window: int) -> int:
        """Caps slice size so it never exceeds max_participation_pct of market volume."""
        if market_volume_window <= 0:
            return desired_qty
        allowed = int(market_volume_window * self.max_participation_pct)
        return max(1, min(desired_qty, allowed))


class AlgoExecutionEngine:
    """
    T-250 & T-253: Algo Execution Control Engine & Hierarchy Manager.
    Manages active algos, start/pause/resume/kill operations, and order fill tracking.
    """
    def __init__(self):
        self.active_algos: Dict[str, ParentAlgoOrder] = {}
        self.completed_algos: Dict[str, ParentAlgoOrder] = {}
        self.pacer = OrderPacer()

    def start_algo(
        self,
        algo_type: Union[AlgoType, str],
        symbol: str,
        side: str,
        total_quantity: int,
        arrival_price: float,
        params: Optional[Dict[str, Any]] = None
    ) -> ParentAlgoOrder:
        params = params or {}
        algo_id = f"ALGO_{uuid.uuid4().hex[:8].upper()}"
        if isinstance(algo_type, str):
            algo_type = AlgoType(algo_type.upper())

        parent = ParentAlgoOrder(
            algo_id=algo_id,
            algo_type=algo_type,
            symbol=symbol.upper(),
            side=side.upper(),
            total_quantity=total_quantity,
            arrival_price=arrival_price,
            status=AlgoStatus.ACTIVE,
            params=params
        )

        # Generate initial child slices based on AlgoType
        if algo_type == AlgoType.TWAP:
            duration = params.get("duration_seconds", 300)
            n_slices = params.get("n_slices", 5)
            parent.child_orders = generate_twap_slices(
                algo_id, symbol, side, total_quantity, arrival_price, duration, n_slices
            )

        elif algo_type == AlgoType.VWAP:
            profile = params.get("volume_profile", [0.25, 0.15, 0.10, 0.15, 0.35])
            duration = params.get("duration_seconds", 300)
            parent.child_orders = generate_vwap_slices(
                algo_id, symbol, side, total_quantity, arrival_price, profile, duration
            )

        elif algo_type == AlgoType.ICEBERG:
            vis_qty = params.get("visible_quantity", max(1, total_quantity // 5))
            first_slice = generate_iceberg_slice(
                algo_id, symbol, side, total_quantity, vis_qty, arrival_price, 1
            )
            if first_slice:
                parent.child_orders = [first_slice]

        elif algo_type == AlgoType.SNIPER:
            trigger_price = params.get("trigger_price", arrival_price)
            slice_order = ChildOrder(
                slice_id=f"{algo_id}_SNIPER_1",
                parent_id=algo_id,
                symbol=symbol,
                side=side,
                quantity=total_quantity,
                price=trigger_price,
                scheduled_time=time.time(),
                is_hidden=True
            )
            parent.child_orders = [slice_order]

        self.active_algos[algo_id] = parent
        return parent

    def pause_algo(self, algo_id: str) -> bool:
        """T-250: Pause active algo."""
        if algo_id in self.active_algos:
            self.active_algos[algo_id].status = AlgoStatus.PAUSED
            return True
        return False

    def resume_algo(self, algo_id: str) -> bool:
        """T-250: Resume paused algo."""
        if algo_id in self.active_algos:
            if self.active_algos[algo_id].status == AlgoStatus.PAUSED:
                self.active_algos[algo_id].status = AlgoStatus.ACTIVE
                return True
        return False

    def kill_algo(self, algo_id: str) -> bool:
        """T-250: Emergency Kill active or paused algo."""
        if algo_id in self.active_algos:
            parent = self.active_algos.pop(algo_id)
            parent.status = AlgoStatus.KILLED
            for child in parent.child_orders:
                if child.status == ChildOrderStatus.PENDING:
                    child.status = ChildOrderStatus.CANCELLED
            self.completed_algos[algo_id] = parent
            return True
        return False

    def fill_child_order(
        self,
        algo_id: str,
        slice_id: str,
        fill_price: float,
        explicit_cost: float = 0.0
    ) -> Optional[ParentAlgoOrder]:
        """Processes child slice execution fill and updates Implementation Shortfall."""
        if algo_id not in self.active_algos:
            return None

        parent = self.active_algos[algo_id]
        if parent.status != AlgoStatus.ACTIVE:
            return parent

        target_child = None
        for child in parent.child_orders:
            if child.slice_id == slice_id and child.status == ChildOrderStatus.PENDING:
                target_child = child
                break

        if not target_child:
            return parent

        target_child.status = ChildOrderStatus.FILLED
        target_child.fill_price = fill_price
        target_child.fill_time = time.time()

        # Calculate child slippage bps
        side_sign = 1.0 if parent.side == "BUY" else -1.0
        slippage_diff = (fill_price - parent.arrival_price) * side_sign
        target_child.slippage_bps = round((slippage_diff / parent.arrival_price) * 10000.0, 2)

        # Update parent aggregates
        new_filled_qty = parent.filled_quantity + target_child.quantity
        tot_spent = (parent.avg_fill_price * parent.filled_quantity) + (fill_price * target_child.quantity)
        parent.filled_quantity = new_filled_qty
        parent.avg_fill_price = round(tot_spent / new_filled_qty, 2) if new_filled_qty > 0 else 0.0
        parent.explicit_costs += explicit_cost

        is_curr, is_bps = calculate_implementation_shortfall(
            parent.side, parent.arrival_price, parent.avg_fill_price, parent.filled_quantity, parent.explicit_costs
        )
        parent.implementation_shortfall_bps = is_bps
        parent.total_slippage_bps = is_bps

        # Iceberg logic: spawn next slice if unfilled quantity remains
        if parent.algo_type == AlgoType.ICEBERG and parent.filled_quantity < parent.total_quantity:
            vis_qty = parent.params.get("visible_quantity", max(1, parent.total_quantity // 5))
            rem_qty = parent.total_quantity - parent.filled_quantity
            next_slice_idx = len(parent.child_orders) + 1
            next_child = generate_iceberg_slice(
                algo_id, parent.symbol, parent.side, rem_qty, vis_qty, parent.arrival_price, next_slice_idx
            )
            if next_child:
                parent.child_orders.append(next_child)

        # Check completion
        if parent.filled_quantity >= parent.total_quantity:
            parent.status = AlgoStatus.COMPLETED
            self.completed_algos[algo_id] = self.active_algos.pop(algo_id)

        return parent

    def step_market_tick(self, symbol: str, current_price: float) -> List[Dict[str, Any]]:
        """
        Processes market price update for active algos (specifically Sniper triggers).
        Returns list of executed slice fills.
        """
        fills = []
        for algo_id, parent in list(self.active_algos.items()):
            if parent.symbol != symbol or parent.status != AlgoStatus.ACTIVE:
                continue

            if parent.algo_type == AlgoType.SNIPER:
                trig_price = parent.params.get("trigger_price", parent.arrival_price)
                if evaluate_sniper_trigger(parent.side, current_price, trig_price):
                    for child in parent.child_orders:
                        if child.status == ChildOrderStatus.PENDING:
                            self.fill_child_order(algo_id, child.slice_id, current_price)
                            fills.append({
                                "algo_id": algo_id,
                                "slice_id": child.slice_id,
                                "fill_price": current_price,
                                "quantity": child.quantity
                            })
        return fills

    def get_hierarchy_tree(self, algo_id: str) -> Optional[Dict[str, Any]]:
        """T-253: Returns parent-child order status visualization hierarchy."""
        parent = self.active_algos.get(algo_id) or self.completed_algos.get(algo_id)
        if not parent:
            return None
        return parent.to_dict()

    def get_slippage_analytics(self) -> List[Dict[str, Any]]:
        """T-251: Execution slippage log analytics table for completed algos."""
        logs = []
        for algo_id, parent in self.completed_algos.items():
            logs.append({
                "algo_id": parent.algo_id,
                "algo_type": parent.algo_type.value if isinstance(parent.algo_type, Enum) else parent.algo_type,
                "symbol": parent.symbol,
                "side": parent.side,
                "total_quantity": parent.total_quantity,
                "filled_quantity": parent.filled_quantity,
                "arrival_price": parent.arrival_price,
                "avg_fill_price": parent.avg_fill_price,
                "implementation_shortfall_bps": parent.implementation_shortfall_bps,
                "status": parent.status.value if isinstance(parent.status, Enum) else parent.status,
                "child_count": len(parent.child_orders)
            })
        return logs


# Global singleton instance for easy web server API integration
global_algo_engine = AlgoExecutionEngine()
