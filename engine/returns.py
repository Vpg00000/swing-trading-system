"""
engine/returns.py — Net Return & Tax Calculation Engine (TASK-018).

Calculates exact gross, transaction costs, tax (STCG / LTCG), and net return metrics for Indian equities.
Enforces zero hardcoded values by routing all fee and tax parameters through configurable `TaxAndCostConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class TaxAndCostConfig:
    """
    Configurable tax and cost rates for Indian equity delivery trading.
    All rates are expressed as decimals (e.g. 0.001 = 0.1%, 0.18 = 18%).
    Zero hardcoded values requirement: callers can pass custom instances or override defaults.
    """
    stt_delivery_buy_rate: float = 0.001       # 0.1% on buy
    stt_delivery_sell_rate: float = 0.001      # 0.1% on sell
    brokerage_per_order: float = 0.0           # ₹0 flat (Dhan default for delivery)
    brokerage_pct: float = 0.0                 # 0% (Dhan default for delivery)
    gst_rate: float = 0.18                     # 18% GST on (brokerage + exchange charges)
    stamp_duty_buy_rate: float = 0.00015       # 0.015% on buy only
    exchange_charge_rate: float = 0.0000297    # 0.00297% per side (NSE cash)
    sebi_charge_per_cr: float = 10.0           # ₹10 per crore turnover
    stcg_rate: float = 0.20                    # 20% STCG (<365 days)
    ltcg_rate: float = 0.125                   # 12.5% LTCG (>=365 days)
    ltcg_holding_days: int = 365               # 365 days for LTCG classification
    ltcg_exemption_annual_inr: float = 125_000.0  # ₹1,25,000 annual exemption limit


@dataclass
class TransactionCostBreakdown:
    symbol: str
    buy_value_inr: float
    sell_value_inr: float
    round_trip_turnover_inr: float
    stt_buy_inr: float
    stt_sell_inr: float
    total_stt_inr: float
    brokerage_inr: float
    exchange_charges_inr: float
    stamp_duty_inr: float
    gst_inr: float
    sebi_charges_inr: float
    slippage_inr: float
    total_costs_inr: float
    total_costs_pct: float                     # % of buy value


@dataclass
class TaxBreakdown:
    holding_days: int
    is_ltcg: bool
    gross_gain_inr: float
    deductible_expenses_inr: float
    taxable_gain_inr: float
    ltcg_exemption_applied_inr: float
    tax_type: str                              # "STCG", "LTCG", or "NONE"
    tax_rate: float
    tax_inr: float


@dataclass
class NetReturnResult:
    symbol: str
    quantity: float
    buy_price: float
    sell_price: float
    holding_days: int
    buy_value_inr: float
    sell_value_inr: float
    gross_profit_inr: float
    gross_return_pct: float
    transaction_costs: TransactionCostBreakdown
    tax: TaxBreakdown
    net_profit_inr: float
    net_return_pct: float
    breakeven_sell_price: float
    breakeven_move_pct: float
    gross_to_net_bridge: List[Dict[str, Any]] = field(default_factory=list)


def calculate_transaction_costs(
    symbol: str,
    buy_price: float,
    sell_price: float,
    quantity: float,
    config: Optional[TaxAndCostConfig] = None,
    slippage_rate_pct: float = 0.0,
) -> TransactionCostBreakdown:
    """
    Compute full round-trip transaction costs for an equity delivery trade.
    """
    cfg = config or TaxAndCostConfig()

    buy_val = max(0.0, buy_price * quantity)
    sell_val = max(0.0, sell_price * quantity)
    turnover = buy_val + sell_val

    # Brokerage
    brokerage_buy = cfg.brokerage_per_order + (buy_val * cfg.brokerage_pct)
    brokerage_sell = cfg.brokerage_per_order + (sell_val * cfg.brokerage_pct)
    brokerage_total = brokerage_buy + brokerage_sell

    # STT
    stt_buy = buy_val * cfg.stt_delivery_buy_rate
    stt_sell = sell_val * cfg.stt_delivery_sell_rate
    stt_total = stt_buy + stt_sell

    # Exchange charges
    exchange_charges = turnover * cfg.exchange_charge_rate

    # Stamp duty (buy side only)
    stamp_duty = buy_val * cfg.stamp_duty_buy_rate

    # GST on (brokerage + exchange charges)
    gst = (brokerage_total + exchange_charges) * cfg.gst_rate

    # SEBI charges
    sebi = (turnover / 10_000_000.0) * cfg.sebi_charge_per_cr

    # Slippage
    slippage = buy_val * (slippage_rate_pct / 100.0) * 2.0  # buy + sell side

    total_costs = brokerage_total + stt_total + exchange_charges + stamp_duty + gst + sebi + slippage
    total_costs_pct = (total_costs / buy_val * 100.0) if buy_val > 0 else 0.0

    return TransactionCostBreakdown(
        symbol=symbol,
        buy_value_inr=round(buy_val, 2),
        sell_value_inr=round(sell_val, 2),
        round_trip_turnover_inr=round(turnover, 2),
        stt_buy_inr=round(stt_buy, 2),
        stt_sell_inr=round(stt_sell, 2),
        total_stt_inr=round(stt_total, 2),
        brokerage_inr=round(brokerage_total, 2),
        exchange_charges_inr=round(exchange_charges, 2),
        stamp_duty_inr=round(stamp_duty, 2),
        gst_inr=round(gst, 2),
        sebi_charges_inr=round(sebi, 4),
        slippage_inr=round(slippage, 2),
        total_costs_inr=round(total_costs, 2),
        total_costs_pct=round(total_costs_pct, 4),
    )


def calculate_capital_gains_tax(
    gross_gain_inr: float,
    holding_days: int,
    deductible_expenses_inr: float = 0.0,
    config: Optional[TaxAndCostConfig] = None,
    ltcg_exemption_used_inr: float = 0.0,
) -> TaxBreakdown:
    """
    Calculate short-term (STCG) or long-term (LTCG) capital gains tax.
    Under Sec 48, transfer expenses (brokerage, stamp duty) reduce capital gains,
    while STT is non-deductible for tax purposes.
    If gross gain after deductible expenses <= 0, tax is zero.
    """
    cfg = config or TaxAndCostConfig()

    net_gain = max(0.0, gross_gain_inr - max(0.0, deductible_expenses_inr))

    if net_gain <= 0:
        return TaxBreakdown(
            holding_days=holding_days,
            is_ltcg=holding_days >= cfg.ltcg_holding_days,
            gross_gain_inr=round(gross_gain_inr, 2),
            deductible_expenses_inr=round(deductible_expenses_inr, 2),
            taxable_gain_inr=0.0,
            ltcg_exemption_applied_inr=0.0,
            tax_type="NONE",
            tax_rate=0.0,
            tax_inr=0.0,
        )

    is_ltcg = holding_days >= cfg.ltcg_holding_days

    if is_ltcg:
        tax_type = "LTCG"
        available_exemption = max(0.0, cfg.ltcg_exemption_annual_inr - max(0.0, ltcg_exemption_used_inr))
        exemption_applied = min(net_gain, available_exemption)
        taxable_gain = max(0.0, net_gain - exemption_applied)
        tax_rate = cfg.ltcg_rate
        tax_inr = taxable_gain * tax_rate
    else:
        tax_type = "STCG"
        exemption_applied = 0.0
        taxable_gain = net_gain
        tax_rate = cfg.stcg_rate
        tax_inr = taxable_gain * tax_rate

    return TaxBreakdown(
        holding_days=holding_days,
        is_ltcg=is_ltcg,
        gross_gain_inr=round(gross_gain_inr, 2),
        deductible_expenses_inr=round(deductible_expenses_inr, 2),
        taxable_gain_inr=round(taxable_gain, 2),
        ltcg_exemption_applied_inr=round(exemption_applied, 2),
        tax_type=tax_type,
        tax_rate=tax_rate,
        tax_inr=round(tax_inr, 2),
    )


def calculate_net_return(
    symbol: str,
    buy_price: float,
    sell_price: float,
    quantity: float,
    holding_days: int,
    config: Optional[TaxAndCostConfig] = None,
    slippage_rate_pct: float = 0.0,
    ltcg_exemption_used_inr: float = 0.0,
) -> NetReturnResult:
    """
    Calculate full gross-to-net return bridge for a position.
    """
    cfg = config or TaxAndCostConfig()

    costs = calculate_transaction_costs(
        symbol=symbol,
        buy_price=buy_price,
        sell_price=sell_price,
        quantity=quantity,
        config=cfg,
        slippage_rate_pct=slippage_rate_pct,
    )

    buy_val = buy_price * quantity
    sell_val = sell_price * quantity
    gross_profit = sell_val - buy_val
    gross_return_pct = (gross_profit / buy_val * 100.0) if buy_val > 0 else 0.0

    # Deductible transfer costs for tax (brokerage + stamp duty + exchange charges + GST)
    deductible_costs = costs.brokerage_inr + costs.stamp_duty_inr + costs.exchange_charges_inr + costs.gst_inr

    tax = calculate_capital_gains_tax(
        gross_gain_inr=gross_profit,
        holding_days=holding_days,
        deductible_expenses_inr=deductible_costs,
        config=cfg,
        ltcg_exemption_used_inr=ltcg_exemption_used_inr,
    )

    net_profit = gross_profit - costs.total_costs_inr - tax.tax_inr
    net_return_pct = (net_profit / buy_val * 100.0) if buy_val > 0 else 0.0

    # Breakeven calculation (sell price needed to yield ₹0 net profit)
    # At breakeven: Sell_Val - Buy_Val - Costs(Sell_Val) = 0 (assuming loss/zero profit owes no tax)
    # Costs ≈ buy_costs + sell_val * (stt_sell + exchange_charge + sebi_rate)
    sell_cost_rate = cfg.stt_delivery_sell_rate + cfg.exchange_charge_rate + (1.0 / 10_000_000.0 * cfg.sebi_charge_per_cr)
    buy_costs = costs.stt_buy_inr + costs.stamp_duty_inr + costs.brokerage_inr + costs.gst_inr + (buy_val * cfg.exchange_charge_rate)
    target_sell_val = (buy_val + buy_costs) / (1.0 - sell_cost_rate) if (1.0 - sell_cost_rate) > 0 else buy_val
    breakeven_sell_price = target_sell_val / quantity if quantity > 0 else buy_price
    breakeven_move_pct = ((breakeven_sell_price - buy_price) / buy_price * 100.0) if buy_price > 0 else 0.0

    # Build gross-to-net bridge
    bridge = [
        {"step": "Initial Investment", "amount_inr": round(buy_val, 2), "pct_of_buy": 100.0},
        {"step": "Gross Sale Proceeds", "amount_inr": round(sell_val, 2), "pct_of_buy": round((sell_val / buy_val * 100) if buy_val else 0, 2)},
        {"step": "Gross Profit", "amount_inr": round(gross_profit, 2), "pct_of_buy": round(gross_return_pct, 2)},
        {"step": "STT (Securities Transaction Tax)", "amount_inr": -costs.total_stt_inr, "pct_of_buy": round(-costs.total_stt_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "Brokerage", "amount_inr": -costs.brokerage_inr, "pct_of_buy": round(-costs.brokerage_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "Exchange Charges", "amount_inr": -costs.exchange_charges_inr, "pct_of_buy": round(-costs.exchange_charges_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "Stamp Duty", "amount_inr": -costs.stamp_duty_inr, "pct_of_buy": round(-costs.stamp_duty_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "GST", "amount_inr": -costs.gst_inr, "pct_of_buy": round(-costs.gst_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "SEBI Charges", "amount_inr": -costs.sebi_charges_inr, "pct_of_buy": round(-costs.sebi_charges_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "Slippage Impact", "amount_inr": -costs.slippage_inr, "pct_of_buy": round(-costs.slippage_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": f"Capital Gains Tax ({tax.tax_type} @ {tax.tax_rate * 100:.1f}%)", "amount_inr": -tax.tax_inr, "pct_of_buy": round(-tax.tax_inr / buy_val * 100 if buy_val else 0, 4)},
        {"step": "Net Realized Profit", "amount_inr": round(net_profit, 2), "pct_of_buy": round(net_return_pct, 4)},
    ]

    return NetReturnResult(
        symbol=symbol,
        quantity=quantity,
        buy_price=buy_price,
        sell_price=sell_price,
        holding_days=holding_days,
        buy_value_inr=round(buy_val, 2),
        sell_value_inr=round(sell_val, 2),
        gross_profit_inr=round(gross_profit, 2),
        gross_return_pct=round(gross_return_pct, 4),
        transaction_costs=costs,
        tax=tax,
        net_profit_inr=round(net_profit, 2),
        net_return_pct=round(net_return_pct, 4),
        breakeven_sell_price=round(breakeven_sell_price, 2),
        breakeven_move_pct=round(breakeven_move_pct, 4),
        gross_to_net_bridge=bridge,
    )


def calculate_expected_net_return(
    expected_upside_pct: float,
    expected_downside_pct: float,
    holding_days: int = 60,
    config: Optional[TaxAndCostConfig] = None,
    slippage_rate_pct: float = 0.05,
) -> Dict[str, float]:
    """
    Calculate estimated net upside % and net downside % after transaction costs and tax.
    Useful for screening/opportunity scoring before entry.
    """
    cfg = config or TaxAndCostConfig()

    # Round trip cost %
    round_trip_cost_pct = (
        (cfg.stt_delivery_buy_rate + cfg.stt_delivery_sell_rate) * 100.0 +
        (cfg.exchange_charge_rate * 2.0) * 100.0 +
        (cfg.stamp_duty_buy_rate) * 100.0 +
        (slippage_rate_pct * 2.0)
    )

    # Net upside after cost & tax
    gross_up = expected_upside_pct
    up_after_cost = max(0.0, gross_up - round_trip_cost_pct)
    tax_rate = cfg.ltcg_rate if holding_days >= cfg.ltcg_holding_days else cfg.stcg_rate
    net_up = up_after_cost * (1.0 - tax_rate)

    # Net downside after cost (losses accumulate costs, no tax relief assumed)
    gross_down = abs(expected_downside_pct)
    net_down = gross_down + round_trip_cost_pct

    return {
        "gross_upside_pct": round(gross_up, 4),
        "net_upside_pct": round(net_up, 4),
        "gross_downside_pct": round(gross_down, 4),
        "net_downside_pct": round(net_down, 4),
        "round_trip_cost_pct": round(round_trip_cost_pct, 4),
        "estimated_tax_rate": tax_rate,
    }
