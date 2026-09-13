"""
Unit tests for Good-Till-Triggered (GTT) Order Engine & FastAPI Endpoints (Phase 3 Task C).

Verifies:
1. GTTOrderEngine Single and OCO order creation and state tracking.
2. Market tick evaluation (`evaluate_ticks`) for trigger breaches and OCO leg cancellation.
3. Helper functions: get_gtt_orders, create_gtt_order, cancel_gtt_order, evaluate_ticks.
4. FastAPI web server `/api/gtt` endpoints (GET, POST, DELETE, evaluate).
"""

import unittest
from fastapi.testclient import TestClient

from engine.gtt_engine import (
    GTTOrderEngine,
    GTTType,
    GTTStatus,
    GTTCondition,
    get_gtt_engine,
    reset_gtt_engine,
    get_gtt_orders,
    create_gtt_order,
    cancel_gtt_order,
    evaluate_ticks
)
from web_server import app


class TestGTTEngine(unittest.TestCase):
    def setUp(self):
        reset_gtt_engine()
        self.engine = get_gtt_engine()

    def test_single_gtt_creation(self):
        order = self.engine.create_single_gtt(
            symbol="RELIANCE",
            trigger_price=2400.0,
            order_price=2405.0,
            quantity=10,
            transaction_type="BUY",
            condition="LESS_THAN_EQUAL"
        )
        self.assertIsNotNone(order.gtt_id)
        self.assertEqual(order.symbol, "RELIANCE")
        self.assertEqual(order.gtt_type, GTTType.SINGLE)
        self.assertEqual(order.trigger_price, 2400.0)
        self.assertEqual(order.order_price, 2405.0)
        self.assertEqual(order.quantity, 10)
        self.assertEqual(order.order_type, "BUY")
        self.assertIn(order.status, [GTTStatus.ACTIVE, GTTStatus.PENDING])
        self.assertIsNotNone(order.created_at)
        self.assertIsNone(order.triggered_at)

    def test_oco_gtt_creation(self):
        order = self.engine.create_oco_gtt(
            symbol="INFY",
            stop_loss_trigger=1400.0,
            stop_loss_price=1398.0,
            target_trigger=1600.0,
            target_price=1602.0,
            quantity=25,
            transaction_type="SELL"
        )
        self.assertEqual(order.symbol, "INFY")
        self.assertEqual(order.gtt_type, GTTType.OCO)
        self.assertEqual(order.stop_loss_trigger, 1400.0)
        self.assertEqual(order.stop_loss_price, 1398.0)
        self.assertEqual(order.target_trigger, 1600.0)
        self.assertEqual(order.target_price, 1602.0)
        self.assertEqual(len(order.legs), 2)

    def test_evaluate_ticks_single_trigger(self):
        self.engine.create_single_gtt(
            symbol="TCS",
            trigger_price=3500.0,
            order_price=3500.0,
            quantity=5,
            transaction_type="BUY",
            condition="LESS_THAN_EQUAL"
        )

        # Tick price above trigger - should not fire
        events = evaluate_ticks({"TCS": 3550.0}, auto_execute=False)
        self.assertEqual(len(events), 0)

        # Tick price at/below trigger - should fire
        events = evaluate_ticks({"TCS": 3490.0}, auto_execute=False)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["symbol"], "TCS")
        self.assertEqual(events[0]["triggered_leg"], "SINGLE")

        orders = get_gtt_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["status"], GTTStatus.TRIGGERED.value)
        self.assertIsNotNone(orders[0]["triggered_at"])

    def test_evaluate_ticks_oco_stop_loss_trigger(self):
        order = self.engine.create_oco_gtt(
            symbol="HDFCBANK",
            stop_loss_trigger=1500.0,
            stop_loss_price=1495.0,
            target_trigger=1700.0,
            target_price=1705.0,
            quantity=15,
            transaction_type="SELL"
        )

        # Price drops to 1490 - triggers stop loss, target leg cancelled
        events = evaluate_ticks({"HDFCBANK": 1490.0}, auto_execute=False)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["triggered_leg"], "STOP_LOSS")

        order_dict = self.engine.get_gtt_order(order.gtt_id).to_dict()
        sl_leg = next(l for l in order_dict["legs"] if l["leg_name"] == "STOP_LOSS")
        tgt_leg = next(l for l in order_dict["legs"] if l["leg_name"] == "TARGET")

        self.assertEqual(sl_leg["status"], "TRIGGERED")
        self.assertEqual(tgt_leg["status"], "CANCELLED")

    def test_evaluate_ticks_oco_target_trigger(self):
        order = self.engine.create_oco_gtt(
            symbol="ICICIBANK",
            stop_loss_trigger=950.0,
            stop_loss_price=945.0,
            target_trigger=1100.0,
            target_price=1105.0,
            quantity=20,
            transaction_type="SELL"
        )

        # Price rises to 1110 - triggers target leg, stop loss leg cancelled
        events = evaluate_ticks({"ICICIBANK": 1110.0}, auto_execute=False)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["triggered_leg"], "TARGET")

        order_dict = self.engine.get_gtt_order(order.gtt_id).to_dict()
        sl_leg = next(l for l in order_dict["legs"] if l["leg_name"] == "STOP_LOSS")
        tgt_leg = next(l for l in order_dict["legs"] if l["leg_name"] == "TARGET")

        self.assertEqual(tgt_leg["status"], "TRIGGERED")
        self.assertEqual(sl_leg["status"], "CANCELLED")

    def test_helper_functions(self):
        # Create Single order via helper
        single_params = {
            "symbol": "SBIN",
            "trigger_price": 600.0,
            "order_price": 602.0,
            "quantity": 30,
            "order_type": "BUY",
            "condition": "LESS_THAN_EQUAL"
        }
        res_create = create_gtt_order(single_params)
        self.assertEqual(res_create["symbol"], "SBIN")
        gtt_id = res_create["gtt_id"]

        # List orders via helper
        orders = get_gtt_orders()
        self.assertEqual(len(orders), 1)

        # Cancel order via helper
        res_cancel = cancel_gtt_order(gtt_id)
        self.assertIsNotNone(res_cancel)
        self.assertEqual(res_cancel["status"], GTTStatus.CANCELLED.value)


