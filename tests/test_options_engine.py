"""
Unit Tests for Real-Time Options Engine (Phase 17 - Task T-224).

Tests:
1. Black-Scholes European Pricing & Exact Option Greeks (Call/Put Delta, Gamma, Theta, Vega, Rho).
2. Implied Volatility (IV) Solver.
3. IV Surface Model & IV Rank / Percentile Calculation.
4. Options Chain Generator & Put-Call Ratio (PCR).
5. Open Interest (OI) Buildup Analyzer.
6. Options Strategy Payoff Engine (Straddle, Strangle, Bull Call Spread, Iron Condor).
7. Max Pain Strike Price Calculation Engine.
8. Volatility Skew / Smile Calculation.
9. Portfolio Option Greeks Aggregate Risk Calculator.
10. Option Strategy Backtester Engine & API endpoints.
"""

import pytest
import math
from engine.options_engine import (
    bs_greeks,
    calculate_implied_volatility,
    calculate_iv_rank_and_percentile,
    generate_iv_surface,
    generate_option_chain,
    analyze_oi_buildup,
    OptionLeg,
    build_preset_strategy,
    calculate_strategy_payoff,
    calculate_max_pain,
    calculate_volatility_skew,
    PortfolioPosition,
    calculate_portfolio_greeks_risk,
    run_options_backtest,
)


def test_black_scholes_call_greeks():
    """Test Call Option Black-Scholes price and Greeks (T-215)."""
    spot = 22000.0
    strike = 22000.0
    T = 30 / 365.0
    r = 0.065
    vol = 0.18

    call = bs_greeks(spot, strike, T, r, vol, option_type="CALL")

    assert call["price"] > 0
    # ATM Call Delta should be close to 0.50 ~ 0.55 (accounting for interest rate)
    assert 0.50 <= call["delta"] <= 0.60
    assert call["gamma"] > 0
    assert call["vega"] > 0
    assert call["theta"] < 0  # Time decay is negative
    assert call["rho"] > 0


def test_black_scholes_put_greeks():
    """Test Put Option Black-Scholes price and Greeks (T-215)."""
    spot = 22000.0
    strike = 22000.0
    T = 30 / 365.0
    r = 0.065
    vol = 0.18

    put = bs_greeks(spot, strike, T, r, vol, option_type="PUT")

    assert put["price"] > 0
    # ATM Put Delta should be around -0.40 to -0.50
    assert -0.55 <= put["delta"] <= -0.40
    assert put["gamma"] > 0
    assert put["vega"] > 0
    assert put["theta"] < 0
    assert put["rho"] < 0


def test_implied_volatility_solver():
    """Test IV solver recovers the original volatility (T-215)."""
    spot = 22000.0
    strike = 22000.0
    T = 30 / 365.0
    r = 0.065
    target_vol = 0.22

    res = bs_greeks(spot, strike, T, r, target_vol, "CALL")
    price = res["price"]

    solved_iv = calculate_implied_volatility(price, spot, strike, T, r, "CALL")
    assert abs(solved_iv - target_vol) < 0.005


def test_iv_rank_and_percentile():
    """Test IV Rank and Percentile calculation (T-216)."""
    history = [0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.30]
    current_iv = 0.20

    res = calculate_iv_rank_and_percentile("NIFTY", current_iv, history)

    # IV Rank = (0.20 - 0.10) / (0.30 - 0.10) * 100 = 50.0%
    assert res["iv_rank"] == 50.0
    # 4 values below 0.20 out of 8 = 50.0%
    assert res["iv_percentile"] == 50.0


def test_generate_iv_surface():
    """Test IV surface generator across strikes and terms (T-216)."""
    surface = generate_iv_surface("BANKNIFTY", 48000.0, base_iv=0.18)

    assert surface["symbol"] == "BANKNIFTY"
    assert len(surface["surface"]) == 5  # 5 DTE terms
    assert len(surface["surface"][0]["skew_points"]) == 11


