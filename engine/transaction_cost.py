"""
engine/transaction_cost.py — Transaction Cost Engine (Module 22).

Computes full Indian equity delivery transaction costs for a round-trip trade.
All rates as of FY2025 (NSE cash equity delivery segment).

Cost components (per leg):
  Brokerage:        Dhan = ₹0 for equity delivery (free)
  STT:              0.1% on buy + 0.1% on sell (delivery)
  Exchange charges: 0.00297% (NSE) per side
  Stamp duty:       0.015% on BUY only (not on sell)
  GST:              18% on (brokerage + exchange charges)
  SEBI charges:     ₹10 per crore of turnover
  Slippage:         Estimated based on stock liquidity tier

Total round-trip cost is expressed as % of trade value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Rate constants ─────────────────────────────────────────────────────────────
STT_RATE_DELIVERY = 0.001         # 0.1% both buy and sell
EXCHANGE_CHARGE_RATE = 0.0000297  # NSE: 0.00297% per side
STAMP_DUTY_RATE = 0.00015         # 0.015% on buy only
GST_RATE = 0.18                   # 18% on brokerage + exchange charges
SEBI_CHARGE_PER_CR = 10.0         # ₹10 per crore turnover

# Slippage by liquidity tier (% of trade value, one-way)
SLIPPAGE_BY_TIER = {
    "LARGE_CAP":  0.0005,    # 0.05% — Nifty 50 stocks, very tight spreads
    "MID_CAP":    0.0010,    # 0.10% — Nifty Midcap 150
    "SMALL_CAP":  0.0020,    # 0.20% — smaller names, wider spreads
    "MICRO_CAP":  0.0050,    # 0.50% — illiquid, avoid for large trades
}


def _classify_liquidity_tier(avg_daily_turnover_inr: Optional[float]) -> str:
    """Classify stock by average daily turnover (₹)."""
    if avg_daily_turnover_inr is None:
        return "MID_CAP"  # neutral assumption
    if avg_daily_turnover_inr >= 1e9:          # ≥ ₹100 Cr
        return "LARGE_CAP"
    elif avg_daily_turnover_inr >= 1e8:        # ≥ ₹10 Cr
        return "MID_CAP"
    elif avg_daily_turnover_inr >= 1e7:        # ≥ ₹1 Cr
        return "SMALL_CAP"
    else:
        return "MICRO_CAP"


@dataclass
class TransactionCost:
    symbol: str
    trade_value_inr: float          # ₹ value of the round-trip trade
    # Individual cost components (₹)
    stt_inr: float                  # STT buy + sell
    exchange_charges_inr: float     # NSE exchange charges buy + sell
    stamp_duty_inr: float           # stamp duty (buy only)
    gst_inr: float                  # GST on exchange charges
    sebi_charges_inr: float         # SEBI regulatory fee
    slippage_inr: float             # estimated market impact
    total_cost_inr: float           # all-in cost ₹
    # Rates as % of trade value
    total_cost_pct: float           # total cost as % of round-trip value
    # Breakdown for reporting
    liquidity_tier: str
    slippage_rate_pct: float        # one-way slippage used
    # Net P&L impact
    breakeven_move_pct: float       # stock must move this % just to break even


def compute_transaction_cost(
    symbol: str,
    trade_value_inr: float,                    # ₹ value of the position (quantity × price)
    avg_daily_turnover_inr: Optional[float] = None,
    brokerage_inr: float = 0.0,                # Dhan = ₹0 delivery; override for other brokers
) -> TransactionCost:
    """
    Compute the full round-trip transaction cost for one delivery trade.

    trade_value_inr: the position size in ₹ (e.g. ₹2,00,000 for 100 shares × ₹2000)
    """
    tv = trade_value_inr

    # ── STT (both sides) ──────────────────────────────────────────────────────
    stt = tv * STT_RATE_DELIVERY * 2   # 0.1% buy + 0.1% sell

    # ── Exchange charges (both sides) ─────────────────────────────────────────
    exchange = tv * EXCHANGE_CHARGE_RATE * 2

    # ── Stamp duty (buy side only) ────────────────────────────────────────────
    stamp = tv * STAMP_DUTY_RATE

    # ── GST on brokerage + exchange charges ───────────────────────────────────
    gst = (brokerage_inr + exchange) * GST_RATE

    # ── SEBI charges ──────────────────────────────────────────────────────────
    sebi = (tv * 2) / 1e7 * SEBI_CHARGE_PER_CR  # per crore turnover, both sides

    # ── Slippage ──────────────────────────────────────────────────────────────
    tier = _classify_liquidity_tier(avg_daily_turnover_inr)
    slip_rate = SLIPPAGE_BY_TIER[tier]
    slippage = tv * slip_rate * 2  # buy + sell side

    # ── Total ─────────────────────────────────────────────────────────────────
    total = brokerage_inr + stt + exchange + stamp + gst + sebi + slippage
    total_pct = (total / tv) * 100.0 if tv > 0 else 0.0

    # Breakeven: trade must return this % just to cover costs
    breakeven = total_pct  # simplified (one-way equivalent)

    return TransactionCost(
        symbol=symbol,
        trade_value_inr=round(tv, 2),
        stt_inr=round(stt, 2),
        exchange_charges_inr=round(exchange, 2),
        stamp_duty_inr=round(stamp, 2),
        gst_inr=round(gst, 2),
        sebi_charges_inr=round(sebi, 4),
        slippage_inr=round(slippage, 2),
        total_cost_inr=round(total, 2),
        total_cost_pct=round(total_pct, 4),
        liquidity_tier=tier,
        slippage_rate_pct=round(slip_rate * 100.0, 3),
        breakeven_move_pct=round(breakeven, 4),
    )


def net_expected_return(
    expected_upside_pct: float,
    expected_loss_pct: float,
    cost: TransactionCost,
) -> tuple[float, float]:
    """
    Adjust expected upside and loss for transaction costs.
    Returns (net_upside_pct, net_loss_pct).
    """
    half_cost = cost.total_cost_pct / 2.0  # split across win and loss scenarios
    net_up = expected_upside_pct - cost.total_cost_pct
    net_loss = expected_loss_pct + cost.total_cost_pct
    return round(net_up, 4), round(net_loss, 4)


if __name__ == "__main__":
    # Self-test: WELCORP position of ₹2,34,600 (100 shares × ₹2346)
    cost = compute_transaction_cost(
        symbol="WELCORP",
        trade_value_inr=234600.0,
        avg_daily_turnover_inr=2e9,   # large cap equivalent turnover
    )
    print("=== WELCORP — ₹2,34,600 delivery trade ===")
    print(f"  STT:              ₹{cost.stt_inr:.2f}")
    print(f"  Exchange charges: ₹{cost.exchange_charges_inr:.2f}")
    print(f"  Stamp duty:       ₹{cost.stamp_duty_inr:.2f}")
    print(f"  GST:              ₹{cost.gst_inr:.2f}")
    print(f"  SEBI charges:     ₹{cost.sebi_charges_inr:.4f}")
    print(f"  Slippage:         ₹{cost.slippage_inr:.2f} ({cost.slippage_rate_pct}% one-way, tier: {cost.liquidity_tier})")
    print(f"  ─────────────────────────────────────")
    print(f"  TOTAL COST:       ₹{cost.total_cost_inr:.2f}  ({cost.total_cost_pct:.3f}% of trade)")
    print(f"  Breakeven move:   {cost.breakeven_move_pct:.3f}%")
    print()

    # Test with a small-cap trade
    cost2 = compute_transaction_cost(
        symbol="SMALL_CO",
        trade_value_inr=100000.0,
        avg_daily_turnover_inr=5e6,   # small cap
    )
    print("=== SMALL_CO — ₹1,00,000 delivery trade (small cap) ===")
    print(f"  TOTAL COST:       ₹{cost2.total_cost_inr:.2f}  ({cost2.total_cost_pct:.3f}% of trade)")
    print(f"  Breakeven move:   {cost2.breakeven_move_pct:.3f}%")
    print(f"  Slippage tier:    {cost2.liquidity_tier}")
