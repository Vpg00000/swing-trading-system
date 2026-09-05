"""
tests/test_risk.py — Unit tests for TASK-019: Portfolio Risk Engine.

Verifies hard risk constraints (max position size %, CVaR, drawdown limit, max sector exposure %, portfolio beta)
that strictly block or scale down unsafe allocations.
"""

import pytest
from engine.portfolio_optimizer import (
    RiskConfig,
    RiskCheckResult,
    validate_portfolio_risk,
    enforce_hard_risk_constraints,
    calculate_cvar_95,
    calculate_portfolio_beta,
)


def test_safe_portfolio_passes_risk_validation():
    """A well-balanced, low-beta portfolio within all limits passes clean."""
    weights = {"INFY.NS": 0.10, "TCS.NS": 0.08, "RELIANCE.NS": 0.12, "HDFCBANK.NS": 0.10}
    sector_map = {"INFY.NS": "IT", "TCS.NS": "IT", "RELIANCE.NS": "Energy", "HDFCBANK.NS": "Banking"}
    asset_betas = {"INFY.NS": 0.9, "TCS.NS": 0.8, "RELIANCE.NS": 1.0, "HDFCBANK.NS": 0.95}

    result = validate_portfolio_risk(
        weights=weights,
        sector_map=sector_map,
        asset_betas=asset_betas,
        current_drawdown_pct=5.0,  # 5% drawdown (under 15% limit)
    )

    assert result.passed is True
    assert len(result.violations) == 0
    assert result.action == "ALLOW"


def test_position_size_limit_blocking():
    """Single position weight exceeding 15% triggers a risk violation."""
    weights = {"INFY.NS": 0.25, "RELIANCE.NS": 0.10}  # INFY is 25% > max 15%
    sector_map = {"INFY.NS": "IT", "RELIANCE.NS": "Energy"}

    result = validate_portfolio_risk(weights=weights, sector_map=sector_map)

    assert result.passed is False
    assert any("Position size for INFY.NS" in v for v in result.violations)
    assert result.action == "SCALE_DOWN"

    # Enforce constraints and verify INFY weight is capped to 15%
    clean_w, clean_res = enforce_hard_risk_constraints(weights, sector_map)
    assert clean_w["INFY.NS"] <= 0.15
    assert clean_res.passed is True


def test_sector_exposure_limit_blocking():
    """Aggregate sector exposure exceeding 20% triggers a risk violation and gets capped."""
    weights = {"INFY.NS": 0.12, "TCS.NS": 0.12, "WIPRO.NS": 0.10}  # IT sector total = 34% > max 20%
    sector_map = {"INFY.NS": "IT", "TCS.NS": "IT", "WIPRO.NS": "IT"}

    result = validate_portfolio_risk(weights=weights, sector_map=sector_map)

    assert result.passed is False
    assert any("Sector exposure for 'IT'" in v for v in result.violations)

    # Enforce constraints and verify aggregate IT sector is capped to max 20%
    clean_w, clean_res = enforce_hard_risk_constraints(weights, sector_map)
    assert sum(clean_w.values()) <= 0.20 + 1e-4
    assert clean_res.passed is True


test_returns_bad = [-0.10, -0.08, -0.07, -0.06, -0.05, 0.01, 0.02, 0.01, 0.02, 0.03]  # Tail loss is high (~7-10%)

def test_cvar_95_limit_blocking():
    """Portfolio with CVaR 95% exceeding 5% limit triggers violation."""
    weights = {"HIGH_VOL.NS": 0.15}
    sector_map = {"HIGH_VOL.NS": "Speculative"}
    returns_matrix = {"HIGH_VOL.NS": test_returns_bad}

    result = validate_portfolio_risk(
        weights=weights,
        sector_map=sector_map,
        returns_matrix=returns_matrix,
    )

    assert result.passed is False
    assert any("CVaR 95%" in v for v in result.violations)


def test_drawdown_limit_hard_stop_blocking():
    """Portfolio drawdown at or exceeding 15% limit strictly BLOCKS all allocations (zeroes weights)."""
    weights = {"INFY.NS": 0.10, "RELIANCE.NS": 0.10}
    sector_map = {"INFY.NS": "IT", "RELIANCE.NS": "Energy"}

    # Drawdown = 18.0% (> 15% limit)
    result = validate_portfolio_risk(
        weights=weights,
        sector_map=sector_map,
        current_drawdown_pct=18.0,
    )

    assert result.passed is False
    assert result.action == "BLOCK"
    assert any("Drawdown" in v for v in result.violations)

    # Enforce hard risk constraints must ZERO out all weights when drawdown limit is reached
    clean_w, clean_res = enforce_hard_risk_constraints(
        candidate_weights=weights,
        sector_map=sector_map,
        current_drawdown_pct=18.0,
    )

    assert clean_res.action == "BLOCK"
    assert all(w == 0.0 for w in clean_w.values())


def test_portfolio_beta_capping():
    """Portfolio with beta > 1.0 is scaled down to maintain beta <= 1.0 limit."""
    weights = {"HIGH_BETA_1.NS": 0.15, "HIGH_BETA_2.NS": 0.15}
    sector_map = {"HIGH_BETA_1.NS": "Cyclical", "HIGH_BETA_2.NS": "Tech"}
    asset_betas = {"HIGH_BETA_1.NS": 1.5, "HIGH_BETA_2.NS": 1.6}  # Weighted beta = 1.55

    result = validate_portfolio_risk(
        weights=weights,
        sector_map=sector_map,
        asset_betas=asset_betas,
    )

    assert result.passed is False
    assert any("Portfolio Beta" in v for v in result.violations)

    clean_w, clean_res = enforce_hard_risk_constraints(
        candidate_weights=weights,
        sector_map=sector_map,
        asset_betas=asset_betas,
    )

    final_beta = calculate_portfolio_beta(clean_w, asset_betas)
    assert final_beta <= 1.0 + 1e-4


def test_zero_hardcoded_values_custom_risk_config():
    """Verify that custom RiskConfig parameters are honored strictly."""
    strict_config = RiskConfig(
        max_position_size_pct=0.08,   # Strict 8% single stock cap
        max_sector_exposure_pct=0.12, # Strict 12% sector cap
        max_drawdown_limit_pct=0.10,  # Strict 10% drawdown cap
    )

    weights = {"INFY.NS": 0.10}  # 10% exceeds 8% custom cap
    sector_map = {"INFY.NS": "IT"}

    res = validate_portfolio_risk(weights=weights, sector_map=sector_map, risk_config=strict_config)
    assert res.passed is False
    assert any("8.00%" in v for v in res.violations)
