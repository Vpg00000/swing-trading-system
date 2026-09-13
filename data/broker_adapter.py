"""
Multi-Broker Adapter & Latency Failover Circuit Breaker Module (TASK-041).

Provides:
1. Standardized `BrokerAdapter` base class for Dhan, Zerodha, and Upstox brokers.
2. Latency monitoring and circuit breaker mechanism (>500ms threshold).
3. `MultiBrokerRouter` for automatic, seamless failover to secondary broker adapters.
"""

import time
import logging
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)

# Default failover latency threshold in milliseconds
DEFAULT_MAX_LATENCY_MS = 500.0


class CircuitState(str, Enum):
    CLOSED = "CLOSED"       # Normal operation; primary broker active
    OPEN = "OPEN"           # Circuit tripped; primary broken/slow, failover active
    HALF_OPEN = "HALF_OPEN" # Recovery testing state


class BrokerAdapter(ABC):
    """Abstract base interface for all broker integration adapters."""

    def __init__(self, name: str, default_latency_ms: float = 120.0):
        self.name = name.lower()
        self._latency_ms = float(default_latency_ms)
        self._is_active = True
        self._error_count = 0
        self._last_ping_time = datetime.now(timezone.utc).isoformat()

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    @latency_ms.setter
    def latency_ms(self, value: float):
        self._latency_ms = float(value)

    def is_healthy(self, max_latency_ms: float = DEFAULT_MAX_LATENCY_MS) -> bool:
        return self._is_active and self._latency_ms <= max_latency_ms and self._error_count < 3

    def set_latency(self, latency_ms: float):
        self._latency_ms = float(latency_ms)

    def set_active(self, active: bool):
        self._is_active = active

    def record_error(self):
        self._error_count += 1

    def reset_errors(self):
        self._error_count = 0

    def ping(self) -> float:
        """Simulate/measure latency check."""
        self._last_ping_time = datetime.now(timezone.utc).isoformat()
        return self._latency_ms

    @abstractmethod
    def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Place an order through the broker API."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieve current open positions."""
        pass

    @abstractmethod
    def get_orders(self) -> List[Dict[str, Any]]:
        """Retrieve order history/book."""
        pass


class DhanBrokerAdapter(BrokerAdapter):
    """Dhan Broker Integration Adapter."""

    def __init__(self, default_latency_ms: float = 110.0):
        super().__init__(name="dhan", default_latency_ms=default_latency_ms)
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: List[Dict[str, Any]] = []

    def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()
        if self._latency_ms > DEFAULT_MAX_LATENCY_MS or not self._is_active:
            self.record_error()
            raise TimeoutError(f"Dhan broker latency ({self._latency_ms:.1f}ms) exceeds {DEFAULT_MAX_LATENCY_MS}ms threshold or is offline")

        order_id = order_payload.get("order_id") or f"DHAN-{int(time.time()*1000)}"
        symbol = order_payload.get("tradingSymbol") or order_payload.get("symbol", "UNKNOWN")
        qty = order_payload.get("quantity", 1)
        price = order_payload.get("price", 0.0)

        record = {
            "order_id": order_id,
            "broker": "dhan",
            "symbol": symbol,
            "quantity": qty,
            "price": price,
            "status": "FILLED",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": self._latency_ms
        }
        self._orders[order_id] = record
        return record

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            return {"status": "SUCCESS", "order_id": order_id, "broker": "dhan"}
        return {"status": "SUCCESS", "order_id": order_id, "broker": "dhan", "note": "Order not found or already closed"}

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions)

    def set_positions(self, positions: List[Dict[str, Any]]):
        self._positions = positions

    def get_orders(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())


