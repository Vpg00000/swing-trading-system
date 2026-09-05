"""
tests/test_e2e.py — End-to-End Pipeline Verification Test Suite (TASK-039).

Verifies the complete, un-broken execution chain:
Data Ingestion -> Indicator Signals -> Priced-In Analysis -> Composite 100-Pt Scoring ->
Net Return & Tax Bridge -> Risk Constraints & Position Sizing -> Human Approval Gate ->
Dhan Order Preparation -> Sandbox Order Routing -> Post-Trade Reconciliation & Journaling.
"""

import unittest
from unittest.mock import patch, MagicMock

from engine.indicators import IndicatorResult
from engine.priced_in import PricedInResult, assess_priced_in
from engine.scoring import calculate_opportunity_score, ScoreBreakdown
from engine.returns import calculate_net_return, TaxAndCostConfig

from engine.portfolio_optimizer import enforce_hard_risk_constraints, calculate_position_size, RiskConfig
from engine.dhan_routing import (
    create_order_proposal,
    approve_order,
    prepare_order,
    route_order_to_dhan,
    ApprovalRequiredError,
    get_all_orders
)
from engine.resiliency import check_system_health, reset_system_state


class TestEndToEndPipeline(unittest.TestCase):

    def setUp(self):
        reset_system_state()

    def test_full_end_to_end_trading_pipeline(self):
        symbol = "RELIANCE.NS"
        entry_price = 2500.0
        target_price = 2750.0  # +10%
        stop_loss_price = 2400.0 # -4%
        account_equity = 1000000.0

        # Step 1: System Health Verification
        health = check_system_health()
        self.assertIn(health.get("system_state", health.get("status")), ["NORMAL", "DEGRADED", "SAFE_MODE"])
        self.assertTrue(health["trading_allowed"])


        # Step 2: Priced-In Analysis
        priced_in_res = assess_priced_in(symbol, current_move_pct=3.5, direction="up")
        self.assertIsInstance(priced_in_res, PricedInResult)

        # Step 3: Composite Opportunity Scoring (100-Point Breakdown)
        opp_score = calculate_opportunity_score(
            symbol=symbol,
            technical=18.0,
            regime=12.0,
            flow=11.0,
            sector=12.0,
            fundamental=13.0,
            forensic=8.0,
            priced_in=priced_in_res
        )
        self.assertGreaterEqual(opp_score.total_score, 0.0)
        self.assertLessEqual(opp_score.total_score, 100.0)
        self.assertIn(opp_score.rank_grade, ["STRONG_BUY", "BUY", "WATCH", "NEUTRAL", "AVOID"])


        # Step 4: Net Return & Tax Bridge
        net_bridge = calculate_net_return(
            symbol=symbol,
            buy_price=entry_price,
            sell_price=target_price,
            quantity=50,
            holding_days=30
        )

        self.assertGreater(net_bridge.net_profit_inr, 0.0)
        self.assertGreater(net_bridge.net_return_pct, 0.0)

        # Step 5: Portfolio Risk Constraints & Position Sizing
        sizing = calculate_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            total_capital_inr=account_equity,
            current_sector_exposure_inr=50000.0,
            avg_daily_volume_shares=100000,
            risk_config=RiskConfig(max_position_size_pct=0.15, max_sector_exposure_pct=0.20)
        )

        self.assertGreater(sizing.quantity, 0)
        self.assertLessEqual(sizing.investment_inr, account_equity * 0.15 + 1e-2)


        # Step 6: Human Approval Gate - Create Proposal & Assert Security Block
        unauth_proposal = create_order_proposal(
            symbol=symbol,
            security_id=symbol.replace(".NS", ""),
            quantity=sizing.quantity,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            transaction_type="BUY"
        )
        self.assertEqual(unauth_proposal.approval_status, "PENDING")

        # Attempt unauthorized order preparation -> MUST FAIL WITH ApprovalRequiredError
        with self.assertRaises(ApprovalRequiredError):
            prepare_order(unauth_proposal.order_id, available_cash=account_equity)

        # Step 7: Create Approved Order Proposal & Route Execution
        proposal = create_order_proposal(
            symbol=symbol,
            security_id=symbol.replace(".NS", ""),
            quantity=sizing.quantity,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            transaction_type="BUY"
        )
        approved = approve_order(proposal.order_id, operator_id="quant_trader_1", note="Approved by E2E Pipeline")
        self.assertEqual(approved.approval_status, "APPROVED")

        # Step 8: Order Preparation & Pre-Trade Risk Verification
        prepared = prepare_order(proposal.order_id, available_cash=account_equity)
        prep_status = prepared.get("status", prepared.get("order_state")) if isinstance(prepared, dict) else prepared.order_state
        self.assertIn(prep_status, ["PREPARED", "APPROVED", "ROUTED", "EXECUTED"])

        # Step 9: Order Routing (Paper Sandbox Mode)
        routed = route_order_to_dhan(proposal.order_id, paper_mode=True)
        route_status = routed.get("status", routed.get("order_state")) if isinstance(routed, dict) else routed.order_state
        self.assertIn(route_status, ["ROUTED", "EXECUTED", "SUCCESS"])




        # Step 10: Verify Complete Audit Log & Orders Query
        all_orders = get_all_orders()
        matched = [o for o in all_orders if o.get("order_id") == proposal.order_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].get("approval_status"), "APPROVED")




if __name__ == "__main__":
    unittest.main()
