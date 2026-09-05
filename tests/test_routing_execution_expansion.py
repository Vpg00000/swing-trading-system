"""
Comprehensive Test Suite for Routing & Execution Expansion Tasks (TASK-041 to TASK-045).

Tests:
1. TASK-041: Multi-Broker Adapter & >500ms Latency Failover Circuit Breaker.
2. TASK-042: Level-2 Bid-Ask Spread & Depth Smart Order Router (NSE vs BSE).
3. TASK-043: Server-side Good-Till-Triggered (GTT) and OCO Order Engine.
4. TASK-044: Basis-point Slippage Calculator & Fill Rate Tracker.
5. TASK-045: Emergency Kill Switch (Flatten all open positions & cancel orders in <2s).
"""

import time
import unittest
from unittest.mock import MagicMock

from data.broker_adapter import (
    DhanBrokerAdapter,
    ZerodhaBrokerAdapter,
    UpstoxBrokerAdapter,
    MultiBrokerRouter,
    CircuitState,
    get_multi_broker_router,
    reset_broker_router
)

from engine.smart_router import (
    SmartOrderRouter,
    Level2Depth,
    calculate_effective_execution_price,
    route_smart_order,
    get_smart_router
)

from engine.gtt_engine import (
    GTTEngine,
    GTTType,
    GTTStatus,
    GTTCondition,
    get_gtt_engine,
    reset_gtt_engine
)

from engine.slippage import (
    SlippageTracker,
    calculate_slippage_bps,
    get_slippage_tracker,
    reset_slippage_tracker
)

from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    prepare_order,
    get_order,
    reset_order_book,
    emergency_flatten_all_positions,
    get_emergency_kill_logs,
    OrderState
)

from engine.resiliency import (
    reset_system_state,
    get_system_state,
    is_trading_allowed,
    SystemState
)


class TestTask041BrokerAdapterFailover(unittest.TestCase):
    """TASK-041: Unified BrokerAdapter interface with >500ms latency circuit breaker."""

    def setUp(self):
        reset_broker_router()

    def test_default_primary_dhan_adapter(self):
        router = get_multi_broker_router()
        active = router.get_active_broker()
        self.assertEqual(active.name, "dhan")
        self.assertEqual(router.circuit_state, CircuitState.CLOSED)
        self.assertTrue(active.is_healthy())

    def test_latency_failover_circuit_breaker_trigger(self):
        router = get_multi_broker_router()
        dhan = router.get_adapter("dhan")
        self.assertIsNotNone(dhan)

        # Set primary broker (Dhan) latency to 650ms (> 500ms threshold)
        dhan.set_latency(650.0)

        # Active broker should automatically switch to secondary (Zerodha)
        active = router.get_active_broker()
        self.assertEqual(active.name, "zerodha")
        self.assertEqual(router.circuit_state, CircuitState.OPEN)

        # Place order and verify execution routes to Zerodha
        res = router.place_order({
            "tradingSymbol": "RELIANCE",
            "quantity": 10,
            "price": 2500.0
        })
        self.assertEqual(res["broker"], "zerodha")
        self.assertEqual(res["circuit_state"], CircuitState.OPEN)

        # Check failover log audit trail
        logs = router.get_failover_log()
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[-1]["active_broker"], "zerodha")
        self.assertEqual(logs[-1]["primary_broker"], "dhan")

    def test_secondary_failover_to_upstox(self):
        router = get_multi_broker_router()
        router.update_broker_latency("dhan", 700.0)
        router.update_broker_latency("zerodha", 550.0)

        active = router.get_active_broker()
        self.assertEqual(active.name, "upstox")

        res = router.place_order({
            "tradingSymbol": "TCS",
            "quantity": 5,
            "price": 3600.0
        })
        self.assertEqual(res["broker"], "upstox")

    def test_circuit_reset(self):
        router = get_multi_broker_router()
        router.update_broker_latency("dhan", 800.0)
        _ = router.get_active_broker()
        self.assertEqual(router.circuit_state, CircuitState.OPEN)

        # Restore latency and reset circuit
        router.update_broker_latency("dhan", 100.0)
        router.reset_circuit()
        self.assertEqual(router.circuit_state, CircuitState.CLOSED)
        self.assertEqual(router.get_active_broker().name, "dhan")


