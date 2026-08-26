"""
Tax-cost netting for the "SELL"/"switch" decision -- per DESIGN.md's "Tax and
cost discipline" section: STCG/LTCG classification, an STCG->LTCG countdown
(a few more days of holding can drop the rate from 20% to 12.5%), a
round-trip transaction cost estimate to net against any switch, and a
tax-loss-harvesting flag (real unrealized losses only, never an artificial
transaction). All figures are estimates to inform the user's own manual
filing decisions -- not tax advice.
"""

from dataclasses import dataclass
from datetime import date, datetime

STCG_RATE = 0.20  # equity STCG (<12mo), flat
LTCG_RATE = 0.125  # equity LTCG (>12mo), above the annual exemption
LTCG_EXEMPTION_INR = 125_000  # per financial year, DESIGN.md
LTCG_HOLDING_DAYS = 365
ROUND_TRIP_COST_PCT = 0.25  # midpoint of DESIGN.md's 0.15-0.35% estimate
LTCG_COUNTDOWN_WARN_DAYS = 15  # flag positions this close to crossing the 12mo mark


@dataclass
class HoldingTaxStatus:
    symbol: str
    buy_date: date
    days_held: int
    days_to_ltcg: int  # <=0 once already LTCG
    is_ltcg: bool
    unrealized_gain_inr: float
    unrealized_gain_pct: float


def classify_holding(holding: dict, current_price: float, as_of: date | None = None) -> HoldingTaxStatus:
    """
    Needs `buy_date` ("YYYY-MM-DD"), `buy_price`, `quantity` on the holding
    record (config/portfolio.json) -- these are the minimum facts required to
    know STCG vs LTCG and unrealized gain, and AMFI/NSE data alone can't
    supply them since they're specific to the user's own purchase.
    """
    as_of = as_of or date.today()
    buy_date = datetime.strptime(holding["buy_date"], "%Y-%m-%d").date()
    days_held = (as_of - buy_date).days
    qty = holding["quantity"]
    buy_price = holding["buy_price"]
    gain_inr = (current_price - buy_price) * qty
    gain_pct = (current_price / buy_price - 1) * 100 if buy_price else 0.0
    return HoldingTaxStatus(
        symbol=holding["symbol"],
        buy_date=buy_date,
        days_held=days_held,
        days_to_ltcg=LTCG_HOLDING_DAYS - days_held,
        is_ltcg=days_held >= LTCG_HOLDING_DAYS,
        unrealized_gain_inr=gain_inr,
        unrealized_gain_pct=gain_pct,
    )


def estimate_sale_tax_inr(status: HoldingTaxStatus, ltcg_exemption_used_inr: float = 0.0) -> float:
    """Estimated tax if sold today at the current unrealized gain. A loss owes no tax."""
    if status.unrealized_gain_inr <= 0:
        return 0.0
    if not status.is_ltcg:
        return status.unrealized_gain_inr * STCG_RATE
    remaining_exemption = max(0.0, LTCG_EXEMPTION_INR - ltcg_exemption_used_inr)
    taxable = max(0.0, status.unrealized_gain_inr - remaining_exemption)
    return taxable * LTCG_RATE


def round_trip_cost_inr(principal_inr: float) -> float:
    return principal_inr * (ROUND_TRIP_COST_PCT / 100)


def net_switch_hurdle_inr(status: HoldingTaxStatus, principal_inr: float,
                           ltcg_exemption_used_inr: float = 0.0) -> float:
    """
    Tax + round-trip transaction cost that an incremental-return switch must
    clear, per DESIGN.md: "Switch only if incremental expected net return >
    transaction cost + tax cost + uncertainty premium." Selling a real loss
    costs nothing in tax (may even help via harvesting), so the hurdle there
    is transaction cost only.
    """
    return estimate_sale_tax_inr(status, ltcg_exemption_used_inr) + round_trip_cost_inr(principal_inr)


def ltcg_countdown_flags(statuses: list[HoldingTaxStatus]) -> list[HoldingTaxStatus]:
    """Still-STCG positions crossing to LTCG within LTCG_COUNTDOWN_WARN_DAYS --
    holding a few more days drops the rate from 20% to 12.5%."""
    return [s for s in statuses if not s.is_ltcg and 0 < s.days_to_ltcg <= LTCG_COUNTDOWN_WARN_DAYS]


def tax_loss_harvest_candidates(statuses: list[HoldingTaxStatus]) -> list[HoldingTaxStatus]:
    """Real unrealized losses only -- no artificial/wash transactions, per DESIGN.md."""
    return [s for s in statuses if s.unrealized_gain_inr < 0]


if __name__ == "__main__":
    demo_holdings = [
        {"symbol": "DEMO1.NS", "buy_date": "2025-09-10", "buy_price": 1000.0, "quantity": 50},
        {"symbol": "DEMO2.NS", "buy_date": "2026-06-01", "buy_price": 500.0, "quantity": 100},
        {"symbol": "DEMO3.NS", "buy_date": "2025-11-01", "buy_price": 2000.0, "quantity": 25},
    ]
    demo_prices = {"DEMO1.NS": 1250.0, "DEMO2.NS": 420.0, "DEMO3.NS": 2100.0}

    statuses = [classify_holding(h, demo_prices[h["symbol"]]) for h in demo_holdings]
    for s in statuses:
        tax = estimate_sale_tax_inr(s)
        print(f"{s.symbol:<10} held {s.days_held:>4}d  "
              f"{'LTCG' if s.is_ltcg else 'STCG':<4}  "
              f"gain Rs{s.unrealized_gain_inr:>10,.0f} ({s.unrealized_gain_pct:+.1f}%)  "
              f"est. tax Rs{tax:>8,.0f}")

    print("\nSTCG->LTCG countdown (<=15 days out):")
    for s in ltcg_countdown_flags(statuses):
        print(f"  {s.symbol} — {s.days_to_ltcg} day(s) to LTCG")

    print("\nTax-loss harvest candidates:")
    for s in tax_loss_harvest_candidates(statuses):
        print(f"  {s.symbol} — unrealized loss Rs{s.unrealized_gain_inr:,.0f}")