class ZerodhaBrokerAdapter(BrokerAdapter):
    """Zerodha (Kite Connect) Broker Integration Adapter."""

    def __init__(self, default_latency_ms: float = 140.0):
        super().__init__(name="zerodha", default_latency_ms=default_latency_ms)
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: List[Dict[str, Any]] = []

    def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._latency_ms > DEFAULT_MAX_LATENCY_MS or not self._is_active:
            self.record_error()
            raise TimeoutError(f"Zerodha broker latency ({self._latency_ms:.1f}ms) exceeds threshold or is offline")

        order_id = order_payload.get("order_id") or f"ZERODHA-{int(time.time()*1000)}"
        symbol = order_payload.get("tradingSymbol") or order_payload.get("symbol", "UNKNOWN")
        qty = order_payload.get("quantity", 1)
        price = order_payload.get("price", 0.0)

        record = {
            "order_id": order_id,
            "broker": "zerodha",
            "symbol": symbol,
            "quantity": qty,
            "price": price,
            "status": "FILLED",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": self._latency_ms
        }
        self._orders[order_id] = record
        return record

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            return {"status": "SUCCESS", "order_id": order_id, "broker": "zerodha"}
        return {"status": "SUCCESS", "order_id": order_id, "broker": "zerodha"}

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions)

    def set_positions(self, positions: List[Dict[str, Any]]):
        self._positions = positions

    def get_orders(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())


class UpstoxBrokerAdapter(BrokerAdapter):
    """Upstox Broker Integration Adapter."""

    def __init__(self, default_latency_ms: float = 160.0):
        super().__init__(name="upstox", default_latency_ms=default_latency_ms)
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: List[Dict[str, Any]] = []

    def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._latency_ms > DEFAULT_MAX_LATENCY_MS or not self._is_active:
            self.record_error()
            raise TimeoutError(f"Upstox broker latency ({self._latency_ms:.1f}ms) exceeds threshold or is offline")

        order_id = order_payload.get("order_id") or f"UPSTOX-{int(time.time()*1000)}"
        symbol = order_payload.get("tradingSymbol") or order_payload.get("symbol", "UNKNOWN")
        qty = order_payload.get("quantity", 1)
        price = order_payload.get("price", 0.0)

        record = {
            "order_id": order_id,
            "broker": "upstox",
            "symbol": symbol,
            "quantity": qty,
            "price": price,
            "status": "FILLED",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": self._latency_ms
        }
        self._orders[order_id] = record
        return record

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            return {"status": "SUCCESS", "order_id": order_id, "broker": "upstox"}
        return {"status": "SUCCESS", "order_id": order_id, "broker": "upstox"}

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions)

    def set_positions(self, positions: List[Dict[str, Any]]):
        self._positions = positions

    def get_orders(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())