class TestTask042SmartOrderRouter(unittest.TestCase):
    """TASK-042: Level-2 bid-ask spread and depth Smart Order Router."""

    def setUp(self):
        self.router = get_smart_router()

    def test_depth_effective_price_vwap(self):
        # Level 2 Depth asks: Level 1 has 50 shares @ 100, Level 2 has 100 shares @ 102
        depth = Level2Depth(
            bids=[{"price": 99.0, "quantity": 100}],
            asks=[
                {"price": 100.0, "quantity": 50},
                {"price": 102.0, "quantity": 100}
            ]
        )
        # Buying 100 shares: 50 @ 100 + 50 @ 102 = 5000 + 5100 = 10100 -> VWAP = 101.0
        exec_metrics = calculate_effective_execution_price(depth, "BUY", 100)
        self.assertEqual(exec_metrics["effective_price"], 101.0)
        self.assertEqual(exec_metrics["filled_quantity"], 100)
        self.assertEqual(exec_metrics["levels_used"], 2)

    def test_nse_selected_for_lower_buy_price(self):
        nse_l2 = Level2Depth(
            bids=[{"price": 499.0, "quantity": 500}],
            asks=[{"price": 500.0, "quantity": 500}]  # Best ask 500
        )
        bse_l2 = Level2Depth(
            bids=[{"price": 501.0, "quantity": 500}],
            asks=[{"price": 503.0, "quantity": 500}]  # Best ask 503
        )

        decision = self.router.evaluate_exchanges("INFY", "BUY", 100, nse_l2, bse_l2)
        self.assertEqual(decision["selected_exchange"], "NSE")
        self.assertGreater(decision["price_savings_bps"], 0.0)
        self.assertIsNotNone(decision["evidence"])
        self.assertEqual(decision["evidence"]["selected_exchange"], "NSE")

    def test_bse_selected_for_higher_sell_price(self):
        nse_l2 = Level2Depth(
            bids=[{"price": 1200.0, "quantity": 200}],
            asks=[{"price": 1202.0, "quantity": 200}]
        )
        bse_l2 = Level2Depth(
            bids=[{"price": 1205.0, "quantity": 200}], # Higher bid on BSE for SELL
            asks=[{"price": 1207.0, "quantity": 200}]
        )

        decision = self.router.evaluate_exchanges("HDFCBANK", "SELL", 50, nse_l2, bse_l2)
        self.assertEqual(decision["selected_exchange"], "BSE")
        self.assertIn("BSE offers higher sell execution price", decision["reason"])


class TestTask043GTTEngine(unittest.TestCase):
    """TASK-043: Server-side GTT and OCO Order Engine."""

    def setUp(self):
        reset_gtt_engine()
        reset_order_book()
        reset_system_state()
        self.engine = get_gtt_engine()

    def test_create_single_gtt(self):
        gtt = self.engine.create_single_gtt(
            symbol="TATAMOTORS",
            trigger_price=900.0,
            order_price=895.0,
            quantity=20,
            transaction_type="BUY",
            condition="LESS_THAN_EQUAL"
        )
        self.assertEqual(gtt.symbol, "TATAMOTORS")
        self.assertEqual(gtt.gtt_type, GTTType.SINGLE)
        self.assertEqual(gtt.status, GTTStatus.ACTIVE)

    def test_oco_gtt_trigger_and_opposite_leg_cancellation(self):
        # Create OCO order: Stop loss @ 950.0 (<=), Target @ 1050.0 (>=)
        gtt = self.engine.create_oco_gtt(
            symbol="AXISBANK",
            stop_loss_trigger=950.0,
            stop_loss_price=948.0,
            target_trigger=1050.0,
            target_price=1052.0,
            quantity=15,
            transaction_type="SELL"
        )

        self.assertEqual(len(gtt.legs), 2)
        sl_leg = next(l for l in gtt.legs if l.leg_name == "STOP_LOSS")
        tgt_leg = next(l for l in gtt.legs if l.leg_name == "TARGET")

        self.assertEqual(sl_leg.status, "PENDING")
        self.assertEqual(tgt_leg.status, "PENDING")

        # Simulate price drop to 945.0 (triggers stop loss)
        events = self.engine.process_market_tick("AXISBANK", 945.0, auto_execute=True)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["triggered_leg"], "STOP_LOSS")
        self.assertLess(events[0]["eval_latency_ms"], 100.0)

        # Verify stop loss leg triggered and target leg CANCELLED
        self.assertEqual(sl_leg.status, "TRIGGERED")
        self.assertEqual(tgt_leg.status, "CANCELLED")
        self.assertIn(tgt_leg.leg_id, events[0]["cancelled_other_legs"])
        self.assertEqual(gtt.status, GTTStatus.EXECUTED)

    def test_cancel_gtt_order(self):
        gtt = self.engine.create_single_gtt("WIPRO", 450.0, 452.0, 50, "BUY", "GREATER_THAN_EQUAL")
        cancelled = self.engine.cancel_gtt_order(gtt.gtt_id)
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.status, GTTStatus.CANCELLED)


