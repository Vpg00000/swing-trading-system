"""
Unit & Integration Security Tests for TASK-038: Resilience Safe Mode Engine.

Tests:
1. Default system state is NORMAL and trading is allowed.
2. Explicit call to trigger_safe_mode() transitions system state to SAFE_MODE and blocks trading.
3. Explicit call to trigger_trading_blocked() transitions state to TRADING_BLOCKED and blocks trading.
4. Detection of missing or stale market data timestamp automatically triggers SAFE_MODE.
5. Critical data feed error automatically triggers TRADING_BLOCKED.
6. System in SAFE_MODE or TRADING_BLOCKED strictly blocks order preparation and raises TradingBlockedError.
7. System in SAFE_MODE or TRADING_BLOCKED strictly blocks order routing and raises TradingBlockedError.
8. State reset restores NORMAL state and enables trading.
9. System health check (/healthz integration) exposes system_state, trading_allowed, and status reasons.
"""

import unittest
import time
from datetime import datetime, timedelta, timezone
from engine.resiliency import (
    get_system_state,
    is_trading_allowed,
    trigger_safe_mode,
    trigger_trading_blocked,
    reset_system_state,
    check_data_staleness,
    report_data_error,
    check_system_health,
    SystemState
)
from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    prepare_order,
    route_order_to_dhan,
    reset_order_book,
    TradingBlockedError
)


class TestSafeModeResilienceEngine(unittest.TestCase):

    def setUp(self):
        reset_order_book()
        reset_system_state("Reset for test_safe_mode")

    def test_initial_normal_state(self):
        self.assertEqual(get_system_state(), "NORMAL")
        self.assertTrue(is_trading_allowed())

    def test_trigger_safe_mode(self):
        trigger_safe_mode("Manual emergency trigger")
        self.assertEqual(get_system_state(), "SAFE_MODE")
        self.assertFalse(is_trading_allowed())

    def test_trigger_trading_blocked(self):
        trigger_trading_blocked("Critical exchange connectivity loss")
        self.assertEqual(get_system_state(), "TRADING_BLOCKED")
        self.assertFalse(is_trading_allowed())

    def test_stale_data_detection_triggers_safe_mode(self):
        # 1. Missing timestamp (None)
        is_stale = check_data_staleness(feed_name="NSE_LTP_FEED", timestamp=None, max_age_seconds=300)
        self.assertTrue(is_stale)
        self.assertEqual(get_system_state(), "SAFE_MODE")
        self.assertFalse(is_trading_allowed())

        # Reset state
        reset_system_state()
        self.assertTrue(is_trading_allowed())

        # 2. Timestamp older than threshold (e.g. 10 minutes ago)
        old_ts = time.time() - 600.0  # 600s old > 300s max
        is_stale = check_data_staleness(feed_name="OHLC_DAILY", timestamp=old_ts, max_age_seconds=300)
        self.assertTrue(is_stale)
        self.assertEqual(get_system_state(), "SAFE_MODE")
        self.assertFalse(is_trading_allowed())

    def test_data_feed_error_triggers_trading_blocked(self):
        report_data_error(feed_name="FII_DII_FEED", error_msg="HTTP 500 Connection Refused", is_critical=True)
        self.assertEqual(get_system_state(), "TRADING_BLOCKED")
        self.assertFalse(is_trading_allowed())

    def test_safe_mode_blocks_dhan_order_preparation(self):
        # Create and approve order
        order = create_order_proposal("RELIANCE", "1333", 10, 2500.0, 2700.0, 2400.0)
        approve_order(order.order_id, operator_id="trader_john")

        # Now trigger safe mode
        trigger_safe_mode("Stale market depth feed")

        # Order preparation must be blocked and raise TradingBlockedError
        with self.assertRaises(TradingBlockedError):
            prepare_order(order.order_id)

    def test_safe_mode_blocks_dhan_order_routing(self):
        order = create_order_proposal("TCS", "11536", 5, 3500.0, 3800.0, 3400.0)
        approve_order(order.order_id, operator_id="trader_john")
        prepare_order(order.order_id, available_cash=50000.0)

        # Trigger trading blocked
        trigger_trading_blocked("Broker API outage")

        # Order routing must be blocked and raise TradingBlockedError
        with self.assertRaises(TradingBlockedError):
            route_order_to_dhan(order.order_id, paper_mode=True)

    def test_reset_system_state_restores_trading(self):
        trigger_safe_mode("Temporary network jitter")
        self.assertFalse(is_trading_allowed())

        reset_system_state("Network connection re-established")
        self.assertEqual(get_system_state(), "NORMAL")
        self.assertTrue(is_trading_allowed())

    def test_health_check_integration(self):
        health = check_system_health()
        self.assertIn("system_state", health)
        self.assertIn("trading_allowed", health)
        self.assertEqual(health["system_state"], "NORMAL")
        self.assertTrue(health["trading_allowed"])

        trigger_safe_mode("Test health update")
        health_updated = check_system_health()
        self.assertEqual(health_updated["system_state"], "SAFE_MODE")
        self.assertFalse(health_updated["trading_allowed"])


if __name__ == "__main__":
    unittest.main()
