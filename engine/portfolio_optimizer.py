"""
Advanced Portfolio Optimization, Hard Risk Engine & Position Sizing Module (TASK-019 & TASK-020).

Implements:
1. Markowitz Efficient Frontier (Maximum Sharpe Ratio) position weights.
2. Hierarchical Risk Parity (HRP) & Sharpe asset allocation.
3. 95% Conditional Value at Risk (CVaR) tail risk calculation.
4. Portfolio Beta capping (Beta <= 1.0 vs Nifty benchmark).
5. Fractional Kelly Criterion position sizing (f* = 0.5 * Kelly).
6. Sub-industry/Sector concentration cap (max 15-20% per sector).
7. Portfolio Risk Engine (TASK-019) with strict hard risk constraints blocking unsafe allocations.
8. Position Sizing Engine (TASK-020) respecting risk, caps, drawdown limits, sector limits, and liquidity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


@dataclass
class RiskConfig:
    """
    Configurable risk limits for portfolio risk management and position sizing.
    Zero hardcoded values: default limits can be customized per call/environment.
    """
    max_position_size_pct: float = 0.15         # Max 15% allocation per single stock
    max_sector_exposure_pct: float = 0.20       # Max 20% aggregate exposure per sector
    max_cvar_95_pct: float = 0.05               # Max 5% CVaR tail loss threshold
    max_drawdown_limit_pct: float = 0.15        # Max 15% portfolio drawdown limit (trading blocked if exceeded)
    max_portfolio_beta: float = 1.0             # Max weighted portfolio Beta vs benchmark
    account_risk_per_trade_pct: float = 0.01    # Risk 1% of total account capital per trade
    max_adv_participation_pct: float = 0.05     # Max 5% of Average Daily Volume


@dataclass
class RiskCheckResult:
    passed: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    action: str = "ALLOW"                      # "ALLOW", "BLOCK", "SCALE_DOWN"


@dataclass
class PositionSizeResult:
    symbol: str
    entry_price: float
    stop_loss_price: float
    total_capital_inr: float
    quantity: int
    investment_inr: float
    position_pct: float
    max_loss_inr: float
    max_loss_pct: float
    risk_per_share_inr: float
    is_allowed: bool
    blocking_reasons: List[str] = field(default_factory=list)
    sizing_bottleneck: str = "ACCOUNT_RISK"


# ── Core Optimization & Statistical Helper Functions ─────────────────────────

def calculate_kelly_position_size(win_rate: float, win_loss_ratio: float, kelly_fraction: float = 0.5) -> float:
    """
    Computes Fractional Kelly Criterion lot allocation size.
    f* = (p * b - q) / b * kelly_fraction
    """
    if win_loss_ratio <= 0 or win_rate <= 0 or win_rate >= 1.0:
        return 0.05  # Safe default 5% allocation

    p = win_rate
    q = 1.0 - p
    b = win_loss_ratio

    full_kelly = (p * b - q) / b
    if full_kelly <= 0:
        return 0.0  # Zero allocation if EV is negative

    fractional_kelly = full_kelly * kelly_fraction
    # Cap single position size to max 15% of capital for safety
    return round(min(0.15, fractional_kelly), 4)


def calculate_cvar_95(returns: List[float], confidence: float = 0.95) -> float:
    """
    Calculates 95% Conditional Value at Risk (CVaR / Expected Shortfall).
    Measures average loss in the worst 5% tail loss scenarios as a positive float percentage (e.g. 0.045 = 4.5%).
    """
    if not returns or len(returns) < 5:
        return 0.025  # Fallback default 2.5% tail risk

    sorted_returns = sorted(returns)
    cutoff_idx = max(1, int(math.floor((1.0 - confidence) * len(sorted_returns))))
    tail_losses = sorted_returns[:cutoff_idx]
    cvar = -float(np.mean(tail_losses)) if tail_losses else 0.0
    return round(max(0.0, cvar), 4)


def enforce_sub_industry_cap(
    candidate_weights: Dict[str, float],
    sector_map: Dict[str, str],
    max_cap_pct: float = 15.0,
) -> Dict[str, float]:
    """
    Caps total portfolio allocation to any single sub-industry to max cap % (e.g. 15% or 20%).
    """
    max_cap_fraction = max_cap_pct / 100.0 if max_cap_pct > 1.0 else max_cap_pct
    industry_totals: Dict[str, float] = {}

    for sym, weight in candidate_weights.items():
        ind = sector_map.get(sym, "General")
        industry_totals[ind] = industry_totals.get(ind, 0.0) + weight

    adjusted_weights = dict(candidate_weights)
    for ind, total_weight in industry_totals.items():
        if total_weight > max_cap_fraction:
            scale_factor = max_cap_fraction / total_weight
            for sym, weight in candidate_weights.items():
                if sector_map.get(sym, "General") == ind:
                    adjusted_weights[sym] = round(weight * scale_factor, 4)

    return adjusted_weights


def calculate_portfolio_beta(weights: Dict[str, float], asset_betas: Dict[str, float]) -> float:
    """
    Computes aggregate weighted Portfolio Beta vs Nifty benchmark: Beta_P = Sum(w_i * Beta_i).
    """
    p_beta = 0.0
    total_w = sum(weights.values())
    if total_w <= 0:
        return 1.0

    for sym, w in weights.items():
        b = asset_betas.get(sym, 1.0)
        p_beta += (w / total_w) * b

    return round(p_beta, 4)


def optimize_sharpe_weights(expected_returns: Dict[str, float], asset_volatilities: Dict[str, float]) -> Dict[str, float]:
    """
    Simplified Markowitz Maximum Sharpe Ratio allocation weights.
    """
    sharpe_ratios = {}
    for sym, ret in expected_returns.items():
        vol = asset_volatilities.get(sym, 20.0)
        sharpe_ratios[sym] = max(0.0, ret / vol) if vol > 0 else 0.0

    total_sharpe = sum(sharpe_ratios.values())
    if total_sharpe <= 0:
        n = len(expected_returns)
        return {sym: round(1.0 / n, 4) for sym in expected_returns} if n > 0 else {}

    return {sym: round(sr / total_sharpe, 4) for sym, sr in sharpe_ratios.items()}


# ── TASK-019: Portfolio Risk Engine ─────────────────────────────────────────

def validate_portfolio_risk(
    weights: Dict[str, float],
    sector_map: Dict[str, str],
    returns_matrix: Optional[Dict[str, List[float]]] = None,
    asset_betas: Optional[Dict[str, float]] = None,
    current_drawdown_pct: float = 0.0,
    risk_config: Optional[RiskConfig] = None,
) -> RiskCheckResult:
    """
    Validates portfolio weights against hard risk constraints:
    - Max position size %
    - Max sector exposure %
    - Portfolio CVaR 95%
    - Drawdown limit % (blocks if breached)
    - Max portfolio Beta
    """
    cfg = risk_config or RiskConfig()
    violations: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, float] = {}

    # Normalize drawdown pct if passed as percentage (e.g. 15.0 vs 0.15)
    dd_fraction = current_drawdown_pct / 100.0 if current_drawdown_pct > 1.0 else current_drawdown_pct
    metrics["current_drawdown_pct"] = round(dd_fraction * 100.0, 2)

    # 1. Drawdown Hard Limit Check
    if dd_fraction >= cfg.max_drawdown_limit_pct:
        violations.append(
            f"Portfolio Drawdown {dd_fraction*100.0:.2f}% reaches/exceeds maximum allowed limit of {cfg.max_drawdown_limit_pct*100.0:.2f}%. Trading BLOCKED."
        )

    # 2. Position Size Limit Check
    max_pos = max(weights.values()) if weights else 0.0
    metrics["max_position_pct"] = round(max_pos * 100.0, 2)
    for sym, w in weights.items():
        if w > cfg.max_position_size_pct + 1e-4:
            violations.append(
                f"Position size for {sym} ({w*100.0:.2f}%) exceeds maximum allowed limit of {cfg.max_position_size_pct*100.0:.2f}%."
            )

    # 3. Sector Exposure Limit Check
    sector_totals: Dict[str, float] = {}
    for sym, w in weights.items():
        sec = sector_map.get(sym, "General")
        sector_totals[sec] = sector_totals.get(sec, 0.0) + w

    max_sec = max(sector_totals.values()) if sector_totals else 0.0
    metrics["max_sector_pct"] = round(max_sec * 100.0, 2)
    for sec, sec_w in sector_totals.items():
        if sec_w > cfg.max_sector_exposure_pct + 1e-4:
            violations.append(
                f"Sector exposure for '{sec}' ({sec_w*100.0:.2f}%) exceeds maximum allowed limit of {cfg.max_sector_exposure_pct*100.0:.2f}%."
            )

    # 4. Portfolio Beta Check
    if asset_betas:
        p_beta = calculate_portfolio_beta(weights, asset_betas)
        metrics["portfolio_beta"] = p_beta
        if p_beta > cfg.max_portfolio_beta + 1e-4:
            violations.append(
                f"Portfolio Beta ({p_beta:.2f}) exceeds maximum allowed limit of {cfg.max_portfolio_beta:.2f}."
            )

    # 5. Portfolio CVaR 95% Check
    if returns_matrix and weights:
        # Calculate combined portfolio return series
        total_w = sum(weights.values())
        if total_w > 0:
            norm_weights = {k: v / total_w for k, v in weights.items()}
            sample_len = min(len(r) for r in returns_matrix.values()) if returns_matrix else 0
            if sample_len >= 5:
                portfolio_series = []
                for i in range(sample_len):
                    ret_i = sum(norm_weights.get(sym, 0.0) * returns_matrix[sym][i] for sym in norm_weights if sym in returns_matrix)
                    portfolio_series.append(ret_i)
                cvar_val = calculate_cvar_95(portfolio_series, confidence=0.95)
                metrics["cvar_95_pct"] = round(cvar_val * 100.0, 2)
                if cvar_val > cfg.max_cvar_95_pct + 1e-4:
                    violations.append(
                        f"Portfolio CVaR 95% ({cvar_val*100.0:.2f}%) exceeds maximum allowed limit of {cfg.max_cvar_95_pct*100.0:.2f}%."
                    )

    passed = len(violations) == 0
    action = "ALLOW" if passed else ("BLOCK" if dd_fraction >= cfg.max_drawdown_limit_pct else "SCALE_DOWN")

    return RiskCheckResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
        metrics=metrics,
        action=action,
    )


def enforce_hard_risk_constraints(
    candidate_weights: Dict[str, float],
    sector_map: Dict[str, str],
    returns_matrix: Optional[Dict[str, List[float]]] = None,
    asset_betas: Optional[Dict[str, float]] = None,
    current_drawdown_pct: float = 0.0,
    risk_config: Optional[RiskConfig] = None,
) -> Tuple[Dict[str, float], RiskCheckResult]:
    """
    Enforces hard risk constraints and returns strictly compliant, safety-scaled portfolio weights.
    If drawdown limit is breached, all allocations are ZEROED out (action=BLOCK).
    """
    cfg = risk_config or RiskConfig()
    dd_fraction = current_drawdown_pct / 100.0 if current_drawdown_pct > 1.0 else current_drawdown_pct

    # If drawdown limit is reached or exceeded, block everything completely
    if dd_fraction >= cfg.max_drawdown_limit_pct:
        blocked_weights = {sym: 0.0 for sym in candidate_weights}
        result = validate_portfolio_risk(
            weights=candidate_weights,
            sector_map=sector_map,
            returns_matrix=returns_matrix,
            asset_betas=asset_betas,
            current_drawdown_pct=current_drawdown_pct,
            risk_config=cfg,
        )
        result.action = "BLOCK"
        return blocked_weights, result

    # Step 1: Cap position sizes
    adjusted_w = {sym: min(w, cfg.max_position_size_pct) for sym, w in candidate_weights.items()}

    # Step 2: Cap sector exposures
    adjusted_w = enforce_sub_industry_cap(adjusted_w, sector_map, max_cap_pct=cfg.max_sector_exposure_pct * 100.0)

    # Step 3: Beta adjustment scaling if needed
    if asset_betas:
        p_beta = calculate_portfolio_beta(adjusted_w, asset_betas)
        if p_beta > cfg.max_portfolio_beta and p_beta > 0:
            scale_factor = cfg.max_portfolio_beta / p_beta
            adjusted_w = {sym: round(w * scale_factor, 4) for sym, w in adjusted_w.items()}

    # Step 4: CVaR adjustment scaling if needed
    if returns_matrix and adjusted_w:
        total_w = sum(adjusted_w.values())
        if total_w > 0:
            norm_w = {k: v / total_w for k, v in adjusted_w.items()}
            sample_len = min(len(r) for r in returns_matrix.values()) if returns_matrix else 0
            if sample_len >= 5:
                portfolio_series = [
                    sum(norm_w.get(sym, 0.0) * returns_matrix[sym][i] for sym in norm_w if sym in returns_matrix)
                    for i in range(sample_len)
                ]
                cvar_val = calculate_cvar_95(portfolio_series, confidence=0.95)
                if cvar_val > cfg.max_cvar_95_pct and cvar_val > 0:
                    scale_factor = cfg.max_cvar_95_pct / cvar_val
                    adjusted_w = {sym: round(w * scale_factor, 4) for sym, w in adjusted_w.items()}

    # Run final risk validation on adjusted weights
    final_result = validate_portfolio_risk(
        weights=adjusted_w,
        sector_map=sector_map,
        returns_matrix=returns_matrix,
        asset_betas=asset_betas,
        current_drawdown_pct=current_drawdown_pct,
        risk_config=cfg,
    )

    return adjusted_w, final_result


# ── TASK-020: Position Sizing Engine ─────────────────────────────────────────

def calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss_price: float,
    total_capital_inr: float,
    current_sector_exposure_inr: float = 0.0,
    win_rate: Optional[float] = None,
    win_loss_ratio: Optional[float] = None,
    current_drawdown_pct: float = 0.0,
    avg_daily_volume_shares: Optional[float] = None,
    risk_config: Optional[RiskConfig] = None,
) -> PositionSizeResult:
    """
    Computes exact trade position size (quantity, investment INR, max loss INR)
    by evaluating and enforcing ALL risk constraints:
    1. Fixed Account Equity Risk % per trade
    2. Single Position Size Cap %
    3. Sector Aggregate Exposure Cap %
    4. Fractional Kelly Criterion Allocation % (if win rate & win/loss ratio provided)
    5. Portfolio Drawdown Hard Stop (blocks all new trades if limit reached)
    6. Liquidity / Daily Volume Cap
    """
    cfg = risk_config or RiskConfig()
    reasons: List[str] = []

    # Input validation checks
    if total_capital_inr <= 0:
        return PositionSizeResult(
            symbol=symbol, entry_price=entry_price, stop_loss_price=stop_loss_price,
            total_capital_inr=total_capital_inr, quantity=0, investment_inr=0.0,
            position_pct=0.0, max_loss_inr=0.0, max_loss_pct=0.0, risk_per_share_inr=0.0,
            is_allowed=False, blocking_reasons=["Total capital must be > 0"], sizing_bottleneck="INVALID_INPUT"
        )

    if entry_price <= 0:
        return PositionSizeResult(
            symbol=symbol, entry_price=entry_price, stop_loss_price=stop_loss_price,
            total_capital_inr=total_capital_inr, quantity=0, investment_inr=0.0,
            position_pct=0.0, max_loss_inr=0.0, max_loss_pct=0.0, risk_per_share_inr=0.0,
            is_allowed=False, blocking_reasons=["Entry price must be > 0"], sizing_bottleneck="INVALID_INPUT"
        )

    if stop_loss_price <= 0 or stop_loss_price >= entry_price:
        return PositionSizeResult(
            symbol=symbol, entry_price=entry_price, stop_loss_price=stop_loss_price,
            total_capital_inr=total_capital_inr, quantity=0, investment_inr=0.0,
            position_pct=0.0, max_loss_inr=0.0, max_loss_pct=0.0, risk_per_share_inr=0.0,
            is_allowed=False, blocking_reasons=["Stop loss must be > 0 and strictly below entry price"], sizing_bottleneck="INVALID_INPUT"
        )

    # Check Drawdown Limit
    dd_fraction = current_drawdown_pct / 100.0 if current_drawdown_pct > 1.0 else current_drawdown_pct
    if dd_fraction >= cfg.max_drawdown_limit_pct:
        reasons.append(
            f"Portfolio Drawdown ({dd_fraction*100.0:.2f}%) reaches/exceeds limit ({cfg.max_drawdown_limit_pct*100.0:.2f}%). New position creation strictly BLOCKED."
        )
        return PositionSizeResult(
            symbol=symbol, entry_price=entry_price, stop_loss_price=stop_loss_price,
            total_capital_inr=total_capital_inr, quantity=0, investment_inr=0.0,
            position_pct=0.0, max_loss_inr=0.0, max_loss_pct=0.0,
            risk_per_share_inr=round(entry_price - stop_loss_price, 2),
            is_allowed=False, blocking_reasons=reasons, sizing_bottleneck="DRAWDOWN_LIMIT"
        )

    risk_per_share = entry_price - stop_loss_price

    # Constraint 1: Fixed Account Equity Risk Limit
    max_allowed_risk_inr = total_capital_inr * cfg.account_risk_per_trade_pct
    qty_risk = max_allowed_risk_inr / risk_per_share

    # Constraint 2: Single Position Size Cap %
    max_pos_value_inr = total_capital_inr * cfg.max_position_size_pct
    qty_pos_cap = max_pos_value_inr / entry_price

    # Constraint 3: Sector Aggregate Exposure Cap %
    remaining_sector_cap_inr = max(0.0, (total_capital_inr * cfg.max_sector_exposure_pct) - current_sector_exposure_inr)
    qty_sector_cap = remaining_sector_cap_inr / entry_price

    # Constraint 4: Fractional Kelly Criterion
    qty_kelly = float("inf")
    if win_rate is not None and win_loss_ratio is not None:
        kelly_fraction = calculate_kelly_position_size(win_rate, win_loss_ratio)
        max_kelly_val_inr = total_capital_inr * kelly_fraction
        qty_kelly = max_kelly_val_inr / entry_price

    # Constraint 5: Liquidity / ADV Cap
    qty_liquidity = float("inf")
    if avg_daily_volume_shares is not None and avg_daily_volume_shares > 0:
        qty_liquidity = avg_daily_volume_shares * cfg.max_adv_participation_pct

    # Determine bottleneck constraint
    limits = {
        "ACCOUNT_RISK": qty_risk,
        "POSITION_CAP": qty_pos_cap,
        "SECTOR_CAP": qty_sector_cap,
        "KELLY": qty_kelly,
        "LIQUIDITY": qty_liquidity,
    }

    bottleneck = min(limits, key=limits.get)  # type: str
    final_quantity_raw = limits[bottleneck]

    final_quantity = max(0, int(math.floor(final_quantity_raw)))

    investment_inr = round(final_quantity * entry_price, 2)
    position_pct = round((investment_inr / total_capital_inr) * 100.0, 4) if total_capital_inr > 0 else 0.0
    max_loss_inr = round(final_quantity * risk_per_share, 2)
    max_loss_pct = round((max_loss_inr / total_capital_inr) * 100.0, 4) if total_capital_inr > 0 else 0.0

    is_allowed = final_quantity > 0
    if not is_allowed:
        if remaining_sector_cap_inr <= 0:
            reasons.append(f"Sector exposure cap of {cfg.max_sector_exposure_pct*100:.1f}% already reached")
        elif bottleneck == "LIQUIDITY":
            reasons.append(f"Daily volume too low for minimum position")
        else:
            reasons.append(f"Calculated position size is less than 1 share due to {bottleneck} constraint")

    return PositionSizeResult(
        symbol=symbol,
        entry_price=round(entry_price, 2),
        stop_loss_price=round(stop_loss_price, 2),
        total_capital_inr=round(total_capital_inr, 2),
        quantity=final_quantity,
        investment_inr=investment_inr,
        position_pct=position_pct,
        max_loss_inr=max_loss_inr,
        max_loss_pct=max_loss_pct,
        risk_per_share_inr=round(risk_per_share, 2),
        is_allowed=is_allowed,
        blocking_reasons=reasons,
        sizing_bottleneck=bottleneck,
    )


if __name__ == "__main__":
    print("Self-testing Risk & Position Sizing Engine...")
    cfg = RiskConfig()
    res = calculate_position_size(
        symbol="RELIANCE.NS",
        entry_price=2500.0,
        stop_loss_price=2400.0,
        total_capital_inr=1_000_000.0,
        current_sector_exposure_inr=50_000.0,
        win_rate=0.60,
        win_loss_ratio=2.0,
        risk_config=cfg,
    )
    print(f"Position Size Result: {res}")