class TestTask044SlippageTracker(unittest.TestCase):
    """TASK-044: Basis-point slippage calculator and fill rate tracker."""

    def setUp(self):
        reset_slippage_tracker()
        self.tracker = get_slippage_tracker()

    def test_calculate_slippage_bps_buy_and_sell(self):
        # BUY: benchmark 100, fill 101 -> +100 bps adverse
        self.assertEqual(calculate_slippage_bps("BUY", 100.0, 101.0), 100.0)
        # BUY: benchmark 100, fill 99 -> -100 bps favorable
        self.assertEqual(calculate_slippage_bps("BUY", 100.0, 99.0), -100.0)

        # SELL: benchmark 200, fill 198 -> +100 bps adverse
        self.assertEqual(calculate_slippage_bps("SELL", 200.0, 198.0), 100.0)
        # SELL: benchmark 200, fill 202 -> -100 bps favorable
        self.assertEqual(calculate_slippage_bps("SELL", 200.0, 202.0), -100.0)

    def test_record_execution_and_aggregate_stats(self):
        rec1 = self.tracker.record_execution(
            order_id="ORD-101",
            symbol="SBIN",
            transaction_type="BUY",
            requested_quantity=100,
            executed_quantity=100,
            benchmark_price=600.0,
            actual_fill_price=603.0, # +50 bps adverse
            broker="dhan",
            exchange="NSE"
        )
        self.assertEqual(rec1.slippage_bps, 50.0)
        self.assertEqual(rec1.fill_rate_pct, 100.0)
        self.assertEqual(rec1.market_impact_cost, 300.0)

        rec2 = self.tracker.record_execution(
            order_id="ORD-102",
            symbol="SBIN",
            transaction_type="BUY",
            requested_quantity=100,
            executed_quantity=80, # 80% fill rate
            benchmark_price=600.0,
            actual_fill_price=597.0, # -50 bps favorable
            broker="zerodha",
            exchange="NSE"
        )
        self.assertEqual(rec2.slippage_bps, -50.0)
        self.assertEqual(rec2.fill_rate_pct, 80.0)

        stats = self.tracker.calculate_stats(symbol="SBIN")
        self.assertEqual(stats["total_orders"], 2)
        self.assertEqual(stats["avg_slippage_bps"], 0.0)
        self.assertEqual(stats["avg_fill_rate_pct"], 90.0)
        self.assertEqual(stats["adverse_fills_count"], 1)
        self.assertEqual(stats["favorable_fills_count"], 1)

        report = self.tracker.generate_slippage_report()
        self.assertIn("overall_summary", report)
        self.assertIn("dhan", report["broker_breakdown"])
        self.assertIn("zerodha", report["broker_breakdown"])


class TestTask045EmergencyKillSwitch(unittest.TestCase):
    """TASK-045: Emergency Flatten all open positions and cancel orders protocol."""

    def setUp(self):
        reset_order_book()
        reset_system_state("Reset for kill switch test")

    def test_invalid_confirmation_token_raises_error(self):
        with self.assertRaises(ValueError):
            emergency_flatten_all_positions(confirmation_token="INVALID_TOKEN")

    def test_emergency_flatten_protocol_execution(self):
        # 1. Populate Order Book with proposals and approved orders
        o1 = create_order_proposal("ICICIBANK", "4963", 50, 1000.0, 1100.0, 950.0)
        approve_order(o1.order_id)
        prepare_order(o1.order_id)

        o2 = create_order_proposal("KOTAKBANK", "1922", 30, 1800.0, 1950.0, 1700.0)

        self.assertEqual(get_order(o1.order_id).status, OrderState.PREPARED)
        self.assertEqual(get_order(o2.order_id).status, OrderState.PROPOSED)

        # Mock position provider returning 2 open positions
        mock_positions = [
            {"symbol": "ICICIBANK", "quantity": 50, "price": 1000.0, "security_id": "4963"},
            {"symbol": "TATASTEEL", "quantity": -100, "price": 140.0, "security_id": "3499"}
        ]

        # 2. Trigger Emergency Kill Switch Protocol
        event = emergency_flatten_all_positions(
            confirmation_token="CONFIRM_EMERGENCY_FLATTEN",
            position_provider=lambda: mock_positions,
            operator_id="CHIEF_RISK_OFFICER"
        )

        # 3. Assertions
        self.assertEqual(event["status"], "SUCCESS")
        self.assertEqual(event["orders_cancelled_count"], 2)
        self.assertEqual(event["positions_flattened_count"], 2)
        self.assertLess(event["response_time_ms"], 2000.0)  # Must complete in < 2 seconds

        # Verify Resilience Engine system state is TRADING_BLOCKED
        self.assertEqual(get_system_state(), SystemState.TRADING_BLOCKED.value)
        self.assertFalse(is_trading_allowed())

        # Verify all orders cancelled
        self.assertEqual(get_order(o1.order_id).status, OrderState.CANCELLED)
        self.assertEqual(get_order(o2.order_id).status, OrderState.CANCELLED)

        # Verify emergency kill logs
        logs = get_emergency_kill_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["operator_id"], "CHIEF_RISK_OFFICER")


if __name__ == "__main__":
    unittest.main()
