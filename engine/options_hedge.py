"""
Nifty Index Options Tail-Risk Hedging Engine (TASK-050).

Implements:
1. Black-Scholes European Options Pricing Model & Exact Options Greeks (Delta, Gamma, Vega, Theta).
2. Portfolio Delta & Beta Exposure Aggregator.
3. Tail-Risk Hedge Trigger Protocol (Triggers when portfolio long beta > 0.85 & India VIX > 18.0 / VIX spikes).
4. Optimal OTM Nifty Put Strike Selection (3-5% Out-of-the-Money).
5. Dynamic Lot Sizing & Contract Calculation capping max tail-risk hedge cost at 3% of portfolio value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
from scipy.stats import norm


def bs_option_price(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float = 0.065,  # RBI 364D T-bill risk-free rate ~ 6.5%
    volatility: float = 0.18,       # Volatility (e.g. India VIX / 100)
    option_type: str = "PUT"
) -> Dict[str, float]:
    """
    Computes Black-Scholes European option price and standard Greeks (Delta, Gamma, Vega, Theta).
    """
    if spot <= 0 or strike <= 0 or time_to_expiry_years <= 0 or volatility <= 0:
        # Edge case / boundary defaults
        price = max(0.0, strike - spot) if option_type.upper() == "PUT" else max(0.0, spot - strike)
        return {
            "price": round(price, 2),
            "delta": -0.5 if option_type.upper() == "PUT" else 0.5,
            "gamma": 0.0,
            "vega": 0.0,
            "theta": 0.0,
        }

    S = float(spot)
    K = float(strike)
    T = float(time_to_expiry_years)
    r = float(risk_free_rate)
    sigma = float(volatility)
    opt_type = option_type.upper()

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)
    cdf_d2 = norm.cdf(d2)

    cdf_neg_d1 = norm.cdf(-d1)
    cdf_neg_d2 = norm.cdf(-d2)

    if opt_type == "CALL":
        price = S * cdf_d1 - K * math.exp(-r * T) * cdf_d2
        delta = cdf_d1
        theta = (-S * pdf_d1 * sigma / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * cdf_d2) / 365.0
    else:  # PUT
        price = K * math.exp(-r * T) * cdf_neg_d2 - S * cdf_neg_d1
        delta = cdf_d1 - 1.0  # Or -cdf_neg_d1
        theta = (-S * pdf_d1 * sigma / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * cdf_neg_d2) / 365.0

    gamma = pdf_d1 / (S * sigma * math.sqrt(T))
    vega = (S * pdf_d1 * math.sqrt(T)) / 100.0  # Per 1% IV change

    return {
        "price": round(max(0.01, price), 2),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
    }


def calculate_tail_risk_hedge(
    portfolio_value_inr: float,
    portfolio_beta: float,
    nifty_spot: float,
    india_vix: float,
    days_to_expiry: int = 30,
    max_hedge_cost_pct: float = 0.03,   # Tail risk cost capped at 3% of portfolio
    beta_threshold: float = 0.85,
    vix_threshold: float = 18.0,
    nifty_lot_size: int = 25
) -> Dict[str, Any]:
    """
    Calculates required Nifty OTM Put-buying options hedge to neutralize portfolio tail-risk.
    
    Trigger Condition:
    Portfolio Long Beta > beta_threshold (0.85) AND India VIX >= vix_threshold (18.0).
    
    Returns strike price, number of contracts, total premium cost, delta neutrality proof, and risk metrics.
    """
    if portfolio_value_inr <= 0 or nifty_spot <= 0:
        raise ValueError("portfolio_value_inr and nifty_spot must be > 0")

    # 1. Trigger Check
    vix_spike = india_vix >= vix_threshold
    beta_high = portfolio_beta >= beta_threshold
    hedge_required = bool(beta_high and vix_spike)

    reasons: List[str] = []
    if not beta_high:
        reasons.append(f"Portfolio Beta ({portfolio_beta:.2f}) is below trigger threshold ({beta_threshold:.2f})")
    if not vix_spike:
        reasons.append(f"India VIX ({india_vix:.1f}) is below spike threshold ({vix_threshold:.1f})")

    # Target Hedge Dollar Delta = Portfolio Value * Beta
    portfolio_dollar_delta = portfolio_value_inr * portfolio_beta

    if not hedge_required:
        return {
            "hedge_required": False,
            "recommended_action": "NO_HEDGE_NEEDED",
            "trigger_reasons": reasons,
            "portfolio_value_inr": round(portfolio_value_inr, 2),
            "portfolio_beta": round(portfolio_beta, 2),
            "portfolio_dollar_delta": round(portfolio_dollar_delta, 2),
            "india_vix": round(india_vix, 2),
            "recommended_strike": None,
            "num_contracts": 0,
            "num_lots": 0,
            "total_hedge_cost": 0.0,
            "hedge_cost_pct": 0.0,
            "max_tail_loss_capped": True,
        }

    # 2. Strike Selection: 4% OTM Nifty Put option rounded to nearest 50 points
    otm_pct = 0.04
    raw_strike = nifty_spot * (1.0 - otm_pct)
    # Round to nearest 50 Nifty strike step
    strike = float(round(raw_strike / 50.0) * 50)

    # 3. Compute Option Pricing & Greeks
    T_years = max(1 / 365.0, days_to_expiry / 365.0)
    volatility = max(0.10, india_vix / 100.0)
    
    greeks = bs_option_price(
        spot=nifty_spot,
        strike=strike,
        time_to_expiry_years=T_years,
        risk_free_rate=0.065,
        volatility=volatility,
        option_type="PUT"
    )

    put_price = greeks["price"]
    put_delta = abs(greeks["delta"])  # Absolute put delta e.g. 0.25

    # 4. Compute Number of Contracts & Lots
    # Dollar delta protected per put lot = put_delta * nifty_spot * lot_size
    lot_dollar_delta = max(1.0, put_delta * nifty_spot * nifty_lot_size)
    raw_lots = portfolio_dollar_delta / lot_dollar_delta
    recommended_lots = max(1, int(math.ceil(raw_lots)))

    # Compute Total Premium Cost
    cost_per_lot = put_price * nifty_lot_size
    total_cost = recommended_lots * cost_per_lot
    max_budget_inr = portfolio_value_inr * max_hedge_cost_pct

    # Cap cost at max_hedge_cost_pct (e.g. 3%)
    if total_cost > max_budget_inr and recommended_lots > 1:
        recommended_lots = max(1, int(math.floor(max_budget_inr / cost_per_lot)))
        total_cost = recommended_lots * cost_per_lot
        reasons.append(f"Hedge lot size scaled down to cap premium cost at {max_hedge_cost_pct*100:.1f}% of portfolio")

    hedge_cost_pct = round((total_cost / portfolio_value_inr) * 100.0, 4)

    # Post-hedge residual portfolio delta
    hedged_dollar_delta = portfolio_dollar_delta - (recommended_lots * lot_dollar_delta)
    net_beta_after_hedge = round(max(0.0, hedged_dollar_delta / portfolio_value_inr), 2)

    return {
        "hedge_required": True,
        "recommended_action": "BUY_NIFTY_OTM_PUTS",
        "trigger_reasons": ["High portfolio Beta and VIX spike threshold breached"],
        "portfolio_value_inr": round(portfolio_value_inr, 2),
        "portfolio_beta": round(portfolio_beta, 2),
        "portfolio_dollar_delta": round(portfolio_dollar_delta, 2),
        "india_vix": round(india_vix, 2),
        "recommended_strike": strike,
        "days_to_expiry": days_to_expiry,
        "nifty_spot": round(nifty_spot, 2),
        "put_option_price": put_price,
        "num_lots": recommended_lots,
        "num_contracts": recommended_lots * nifty_lot_size,
        "lot_size": nifty_lot_size,
        "total_hedge_cost": round(total_cost, 2),
        "hedge_cost_pct": hedge_cost_pct,
        "max_tail_loss_capped": bool(hedge_cost_pct <= (max_hedge_cost_pct * 100.0)),
        "net_beta_after_hedge": net_beta_after_hedge,
        "greeks": greeks,
    }


class OptionsTailRiskHedgeEngine:
    """
    Object-oriented Nifty Index Options Tail-Risk Hedging Engine.
    """
    def __init__(
        self,
        max_hedge_cost_pct: float = 0.03,
        beta_threshold: float = 0.85,
        vix_threshold: float = 18.0,
        nifty_lot_size: int = 25
    ) -> None:
        self.max_hedge_cost_pct = max_hedge_cost_pct
        self.beta_threshold = beta_threshold
        self.vix_threshold = vix_threshold
        self.nifty_lot_size = nifty_lot_size

    def evaluate_portfolio_hedge(
        self,
        portfolio_value_inr: float,
        portfolio_beta: float,
        nifty_spot: float,
        india_vix: float,
        days_to_expiry: int = 30
    ) -> Dict[str, Any]:
        return calculate_tail_risk_hedge(
            portfolio_value_inr=portfolio_value_inr,
            portfolio_beta=portfolio_beta,
            nifty_spot=nifty_spot,
            india_vix=india_vix,
            days_to_expiry=days_to_expiry,
            max_hedge_cost_pct=self.max_hedge_cost_pct,
            beta_threshold=self.beta_threshold,
            vix_threshold=self.vix_threshold,
            nifty_lot_size=self.nifty_lot_size,
        )


if __name__ == "__main__":
    print("Testing Options Tail-Risk Hedging Engine...")
    hedge = calculate_tail_risk_hedge(
        portfolio_value_inr=10_000_000.0,
        portfolio_beta=1.15,
        nifty_spot=22000.0,
        india_vix=21.5,
        days_to_expiry=25
    )
    print(f"Options Hedge Recommendation: {hedge}")
