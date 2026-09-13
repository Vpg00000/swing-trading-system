"""
Server-Side Good-Till-Triggered (GTT) & OCO Order Engine (TASK-043 / Phase 3 Task C).

Implements:
1. Server-side GTT monitoring for SINGLE and OCO (One-Cancels-the-Other) orders.
2. Market price tick processing and trigger evaluation (`evaluate_ticks`).
3. Automatic leg cancellation when OCO trigger fires (Stop Loss vs Target).
4. Full lifecycle management (PENDING, ACTIVE, TRIGGERED, EXECUTED, CANCELLED, EXPIRED).
5. Helper functions: get_gtt_orders, create_gtt_order, cancel_gtt_order, evaluate_ticks.
"""

import uuid
import time
import logging
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    prepare_order,
    route_order_to_dhan,
)

log = logging.getLogger(__name__)


class GTTType(str, Enum):
    SINGLE = "SINGLE"
    OCO = "OCO"  # One-Cancels-the-Other (Stop-Loss + Target)


class GTTStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class GTTCondition(str, Enum):
    LESS_THAN_EQUAL = "LESS_THAN_EQUAL"       # <= trigger price (e.g. Stop Loss for BUY position)
    GREATER_THAN_EQUAL = "GREATER_THAN_EQUAL" # >= trigger price (e.g. Target for BUY position)


class GTTLeg:
    """Represents an individual leg of a GTT or OCO order."""

    def __init__(
        self,
        trigger_price: float,
        order_price: float,
        quantity: int,
        transaction_type: str = "SELL",
        condition: Union[GTTCondition, str] = GTTCondition.LESS_THAN_EQUAL,
        leg_name: str = "PRIMARY",
        leg_id: Optional[str] = None
    ):
        self.leg_id = leg_id or f"LEG-{uuid.uuid4().hex[:6].upper()}"
        self.leg_name = leg_name.upper()
        self.trigger_price = float(trigger_price)
        self.order_price = float(order_price)
        self.quantity = int(quantity)
        self.transaction_type = transaction_type.upper()

        if isinstance(condition, str):
            cond_str = condition.upper()
            if cond_str in ("<=", "LESS_THAN_EQUAL", "SL"):
                self.condition = GTTCondition.LESS_THAN_EQUAL
            elif cond_str in (">=", "GREATER_THAN_EQUAL", "TARGET"):
                self.condition = GTTCondition.GREATER_THAN_EQUAL
            else:
                self.condition = GTTCondition(cond_str)
        else:
            self.condition = condition

        self.status = "PENDING"  # PENDING, TRIGGERED, CANCELLED
        self.triggered_at: Optional[str] = None
        self.triggered_price: Optional[float] = None

    def evaluate(self, current_price: float) -> bool:
        if self.status != "PENDING":
            return False

        if self.condition == GTTCondition.LESS_THAN_EQUAL:
            return current_price <= self.trigger_price
        elif self.condition == GTTCondition.GREATER_THAN_EQUAL:
            return current_price >= self.trigger_price
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "leg_name": self.leg_name,
            "trigger_price": self.trigger_price,
            "order_price": self.order_price,
            "quantity": self.quantity,
            "transaction_type": self.transaction_type,
            "condition": self.condition.value if isinstance(self.condition, GTTCondition) else self.condition,
            "status": self.status,
            "triggered_at": self.triggered_at,
            "triggered_price": self.triggered_price
        }


