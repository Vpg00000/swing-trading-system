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

__all__ = [
    "TaxAndCostConfig",
    "TransactionCostBreakdown",
    "TaxBreakdown",
    "NetReturnResult",
    "calculate_transaction_costs",
    "calculate_capital_gains_tax",
    "calculate_net_return",
    "calculate_expected_net_return",
]
