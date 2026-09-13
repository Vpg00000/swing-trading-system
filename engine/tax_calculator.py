"""
engine/tax_calculator.py — Indian Equity Tax & Tax Loss Harvesting Engine (Phase 3 Task D).

Implements TaxCalculator for Indian Stock Market (STCG @ 20%, LTCG @ 12.5% beyond ₹1.25 Lakh exemption under Budget 2024 rules).
Calculates tax liability breakdown and tax loss harvesting opportunities.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import json
import logging
from pathlib import Path

# Retain existing imports for backward compatibility
from engine.returns import (
    TaxAndCostConfig,
    TransactionCostBreakdown,
    TaxBreakdown,
    NetReturnResult,
    calculate_transaction_costs,
    calculate_capital_gains_tax,
    calculate_net_return,
    calculate_expected_net_return,
)

logger = logging.getLogger(__name__)

# Budget 2024 Indian Equity Tax Rates & Exemption Thresholds
DEFAULT_STCG_RATE = 0.20        # 20.0% STCG for equity assets held <= 365 days
DEFAULT_LTCG_RATE = 0.125       # 12.5% LTCG for equity assets held > 365 days
DEFAULT_LTCG_EXEMPTION_LIMIT = 125_000.0  # ₹1.25 Lakh annual exemption under Budget 2024


class TaxCalculator:
    """
    Tax calculator for Indian Stock Market trading according to Union Budget 2024 rules.
    STCG: 20%
    LTCG: 12.5% above ₹1,25,000 exemption limit.
    """

    def __init__(
        self,
        stcg_rate: float = DEFAULT_STCG_RATE,
        ltcg_rate: float = DEFAULT_LTCG_RATE,
        ltcg_exemption_limit: float = DEFAULT_LTCG_EXEMPTION_LIMIT
    ):
        self.stcg_rate = stcg_rate
        self.ltcg_rate = ltcg_rate
        self.ltcg_exemption_limit = ltcg_exemption_limit

    def calculate_tax_liability(
        self,
        realized_trades: Optional[List[Dict[str, Any]]] = None,
        ltcg_exemption_used_so_far: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculates STCG and LTCG tax liability based on realized trades.
        """
        if not realized_trades:
            realized_trades = []

        realized_stcg_gains = 0.0
        realized_stcg_losses = 0.0
        realized_ltcg_gains = 0.0
        realized_ltcg_losses = 0.0

        for trade in realized_trades:
            pnl = trade.get("pnl", trade.get("gain_loss", 0.0))
            holding_days = trade.get("holding_days", trade.get("days_held", 0))
            is_ltcg = trade.get("is_ltcg", holding_days > 365)

            if is_ltcg:
                if pnl > 0:
                    realized_ltcg_gains += pnl
                else:
                    realized_ltcg_losses += abs(pnl)
            else:
                if pnl > 0:
                    realized_stcg_gains += pnl
                else:
                    realized_stcg_losses += abs(pnl)

        net_stcg_gain = max(0.0, realized_stcg_gains - realized_stcg_losses)
        net_ltcg_gain = max(0.0, realized_ltcg_gains - realized_ltcg_losses)

        # Apply LTCG Exemption Threshold (₹1.25 Lakh per financial year)
        remaining_exemption = max(0.0, self.ltcg_exemption_limit - ltcg_exemption_used_so_far)
        taxable_ltcg = max(0.0, net_ltcg_gain - remaining_exemption)
        exemption_used = min(net_ltcg_gain, remaining_exemption)

        stcg_tax = net_stcg_gain * self.stcg_rate
        ltcg_tax = taxable_ltcg * self.ltcg_rate
        total_tax = stcg_tax + ltcg_tax

        return {
            "stcg_rate_pct": round(self.stcg_rate * 100, 2),
            "ltcg_rate_pct": round(self.ltcg_rate * 100, 2),
            "ltcg_exemption_limit_inr": self.ltcg_exemption_limit,
            "realized_stcg_gains_inr": round(realized_stcg_gains, 2),
            "realized_stcg_losses_inr": round(realized_stcg_losses, 2),
            "net_stcg_gain_inr": round(net_stcg_gain, 2),
            "stcg_tax_liability_inr": round(stcg_tax, 2),
            "realized_ltcg_gains_inr": round(realized_ltcg_gains, 2),
            "realized_ltcg_losses_inr": round(realized_ltcg_losses, 2),
            "net_ltcg_gain_inr": round(net_ltcg_gain, 2),
            "ltcg_exemption_used_inr": round(exemption_used, 2),
            "taxable_ltcg_gain_inr": round(taxable_ltcg, 2),
            "ltcg_tax_liability_inr": round(ltcg_tax, 2),
            "total_tax_liability_inr": round(total_tax, 2),
        }

    def calculate_tax_loss_harvesting(
        self,
        holdings: Optional[List[Dict[str, Any]]] = None,
        realized_stcg_gains: float = 0.0,
        realized_ltcg_gains: float = 0.0
    ) -> Dict[str, Any]:
        """
        Identifies tax loss harvesting opportunities from unrealized loss positions.
        """
        if not holdings:
            holdings = []

        harvest_candidates = []
        total_harvestable_stcg_loss = 0.0
        total_harvestable_ltcg_loss = 0.0

        for h in holdings:
            qty = h.get("quantity", 0)
            if qty <= 0:
                continue

            buy_price = h.get("buy_price", h.get("avg_price", 0.0))
            current_price = h.get("current_price", h.get("close", buy_price))
            holding_days = h.get("holding_days", h.get("days_held", 30))
            is_ltcg = h.get("is_ltcg", holding_days > 365)

            unrealized_pnl = (current_price - buy_price) * qty
            if unrealized_pnl < 0:
                loss_inr = abs(unrealized_pnl)
                applicable_tax_rate = self.ltcg_rate if is_ltcg else self.stcg_rate
                estimated_tax_savings = loss_inr * applicable_tax_rate

                if is_ltcg:
                    total_harvestable_ltcg_loss += loss_inr
                else:
                    total_harvestable_stcg_loss += loss_inr

                harvest_candidates.append({
                    "symbol": h.get("symbol", "UNKNOWN"),
                    "quantity": qty,
                    "buy_price": round(buy_price, 2),
                    "current_price": round(current_price, 2),
                    "holding_days": holding_days,
                    "is_ltcg": is_ltcg,
                    "unrealized_loss_inr": round(loss_inr, 2),
                    "estimated_tax_savings_inr": round(estimated_tax_savings, 2),
                    "recommendation": "HARVEST_LTCG_LOSS" if is_ltcg else "HARVEST_STCG_LOSS"
                })

        total_harvestable_loss = total_harvestable_stcg_loss + total_harvestable_ltcg_loss

        estimated_stcg_savings = total_harvestable_stcg_loss * self.stcg_rate
        estimated_ltcg_savings = total_harvestable_ltcg_loss * self.ltcg_rate
        total_estimated_tax_savings = estimated_stcg_savings + estimated_ltcg_savings

        return {
            "realized_stcg_gains_inr": round(realized_stcg_gains, 2),
            "realized_ltcg_gains_inr": round(realized_ltcg_gains, 2),
            "total_harvestable_loss_inr": round(total_harvestable_loss, 2),
            "total_harvestable_stcg_loss_inr": round(total_harvestable_stcg_loss, 2),
            "total_harvestable_ltcg_loss_inr": round(total_harvestable_ltcg_loss, 2),
            "estimated_total_tax_savings_inr": round(total_estimated_tax_savings, 2),
            "candidate_count": len(harvest_candidates),
            "harvest_candidates": harvest_candidates
        }