class TestGTTApiEndpoints(unittest.TestCase):
    def setUp(self):
        reset_gtt_engine()
        self.client = TestClient(app)

    def test_get_gtt_orders_empty(self):
        response = self.client.get("/api/gtt")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["orders"], [])
        self.assertEqual(data["count"], 0)

    def test_post_gtt_create_single_order(self):
        payload = {
            "symbol": "TATAMOTORS",
            "gtt_type": "SINGLE",
            "trigger_price": 880.0,
            "order_price": 885.0,
            "quantity": 15,
            "order_type": "BUY"
        }
        response = self.client.post("/api/gtt", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("gtt_id", data)
        self.assertEqual(data["order"]["symbol"], "TATAMOTORS")
        self.assertEqual(data["order"]["trigger_price"], 880.0)

    def test_post_gtt_create_oco_order(self):
        payload = {
            "symbol": "AXISBANK",
            "gtt_type": "OCO",
            "stop_loss_trigger": 950.0,
            "stop_loss_price": 948.0,
            "target_trigger": 1050.0,
            "target_price": 1052.0,
            "quantity": 20,
            "order_type": "SELL"
        }
        response = self.client.post("/api/gtt", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["order"]["gtt_type"], "OCO")
        self.assertEqual(data["order"]["stop_loss_trigger"], 950.0)
        self.assertEqual(data["order"]["target_trigger"], 1050.0)

    def test_delete_gtt_order_query_param(self):
        # First create an order
        create_res = self.client.post("/api/gtt", json={
            "symbol": "WIPRO",
            "trigger_price": 450.0,
            "order_price": 452.0,
            "quantity": 50
        })
        gtt_id = create_res.json()["gtt_id"]

        # Cancel via query param
        del_res = self.client.delete(f"/api/gtt?gtt_id={gtt_id}")
        self.assertEqual(del_res.status_code, 200)
        data = del_res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["order"]["status"], GTTStatus.CANCELLED.value)

    def test_delete_gtt_order_path_param(self):
        create_res = self.client.post("/api/gtt", json={
            "symbol": "BHARTIARTL",
            "trigger_price": 1100.0,
            "order_price": 1105.0,
            "quantity": 10
        })
        gtt_id = create_res.json()["gtt_id"]

        del_res = self.client.delete(f"/api/gtt/{gtt_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "SUCCESS")

    def test_post_gtt_evaluate_ticks(self):
        # Create an order
        self.client.post("/api/gtt", json={
            "symbol": "MARUTI",
            "trigger_price": 10000.0,
            "order_price": 10000.0,
            "quantity": 2,
            "order_type": "BUY"
        })

        eval_payload = {
            "ticks": {"MARUTI": 9950.0},
            "auto_execute": False
        }
        eval_res = self.client.post("/api/gtt/evaluate", json=eval_payload)
        self.assertEqual(eval_res.status_code, 200)
        data = eval_res.json()
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(len(data["triggered_events"]), 1)
        self.assertEqual(data["triggered_events"][0]["symbol"], "MARUTI")


if __name__ == "__main__":
    unittest.main()