def test_option_chain_generator():
    """Test Option Chain matrix generation and PCR calculation (T-217)."""
    chain = generate_option_chain("NIFTY", spot_price=22000.0, step=50, num_strikes=11)

    assert chain["symbol"] == "NIFTY"
    assert len(chain["chain"]) == 11
    assert chain["pcr"] > 0
    assert chain["pcr_sentiment"] in ["BULLISH", "BEARISH", "NEUTRAL"]

    atm_row = [r for r in chain["chain"] if r["is_atm"]][0]
    assert atm_row["strike"] == 22000
    assert "call" in atm_row and "put" in atm_row


def test_oi_buildup_analyzer():
    """Test Open Interest buildup classification logic (T-218)."""
    lb = analyze_oi_buildup(price_change=15.0, oi_change=5000)
    assert lb["classification"] == "LONG_BUILDUP"
    assert lb["sentiment"] == "BULLISH"

    sc = analyze_oi_buildup(price_change=10.0, oi_change=-2000)
    assert sc["classification"] == "SHORT_COVERING"
    assert sc["sentiment"] == "BULLISH"

    sb = analyze_oi_buildup(price_change=-20.0, oi_change=8000)
    assert sb["classification"] == "SHORT_BUILDUP"
    assert sb["sentiment"] == "BEARISH"

    lu = analyze_oi_buildup(price_change=-15.0, oi_change=-3000)
    assert lu["classification"] == "LONG_UNWINDING"
    assert lu["sentiment"] == "BEARISH"


def test_strategy_payoff_builder():
    """Test Options Strategy Builder & Payoff calculation (T-219)."""
    legs = build_preset_strategy("BULL_CALL_SPREAD", spot_price=22000.0, step=50)
    payoff = calculate_strategy_payoff(legs, spot_price=22000.0, lot_size=25)

    assert payoff["spot_price"] == 22000.0
    assert len(payoff["payoff_curve"]) > 10
    assert "max_profit" in payoff
    assert "max_loss" in payoff
    assert "break_evens" in payoff


def test_max_pain_calculator():
    """Test Max Pain strike price calculation engine (T-220)."""
    chain_data = generate_option_chain("NIFTY", spot_price=22000.0, step=50, num_strikes=11)
    mp = calculate_max_pain(chain_data)

    assert "max_pain_strike" in mp
    assert mp["max_pain_strike"] > 0
    assert len(mp["pain_curve"]) == 11


def test_volatility_skew_calculator():
    """Test Volatility Skew / Smile extraction across strikes (T-221)."""
    chain_data = generate_option_chain("NIFTY", spot_price=22000.0, step=50, num_strikes=11)
    skew = calculate_volatility_skew(chain_data)

    assert skew["symbol"] == "NIFTY"
    assert len(skew["skew_curve"]) == 11
    assert "otm_put_skew" in skew
    assert "otm_call_skew" in skew


def test_portfolio_greeks_risk_calculator():
    """Test Option Greeks Portfolio Aggregate Risk Calculator (T-222)."""
    positions = [
        PortfolioPosition("NIFTY", "EQUITY", 100, 22000.0),
        PortfolioPosition("NIFTY", "CALL", 2, 22000.0, strike=22200.0, dte=14, iv=0.18, lot_size=25),
        PortfolioPosition("NIFTY", "PUT", -2, 22000.0, strike=21800.0, dte=14, iv=0.20, lot_size=25),
    ]

    risk = calculate_portfolio_greeks_risk(positions)

    assert "total_delta_inr" in risk
    assert "total_gamma_inr" in risk
    assert "total_vega_inr" in risk
    assert "total_theta_inr" in risk
    assert isinstance(risk["risk_notes"], list)


def test_options_backtest_engine():
    """Test automated Option Strategy Backtesting engine (T-223)."""
    bt = run_options_backtest(
        symbol="NIFTY",
        strategy_type="BULL_CALL_SPREAD",
        initial_capital=500000.0
    )

    assert bt["symbol"] == "NIFTY"
    assert bt["strategy_type"] == "BULL_CALL_SPREAD"
    assert bt["total_trades"] == 24
    assert bt["win_rate"] > 0
    assert len(bt["equity_curve"]) == 25
    assert len(bt["trade_logs"]) == 24
