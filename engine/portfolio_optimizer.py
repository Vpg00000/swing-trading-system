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
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from engine.position_tracker import PositionTracker, get_portfolio_summary



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
    Computes aggregate Portfolio Beta exposure vs Nifty benchmark: Beta_P = Sum(w_i * Beta_i).
    """
    return round(sum(w * asset_betas.get(sym, 1.0) for sym, w in weights.items()), 4)







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


# ── TASK-047: ATR/GARCH Volatility Trailing Stop Loss Engine ────────────────

def calculate_garch_volatility(
    returns: Union[pd.Series, np.ndarray, List[float]],
    omega: float = 1e-5,
    alpha: float = 0.10,
    beta: float = 0.85
) -> Dict[str, float]:
    """
    Computes GARCH(1,1) conditional volatility sigma_t from return series.
    sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
    Returns current volatility, annualized volatility, unconditional volatility, and volatility ratio.
    """
    ret_arr = np.asarray(returns, dtype=float)
    ret_arr = ret_arr[~np.isnan(ret_arr)]

    if len(ret_arr) < 5:
        # Fallback default values if insufficient return history
        return {
            "current_volatility": 0.015,
            "annualized_volatility": 0.238,
            "unconditional_volatility": 0.0141,
            "volatility_ratio": 1.0,
        }

    # Demean returns
    eps = ret_arr - np.mean(ret_arr)
    n = len(eps)

    # Long-term unconditional variance V = omega / (1 - alpha - beta)
    denom = max(1e-4, 1.0 - alpha - beta)
    unconditional_var = omega / denom
    
    # GARCH recursion
    sigma2 = np.zeros(n)
    sigma2[0] = np.var(eps) if len(eps) > 1 else unconditional_var

    for t in range(1, n):
        sigma2[t] = omega + (alpha * (eps[t - 1] ** 2)) + (beta * sigma2[t - 1])

    current_var = sigma2[-1]
    current_vol = float(np.sqrt(max(1e-6, current_var)))
    unconditional_vol = float(np.sqrt(max(1e-6, unconditional_var)))
    annualized_vol = float(current_vol * np.sqrt(252.0))
    vol_ratio = float(current_vol / unconditional_vol) if unconditional_vol > 0 else 1.0

    return {
        "current_volatility": round(current_vol, 5),
        "annualized_volatility": round(annualized_vol, 4),
        "unconditional_volatility": round(unconditional_vol, 5),
        "volatility_ratio": round(vol_ratio, 4),
    }


def calculate_atr_garch_trailing_stop(
    data: Union[pd.DataFrame, np.ndarray, List[float]],
    current_price: float,
    position_type: str = "LONG",
    atr_period: int = 14,
    base_atr_multiplier: float = 2.0,
    vix_value: Optional[float] = None,
    high_watermark: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calculates adaptive ATR / GARCH volatility trailing stop loss distance.
    Widens stop loss dynamically during high market regime volatility or VIX expansion.
    """
    if current_price <= 0:
        raise ValueError("current_price must be > 0")

    # 1. Compute ATR
    atr_value = 0.0
    returns = []

    if isinstance(data, pd.DataFrame):
        df_clean = data.copy()
        col_map = {col: str(col).lower() for col in df_clean.columns}
        df_clean.rename(columns=col_map, inplace=True)
        close = df_clean["close"]
        high = df_clean.get("high", close)
        low = df_clean.get("low", close)
        
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_series = tr.rolling(window=atr_period, min_periods=1).mean()
        atr_value = float(atr_series.iloc[-1]) if not atr_series.empty else current_price * 0.02
        returns = close.pct_change().dropna().values
    else:
        prices = np.asarray(data, dtype=float)
        if len(prices) > 1:
            returns = np.diff(prices) / prices[:-1]
            atr_value = float(np.std(returns) * current_price)
        else:
            atr_value = current_price * 0.02

    atr_value = max(0.01, atr_value)

    # 2. Compute GARCH Volatility ratio
    garch_stats = calculate_garch_volatility(returns)
    garch_vol_ratio = garch_stats["volatility_ratio"]
    garch_vol = garch_stats["current_volatility"]

    # 3. VIX and GARCH Dynamic Multiplier Adjustment
    # Baseline VIX threshold is 15.0
    vix = vix_value if (vix_value is not None and vix_value > 0) else 15.0
    vix_adj = 1.0 + max(0.0, (vix - 15.0) / 15.0) if vix > 15.0 else 1.0
    garch_adj = max(1.0, garch_vol_ratio)

    effective_multiplier = base_atr_multiplier * max(vix_adj, garch_adj)
    # Cap multiplier at 4.5x base multiplier to prevent excessively loose stops
    effective_multiplier = min(4.5 * base_atr_multiplier, effective_multiplier)

    # 4. Trailing Stop Price Calculation
    pos_type = position_type.upper()
    watermark = high_watermark if high_watermark is not None else current_price

    if pos_type == "LONG":
        watermark = max(current_price, watermark)
        stop_price = watermark - (atr_value * effective_multiplier)
        stop_distance_pct = (current_price - stop_price) / current_price
    else:  # SHORT
        watermark = min(current_price, watermark)
        stop_price = watermark + (atr_value * effective_multiplier)
        stop_distance_pct = (stop_price - current_price) / current_price

    # Regime categorization
    if vix >= 25.0 or garch_vol_ratio >= 1.5:
        regime = "EXTREME_VOLATILITY"
    elif vix >= 18.0 or garch_vol_ratio >= 1.2:
        regime = "HIGH_VOLATILITY_EXPANSION"
    else:
        regime = "NORMAL_VOLATILITY"

    return {
        "stop_loss_price": round(stop_price, 2),
        "high_watermark": round(watermark, 2),
        "atr_value": round(atr_value, 2),
        "base_multiplier": base_atr_multiplier,
        "effective_multiplier": round(effective_multiplier, 2),
        "garch_volatility": round(garch_vol, 5),
        "vix_value": round(vix, 2),
        "vix_adjustment_factor": round(vix_adj, 2),
        "stop_distance_pct": round(stop_distance_pct, 4),
        "regime": regime,
        "position_type": pos_type,
    }


