"""
engine/tax_calculator.py — Re-exports Net Return & Tax Calculation Engine (TASK-018).
"""

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

def identify_tax_loss_harvesting_candidates(
    holdings: list[dict],
    realized_stcg_gains_inr: float = 0.0,
    stcg_tax_rate: float = 0.20
) -> dict:
    """TASK-058: Automated Tax-Loss Harvesting Execution Manager."""
    harvest_candidates = []
    total_harvestable_loss = 0.0

    for h in holdings:
        qty = h.get("quantity", 0)
        cost = h.get("buy_price", h.get("avg_price", 0.0))
        current = h.get("current_price", h.get("close", cost))
        holding_days = h.get("holding_days", 30)

        unrealized_pnl = (current - cost) * qty
        if unrealized_pnl < 0 and holding_days <= 365:  # STCG loss candidate
            loss_inr = abs(unrealized_pnl)
            total_harvestable_loss += loss_inr
            tax_savings = loss_inr * stcg_tax_rate
            harvest_candidates.append({
                "symbol": h.get("symbol", "UNKNOWN"),
                "quantity": qty,
                "buy_price": round(cost, 2),
                "current_price": round(current, 2),
                "holding_days": holding_days,
                "unrealized_loss_inr": round(loss_inr, 2),
                "estimated_tax_savings_inr": round(tax_savings, 2),
                "recommendation": "HARVEST_STCG_LOSS"
            })

    offset_loss = min(total_harvestable_loss, realized_stcg_gains_inr)
    estimated_total_tax_savings = offset_loss * stcg_tax_rate

    return {
        "realized_stcg_gains_inr": round(realized_stcg_gains_inr, 2),
        "total_harvestable_loss_inr": round(total_harvestable_loss, 2),
        "offsetable_loss_inr": round(offset_loss, 2),
        "estimated_total_tax_savings_inr": round(estimated_total_tax_savings, 2),
        "candidate_count": len(harvest_candidates),
        "harvest_candidates": harvest_candidates
    }

__all__ = [
    "TaxAndCostConfig",
    "TransactionCostBreakdown",
    "TaxBreakdown",
    "NetReturnResult",
    "calculate_transaction_costs",
    "calculate_capital_gains_tax",
    "calculate_net_return",
    "calculate_expected_net_return",
    "identify_tax_loss_harvesting_candidates",
]