class MultiBrokerRouter:
    """
    Unified Multi-Broker Manager & Failover Circuit Breaker.
    Monitors broker latency and automatically switches from primary (e.g. Dhan)
    to secondary (Zerodha / Upstox) when primary latency exceeds 500ms or fails.
    """

    def __init__(self, primary_broker: str = "dhan", max_latency_threshold_ms: float = DEFAULT_MAX_LATENCY_MS):
        self.max_latency_threshold_ms = float(max_latency_threshold_ms)
        self._adapters: Dict[str, BrokerAdapter] = {}
        self._fallback_order: List[str] = ["dhan", "zerodha", "upstox"]
        self.primary_broker_name = primary_broker.lower()
        self.circuit_state = CircuitState.CLOSED
        self._failover_log: List[Dict[str, Any]] = []

        # Register standard default adapters
        self.register_adapter(DhanBrokerAdapter())
        self.register_adapter(ZerodhaBrokerAdapter())
        self.register_adapter(UpstoxBrokerAdapter())

    def register_adapter(self, adapter: BrokerAdapter):
        self._adapters[adapter.name.lower()] = adapter
        if adapter.name.lower() not in self._fallback_order:
            self._fallback_order.append(adapter.name.lower())

    def get_adapter(self, name: str) -> Optional[BrokerAdapter]:
        return self._adapters.get(name.lower())

    def update_broker_latency(self, name: str, latency_ms: float):
        adapter = self.get_adapter(name)
        if adapter:
            adapter.set_latency(latency_ms)

    def get_active_broker(self) -> BrokerAdapter:
        """
        Determines the active broker adapter based on latency and circuit breaker status.
        If primary broker latency > max_latency_threshold_ms (500ms) or is offline,
        trips circuit breaker and selects the first healthy fallback broker.
        """
        primary = self._adapters.get(self.primary_broker_name)

        if primary and primary.is_healthy(self.max_latency_threshold_ms):
            if self.circuit_state != CircuitState.CLOSED:
                log.info(f"[MULTI_BROKER] Primary broker '{self.primary_broker_name}' latency restored ({primary.latency_ms:.1f}ms). Closing circuit.")
                self.circuit_state = CircuitState.CLOSED
            return primary

        # Primary is degraded or broken -> Trip circuit breaker
        if self.circuit_state == CircuitState.CLOSED:
            self.circuit_state = CircuitState.OPEN
            reason = f"Primary broker '{self.primary_broker_name}' latency is {primary.latency_ms:.1f}ms (> {self.max_latency_threshold_ms}ms) or offline" if primary else "Primary adapter not registered"
            log.warning(f"[CIRCUIT_BREAKER] Circuit TRIPPED OPEN! {reason}")

        # Find first healthy fallback adapter
        for name in self._fallback_order:
            if name == self.primary_broker_name:
                continue
            adapter = self._adapters.get(name)
            if adapter and adapter.is_healthy(self.max_latency_threshold_ms):
                failover_record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": "FAILOVER_ACTIVATED",
                    "primary_broker": self.primary_broker_name,
                    "primary_latency_ms": primary.latency_ms if primary else None,
                    "active_broker": adapter.name,
                    "active_latency_ms": adapter.latency_ms,
                    "circuit_state": self.circuit_state.value,
                    "reason": f"Latency > {self.max_latency_threshold_ms}ms failover trigger"
                }
                # Log failover event if not already logged for this active broker state
                if not self._failover_log or self._failover_log[-1].get("active_broker") != adapter.name:
                    self._failover_log.append(failover_record)
                    log.warning(f"[MULTI_BROKER] Failover to secondary broker '{adapter.name}' (Latency: {adapter.latency_ms:.1f}ms)")
                return adapter

        # If no brokers are healthy, fall back to primary adapter (or raise error)
        log.error("[MULTI_BROKER] All registered broker adapters are degraded/unhealthy!")
        if primary:
            return primary
        raise RuntimeError("No broker adapters available!")

    def place_order(self, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Routes order placement to the active healthy broker adapter."""
        broker = self.get_active_broker()
        try:
            res = broker.place_order(order_payload)
            res["circuit_state"] = self.circuit_state.value
            return res
        except Exception as exc:
            log.error(f"[MULTI_BROKER] Error placing order on '{broker.name}': {exc}. Attempting secondary failover...")
            broker.record_error()
            self.circuit_state = CircuitState.OPEN
            # Try next active broker
            fallback_broker = self.get_active_broker()
            if fallback_broker != broker:
                res = fallback_broker.place_order(order_payload)
                res["circuit_state"] = self.circuit_state.value
                res["failover_recovered"] = True
                return res
            raise exc

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        broker = self.get_active_broker()
        return broker.cancel_order(order_id)

    def get_failover_log(self) -> List[Dict[str, Any]]:
        return list(self._failover_log)

    def get_status(self) -> Dict[str, Any]:
        primary = self._adapters.get(self.primary_broker_name)
        active = self.get_active_broker()
        return {
            "circuit_state": self.circuit_state.value,
            "primary_broker": self.primary_broker_name,
            "primary_healthy": primary.is_healthy(self.max_latency_threshold_ms) if primary else False,
            "primary_latency_ms": primary.latency_ms if primary else None,
            "active_broker": active.name,
            "active_latency_ms": active.latency_ms,
            "max_latency_threshold_ms": self.max_latency_threshold_ms,
            "adapters": {
                name: {
                    "latency_ms": adapter.latency_ms,
                    "healthy": adapter.is_healthy(self.max_latency_threshold_ms),
                    "error_count": adapter._error_count
                }
                for name, adapter in self._adapters.items()
            },
            "failover_count": len(self._failover_log)
        }

    def reset_circuit(self):
        """Reset circuit breaker state and errors for testing/recovery."""
        self.circuit_state = CircuitState.CLOSED
        self._failover_log.clear()
        for adapter in self._adapters.values():
            adapter.reset_errors()


# Global Singleton Instance
_BROKER_ROUTER = MultiBrokerRouter()


def get_multi_broker_router() -> MultiBrokerRouter:
    return _BROKER_ROUTER


def reset_broker_router():
    global _BROKER_ROUTER
    _BROKER_ROUTER = MultiBrokerRouter()