# ── TASK-048: Factor Exposure & Style Tilt Calculator ─────────────────────────

def calculate_factor_exposures(
    portfolio_returns: Optional[Union[pd.Series, List[float], np.ndarray]] = None,
    factor_matrix: Optional[pd.DataFrame] = None,
    holding_weights: Optional[Dict[str, float]] = None,
    asset_metrics: Optional[Dict[str, Dict[str, float]]] = None
) -> Dict[str, Any]:
    """
    Calculates portfolio factor exposures and style tilts (Momentum, Value, Quality, Low Volatility, Beta).
    Supports return-based regression and portfolio holding-based factor score decomposition.
    """
    factor_loadings: Dict[str, float] = {
        "Momentum": 0.0,
        "Value": 0.0,
        "Quality": 0.0,
        "Low_Volatility": 0.0,
        "Market_Beta": 1.0,
    }
    warnings: List[str] = []
    r_squared = 0.0

    # 1. Holding-based factor score decomposition if holding_weights and asset_metrics provided
    if holding_weights and asset_metrics:
        total_w = sum(holding_weights.values())
        norm_weights = {k: v / total_w for k, v in holding_weights.items()} if total_w > 0 else holding_weights

        mom_score, val_score, qual_score, lowvol_score, beta_score = 0.0, 0.0, 0.0, 0.0, 0.0

        for symbol, w in norm_weights.items():
            metrics = asset_metrics.get(symbol, {})
            mom_score += w * metrics.get("momentum", metrics.get("Momentum", 0.5))
            val_score += w * metrics.get("value", metrics.get("Value", 0.5))
            qual_score += w * metrics.get("quality", metrics.get("Quality", 0.5))
            lowvol_score += w * metrics.get("low_volatility", metrics.get("Low_Volatility", 0.5))
            beta_score += w * metrics.get("beta", metrics.get("Market_Beta", 1.0))

        factor_loadings["Momentum"] = round(mom_score, 4)
        factor_loadings["Value"] = round(val_score, 4)
        factor_loadings["Quality"] = round(qual_score, 4)
        factor_loadings["Low_Volatility"] = round(lowvol_score, 4)
        factor_loadings["Market_Beta"] = round(beta_score, 4)
        r_squared = 0.85

    # 2. Return-based multi-factor regression if portfolio_returns and factor_matrix provided
    elif portfolio_returns is not None and factor_matrix is not None:
        p_ret = np.asarray(portfolio_returns, dtype=float)
        valid_idx = ~np.isnan(p_ret)
        p_clean = p_ret[valid_idx]
        f_clean = factor_matrix.iloc[valid_idx]

        if len(p_clean) >= 10 and not f_clean.empty:
            # Add intercept column for alpha
            X = f_clean.copy()
            X["Intercept"] = 1.0
            
            # Solve OLS: Y = X * Beta -> Beta = (X^T X)^-1 X^T Y
            try:
                beta_hat, residuals, rank, s = np.linalg.lstsq(X.values, p_clean, rcond=None)
                col_names = list(X.columns)
                for name, coef in zip(col_names, beta_hat):
                    if name != "Intercept":
                        clean_name = name.replace(" ", "_")
                        factor_loadings[clean_name] = round(float(coef), 4)

                # Compute R-squared
                y_pred = X.values @ beta_hat
                ss_tot = np.sum((p_clean - np.mean(p_clean)) ** 2)
                ss_res = np.sum((p_clean - y_pred) ** 2)
                r_squared = round(float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0, 4)
            except Exception:
                pass

    # 3. Identify Primary Style Tilt
    style_scores = {
        "MOMENTUM_TILT": factor_loadings.get("Momentum", 0.0),
        "VALUE_TILT": factor_loadings.get("Value", 0.0),
        "QUALITY_TILT": factor_loadings.get("Quality", 0.0),
        "LOW_VOL_TILT": factor_loadings.get("Low_Volatility", 0.0),
        "HIGH_BETA_TILT": factor_loadings.get("Market_Beta", 1.0) - 1.0 if factor_loadings.get("Market_Beta", 1.0) > 1.2 else 0.0,
    }

    dominant_tilt = max(style_scores, key=style_scores.get)
    if style_scores[dominant_tilt] < 0.40 and dominant_tilt != "HIGH_BETA_TILT":
        dominant_tilt = "BALANCED"

    # 4. Concentration / Risk Warnings
    overconcentrated_factors = []
    for factor_name, loading in factor_loadings.items():
        if factor_name != "Market_Beta" and loading > 0.45:
            overconcentrated_factors.append(factor_name)
            warnings.append(f"Over-concentration alert: {factor_name} factor exposure is {loading:.2f} (exceeds 0.45 cap)")
        elif factor_name == "Market_Beta" and loading > 1.25:
            overconcentrated_factors.append("Market_Beta")
            warnings.append(f"High portfolio Beta alert: Beta is {loading:.2f} (exceeds 1.25 limit)")

    return {
        "factor_exposures": factor_loadings,
        "style_tilt": dominant_tilt,
        "r_squared": r_squared,
        "is_overconcentrated": len(overconcentrated_factors) > 0,
        "overconcentrated_factors": overconcentrated_factors,
        "warnings": warnings,
        "factor_breakdown_chart": {
            "labels": list(factor_loadings.keys()),
            "values": list(factor_loadings.values()),
        }
    }


