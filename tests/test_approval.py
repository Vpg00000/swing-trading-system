"""
Unit & Security Integration Tests for TASK-022: Human Approval Gate.

Tests:
1. Initial order state is PROPOSED with PENDING approval status.
2. Explicit human approval transitions order state to APPROVED.
3. Explicit human rejection transitions order state to REJECTED.
4. Unauthorized attempt to prepare or route an unapproved order is strictly blocked (raises ApprovalRequiredError).
5. Unauthorized transition attempt on REJECTED orders is strictly blocked (raises UnauthorizedOrderStateTransitionError).
6. Comprehensive approval log audit trail recording.
"""

import unittest
from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    reject_order,
    prepare_order,
    route_order_to_dhan,
    get_approval_log,
    reset_order_book,
    OrderState,
    ApprovalStatus,
    ApprovalRequiredError,
    UnauthorizedOrderStateTransitionError
)
from engine.resiliency import reset_system_state


class TestHumanApprovalGate(unittest.TestCase):

    def setUp(self):
        reset_order_book()
        reset_system_state("Reset for test_approval")

    def test_order_proposal_initial_state(self):
        order = create_order_proposal(
            symbol="RELIANCE",
            security_id="1333",
            quantity=10,
            entry_price=2500.0,
            target_price=2700.0,
            stop_loss_price=2400.0
        )
        self.assertEqual(order.status, OrderState.PROPOSED)
        self.assertEqual(order.approval_status, ApprovalStatus.PENDING)
        self.assertIsNone(order.approved_by)
        self.assertIsNone(order.approved_at)

    def test_explicit_human_approval(self):
        order = create_order_proposal(
            symbol="TCS",
            security_id="11536",
            quantity=5,
            entry_price=3500.0,
            target_price=3800.0,
            stop_loss_price=3400.0
        )
        approved_order = approve_order(order.order_id, operator_id="trader_john", note="Thesis verified")
        self.assertEqual(approved_order.status, OrderState.APPROVED)
        self.assertEqual(approved_order.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(approved_order.approved_by, "trader_john")
        self.assertIsNotNone(approved_order.approved_at)

        # Verify audit log record
        logs = get_approval_log()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "APPROVED")
        self.assertEqual(logs[0]["order_id"], order.order_id)
        self.assertEqual(logs[0]["operator_id"], "trader_john")

    def test_explicit_human_rejection(self):
        order = create_order_proposal(
            symbol="INFY",
            security_id="1594",
            quantity=15,
            entry_price=1400.0,
            target_price=1550.0,
            stop_loss_price=1350.0
        )
        rejected_order = reject_order(order.order_id, operator_id="trader_john", reason="Risk budget exceeded")
        self.assertEqual(rejected_order.status, OrderState.REJECTED)
        self.assertEqual(rejected_order.approval_status, ApprovalStatus.REJECTED)
        self.assertEqual(rejected_order.rejection_reason, "Risk budget exceeded")

        logs = get_approval_log()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "REJECTED")

    def test_unauthorized_preparation_blocked(self):
        order = create_order_proposal(
            symbol="HDFCBANK",
            security_id="1330",
            quantity=20,
            entry_price=1600.0,
            target_price=1750.0,
            stop_loss_price=1520.0
        )
        # Attempting to prepare without approval must raise ApprovalRequiredError
        with self.assertRaises(ApprovalRequiredError):
            prepare_order(order.order_id)

        # Order status must be changed to BLOCKED
        self.assertEqual(order.status, OrderState.BLOCKED)

    def test_unauthorized_routing_blocked(self):
        order = create_order_proposal(
            symbol="ICICIBANK",
            security_id="4963",
            quantity=10,
            entry_price=1000.0,
            target_price=1100.0,
            stop_loss_price=950.0
        )
        # Attempting to route without approval must raise ApprovalRequiredError
        with self.assertRaises(ApprovalRequiredError):
            route_order_to_dhan(order.order_id, paper_mode=True)

        self.assertEqual(order.status, OrderState.BLOCKED)

    def test_unauthorized_state_transition_from_rejected(self):
        order = create_order_proposal(
            symbol="SBIN",
            security_id="3045",
            quantity=50,
            entry_price=600.0,
            target_price=670.0,
            stop_loss_price=570.0
        )
        reject_order(order.order_id, operator_id="risk_officer", reason="High market volatility")

        # Trying to approve a rejected order must fail
        with self.assertRaises(UnauthorizedOrderStateTransitionError):
            approve_order(order.order_id)

        # Trying to prepare a rejected order must fail
        with self.assertRaises(UnauthorizedOrderStateTransitionError):
            prepare_order(order.order_id)

        # Trying to route a rejected order must fail
        with self.assertRaises(UnauthorizedOrderStateTransitionError):
            route_order_to_dhan(order.order_id, paper_mode=True)

    def test_approval_log_audit_trail(self):
        o1 = create_order_proposal("TATAMOTORS", "3456", 10, 900.0, 1000.0, 850.0)
        o2 = create_order_proposal("WIPRO", "3787", 20, 450.0, 500.0, 420.0)

        approve_order(o1.order_id, operator_id="user_1")
        reject_order(o2.order_id, operator_id="user_2", reason="Earnings event pending")

        log_entries = get_approval_log()
        self.assertEqual(len(log_entries), 2)
        self.assertEqual(log_entries[0]["order_id"], o1.order_id)
        self.assertEqual(log_entries[0]["action"], "APPROVED")
        self.assertEqual(log_entries[1]["order_id"], o2.order_id)
        self.assertEqual(log_entries[1]["action"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
