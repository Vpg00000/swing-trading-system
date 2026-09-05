"""
Dhan Order Preparation, Routing & Human Approval Gate Module.

Implements:
1. Strict Human Approval Gate (TASK-022): Enforces explicit human approval (YES/NO/APPROVE/REJECT)
   before any order preparation or routing can occur. Blocks all unauthorized order state transitions.
2. Dhan Order Routing & Execution Path (TASK-023): Performs pre-trade margin/cash/risk checks,
   generates Dhan bracket order payloads, routes orders to paper mode or Dhan API, and records execution.
3. Resilience Integration (TASK-038): Interlocks with Safe Mode Engine to block order preparation
   and routing whenever trading is blocked or critical data is stale/errored.

Fixes Problems: TASK-022, TASK-023, TASK-038.
"""

import os
import uuid
import logging
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from engine.resiliency import is_trading_allowed, get_system_state

log = logging.getLogger(__name__)


class OrderState(str, Enum):
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PREPARED = "PREPARED"
    ROUTED = "ROUTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalRequiredError(Exception):
    """Raised when order preparation or routing is attempted without explicit human approval."""
    pass


class UnauthorizedOrderStateTransitionError(Exception):
    """Raised when an illegal or unauthorized order state transition is attempted."""
    pass


class PreTradeCheckFailedError(Exception):
    """Raised when pre-trade margin, cash, or risk checks fail."""
    pass


class TradingBlockedError(Exception):
    """Raised when order operations are attempted while Resilience Engine is in SAFE_MODE or TRADING_BLOCKED."""
    pass


class OrderRequest:
    """Represents a trading order throughout its lifecycle."""

    def __init__(
        self,
        symbol: str,
        security_id: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_loss_price: float,
        transaction_type: str = "BUY",
        order_type: str = "LIMIT",
        order_id: Optional[str] = None
    ):
        self.order_id = order_id or f"ORD-{uuid.uuid4().hex[:8].upper()}"
        self.symbol = symbol
        self.security_id = security_id
        self.quantity = int(quantity)
        self.entry_price = float(entry_price)
        self.target_price = float(target_price)
        self.stop_loss_price = float(stop_loss_price)
        self.transaction_type = transaction_type.upper()
        self.order_type = order_type.upper()

        self.status = OrderState.PROPOSED
        self.approval_status = ApprovalStatus.PENDING
        self.approved_by: Optional[str] = None
        self.approved_at: Optional[str] = None
        self.rejection_reason: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.payload: Optional[Dict[str, Any]] = None
        self.execution_details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "security_id": self.security_id,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_loss_price": self.stop_loss_price,
            "transaction_type": self.transaction_type,
            "order_type": self.order_type,
            "status": self.status.value if isinstance(self.status, OrderState) else self.status,
            "approval_status": self.approval_status.value if isinstance(self.approval_status, ApprovalStatus) else self.approval_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "payload": self.payload,
            "execution_details": self.execution_details
        }


# In-memory repositories for orders, approvals, and executed trade logs
_ORDER_BOOK: Dict[str, OrderRequest] = {}
_APPROVAL_LOG: List[Dict[str, Any]] = []
_EXECUTED_TRADES_LOG: List[Dict[str, Any]] = []


def reset_order_book():
    """Resets the in-memory order book, approval log, and executed trades log. Useful for test isolation."""
    global _ORDER_BOOK, _APPROVAL_LOG, _EXECUTED_TRADES_LOG
    _ORDER_BOOK.clear()
    _APPROVAL_LOG.clear()
    _EXECUTED_TRADES_LOG.clear()


def create_order_proposal(
    symbol: str,
    security_id: str,
    quantity: int,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    transaction_type: str = "BUY",
    order_type: str = "LIMIT"
) -> OrderRequest:
    """
    Creates a new order proposal requiring explicit human approval.
    Initial state: PROPOSED, approval_status: PENDING.
    """
    order = OrderRequest(
        symbol=symbol,
        security_id=security_id,
        quantity=quantity,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        transaction_type=transaction_type,
        order_type=order_type
    )
    _ORDER_BOOK[order.order_id] = order
    log.info(f"[ORDER_GATE] Order proposal created: {order.order_id} for {order.symbol}")
    return order


def get_order(order_id: str) -> Optional[OrderRequest]:
    return _ORDER_BOOK.get(order_id)


