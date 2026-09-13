"""
Risk Engine & Risk Guard Evaluation Module for the Swing Trading System.

Implements Phase 22 Tasks:
- T-265: Historical & Parametric Value at Risk (VaR 95% & 99%) calculator.
- T-266: Portfolio Expected Shortfall (CVaR) risk metric engine.
- T-267: Real-Time Portfolio Stress Testing module (Corona 2020 crash, 2008 Lehman crash simulation, etc.).
- T-268: Hard Portfolio Drawdown Kill-Switch (automatically halts all algos if drawdown > limit %).
- T-269: Single-Stock Position Limit Risk Guard (max portfolio weight restriction).
- T-270: Sector Concentration Risk Guard (max sector exposure cap).
- T-271: Daily Loss Limit Circuit Breaker (disables order entry after max daily loss reached).
- T-272: Margin Call Warning Alert & Auto-Deleveraging engine.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np

log = logging.getLogger(__name__)


# Standard Normal Z-Scores for common confidence levels
Z_SCORES = {
    0.90: 1.28155,
    0.95: 1.64485,
    0.975: 1.95996,
    0.99: 2.32635
}


def calculate_var(
    returns: Union[List[float], np.ndarray],
    confidence_level: float = 0.95,
    method: str = "historical",
    portfolio_value: float = 1000000.0
) -> Dict[str, Any]:
    """
    Calculates Value at Risk (VaR) for a given returns series at specified confidence level (95% or 99%).
    Supports 'historical' percentile approach and 'parametric' standard normal approach.
    (T-265)
    """
    if len(returns) == 0:
        return {
            "var_pct": 0.0,
            "var_amount": 0.0,
            "confidence_level": confidence_level,
            "method": method,
            "sample_count": 0
        }

    arr = np.array(returns, dtype=float)
    cl = confidence_level if confidence_level in Z_SCORES else 0.95

    if method.lower() == "parametric":
        mean_ret = float(np.mean(arr))
        std_ret = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        z_score = Z_SCORES.get(cl, 1.64485)
        # VaR loss percentage (positive magnitude)
        var_pct = float(z_score * std_ret - mean_ret)
    else:  # historical
        percentile = (1.0 - cl) * 100.0
        cutoff = float(np.percentile(arr, percentile))
        var_pct = float(-cutoff) if cutoff < 0 else 0.0

    var_pct = max(0.0, var_pct)
    var_amount = float(var_pct * portfolio_value)

    # Calculate both 95% and 99% for comprehensive reporting
    h_95 = float(max(0.0, -np.percentile(arr, 5.0))) if len(arr) > 0 else 0.0
    h_99 = float(max(0.0, -np.percentile(arr, 1.0))) if len(arr) > 0 else 0.0

    mean_r = float(np.mean(arr))
    std_r = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    p_95 = float(max(0.0, Z_SCORES[0.95] * std_r - mean_r))
    p_99 = float(max(0.0, Z_SCORES[0.99] * std_r - mean_r))

    return {
        "var_pct": round(var_pct, 4),
        "var_amount": round(var_amount, 2),
        "confidence_level": cl,
        "method": method,
        "sample_count": len(arr),
        "metrics_summary": {
            "historical_var_95_pct": round(h_95, 4),
            "historical_var_99_pct": round(h_99, 4),
            "historical_var_95_amount": round(h_95 * portfolio_value, 2),
            "historical_var_99_amount": round(h_99 * portfolio_value, 2),
            "parametric_var_95_pct": round(p_95, 4),
            "parametric_var_99_pct": round(p_99, 4),
            "parametric_var_95_amount": round(p_95 * portfolio_value, 2),
            "parametric_var_99_amount": round(p_99 * portfolio_value, 2),
        }
    }


def calculate_cvar(
    returns: Union[List[float], np.ndarray],
    confidence_level: float = 0.95,
    method: str = "historical",
    portfolio_value: float = 1000000.0
) -> Dict[str, Any]:
    """
    Calculates Portfolio Expected Shortfall (CVaR - Conditional Value at Risk).
    CVaR is the expected average loss given that the loss exceeds the VaR threshold.
    (T-266)
    """
    if len(returns) == 0:
        return {
            "cvar_pct": 0.0,
            "cvar_amount": 0.0,
            "confidence_level": confidence_level,
            "var_threshold_pct": 0.0
        }

    arr = np.array(returns, dtype=float)
    cl = confidence_level if confidence_level in Z_SCORES else 0.95
    percentile = (1.0 - cl) * 100.0
    var_threshold = float(np.percentile(arr, percentile))

    # Select returns worse than or equal to VaR threshold
    tail_returns = arr[arr <= var_threshold]
    if len(tail_returns) == 0:
        cvar_pct = float(-var_threshold) if var_threshold < 0 else 0.0
    else:
        cvar_pct = float(-np.mean(tail_returns))

    cvar_pct = max(0.0, cvar_pct)
    cvar_amount = float(cvar_pct * portfolio_value)

    return {
        "cvar_pct": round(cvar_pct, 4),
        "cvar_amount": round(cvar_amount, 2),
        "confidence_level": cl,
        "var_threshold_pct": round(float(-var_threshold if var_threshold < 0 else 0.0), 4),
        "tail_sample_count": len(tail_returns),
        "total_sample_count": len(arr)
    }


STRESS_SCENARIOS = {
    "corona_2020": {
        "name": "Corona 2020 Market Crash",
        "description": "Simulates March 2020 COVID crash (-30% market baseline, heavy hit on travel/financials)",
        "market_shock_pct": -30.0,
        "sector_shocks": {
            "FINANCIALS": -35.0,
            "BANKING": -35.0,
            "AUTOMOBILE": -40.0,
            "TRAVEL_LEISURE": -45.0,
            "REAL_ESTATE": -40.0,
            "ENERGY": -30.0,
            "TECHNOLOGY": -20.0,
            "PHARMA": -10.0,
            "FMCG": -15.0,
            "DEFAULT": -30.0
        }
    },
    "lehman_2008": {
        "name": "2008 Lehman Brothers Financial Crisis",
        "description": "Simulates 2008 GFC (-45% market baseline, extreme financial & real estate meltdown)",
        "market_shock_pct": -45.0,
        "sector_shocks": {
            "FINANCIALS": -60.0,
            "BANKING": -60.0,
            "REAL_ESTATE": -55.0,
            "METALS_MINING": -50.0,
            "ENERGY": -40.0,
            "TECHNOLOGY": -35.0,
            "PHARMA": -20.0,
            "FMCG": -25.0,
            "DEFAULT": -45.0
        }
    },
    "rate_spike_2022": {
        "name": "Global Rate Spike & Liquidity Tightening",
        "description": "Simulates aggressive central bank rate hikes (-20% market, heavy tech valuation compression)",
        "market_shock_pct": -20.0,
        "sector_shocks": {
            "TECHNOLOGY": -35.0,
            "REAL_ESTATE": -25.0,
            "FINANCIALS": -10.0,
            "PHARMA": -12.0,
            "FMCG": -10.0,
            "DEFAULT": -18.0
        }
    },
    "geopolitical_oil_shock": {
        "name": "Geopolitical War & Energy Shock",
        "description": "Crude oil spikes to $140+, high inflation hit on auto & aviation, energy outperforms",
        "market_shock_pct": -18.0,
        "sector_shocks": {
            "ENERGY": +15.0,
            "AUTOMOBILE": -25.0,
            "AVIATION": -35.0,
            "PAINTS_CHEMICALS": -28.0,
            "FINANCIALS": -15.0,
            "DEFAULT": -18.0
        }
    }
}


def run_stress_test(
    positions: List[Dict[str, Any]],
    total_portfolio_value: float = 1000000.0,
    scenario_key: str = "corona_2020"
) -> Dict[str, Any]:
    """
    Simulates real-time portfolio stress testing under historical and macro crisis scenarios.
    (T-267)
    """
    scenario = STRESS_SCENARIOS.get(scenario_key, STRESS_SCENARIOS["corona_2020"])
    sector_shocks = scenario["sector_shocks"]
    default_shock = scenario["market_shock_pct"]

    total_projected_loss = 0.0
    position_stress_details = []

    for pos in positions:
        symbol = pos.get("symbol", "UNKNOWN")
        sector = str(pos.get("sector", "DEFAULT")).upper().replace(" ", "_")
        value = float(pos.get("position_value", pos.get("value", 0.0)))
        weight_pct = (value / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0

        # Match sector shock
        shock_pct = sector_shocks.get(sector, sector_shocks.get("DEFAULT", default_shock))
        # Account for beta if provided
        beta = float(pos.get("beta", 1.0))
        adjusted_shock_pct = shock_pct * beta

        pos_loss = float(value * (abs(adjusted_shock_pct) / 100.0)) if adjusted_shock_pct < 0 else float(-value * (adjusted_shock_pct / 100.0))
        total_projected_loss += pos_loss

        position_stress_details.append({
            "symbol": symbol,
            "sector": sector,
            "position_value": value,
            "weight_pct": round(weight_pct, 2),
            "beta": beta,
            "applied_shock_pct": round(adjusted_shock_pct, 2),
            "projected_loss": round(pos_loss, 2)
        })

    loss_pct = (total_projected_loss / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0
    post_stress_portfolio_value = max(0.0, total_portfolio_value - total_projected_loss)

    return {
        "scenario_key": scenario_key,
        "scenario_name": scenario["name"],
        "description": scenario["description"],
        "initial_portfolio_value": round(total_portfolio_value, 2),
        "post_stress_portfolio_value": round(post_stress_portfolio_value, 2),
        "total_projected_loss": round(total_projected_loss, 2),
        "projected_drawdown_pct": round(loss_pct, 2),
        "position_count": len(positions),
        "position_details": position_stress_details,
        "stress_level": "CRITICAL" if loss_pct > 25.0 else ("HIGH" if loss_pct > 15.0 else "MODERATE")
    }


def check_drawdown_kill_switch(
    current_portfolio_value: float,
    peak_portfolio_value: float,
    max_drawdown_limit_pct: float = 15.0
) -> Dict[str, Any]:
    """
    Hard Portfolio Drawdown Kill-Switch.
    Automatically halts all algos and triggers trading suspension if portfolio drawdown > max_drawdown_limit_pct.
    (T-268)
    """
    if peak_portfolio_value <= 0:
        current_drawdown_pct = 0.0
    else:
        current_drawdown_pct = float((peak_portfolio_value - current_portfolio_value) / peak_portfolio_value * 100.0)

    current_drawdown_pct = max(0.0, current_drawdown_pct)
    kill_switch_triggered = current_drawdown_pct >= max_drawdown_limit_pct

    return {
        "status": "HALTED" if kill_switch_triggered else "ACTIVE",
        "kill_switch_triggered": kill_switch_triggered,
        "action": "HALT_ALL_ALGOS_AND_CANCEL_ORDERS" if kill_switch_triggered else "CONTINUE_TRADING",
        "current_drawdown_pct": round(current_drawdown_pct, 2),
        "max_drawdown_limit_pct": max_drawdown_limit_pct,
        "current_portfolio_value": round(current_portfolio_value, 2),
        "peak_portfolio_value": round(peak_portfolio_value, 2),
        "drawdown_amount": round(max(0.0, peak_portfolio_value - current_portfolio_value), 2)
    }


def check_single_stock_position_limit(
    positions: List[Dict[str, Any]],
    total_portfolio_value: float = 1000000.0,
    max_weight_pct: float = 10.0
) -> Dict[str, Any]:
    """
    Single-Stock Position Limit Risk Guard.
    Restricts any single stock position from exceeding max_weight_pct of total portfolio value.
    (T-269)
    """
    violations = []
    position_weights = []

    for pos in positions:
        symbol = pos.get("symbol", "UNKNOWN")
        val = float(pos.get("position_value", pos.get("value", 0.0)))
        weight_pct = (val / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0

        item = {
            "symbol": symbol,
            "position_value": round(val, 2),
            "weight_pct": round(weight_pct, 2),
            "max_allowed_pct": max_weight_pct,
            "is_violation": weight_pct > max_weight_pct
        }
        position_weights.append(item)
        if weight_pct > max_weight_pct:
            violations.append(item)

    is_passed = len(violations) == 0
    return {
        "is_passed": is_passed,
        "status": "PASSED" if is_passed else "REJECTED_POSITION_LIMIT_EXCEEDED",
        "max_weight_pct_limit": max_weight_pct,
        "violation_count": len(violations),
        "violations": violations,
        "position_weights": position_weights
    }


def check_sector_concentration_limit(
    positions: List[Dict[str, Any]],
    total_portfolio_value: float = 1000000.0,
    max_sector_weight_pct: float = 25.0
) -> Dict[str, Any]:
    """
    Sector Concentration Risk Guard.
    Enforces maximum total exposure cap per sector across all portfolio holdings.
    (T-270)
    """
    sector_totals: Dict[str, float] = {}

    for pos in positions:
        sector = str(pos.get("sector", "UNCLASSIFIED")).upper().replace(" ", "_")
        val = float(pos.get("position_value", pos.get("value", 0.0)))
        sector_totals[sector] = sector_totals.get(sector, 0.0) + val

    sector_breakdown = []
    violations = []

    for sector, total_val in sector_totals.items():
        weight_pct = (total_val / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0
        item = {
            "sector": sector,
            "sector_value": round(total_val, 2),
            "weight_pct": round(weight_pct, 2),
            "max_allowed_pct": max_sector_weight_pct,
            "is_violation": weight_pct > max_sector_weight_pct
        }
        sector_breakdown.append(item)
        if weight_pct > max_sector_weight_pct:
            violations.append(item)

    is_passed = len(violations) == 0
    return {
        "is_passed": is_passed,
        "status": "PASSED" if is_passed else "REJECTED_SECTOR_CONCENTRATION_EXCEEDED",
        "max_sector_weight_pct_limit": max_sector_weight_pct,
        "violation_count": len(violations),
        "violations": violations,
        "sector_breakdown": sector_breakdown
    }


def check_daily_loss_circuit_breaker(
    realized_daily_pnl: float,
    unrealized_daily_pnl: float,
    total_portfolio_value: float = 1000000.0,
    max_daily_loss_pct: float = 3.0
) -> Dict[str, Any]:
    """
    Daily Loss Limit Circuit Breaker.
    Disables order entry for the remainder of the trading day after max daily loss threshold is breached.
    (T-271)
    """
    total_daily_pnl = realized_daily_pnl + unrealized_daily_pnl
    daily_pnl_pct = (total_daily_pnl / total_portfolio_value * 100.0) if total_portfolio_value > 0 else 0.0

    # Circuit breaker triggers if net loss exceeds max_daily_loss_pct
    circuit_breaker_triggered = daily_pnl_pct <= -abs(max_daily_loss_pct)

    return {
        "circuit_breaker_triggered": circuit_breaker_triggered,
        "order_entry_enabled": not circuit_breaker_triggered,
        "status": "CIRCUIT_BREAKER_ACTIVE_ORDER_ENTRY_DISABLED" if circuit_breaker_triggered else "NORMAL_TRADING",
        "total_daily_pnl": round(total_daily_pnl, 2),
        "daily_pnl_pct": round(daily_pnl_pct, 2),
        "realized_daily_pnl": round(realized_daily_pnl, 2),
        "unrealized_daily_pnl": round(unrealized_daily_pnl, 2),
        "max_daily_loss_pct_limit": max_daily_loss_pct,
        "remaining_loss_headroom_amount": round(
            max(0.0, (total_portfolio_value * (max_daily_loss_pct / 100.0)) + total_daily_pnl), 2
        )
    }


def check_circuit_proximity(
    symbol: str,
    price: float,
    prev_close: float,
    circuit_limit_pct: float = 10.0,
    buffer_pct: float = 1.0
) -> Dict[str, Any]:
    """
    Individual Stock Circuit Breaker Proximity Guard.
    Detects if an equity is within buffer_pct (default 1.0%) of its daily circuit limits (upper or lower).
    Protects against execution failure:
      - Near lower circuit: Stop-loss will fail or not fill, locking capital into freeze.
      - Near upper circuit: New buy orders will be trapped at the ceiling with high gap-down risk.
    """
    if prev_close <= 0 or price <= 0:
        return {
            "symbol": symbol,
            "is_near_circuit": False,
            "is_near_upper_circuit": False,
            "is_near_lower_circuit": False,
            "status": "DATA_UNAVAILABLE",
            "upper_circuit": 0.0,
            "lower_circuit": 0.0,
            "distance_to_upper_pct": 0.0,
            "distance_to_lower_pct": 0.0,
            "warning": None
        }

    upper_circuit = round(prev_close * (1.0 + circuit_limit_pct / 100.0), 2)
    lower_circuit = round(prev_close * (1.0 - circuit_limit_pct / 100.0), 2)

    dist_upper_pct = round(((upper_circuit - price) / price) * 100.0, 2)
    dist_lower_pct = round(((price - lower_circuit) / price) * 100.0, 2)

    is_near_upper = dist_upper_pct <= buffer_pct or price >= upper_circuit
    is_near_lower = dist_lower_pct <= buffer_pct or price <= lower_circuit
    is_near_circuit = is_near_upper or is_near_lower

    warning = None
    if is_near_lower:
        warning = f"CRITICAL: {symbol} is within {dist_lower_pct:.1f}% of lower circuit (₹{lower_circuit}). Stop-loss execution may fail!"
    elif is_near_upper:
        warning = f"ATTENTION: {symbol} is within {dist_upper_pct:.1f}% of upper circuit (₹{upper_circuit}). Ceiled order entry risk!"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "prev_close": round(prev_close, 2),
        "circuit_limit_pct": circuit_limit_pct,
        "upper_circuit": upper_circuit,
        "lower_circuit": lower_circuit,
        "distance_to_upper_pct": dist_upper_pct,
        "distance_to_lower_pct": dist_lower_pct,
        "is_near_circuit": is_near_circuit,
        "is_near_upper_circuit": is_near_upper,
        "is_near_lower_circuit": is_near_lower,
        "order_entry_allowed": not is_near_circuit,
        "status": "CIRCUIT_RISK_BREACH" if is_near_circuit else "PASSED",
        "warning": warning
    }



def evaluate_margin_call_and_deleverage(
    total_equity: float,
    margin_used: float,
    positions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Margin Call Warning Alert & Auto-Deleveraging engine.
    Monitors margin utilization ratio (margin_used / total_equity).
    Triggers Warning (70-85%), Margin Call (85-95%), and Auto-Deleveraging Liquidation Plan (>= 95%).
    (T-272)
    """
    if total_equity <= 0:
        margin_utilization_pct = 100.0
    else:
        margin_utilization_pct = float(margin_used / total_equity * 100.0)

    margin_utilization_pct = max(0.0, margin_utilization_pct)

    if margin_utilization_pct >= 95.0:
        alert_level = "CRITICAL_AUTO_DELEVERAGE"
        action = "AUTO_LIQUIDATE_HIGHEST_RISK_POSITIONS"
    elif margin_utilization_pct >= 85.0:
        alert_level = "MARGIN_CALL"
        action = "REQUIRE_ADDITIONAL_MARGIN_OR_REDUCE_POSITIONS"
    elif margin_utilization_pct >= 70.0:
        alert_level = "WARNING"
        action = "MONITOR_MARGIN_UTILIZATION"
    else:
        alert_level = "SAFE"
        action = "NO_ACTION_REQUIRED"

    # Compute deleveraging liquidation plan if margin_utilization_pct >= 85%
    deleveraging_plan = []
    target_margin_used = total_equity * 0.70  # target 70% utilization
    required_reduction = max(0.0, margin_used - target_margin_used)

    if required_reduction > 0 and positions:
        # Sort positions by risk factor: higher beta, negative unrealized pnl first
        sorted_pos = sorted(
            positions,
            key=lambda x: (
                -float(x.get("beta", 1.0)),
                float(x.get("unrealized_pnl", 0.0))
            )
        )

        freed_margin = 0.0
        for pos in sorted_pos:
            if freed_margin >= required_reduction:
                break
            sym = pos.get("symbol", "UNKNOWN")
            val = float(pos.get("position_value", pos.get("value", 0.0)))
            margin_req = float(pos.get("margin_required", val * 0.20))  # default 20% margin
            qty = int(pos.get("qty", 1))

            deleveraging_plan.append({
                "symbol": sym,
                "action": "CLOSE_POSITION",
                "qty_to_liquidate": qty,
                "position_value": round(val, 2),
                "margin_freed": round(margin_req, 2),
                "reason": f"High beta ({pos.get('beta', 1.0)}) / margin deleveraging prioritization"
            })
            freed_margin += margin_req

    return {
        "alert_level": alert_level,
        "action_required": action,
        "total_equity": round(total_equity, 2),
        "margin_used": round(margin_used, 2),
        "margin_available": round(max(0.0, total_equity - margin_used), 2),
        "margin_utilization_pct": round(margin_utilization_pct, 2),
        "is_margin_call": margin_utilization_pct >= 85.0,
        "auto_deleverage_triggered": margin_utilization_pct >= 95.0,
        "required_margin_reduction": round(required_reduction, 2),
        "deleveraging_plan": deleveraging_plan
    }


