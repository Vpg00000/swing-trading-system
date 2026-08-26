"""
Tax Lot Identification & Tax-Loss Harvesting Engine.

Implements:
1. Strict First-In-First-Out (FIFO) tax lot tracking per asset parcel.
2. Tax-Loss Harvesting auto-suggestions before March 31 fiscal year end.
3. Wash-Sale turnover detection (re-buying stock within 9 days of booking loss).

Fixes Problems: 131, 132, 137.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any


@dataclass
class TaxLot:
    lot_id: str
    symbol: str
    buy_date: str
    quantity: int
    buy_price: float
    remaining_qty: int


@dataclass
class TaxHarvestSuggestion:
    symbol: str
    unrealized_loss_inr: float
    holding_days: int
    tax_type: str             # STCL (Short-Term Capital Loss)
    potential_tax_saving: float
    recommendation: str


def match_fifo_tax_lots(buy_lots: List[TaxLot], sell_qty: int, sell_price: float) -> Dict[str, Any]:
    """
    Executes First-In-First-Out (FIFO) lot matching against open purchase parcels.
    (Fixes Problem 131)
    """
    remaining_to_sell = sell_qty
    matched_lots = []
    total_cost_basis = 0.0
    total_proceeds = 0.0
    stcg_gain = 0.0
    ltcg_gain = 0.0

    # Sort lots by buy date (FIFO)
    sorted_lots = sorted(buy_lots, key=lambda x: x.buy_date)

    for lot in sorted_lots:
        if remaining_to_sell <= 0:
            break
        if lot.remaining_qty <= 0:
            continue

        take_qty = min(lot.remaining_qty, remaining_to_sell)
        lot.remaining_qty -= take_qty
        remaining_to_sell -= take_qty

        cost = take_qty * lot.buy_price
        proceeds = take_qty * sell_price
        gain = proceeds - cost

        buy_dt = datetime.strptime(lot.buy_date, "%Y-%m-%d")
        holding_days = (datetime.now() - buy_dt).days

        if holding_days >= 365:
            ltcg_gain += gain
        else:
            stcg_gain += gain

        total_cost_basis += cost
        total_proceeds += proceeds
        matched_lots.append({
            "lot_id": lot.lot_id,
            "qty_matched": take_qty,
            "buy_price": lot.buy_price,
            "gain": round(gain, 2),
            "holding_days": holding_days
        })

    return {
        "matched_lots": matched_lots,
        "total_cost_basis": round(total_cost_basis, 2),
        "total_proceeds": round(total_proceeds, 2),
        "stcg_gain": round(stcg_gain, 2),
        "ltcg_gain": round(ltcg_gain, 2),
        "unmatched_qty": remaining_to_sell
    }


def find_tax_loss_harvest_opportunities(open_positions: List[Dict[str, Any]]) -> List[TaxHarvestSuggestion]:
    """
    Identifies unrealized short-term capital loss positions eligible for harvesting
    to offset STCG taxable gains before March 31.
    (Fixes Problem 132)
    """
    suggestions = []
    for pos in open_positions:
        current_price = float(pos.get("current_price", 0.0))
        buy_price = float(pos.get("buy_price", 0.0))
        qty = int(pos.get("quantity", 0))
        buy_date = pos.get("buy_date", "2026-01-01")

        if buy_price <= 0 or qty <= 0:
            continue

        unrealized = (current_price - buy_price) * qty
        if unrealized < -1000.0:  # Material loss > Rs 1,000
            buy_dt = datetime.strptime(buy_date, "%Y-%m-%d")
            days = (datetime.now() - buy_dt).days
            if days < 365:
                # STCL offsets STCG (taxed at 20%)
                saving = abs(unrealized) * 0.20
                suggestions.append(TaxHarvestSuggestion(
                    symbol=pos.get("symbol", ""),
                    unrealized_loss_inr=round(unrealized, 2),
                    holding_days=days,
                    tax_type="STCL",
                    potential_tax_saving=round(saving, 2),
                    recommendation=f"Sell position to harvest ₹{abs(unrealized):,.0f} loss and save ₹{saving:,.0f} STCG tax."
                ))

    return suggestions


def check_wash_sale_violation(symbol: str, recent_loss_trades: List[Dict[str, Any]], window_days: int = 9) -> bool:
    """
    Flags wash-sale risk if re-buying stock within 9 days of booking a loss.
    (Fixes Problem 137)
    """
    now = datetime.now()
    for trade in recent_loss_trades:
        if trade.get("symbol") == symbol and trade.get("realized_gain", 0.0) < 0:
            exit_dt = datetime.strptime(trade.get("exit_date", "2026-01-01"), "%Y-%m-%d")
            if (now - exit_dt).days <= window_days:
                return True
    return False


if __name__ == "__main__":
    print("Testing Tax Lots & Harvesting Engine...\n")
    lots = [
        TaxLot("L1", "RELIANCE.NS", "2025-10-01", 100, 2400.0, 100),
        TaxLot("L2", "RELIANCE.NS", "2026-02-01", 50, 2700.0, 50),
    ]
    res = match_fifo_tax_lots(lots, 120, 2850.0)
    print(f"  FIFO Match Result: STCG Gain = ₹{res['stcg_gain']}")
    harvest = find_tax_loss_harvest_opportunities([
        {"symbol": "WIPRO.NS", "buy_price": 500.0, "current_price": 420.0, "quantity": 200, "buy_date": "2026-01-15"}
    ])
    print(f"  Tax Loss Harvesting Opportunity: {harvest[0] if harvest else None}")