def get_all_orders() -> List[Dict[str, Any]]:
    return [order.to_dict() for order in _ORDER_BOOK.values()]


def get_approval_log() -> List[Dict[str, Any]]:
    return list(_APPROVAL_LOG)


def get_executed_trades_log() -> List[Dict[str, Any]]:
    return list(_EXECUTED_TRADES_LOG)


def approve_order(order_id: str, operator_id: str = "human_operator", note: str = "") -> OrderRequest:
    """
    Explicit Human Approval Action.
    Transitions order from PROPOSED/PENDING_APPROVAL to APPROVED.
    """
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order '{order_id}' not found.")

    if order.status in (OrderState.REJECTED, OrderState.EXECUTED, OrderState.CANCELLED, OrderState.BLOCKED):
        raise UnauthorizedOrderStateTransitionError(
            f"Cannot approve order {order_id} in terminal/blocked state '{order.status.value}'"
        )

    if order.status not in (OrderState.PROPOSED, OrderState.PENDING_APPROVAL):
        if order.status == OrderState.APPROVED:
            return order  # Already approved
        raise UnauthorizedOrderStateTransitionError(
            f"Invalid transition to APPROVED from state '{order.status.value}'"
        )

    order.status = OrderState.APPROVED
    order.approval_status = ApprovalStatus.APPROVED
    order.approved_by = operator_id
    order.approved_at = datetime.now(timezone.utc).isoformat()

    log_entry = {
        "event_id": f"APP-{uuid.uuid4().hex[:6].upper()}",
        "timestamp": order.approved_at,
        "order_id": order.order_id,
        "symbol": order.symbol,
        "action": "APPROVED",
        "operator_id": operator_id,
        "note": note
    }
    _APPROVAL_LOG.append(log_entry)
    log.info(f"[ORDER_GATE] Order {order.order_id} explicitly APPROVED by {operator_id}")
    return order


def reject_order(order_id: str, operator_id: str = "human_operator", reason: str = "User rejected order") -> OrderRequest:
    """
    Explicit Human Rejection Action.
    Transitions order to REJECTED. Prevents any future preparation or execution.
    """
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order '{order_id}' not found.")

    if order.status in (OrderState.EXECUTED, OrderState.ROUTED):
        raise UnauthorizedOrderStateTransitionError(
            f"Cannot reject order {order_id} in executed/routed state '{order.status.value}'"
        )

    order.status = OrderState.REJECTED
    order.approval_status = ApprovalStatus.REJECTED
    order.rejection_reason = reason

    log_entry = {
        "event_id": f"APP-{uuid.uuid4().hex[:6].upper()}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "order_id": order.order_id,
        "symbol": order.symbol,
        "action": "REJECTED",
        "operator_id": operator_id,
        "reason": reason
    }
    _APPROVAL_LOG.append(log_entry)
    log.info(f"[ORDER_GATE] Order {order.order_id} explicitly REJECTED by {operator_id}")
    return order


def verify_margin_requirement(available_cash: float, order_value: float, margin_pct: float = 100.0) -> bool:
    """
    Verifies if available cash covers the required margin.
    """
    required_cash = order_value * (margin_pct / 100.0)
    return available_cash >= required_cash