def identify_tax_loss_harvesting_candidates(
    holdings: list[dict],
    realized_stcg_gains_inr: float = 0.0,
    stcg_tax_rate: float = 0.20
) -> dict:
    """TASK-058: Automated Tax-Loss Harvesting Execution Manager (Legacy Helper)."""
    calc = TaxCalculator(stcg_rate=stcg_tax_rate)
    res = calc.calculate_tax_loss_harvesting(holdings, realized_stcg_gains=realized_stcg_gains_inr)
    stcg_candidates = [c for c in res["harvest_candidates"] if not c["is_ltcg"]]
    total_stcg_loss = res["total_harvestable_stcg_loss_inr"]
    offset_loss = min(total_stcg_loss, realized_stcg_gains_inr)
    estimated_total_tax_savings = offset_loss * stcg_tax_rate

    return {
        "realized_stcg_gains_inr": round(realized_stcg_gains_inr, 2),
        "total_harvestable_loss_inr": round(total_stcg_loss, 2),
        "offsetable_loss_inr": round(offset_loss, 2),
        "estimated_total_tax_savings_inr": round(estimated_total_tax_savings, 2),
        "candidate_count": len(stcg_candidates),
        "harvest_candidates": stcg_candidates
    }


def calculate_tax_summary(
    holdings: Optional[List[Dict[str, Any]]] = None,
    realized_trades: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Exposes high-level tax calculation summary for dashboard & web server API.
    """
    if holdings is None:
        portfolio_path = Path(__file__).resolve().parent.parent / "config" / "portfolio.json"
        if portfolio_path.exists():
            try:
                with open(portfolio_path, "r") as f:
                    port_data = json.load(f)
                    holdings = port_data.get("holdings", [])
            except Exception as e:
                logger.debug(f"Could not load portfolio.json: {e}")
                holdings = []
        else:
            holdings = []

    if holdings is None:
        holdings = []

    if realized_trades is None:
        realized_trades = []

    calc = TaxCalculator()
    liability = calc.calculate_tax_liability(realized_trades=realized_trades)
    harvesting = calc.calculate_tax_loss_harvesting(
        holdings=holdings,
        realized_stcg_gains=liability["realized_stcg_gains_inr"],
        realized_ltcg_gains=liability["realized_ltcg_gains_inr"]
    )

    return {
        "tax_liability": liability,
        "tax_loss_harvesting": harvesting,
        "summary": {
            "total_tax_liability_inr": liability["total_tax_liability_inr"],
            "stcg_tax_inr": liability["stcg_tax_liability_inr"],
            "ltcg_tax_inr": liability["ltcg_tax_liability_inr"],
            "ltcg_exemption_used_inr": liability["ltcg_exemption_used_inr"],
            "ltcg_exemption_remaining_inr": max(0.0, DEFAULT_LTCG_EXEMPTION_LIMIT - liability["ltcg_exemption_used_inr"]),
            "potential_tax_savings_via_harvesting_inr": harvesting["estimated_total_tax_savings_inr"],
            "harvestable_candidates_count": harvesting["candidate_count"]
        }
    }


__all__ = [
    "TaxCalculator",
    "calculate_tax_summary",
    "identify_tax_loss_harvesting_candidates",
    "TaxAndCostConfig",
    "TransactionCostBreakdown",
    "TaxBreakdown",
    "NetReturnResult",
    "calculate_transaction_costs",
    "calculate_capital_gains_tax",
    "calculate_net_return",
    "calculate_expected_net_return",
]