class GTTOrder:
    """Represents a server-side GTT / OCO order."""

    def __init__(
        self,
        symbol: str,
        gtt_type: Union[GTTType, str],
        legs: List[GTTLeg],
        security_id: str = "0",
        gtt_id: Optional[str] = None,
        order_type: str = "BUY",
        quantity: int = 1,
        trigger_price: Optional[float] = None,
        order_price: Optional[float] = None,
        stop_loss_trigger: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        target_trigger: Optional[float] = None,
        target_price: Optional[float] = None,
        status: Union[GTTStatus, str] = GTTStatus.ACTIVE,
    ):
        self.gtt_id = gtt_id or f"GTT-{uuid.uuid4().hex[:8].upper()}"
        self.symbol = symbol.upper()
        self.security_id = str(security_id)
        self.gtt_type = GTTType(gtt_type.upper()) if isinstance(gtt_type, str) else gtt_type
        self.legs = legs
        self.order_type = order_type.upper()
        self.quantity = quantity
        self.status = GTTStatus(status.upper()) if isinstance(status, str) else status
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.triggered_at: Optional[str] = None
        self.triggered_leg_id: Optional[str] = None
        self.execution_result: Optional[Dict[str, Any]] = None

        if self.gtt_type == GTTType.SINGLE and legs:
            self.trigger_price = trigger_price if trigger_price is not None else legs[0].trigger_price
            self.order_price = order_price if order_price is not None else legs[0].order_price
            self.stop_loss_trigger = None
            self.stop_loss_price = None
            self.target_trigger = None
            self.target_price = None
        else:
            sl_leg = next((l for l in legs if l.leg_name == "STOP_LOSS"), None)
            tgt_leg = next((l for l in legs if l.leg_name == "TARGET"), None)
            self.stop_loss_trigger = stop_loss_trigger if stop_loss_trigger is not None else (sl_leg.trigger_price if sl_leg else None)
            self.stop_loss_price = stop_loss_price if stop_loss_price is not None else (sl_leg.order_price if sl_leg else None)
            self.target_trigger = target_trigger if target_trigger is not None else (tgt_leg.trigger_price if tgt_leg else None)
            self.target_price = target_price if target_price is not None else (tgt_leg.order_price if tgt_leg else None)
            self.trigger_price = self.stop_loss_trigger or trigger_price
            self.order_price = self.stop_loss_price or order_price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gtt_id": self.gtt_id,
            "symbol": self.symbol,
            "security_id": self.security_id,
            "gtt_type": self.gtt_type.value if isinstance(self.gtt_type, GTTType) else self.gtt_type,
            "order_type": self.order_type,
            "transaction_type": self.order_type,
            "quantity": self.quantity,
            "trigger_price": self.trigger_price,
            "order_price": self.order_price,
            "stop_loss_trigger": self.stop_loss_trigger,
            "stop_loss_price": self.stop_loss_price,
            "target_trigger": self.target_trigger,
            "target_price": self.target_price,
            "status": self.status.value if isinstance(self.status, GTTStatus) else self.status,
            "created_at": self.created_at,
            "triggered_at": self.triggered_at,
            "triggered_leg_id": self.triggered_leg_id,
            "legs": [leg.to_dict() for leg in self.legs],
            "execution_result": self.execution_result
        }