def verify_pre_trade_checks(order: OrderRequest, available_cash: float = 1000000.0) -> bool:
    """
    Executes pre-trade risk, cash, margin, price level, and safe mode checks.
    """
    # 1. Resilience Safe Mode check
    if not is_trading_allowed():
        order.status = OrderState.BLOCKED
        raise TradingBlockedError(
            f"Trading is currently blocked by Resilience Safe Mode Engine! State: {get_system_state()}"
        )

    # 2. Strict Human Approval Gate check
    if order.approval_status != ApprovalStatus.APPROVED or order.status not in (OrderState.APPROVED, OrderState.PREPARED):
        order.status = OrderState.BLOCKED
        raise ApprovalRequiredError(
            f"Unauthorized state transition attempt! Order {order.order_id} lacks explicit human approval. "
            f"(Current state: {order.status.value}, Approval Status: {order.approval_status.value})"
        )

    # 3. Parameter and price level sanity checks
    if order.quantity <= 0 or order.entry_price <= 0:
        order.status = OrderState.BLOCKED
        raise PreTradeCheckFailedError("Quantity and entry price must be positive numbers.")

    if order.transaction_type == "BUY":
        if order.stop_loss_price >= order.entry_price:
            order.status = OrderState.BLOCKED
            raise PreTradeCheckFailedError(
                f"Stop loss price ({order.stop_loss_price}) must be strictly lower than entry price ({order.entry_price}) for BUY order."
            )
        if order.target_price <= order.entry_price:
            order.status = OrderState.BLOCKED
            raise PreTradeCheckFailedError(
                f"Target price ({order.target_price}) must be strictly higher than entry price ({order.entry_price}) for BUY order."
            )

    # 4. Cash & Margin check
    order_value = order.quantity * order.entry_price
    margin_pct = float(os.getenv('DANH_MARGIN_PCT', '100.0'))
    if not verify_margin_requirement(available_cash, order_value, margin_pct):
        order.status = OrderState.BLOCKED
        required_margin = order_value * (margin_pct / 100.0)
        raise PreTradeCheckFailedError(
            f"Insufficient available funds ({available_cash:.2f}) for required margin ({required_margin:.2f})."
        )

    return True


def generate_dhan_bracket_order(
    symbol: str,
    security_id: str,
    quantity: int,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    order_type: str = "LIMIT"
) -> Dict[str, Any]:
    """
    Generates Dhan bracket order payload structure.
    """
    margin_pct = float(os.getenv('DANH_MARGIN_PCT', '100.0'))
    order_value = quantity * entry_price
    # Verify margin requirements with a default cash pool if calling directly
    available_cash = float(os.getenv('AVAILABLE_CASH', '1000000.0'))
    if not verify_margin_requirement(available_cash, order_value, margin_pct):
        raise PreTradeCheckFailedError(f"Insufficient cash for margin requirement: {available_cash} < {order_value * (margin_pct / 100.0)}")

    return {
        "dhanClientId": os.getenv("DHAN_CLIENT_ID", "DEMO_CLIENT_ID"),
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "BO",
        "orderType": order_type.upper(),
        "validity": "DAY",
        "tradingSymbol": symbol,
        "securityId": str(security_id),
        "quantity": int(quantity),
        "price": float(entry_price),
        "targetPrice": float(target_price),
        "stopLossPrice": float(stop_loss_price),
        "marginPct": margin_pct
    }


def prepare_order(order_id: str, available_cash: float = 1000000.0) -> Dict[str, Any]:
    """
    Prepares order payload after running pre-trade risk and human approval gate checks.
    Transitions order from APPROVED -> PREPARED.
    """
    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order '{order_id}' not found.")

    if order.status == OrderState.PROPOSED or order.status == OrderState.PENDING_APPROVAL:
        order.status = OrderState.BLOCKED
        raise ApprovalRequiredError(
            f"Order {order_id} cannot be prepared without explicit human approval!"
        )

    if order.status == OrderState.REJECTED:
        raise UnauthorizedOrderStateTransitionError(
            f"Cannot prepare order {order_id} because it was explicitly REJECTED by human operator."
        )

    if order.status in (OrderState.BLOCKED, OrderState.CANCELLED):
        raise UnauthorizedOrderStateTransitionError(
            f"Cannot prepare order {order_id} in state '{order.status.value}'"
        )

    # Run pre-trade checks (will throw exception and update status to BLOCKED if failed)
    verify_pre_trade_checks(order, available_cash=available_cash)

    # Generate Dhan Bracket Order payload
    payload = generate_dhan_bracket_order(
        symbol=order.symbol,
        security_id=order.security_id,
        quantity=order.quantity,
        entry_price=order.entry_price,
        target_price=order.target_price,
        stop_loss_price=order.stop_loss_price,
        order_type=order.order_type
    )

    order.status = OrderState.PREPARED
    order.payload = payload

    log.info(f"[DHAN_ROUTING] Order {order.order_id} PREPARED with payload for {order.symbol}")
    return {
        "status": "PREPARED",
        "order_id": order.order_id,
        "payload": payload
    }