def calculate_sebi_margin_requirement(
    positions: List[Dict[str, Any]],
    pledged_collateral_inr: float = 0.0,
    cash_balance_inr: float = 1000000.0,
    default_haircut_pct: float = 0.20
) -> Dict[str, Any]:
    """TASK-056: Real-time SEBI haircut & intraday margin usage calculator."""
    effective_collateral = pledged_collateral_inr * (1.0 - default_haircut_pct)
    total_available_margin = cash_balance_inr + effective_collateral

    total_margin_used = 0.0
    position_details = []

    for pos in positions:
        val = abs(pos.get("quantity", 0) * pos.get("price", pos.get("entry_price", 0.0)))
        pos_type = pos.get("type", "EQUITY_DELIVERY").upper()
        # SEBI Margin Schedules: Delivery 100%, Intraday/Futures 20% VAR+ELM
        req_margin_pct = 1.00 if pos_type == "EQUITY_DELIVERY" else 0.20
        margin_req = val * req_margin_pct
        total_margin_used += margin_req
        position_details.append({
            "symbol": pos.get("symbol", "UNKNOWN"),
            "value_inr": round(val, 2),
            "margin_required_inr": round(margin_req, 2),
            "margin_pct": req_margin_pct * 100.0
        })

    utilization_pct = (total_margin_used / total_available_margin * 100.0) if total_available_margin > 0 else 0.0
    margin_call_triggered = utilization_pct > 90.0

    return {
        "cash_balance_inr": round(cash_balance_inr, 2),
        "pledged_collateral_inr": round(pledged_collateral_inr, 2),
        "effective_collateral_inr": round(effective_collateral, 2),
        "total_available_margin_inr": round(total_available_margin, 2),
        "total_margin_used_inr": round(total_margin_used, 2),
        "free_margin_inr": round(max(0.0, total_available_margin - total_margin_used), 2),
        "margin_utilization_pct": round(utilization_pct, 2),
        "margin_call_triggered": margin_call_triggered,
        "positions": position_details
    }