class GTTOrderEngine:
    """
    Server-side Good-Till-Triggered and OCO order manager.
    """

    def __init__(self):
        self._gtt_orders: Dict[str, GTTOrder] = {}
        self._trigger_log: List[Dict[str, Any]] = []

    def create_single_gtt(
        self,
        symbol: str,
        trigger_price: float,
        order_price: float,
        quantity: int,
        transaction_type: str = "BUY",
        condition: str = "LESS_THAN_EQUAL",
        security_id: str = "0",
        status: str = "ACTIVE"
    ) -> GTTOrder:
        leg = GTTLeg(
            trigger_price=trigger_price,
            order_price=order_price,
            quantity=quantity,
            transaction_type=transaction_type,
            condition=condition,
            leg_name="SINGLE"
        )
        gtt = GTTOrder(
            symbol=symbol,
            gtt_type=GTTType.SINGLE,
            legs=[leg],
            security_id=security_id,
            order_type=transaction_type,
            quantity=quantity,
            trigger_price=trigger_price,
            order_price=order_price,
            status=status
        )
        self._gtt_orders[gtt.gtt_id] = gtt
        log.info(f"[GTT_ENGINE] Single GTT order created: {gtt.gtt_id} for {symbol} at trigger {trigger_price}")
        return gtt

    def create_oco_gtt(
        self,
        symbol: str,
        stop_loss_trigger: float,
        stop_loss_price: float,
        target_trigger: float,
        target_price: float,
        quantity: int,
        transaction_type: str = "SELL",
        security_id: str = "0",
        status: str = "ACTIVE"
    ) -> GTTOrder:
        """
        Creates an OCO (One-Cancels-the-Other) GTT order with stop-loss and target legs.
        """
        sl_leg = GTTLeg(
            trigger_price=stop_loss_trigger,
            order_price=stop_loss_price,
            quantity=quantity,
            transaction_type=transaction_type,
            condition=GTTCondition.LESS_THAN_EQUAL,
            leg_name="STOP_LOSS"
        )
        target_leg = GTTLeg(
            trigger_price=target_trigger,
            order_price=target_price,
            quantity=quantity,
            transaction_type=transaction_type,
            condition=GTTCondition.GREATER_THAN_EQUAL,
            leg_name="TARGET"
        )
        gtt = GTTOrder(
            symbol=symbol,
            gtt_type=GTTType.OCO,
            legs=[sl_leg, target_leg],
            security_id=security_id,
            order_type=transaction_type,
            quantity=quantity,
            stop_loss_trigger=stop_loss_trigger,
            stop_loss_price=stop_loss_price,
            target_trigger=target_trigger,
            target_price=target_price,
            status=status
        )
        self._gtt_orders[gtt.gtt_id] = gtt
        log.info(f"[GTT_ENGINE] OCO GTT order created: {gtt.gtt_id} for {symbol} (SL: {stop_loss_trigger}, TGT: {target_trigger})")
        return gtt

    def create_gtt_order(self, params: Dict[str, Any]) -> GTTOrder:
        """
        Generic creation method accepting a params dict for Single or OCO GTT orders.
        """
        gtt_type_str = str(params.get("gtt_type", "")).upper()
        symbol = str(params.get("symbol", ""))
        order_type = str(params.get("order_type") or params.get("transaction_type") or "BUY").upper()
        quantity = int(params.get("quantity", 1))
        security_id = str(params.get("security_id", "0"))
        status = str(params.get("status", "ACTIVE")).upper()

        if gtt_type_str == "OCO" or ("stop_loss_trigger" in params and "target_trigger" in params):
            sl_trigger = float(params["stop_loss_trigger"])
            sl_price = float(params.get("stop_loss_price", sl_trigger))
            tgt_trigger = float(params["target_trigger"])
            tgt_price = float(params.get("target_price", tgt_trigger))

            return self.create_oco_gtt(
                symbol=symbol,
                stop_loss_trigger=sl_trigger,
                stop_loss_price=sl_price,
                target_trigger=tgt_trigger,
                target_price=tgt_price,
                quantity=quantity,
                transaction_type=order_type,
                security_id=security_id,
                status=status
            )
        else:
            trig_price = float(params.get("trigger_price", 0.0))
            ord_price = float(params.get("order_price", trig_price))
            condition = str(params.get("condition", "LESS_THAN_EQUAL"))

            return self.create_single_gtt(
                symbol=symbol,
                trigger_price=trig_price,
                order_price=ord_price,
                quantity=quantity,
                transaction_type=order_type,
                condition=condition,
                security_id=security_id,
                status=status
            )

    def cancel_gtt_order(self, gtt_id: str) -> Optional[GTTOrder]:
        gtt = self._gtt_orders.get(gtt_id)
        if not gtt:
            return None

        if gtt.status in (GTTStatus.ACTIVE, GTTStatus.PENDING):
            gtt.status = GTTStatus.CANCELLED
            for leg in gtt.legs:
                if leg.status == "PENDING":
                    leg.status = "CANCELLED"
            log.info(f"[GTT_ENGINE] GTT order {gtt_id} CANCELLED")
        return gtt

    def get_gtt_order(self, gtt_id: str) -> Optional[GTTOrder]:
        return self._gtt_orders.get(gtt_id)

    def get_all_gtt_orders(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        orders = list(self._gtt_orders.values())
        if status_filter:
            sf_upper = status_filter.upper()
            orders = [o for o in orders if o.status.value.upper() == sf_upper or str(o.status).upper() == sf_upper]
        return [o.to_dict() for o in orders]

    def get_trigger_log(self) -> List[Dict[str, Any]]:
        return list(self._trigger_log)

    def process_market_tick(
        self,
        symbol: str,
        current_price: float,
        auto_execute: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Evaluates market data tick against all ACTIVE / PENDING GTT orders for the given symbol.
        Fires triggers within <100ms latency.
        In OCO mode: when one leg triggers, the opposite leg is CANCELLED immediately.
        """
        start_time = time.perf_counter()
        symbol_upper = symbol.upper()
        triggered_events = []

        for gtt_id, gtt in list(self._gtt_orders.items()):
            if gtt.status not in (GTTStatus.ACTIVE, GTTStatus.PENDING) or gtt.symbol != symbol_upper:
                continue

            for leg in gtt.legs:
                if leg.status == "PENDING" and leg.evaluate(current_price):
                    eval_time_ms = (time.perf_counter() - start_time) * 1000.0

                    # 1. Trigger Leg
                    now_str = datetime.now(timezone.utc).isoformat()
                    leg.status = "TRIGGERED"
                    leg.triggered_at = now_str
                    leg.triggered_price = current_price

                    gtt.status = GTTStatus.TRIGGERED
                    gtt.triggered_at = now_str
                    gtt.triggered_leg_id = leg.leg_id

                    # 2. OCO Cancellation Logic: Cancel all other pending legs
                    cancelled_legs = []
                    if gtt.gtt_type == GTTType.OCO:
                        for other_leg in gtt.legs:
                            if other_leg.leg_id != leg.leg_id and other_leg.status == "PENDING":
                                other_leg.status = "CANCELLED"
                                cancelled_legs.append(other_leg.leg_id)

                    # 3. Optional Auto Execution (paper/sandbox routing)
                    exec_result = None
                    if auto_execute:
                        try:
                            sl_price = leg.order_price * 0.95 if leg.transaction_type == "BUY" else leg.order_price * 1.05
                            tgt_price = leg.order_price * 1.05 if leg.transaction_type == "BUY" else leg.order_price * 0.95

                            order_prop = create_order_proposal(
                                symbol=gtt.symbol,
                                security_id=gtt.security_id,
                                quantity=leg.quantity,
                                entry_price=leg.order_price,
                                target_price=tgt_price,
                                stop_loss_price=sl_price,
                                transaction_type=leg.transaction_type
                            )
                            approve_order(order_prop.order_id, operator_id="GTT_AUTO_TRIGGER")
                            prepare_order(order_prop.order_id)
                            exec_result = route_order_to_dhan(order_prop.order_id, paper_mode=True)
                            gtt.status = GTTStatus.EXECUTED
                            gtt.execution_result = exec_result
                        except Exception as exc:
                            log.error(f"[GTT_ENGINE] Auto-execution error for GTT {gtt_id}: {exc}")
                            gtt.execution_result = {"status": "FAILED", "error": str(exc)}

                    event = {
                        "event_id": f"TRIG-{uuid.uuid4().hex[:6].upper()}",
                        "timestamp": now_str,
                        "gtt_id": gtt.gtt_id,
                        "symbol": gtt.symbol,
                        "gtt_type": gtt.gtt_type.value,
                        "triggered_leg": leg.leg_name,
                        "leg_id": leg.leg_id,
                        "trigger_price": leg.trigger_price,
                        "order_price": leg.order_price,
                        "market_price": current_price,
                        "condition": leg.condition.value,
                        "quantity": leg.quantity,
                        "order_type": leg.transaction_type,
                        "eval_latency_ms": round(eval_time_ms, 3),
                        "cancelled_other_legs": cancelled_legs,
                        "execution": exec_result
                    }

                    self._trigger_log.append(event)
                    triggered_events.append(event)
                    log.info(f"[GTT_ENGINE] GTT {gtt.gtt_id} TRIGGERED leg '{leg.leg_name}' at tick {current_price} (latency: {eval_time_ms:.2f}ms)")
                    break

        return triggered_events

    def evaluate_ticks(
        self,
        ticks_dict: Dict[str, Any],
        auto_execute: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Evaluates tick prices against all pending GTT triggers and fires execution signals.
        """
        all_events = []
        for symbol, tick_val in ticks_dict.items():
            if isinstance(tick_val, (int, float)):
                price = float(tick_val)
            elif isinstance(tick_val, dict):
                price = float(
                    tick_val.get("last_price") or
                    tick_val.get("price") or
                    tick_val.get("close", 0.0)
                )
            else:
                continue

            events = self.process_market_tick(symbol, price, auto_execute=auto_execute)
            all_events.extend(events)
        return all_events

    def reset(self):
        """Reset GTT engine state."""
        self._gtt_orders.clear()
        self._trigger_log.clear()


# Alias GTTEngine to GTTOrderEngine for backward compatibility
GTTEngine = GTTOrderEngine

# Global Singleton Instance
_GTT_ENGINE = GTTOrderEngine()


def get_gtt_engine() -> GTTOrderEngine:
    return _GTT_ENGINE


def reset_gtt_engine():
    global _GTT_ENGINE
    _GTT_ENGINE = GTTOrderEngine()


# Helper functions
def get_gtt_orders(status: Optional[str] = None) -> List[Dict[str, Any]]:
    return get_gtt_engine().get_all_gtt_orders(status_filter=status)


def create_gtt_order(params: Dict[str, Any]) -> Dict[str, Any]:
    order = get_gtt_engine().create_gtt_order(params)
    return order.to_dict()


def cancel_gtt_order(gtt_id: str) -> Optional[Dict[str, Any]]:
    order = get_gtt_engine().cancel_gtt_order(gtt_id)
    return order.to_dict() if order else None


def evaluate_ticks(ticks_dict: Dict[str, Any], auto_execute: bool = True) -> List[Dict[str, Any]]:
    return get_gtt_engine().evaluate_ticks(ticks_dict, auto_execute=auto_execute)