def route_order_to_dhan(
    order_id: str,
    paper_mode: bool = True,
    available_cash: float = 1000000.0,
    dhan_client: Any = None
) -> Dict[str, Any]:
    """
    Routes approved and prepared orders to Dhan API or Paper Exchange.
    Transitions order state: PREPARED -> ROUTED -> EXECUTED.
    """
    if not is_trading_allowed():
        order = get_order(order_id)
        if order:
            order.status = OrderState.BLOCKED
        raise TradingBlockedError(
            f"Trading is blocked by Resilience Engine ({get_system_state()}). Routing aborted."
        )

    order = get_order(order_id)
    if not order:
        raise ValueError(f"Order '{order_id}' not found.")

    # Check for terminal or blocked states first
    if order.status in (OrderState.REJECTED, OrderState.EXECUTED, OrderState.CANCELLED, OrderState.BLOCKED) or order.approval_status == ApprovalStatus.REJECTED:
        raise UnauthorizedOrderStateTransitionError(
            f"Cannot route order {order_id} in terminal/rejected state '{order.status.value}'"
        )

    # Strict Gate Verification: Must be human-approved
    if order.approval_status != ApprovalStatus.APPROVED or order.status in (OrderState.PROPOSED, OrderState.PENDING_APPROVAL):
        order.status = OrderState.BLOCKED
        raise ApprovalRequiredError(
            f"Routing blocked! Order {order.order_id} has not received explicit human approval."
        )

        raise UnauthorizedOrderStateTransitionError(
            f"Cannot route rejected order {order_id}."
        )

    if order.status == OrderState.EXECUTED:
        return {
            "status": "SUCCESS",
            "message": "Order already executed",
            "order_id": order.order_id,
            "execution_details": order.execution_details
        }

    # Ensure order is prepared
    if order.status != OrderState.PREPARED:
        prepare_order(order_id, available_cash=available_cash)

    # Route to execution layer (Paper Mode or Live Dhan Client)
    if paper_mode or dhan_client is None or not getattr(dhan_client, "is_active", lambda: False)():
        execution_id = f"EXEC-PAPER-{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.now(timezone.utc).isoformat()
        
        execution_details = {
            "execution_id": execution_id,
            "mode": "PAPER_SANDBOX",
            "status": "FILLED",
            "order_id": order.order_id,
            "symbol": order.symbol,
            "security_id": order.security_id,
            "transaction_type": order.transaction_type,
            "executed_quantity": order.quantity,
            "executed_price": order.entry_price,
            "stop_loss_price": order.stop_loss_price,
            "target_price": order.target_price,
            "executed_at": now_str,
            "slippage": 0.0,
            "brokerage_fees": 0.0
        }

        order.status = OrderState.EXECUTED
        order.execution_details = execution_details

        _EXECUTED_TRADES_LOG.append(execution_details)
        log.info(f"[DHAN_ROUTING] Order {order.order_id} EXECUTED in PAPER mode. Exec ID: {execution_id}")

        return {
            "status": "SUCCESS",
            "mode": "PAPER_SANDBOX",
            "order_id": order.order_id,
            "execution_id": execution_id,
            "order": order.to_dict(),
            "execution_details": execution_details
        }
    else:
        # Live Dhan Client Routing
        order.status = OrderState.ROUTED
        try:
            dhan_response = dhan_client.place_order(order.payload)
            execution_id = dhan_response.get("orderId", f"EXEC-DHAN-{uuid.uuid4().hex[:8].upper()}")
            now_str = datetime.now(timezone.utc).isoformat()

            execution_details = {
                "execution_id": execution_id,
                "mode": "DHAN_LIVE",
                "status": dhan_response.get("orderStatus", "FILLED"),
                "order_id": order.order_id,
                "symbol": order.symbol,
                "executed_quantity": order.quantity,
                "executed_price": order.entry_price,
                "executed_at": now_str,
                "dhan_response": dhan_response
            }
            order.status = OrderState.EXECUTED
            order.execution_details = execution_details
            _EXECUTED_TRADES_LOG.append(execution_details)

            return {
                "status": "SUCCESS",
                "mode": "DHAN_LIVE",
                "order_id": order.order_id,
                "execution_id": execution_id,
                "order": order.to_dict(),
                "execution_details": execution_details
            }
        except Exception as exc:
            order.status = OrderState.BLOCKED
            log.error(f"[DHAN_ROUTING] Failed live Dhan routing for order {order.order_id}: {exc}")
            raise RuntimeError(f"Dhan API routing failure: {exc}")
