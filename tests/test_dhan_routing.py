"""
Unit & Integration Tests for TASK-023: Dhan Order Routing.

Tests:
1. Pre-trade margin & cash sufficiency checks.
2. Pre-trade price level validation (entry vs stop loss vs target).
3. Dhan Bracket Order payload generation.
4. Order preparation flow (APPROVED -> PREPARED).
5. Execution in Sandbox/Paper trading mode (PREPARED -> EXECUTED) and trade recording.
6. Live Dhan routing with mock DhanClient.
7. Full end-to-end order lifecycle.
"""

import unittest
from unittest.mock import MagicMock
from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    prepare_order,
    route_order_to_dhan,
    generate_dhan_bracket_order,
    verify_margin_requirement,
    get_executed_trades_log,
    reset_order_book,
    OrderState,
    PreTradeCheckFailedError
)
from engine.resiliency import reset_system_state


class TestDhanOrderRouting(unittest.TestCase):

    def setUp(self):
        reset_order_book()
        reset_system_state("Reset for test_dhan_routing")

    def test_verify_margin_requirement(self):
        # 10 shares @ 200 = 2000 order value. 100% margin requires 2000.
        self.assertTrue(verify_margin_requirement(available_cash=5000.0, order_value=2000.0, margin_pct=100.0))
        self.assertFalse(verify_margin_requirement(available_cash=1000.0, order_value=2000.0, margin_pct=100.0))

    def test_pre_trade_price_level_validation(self):
        order = create_order_proposal(
            symbol="AXISBANK",
            security_id="5900",
            quantity=10,
            entry_price=1000.0,
            target_price=900.0,  # Invalid: target <= entry for BUY
            stop_loss_price=950.0
        )
        approve_order(order.order_id, operator_id="trader_john")

        with self.assertRaises(PreTradeCheckFailedError):
            prepare_order(order.order_id)

    def test_bracket_order_payload_generation(self):
        payload = generate_dhan_bracket_order(
            symbol="RELIANCE",
            security_id="1333",
            quantity=15,
            entry_price=2400.0,
            target_price=2600.0,
            stop_loss_price=2300.0,
            order_type="LIMIT"
        )
        self.assertEqual(payload["tradingSymbol"], "RELIANCE")
        self.assertEqual(payload["securityId"], "1333")
        self.assertEqual(payload["quantity"], 15)
        self.assertEqual(payload["price"], 2400.0)
        self.assertEqual(payload["targetPrice"], 2600.0)
        self.assertEqual(payload["stopLossPrice"], 2300.0)
        self.assertEqual(payload["productType"], "BO")

    def test_order_preparation_flow(self):
        order = create_order_proposal(
            symbol="TCS",
            security_id="11536",
            quantity=5,
            entry_price=3500.0,
            target_price=3800.0,
            stop_loss_price=3400.0
        )
        approve_order(order.order_id, operator_id="trader_john")
        prep_res = prepare_order(order.order_id, available_cash=50000.0)

        self.assertEqual(prep_res["status"], "PREPARED")
        self.assertEqual(order.status, OrderState.PREPARED)
        self.assertIsNotNone(order.payload)
        self.assertEqual(order.payload["tradingSymbol"], "TCS")

    def test_paper_trading_execution(self):
        order = create_order_proposal(
            symbol="INFY",
            security_id="1594",
            quantity=10,
            entry_price=1500.0,
            target_price=1650.0,
            stop_loss_price=1420.0
        )
        approve_order(order.order_id, operator_id="trader_john")
        prepare_order(order.order_id, available_cash=50000.0)

        route_res = route_order_to_dhan(order.order_id, paper_mode=True)

        self.assertEqual(route_res["status"], "SUCCESS")
        self.assertEqual(route_res["mode"], "PAPER_SANDBOX")
        self.assertEqual(order.status, OrderState.EXECUTED)
        self.assertIsNotNone(order.execution_details)
        self.assertEqual(order.execution_details["executed_quantity"], 10)

        # Check executed trade journal recording
        executed_trades = get_executed_trades_log()
        self.assertEqual(len(executed_trades), 1)
        self.assertEqual(executed_trades[0]["symbol"], "INFY")

    def test_mock_dhan_client_live_routing(self):
        order = create_order_proposal(
            symbol="LT",
            security_id="11483",
            quantity=2,
            entry_price=3000.0,
            target_price=3300.0,
            stop_loss_price=2850.0
        )
        approve_order(order.order_id, operator_id="trader_john")

        mock_client = MagicMock()
        mock_client.is_active.return_value = True
        mock_client.place_order.return_value = {
            "orderId": "DHAN-ORD-998877",
            "orderStatus": "FILLED"
        }

        route_res = route_order_to_dhan(order.order_id, paper_mode=False, dhan_client=mock_client)

        self.assertEqual(route_res["status"], "SUCCESS")
        self.assertEqual(route_res["mode"], "DHAN_LIVE")
        self.assertEqual(order.status, OrderState.EXECUTED)
        mock_client.place_order.assert_called_once_with(order.payload)

    def test_full_order_lifecycle(self):
        # 1. Proposal
        order = create_order_proposal("BHARTIARTL", "10604", 25, 1100.0, 1220.0, 1040.0)
        self.assertEqual(order.status, OrderState.PROPOSED)

        # 2. Approval
        approve_order(order.order_id, operator_id="risk_head")
        self.assertEqual(order.status, OrderState.APPROVED)

        # 3. Preparation & Pre-trade check
        prepare_order(order.order_id, available_cash=100000.0)
        self.assertEqual(order.status, OrderState.PREPARED)

        # 4. Routing & Execution
        result = route_order_to_dhan(order.order_id, paper_mode=True)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(order.status, OrderState.EXECUTED)


if __name__ == "__main__":
    unittest.main()