def evaluate_full_portfolio_risk(
    positions: List[Dict[str, Any]],
    total_equity: float,
    peak_equity: float,
    realized_daily_pnl: float,
    unrealized_daily_pnl: float,
    margin_used: float,
    historical_returns: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Evaluates comprehensive risk assessment aggregating all Phase 22 risk guards.
    """
    returns = historical_returns or []
    var_res = calculate_var(returns, confidence_level=0.95, portfolio_value=total_equity)
    cvar_res = calculate_cvar(returns, confidence_level=0.95, portfolio_value=total_equity)
    stress_res = run_stress_test(positions, total_portfolio_value=total_equity, scenario_key="corona_2020")
    kill_switch_res = check_drawdown_kill_switch(total_equity, peak_equity, max_drawdown_limit_pct=15.0)
    stock_limit_res = check_single_stock_position_limit(positions, total_portfolio_value=total_equity, max_weight_pct=10.0)
    sector_limit_res = check_sector_concentration_limit(positions, total_portfolio_value=total_equity, max_sector_weight_pct=25.0)
    circuit_breaker_res = check_daily_loss_circuit_breaker(realized_daily_pnl, unrealized_daily_pnl, total_portfolio_value=total_equity, max_daily_loss_pct=3.0)
    margin_res = evaluate_margin_call_and_deleverage(total_equity, margin_used, positions)

    overall_status = "HEALTHY"
    if kill_switch_res["kill_switch_triggered"] or circuit_breaker_res["circuit_breaker_triggered"] or margin_res["auto_deleverage_triggered"]:
        overall_status = "CRITICAL_ACTION_REQUIRED"
    elif not stock_limit_res["is_passed"] or not sector_limit_res["is_passed"] or margin_res["is_margin_call"]:
        overall_status = "WARNING_LIMIT_BREACH"

    return {
        "overall_status": overall_status,
        "var": var_res,
        "cvar": cvar_res,
        "stress_test": stress_res,
        "kill_switch": kill_switch_res,
        "single_stock_guard": stock_limit_res,
        "sector_guard": sector_limit_res,
        "circuit_breaker": circuit_breaker_res,
        "margin_deleverage": margin_res
    }


def validate_intraday_short_entry(
    symbol: str,
    current_time_str: Optional[str] = None,
    user_confirmed_watching: bool = False,
    is_fno_eligible: bool = True,
    momentum_rank_bottom_tier: bool = True,
    has_negative_catalyst: bool = True,
    entry_price: float = 0.0,
    atr: float = 0.0,
    capital: float = 1000000.0,
    requested_size_pct: float = 0.04
) -> Dict[str, Any]:
    """
    Enforces all 8 rules for intraday short-selling per DESIGN.md L99-111 & ISSUES_AND_IMPROVEMENTS.md:
      1. User confirmation they have time to watch live (NOT automated)
      2. Momentum rank in bottom tier + confirmed negative catalyst
      3. Stock on F&O-eligible / high-liquidity list
      4. Entry ONLY before 1:30 PM IST
      5. Stop-loss = 2x ATR ABOVE entry
      6. Position size 3-5% hard limit
      7. Hard close / square-off by 3:15 PM regardless of P&L
      8. Never average down
    """
    rejection_reasons = []

    if not user_confirmed_watching:
        rejection_reasons.append("User has not confirmed availability to actively monitor intraday short trade.")

    if not is_fno_eligible:
        rejection_reasons.append(f"{symbol} is not F&O-eligible / high-liquidity.")

    if not (momentum_rank_bottom_tier and has_negative_catalyst):
        rejection_reasons.append("Short candidates require both bottom-tier momentum and confirmed negative catalyst.")

    # Time check (entry allowed only before 13:30 IST)
    time_str = current_time_str or datetime.now().strftime("%H:%M")
    if time_str > "13:30":
        rejection_reasons.append(f"Short entry rejected at {time_str} IST: must enter before 1:30 PM IST.")

    # Size cap (3-5% hard cap)
    capped_size_pct = min(0.05, max(0.03, requested_size_pct))
    if requested_size_pct > 0.05:
        rejection_reasons.append(f"Requested position size {requested_size_pct*100:.1f}% exceeds 5% maximum intraday short limit.")

    stop_loss_price = round(entry_price + 2.0 * atr, 2) if (entry_price > 0 and atr > 0) else 0.0
    allowed_size_inr = round(capital * capped_size_pct, 2)

    is_allowed = len(rejection_reasons) == 0

    return {
        "symbol": symbol,
        "is_short_entry_allowed": is_allowed,
        "status": "APPROVED" if is_allowed else "REJECTED",
        "rejection_reasons": rejection_reasons,
        "entry_time": time_str,
        "stop_loss_price": stop_loss_price,
        "max_size_pct": 5.0,
        "approved_size_pct": round(capped_size_pct * 100.0, 1),
        "approved_size_inr": allowed_size_inr,
        "mandatory_square_off_time": "15:15 IST",
        "average_down_allowed": False
    }


def check_intraday_short_square_off(current_time_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Checks whether intraday short positions must be forcibly closed (3:15 PM IST cutoff).
    Prevents overnight naked short positions and unlimited auction penalty risk.
    """
    time_str = current_time_str or datetime.now().strftime("%H:%M")
    is_square_off = time_str >= "15:15"

    return {
        "current_time": time_str,
        "cutoff_time": "15:15",
        "force_square_off": is_square_off,
        "action": "AUTO_CLOSE_ALL_INTRADAY_SHORTS" if is_square_off else "HOLD_INTRADAY",
        "warning": "CRITICAL: 3:15 PM square-off reached! Liquidate all short trades now." if is_square_off else None
    }