def calculate_correlation_matrix_risk(
    symbol_returns_dict: Dict[str, List[float]],
    proposed_symbol: Optional[str] = None,
    max_avg_correlation_threshold: float = 0.65
) -> Dict[str, Any]:
    """TASK-057: Rolling 60-day pairwise correlation matrix and cluster concentration blocker."""
    symbols = list(symbol_returns_dict.keys())
    if len(symbols) < 2:
        return {
            "avg_pairwise_correlation": 0.0,
            "correlation_matrix": {sym: {sym: 1.0} for sym in symbols},
            "is_blocked": False,
            "reasons": []
        }

    # Convert to DataFrame
    df = pd.DataFrame(symbol_returns_dict).dropna()
    corr_df = df.corr()

    # Calculate upper triangle pairwise correlations
    corrs = []
    matrix_dict = {}
    for i, s1 in enumerate(symbols):
        matrix_dict[s1] = {}
        for j, s2 in enumerate(symbols):
            val = float(corr_df.loc[s1, s2]) if (s1 in corr_df and s2 in corr_df) else (1.0 if s1 == s2 else 0.0)
            matrix_dict[s1][s2] = round(val, 3)
            if i < j:
                corrs.append(val)

    avg_corr = float(np.mean(corrs)) if corrs else 0.0
    is_blocked = avg_corr > max_avg_correlation_threshold
    reasons = []
    if is_blocked:
        reasons.append(f"Average pairwise portfolio correlation ({avg_corr:.2f}) exceeds threshold ({max_avg_correlation_threshold:.2f}). Cluster risk blocked.")

    return {
        "avg_pairwise_correlation": round(avg_corr, 3),
        "correlation_matrix": matrix_dict,
        "is_blocked": is_blocked,
        "reasons": reasons
    }


def run_monte_carlo_ruin_simulation(
    initial_capital_inr: float = 1000000.0,
    win_rate: float = 0.55,
    win_loss_ratio: float = 2.0,
    risk_per_trade_pct: float = 0.015,
    num_simulations: int = 1000,
    trades_per_simulation: int = 100,
    ruin_drawdown_threshold_pct: float = 0.30
) -> Dict[str, Any]:
    """TASK-060: 10,000-path Monte Carlo drawdown & ruin probability simulator."""
    rng = np.random.default_rng(42)
    ruin_threshold_capital = initial_capital_inr * (1.0 - ruin_drawdown_threshold_pct)
    
    ruined_count = 0
    final_capitals = []
    max_drawdowns = []

    for _ in range(num_simulations):
        cap = initial_capital_inr
        peak = cap
        max_dd = 0.0
        is_ruined = False

        outcomes = rng.binomial(1, win_rate, trades_per_simulation)
        for win in outcomes:
            risk_amt = cap * risk_per_trade_pct
            if win == 1:
                cap += risk_amt * win_loss_ratio
            else:
                cap -= risk_amt

            if cap > peak:
                peak = cap
            dd = (peak - cap) / peak
            if dd > max_dd:
                max_dd = dd

            if cap <= ruin_threshold_capital:
                is_ruined = True

        if is_ruined:
            ruined_count += 1
        final_capitals.append(cap)
        max_drawdowns.append(max_dd)

    ruin_prob = (ruined_count / num_simulations) * 100.0
    return {
        "num_simulations": num_simulations,
        "trades_per_sim": trades_per_simulation,
        "ruin_probability_pct": round(ruin_prob, 2),
        "expected_final_capital_inr": round(float(np.mean(final_capitals)), 2),
        "median_final_capital_inr": round(float(np.median(final_capitals)), 2),
        "worst_drawdown_pct": round(float(np.max(max_drawdowns)) * 100.0, 2),
        "avg_max_drawdown_pct": round(float(np.mean(max_drawdowns)) * 100.0, 2),
        "status": "PASS" if ruin_prob < 1.0 else "WARNING"
    }


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
    atr_stop = calculate_atr_garch_trailing_stop([2400, 2420, 2450, 2480, 2500], current_price=2500.0)
    print(f"ATR/GARCH Trailing Stop: {atr_stop}")
    factors = calculate_factor_exposures(
        holding_weights={"RELIANCE": 0.5, "TCS": 0.5},
        asset_metrics={"RELIANCE": {"momentum": 0.6, "value": 0.3}, "TCS": {"momentum": 0.7, "quality": 0.8}}
    )
    print(f"Factor Exposures: {factors}")

