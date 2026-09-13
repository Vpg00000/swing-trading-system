"""
Comprehensive Test Suite for Trading Engine Improvements & Logical Gaps:
1. Individual Stock Circuit Breaker Proximity Guard (engine/risk_engine.py)
2. Hard Concentration Gate on BUY & Circuit Clearance (engine/decision.py)
3. Volume-Weighted Momentum & Sector Peer RS (engine/momentum.py)
4. Mean Reversion & Confluence Scoring (engine/scoring.py)
5. Authentic Data Backtest Engine & Analytics Runner (engine/backtest.py & web_server.py)
"""

import pytest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from engine.risk_engine import (
    check_circuit_proximity,
    validate_intraday_short_entry,
    check_intraday_short_square_off
)
from engine.decision import (
    evaluate_decision,
    classify_action,
    compute_composite_score,
    check_emergency_derisking,
    rank_by_expected_sharpe
)
from engine.momentum import (
    compute_volume_weighted_momentum,
    relative_strength_within_sector,
    calculate_beta_adjusted_size,
    compute_atr_adaptive,
    score_with_earnings_forward,
    filter_earnings_candidates,
    rebalance_momentum_portfolio,
    Candidate
)
from engine.scoring import (
    calculate_mean_reversion_score,
    calculate_confluence_score,
    detect_flow_divergence
)
from engine.backtest import (
    run_standard_momentum_backtest,
    calculate_market_impact,
    monte_carlo_with_correlation,
    walk_forward_backtest,
    TradeMetrics,
    BacktestValidator
)
from engine.regime import (
    get_institutional_score_with_staleness,
    monitor_vix_spike,
    should_hedge_portfolio,
    calculate_hedge_size
)
from data.fetch import load_cached_adjusted
from engine.portfolio_manager import Position, Portfolio
from data.database import (
    log_decision_signal,
    record_signal_outcome,
    get_action_hitrate,
    get_regime_accuracy,
    SignalDB
)
from web_server import app, SimpleRateLimiter, global_backtest_queue


def test_circuit_proximity_guard():
    # 1. Normal trading within limits
    res_normal = check_circuit_proximity("RELIANCE.NS", price=2500.0, prev_close=2500.0, circuit_limit_pct=10.0)
    assert res_normal["status"] == "PASSED"
    assert not res_normal["is_near_circuit"]
    assert res_normal["order_entry_allowed"]

    # 2. Within 1% of upper circuit (2500 + 10% = 2750; price 2735 is 0.5% away)
    res_upper = check_circuit_proximity("RELIANCE.NS", price=2735.0, prev_close=2500.0, circuit_limit_pct=10.0, buffer_pct=1.0)
    assert res_upper["is_near_upper_circuit"]
    assert res_upper["is_near_circuit"]
    assert not res_upper["order_entry_allowed"]
    assert "upper circuit" in res_upper["warning"].lower()

    # 3. Within 1% of lower circuit (2500 - 10% = 2250; price 2260 is < 1% away)
    res_lower = check_circuit_proximity("RELIANCE.NS", price=2260.0, prev_close=2500.0, circuit_limit_pct=10.0, buffer_pct=1.0)
    assert res_lower["is_near_lower_circuit"]
    assert res_lower["is_near_circuit"]
    assert not res_lower["order_entry_allowed"]
    assert "Stop-loss execution may fail" in res_lower["warning"]


def test_hard_concentration_gate_on_buy():
    # Candidate meets all BUY_NOW criteria (top rank 1, high score 80),
    # but sector_stacking_risk is True (already >20% in that sector)
    dec = evaluate_decision(
        symbol="HDFCBANK.NS",
        rank=1,
        total_candidates=10,
        momentum_pct=0.9,
        sector_overall_score=75.0,
        money_flow_total=10.0,
        news_flagged=False,
        priced_in_status=None,
        stop_distance_pct=0.03,
        pledged_pct=0.0,
        has_upcoming_event=False,
        sector_stacking_risk=True,
        is_held=False,
        regime_state="RISK-ON",
    )
    # Hard gate must block BUY_NOW and assign HOLD OFF / SECTOR CONCENTRATED
    assert dec.suggested_action == "HOLD OFF / SECTOR CONCENTRATED"
    assert any("sector-stacking risk" in c for c in dec.concerns)


def test_circuit_risk_gate_on_decision():
    # Candidate meets BUY criteria, but circuit_risk is True
    dec = evaluate_decision(
        symbol="TATAMOTORS.NS",
        rank=2,
        total_candidates=10,
        momentum_pct=0.85,
        sector_overall_score=70.0,
        money_flow_total=8.0,
        news_flagged=False,
        priced_in_status=None,
        stop_distance_pct=0.03,
        pledged_pct=0.0,
        has_upcoming_event=False,
        sector_stacking_risk=False,
        is_held=False,
        regime_state="RISK-ON",
        circuit_risk=True,
    )
    # Order entry must be held until clearance
    assert dec.suggested_action == "WAIT_FOR_CIRCUIT_CLEARANCE"
    assert any("circuit risk" in c for c in dec.concerns)


def test_volume_weighted_momentum():
    dates = pd.date_range("2024-01-01", periods=150)
    # Price steadily rising
    closes = np.linspace(100.0, 150.0, 150)
    # Volume expands 3x in recent bars
    volumes = np.ones(150) * 10000.0
    volumes[-1] = 30000.0

    df = pd.DataFrame({"Close": closes, "Volume": volumes}, index=dates)
    vol_weighted, raw, ret_3m, ret_6m = compute_volume_weighted_momentum(df)

    assert not np.isnan(vol_weighted)
    assert not np.isnan(raw)
    assert vol_weighted > raw  # volume confirmation should scale up momentum score
    assert ret_6m > 0.0


def test_relative_strength_within_sector():
    sector_syms = ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"]
    rs_res = relative_strength_within_sector("TCS.NS", sector_syms, lookback_days=63)
    assert "percentile_rank" in rs_res
    assert "rank" in rs_res
    assert rs_res["total_peers"] >= 1
    assert 0.0 <= rs_res["percentile_rank"] <= 100.0


def test_beta_adjusted_size():
    base_size = 100000.0

    # High beta stock (beta 1.8) should be downscaled
    high_beta_size = calculate_beta_adjusted_size(base_size, beta=1.8, target_beta=1.0)
    assert high_beta_size < base_size
    assert round(high_beta_size, 2) == round(base_size * (1.0 / 1.8), 2)

    # Low beta stock (beta 0.7) should be upscaled
    low_beta_size = calculate_beta_adjusted_size(base_size, beta=0.7, target_beta=1.0)
    assert low_beta_size > base_size


def test_mean_reversion_score():
    # Deeply oversold: RSI 22, BB position -0.1 (below band), Z-score -2.8
    score_oversold = calculate_mean_reversion_score(rsi=22.0, bb_position_pct=-0.1, z_score=-2.8)
    assert score_oversold >= 80.0

    # Overbought / momentum: RSI 75, BB position 0.9, Z-score +2.1
    score_overbought = calculate_mean_reversion_score(rsi=75.0, bb_position_pct=0.9, z_score=2.1)
    assert score_overbought < 20.0


def test_confluence_score():
    # 5 indicators all bullish
    signals_aligned = {
        "rsi_oversold_or_divergence": True,
        "macd_bullish": True,
        "price_above_ema20": True,
        "ema_trend_aligned": True,
        "volume_expansion": True,
        "supertrend_bullish": False,
        "vwap_reclaimed": False,
    }
    res = calculate_confluence_score(signals_aligned)
    assert res["is_high_confluence"]
    assert res["confluence_strength"] == "HIGH"
    assert res["confluence_score"] >= 70.0


def test_authentic_data_backtest_runner():
    res = run_standard_momentum_backtest(
        symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        initial_capital=500000.0,
        lookback_bars=60
    )
    assert res["status"] == "SUCCESS"
    assert res["data_source"] == "AUTHENTIC_NSE_CACHE"
    assert len(res["equity_curve"]) > 0
    assert "sharpe_ratio" in res
    assert "max_drawdown_pct" in res
    assert not np.isnan(res["sharpe_ratio"])


def test_web_server_backtest_endpoints():
    client = TestClient(app)

    # 1. Advanced Backtest (Authentic Momentum Mode)
    r1 = client.get("/api/backtest/advanced?bars=40")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "SUCCESS"
    assert d1["result"]["data_source"] == "AUTHENTIC_NSE_CACHE"

    # 2. Multi-Asset Backtest
    r2 = client.get("/api/backtest/multi_asset")
    assert r2.status_code == 200
    assert r2.json()["status"] == "SUCCESS"

    # 3. Optimize Parameters
    r3 = client.get("/api/backtest/optimize")
    assert r3.status_code == 200
    assert r3.json()["status"] == "SUCCESS"


def test_intraday_short_enforcement():
    # 1. Valid short entry before 1:30 PM with active watch confirmation
    valid_short = validate_intraday_short_entry(
        symbol="TATASTEEL.NS",
        current_time_str="11:45",
        user_confirmed_watching=True,
        is_fno_eligible=True,
        momentum_rank_bottom_tier=True,
        has_negative_catalyst=True,
        entry_price=150.0,
        atr=3.0,
        capital=1000000.0,
        requested_size_pct=0.04
    )
    assert valid_short["is_short_entry_allowed"]
    assert valid_short["status"] == "APPROVED"
    assert valid_short["stop_loss_price"] == 156.0  # entry + 2x ATR

    # 2. Rejection if user did not confirm watching
    unwatched = validate_intraday_short_entry(
        symbol="TATASTEEL.NS",
        current_time_str="11:45",
        user_confirmed_watching=False,
        is_fno_eligible=True,
        momentum_rank_bottom_tier=True,
        has_negative_catalyst=True
    )
    assert not unwatched["is_short_entry_allowed"]
    assert any("monitor" in r for r in unwatched["rejection_reasons"])

    # 3. Rejection if entered after 1:30 PM IST (e.g. 14:00)
    late_short = validate_intraday_short_entry(
        symbol="TATASTEEL.NS",
        current_time_str="14:00",
        user_confirmed_watching=True,
        is_fno_eligible=True,
        momentum_rank_bottom_tier=True,
        has_negative_catalyst=True
    )
    assert not late_short["is_short_entry_allowed"]
    assert any("1:30 PM" in r for r in late_short["rejection_reasons"])

    # 4. Mandatory square-off at 3:15 PM IST
    midday = check_intraday_short_square_off("13:00")
    assert not midday["force_square_off"]

    cutoff = check_intraday_short_square_off("15:20")
    assert cutoff["force_square_off"]
    assert cutoff["action"] == "AUTO_CLOSE_ALL_INTRADAY_SHORTS"


def test_walk_forward_cross_validation():
    wf_res = walk_forward_backtest(train_window=100, test_window=40, roll_step=30)
    assert wf_res["status"] == "SUCCESS"
    assert wf_res["total_folds"] >= 2
    assert "average_test_sharpe" in wf_res
    assert "out_of_sample_return_pct" in wf_res
    assert len(wf_res["folds"]) == wf_res["total_folds"]
    first_fold = wf_res["folds"][0]
    assert "best_params" in first_fold
    assert "test_sharpe" in first_fold


def test_monte_carlo_correlated_cholesky():
    # 3 correlated assets in same sector
    np.random.seed(42)
    days = 150
    base_ret = np.random.normal(0.001, 0.015, days)
    rets = {
        "HDFCBANK.NS": base_ret + np.random.normal(0, 0.005, days),
        "ICICIBANK.NS": base_ret + np.random.normal(0, 0.005, days),
        "KOTAKBANK.NS": base_ret + np.random.normal(0, 0.006, days),
    }
    sector_corr = np.array([
        [1.0, 0.85, 0.80],
        [0.85, 1.0, 0.78],
        [0.80, 0.78, 1.0]
    ])
    mc_res = monte_carlo_with_correlation(rets, sector_corr_matrix=sector_corr, n_sims=300, n_days=60)
    assert mc_res["status"] == "SUCCESS"
    assert mc_res["simulations"] == 300
    assert mc_res["n_assets"] == 3
    assert mc_res["p95_max_drawdown_pct"] > 0
    assert "cvar_95_pct" in mc_res


def test_market_impact_slippage():
    # Large order: 12% of daily volume -> sqrt(0.12) * 50 = ~17.3 bps
    imp_large = calculate_market_impact(position_size_inr=12_000_000, avg_daily_volume_inr=100_000_000)
    assert imp_large > 15.0

    # Medium order: 7% of daily volume -> 0.07 * 25 = 1.75 * 100 ? Wait, formula:
    imp_med = calculate_market_impact(position_size_inr=7_000_000, avg_daily_volume_inr=100_000_000)
    assert imp_med > 0.0

    # Small retail order: 0.5% of volume -> 5 bps baseline
    imp_small = calculate_market_impact(position_size_inr=500_000, avg_daily_volume_inr=100_000_000)
    assert imp_small == 5.0


def test_backtest_validator():
    bt_res = {"assumed_slippage_bps": 15.0, "cagr_pct": 22.0}
    live_trades = [
        TradeMetrics("RELIANCE.NS", "2026-08-01", 2800.0, "2026-08-10", 2950.0, slippage_bps=16.5, holding_days=9, pnl_pct=5.35, driven_by="MOMENTUM"),
        TradeMetrics("TCS.NS", "2026-08-05", 4100.0, "2026-08-12", 4220.0, slippage_bps=14.2, holding_days=7, pnl_pct=2.92, driven_by="MOMENTUM"),
        TradeMetrics("INFY.NS", "2026-08-10", 1850.0, "2026-08-15", 1920.0, slippage_bps=15.0, holding_days=5, pnl_pct=3.78, driven_by="EVENT")
    ]
    val = BacktestValidator(bt_res, live_trades)
    slip = val.validate_slippage()
    assert slip["live_avg_slippage_bps"] == pytest.approx(15.23, rel=1e-2)
    assert not slip["requires_model_update"]

    alpha = val.validate_alpha_attribution()
    assert "MOMENTUM" in alpha["attribution_by_strategy"]
    assert alpha["attribution_by_strategy"]["MOMENTUM"]["trades"] == 2
    assert alpha["attribution_by_strategy"]["EVENT"]["trades"] == 1


def test_momentum_portfolio_rebalancer():
    holdings = {"RELIANCE.NS": 200_000.0, "TCS.NS": 200_000.0, "INFY.NS": 200_000.0}
    candidates = [
        Candidate("HDFCBANK.NS", 1600.0, 0.45, 0.15, 0.30, 5e8, 25.0, 0.03, 1550.0, 160_000.0),
        Candidate("ICICIBANK.NS", 1150.0, 0.42, 0.14, 0.28, 4e8, 18.0, 0.03, 1114.0, 160_000.0),
        Candidate("RELIANCE.NS", 2850.0, 0.38, 0.12, 0.26, 6e8, 35.0, 0.025, 2780.0, 160_000.0),
        Candidate("SBIN.NS", 820.0, 0.35, 0.10, 0.25, 3e8, 12.0, 0.03, 796.0, 160_000.0),
    ]
    rebal = rebalance_momentum_portfolio(holdings, candidates, target_count=4, max_turnover_pct=0.25, total_portfolio_value=600_000.0)
    assert rebal["status"] == "SUCCESS"
    assert "target_holdings" in rebal
    assert rebal["turnover_pct"] <= 25.01  # enforced turnover limit
    assert "estimated_cost_inr" in rebal
    assert len(rebal["target_holdings"]) > 0


def test_adaptive_atr_smoothing():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    df = pd.DataFrame({
        "High": [100 + i + 2 for i in range(40)],
        "Low": [100 + i - 2 for i in range(40)],
        "Close": [100 + i for i in range(40)],
        "Volume": [100000] * 40
    }, index=dates)

    # 1. Normal regime (VIX = 16)
    atr_norm = compute_atr_adaptive(df, vix=16.0)
    assert atr_norm > 0

    # 2. High vol regime (VIX = 28) uses smoothed 21/30 window
    atr_high_vol = compute_atr_adaptive(df, vix=28.0)
    assert atr_high_vol > 0

    # 3. Calm regime (VIX = 10) tighter multiplier
    atr_low_vol = compute_atr_adaptive(df, vix=10.0)
    assert atr_low_vol == round(atr_norm * 0.9, 2)


def test_forward_earnings_discounting():
    cand = Candidate("TCS.NS", 4000.0, 0.50, 0.10, 0.40, 1e9, 45.0, 0.02, 3910.0, 100000.0)
    # 5 days to earnings -> discounted 40% (score * 0.6)
    s_close = score_with_earnings_forward(cand, days_to_earnings=5)
    assert s_close == 0.30

    # 12 days to earnings -> discounted 25% (score * 0.75)
    s_med = score_with_earnings_forward(cand, days_to_earnings=12)
    assert s_med == 0.375

    # 30 days to earnings -> normal
    s_far = score_with_earnings_forward(cand, days_to_earnings=30)
    assert s_far == 0.50

    # Filter out candidates with imminent earnings
    earnings_map = {"TCS.NS": 10, "INFY.NS": 60}
    c2 = Candidate("INFY.NS", 1800.0, 0.48, 0.10, 0.38, 1e9, 25.0, 0.02, 1750.0, 100000.0)
    filtered = filter_earnings_candidates([cand, c2], earnings_lookup=earnings_map, min_days=7, max_days=45)
    assert len(filtered) == 1
    assert filtered[0].symbol == "INFY.NS"


def test_trend_aware_technical_gating():
    # Candidate with high rank 1 and score 75, but extended +6% above 50-DMA
    action_extended = classify_action(
        symbol="DIXON.NS",
        rank=1,
        total_candidates=10,
        composite_score=75.0,
        is_held=False,
        regime_state="RISK-ON",
        news_flagged=False,
        stop_distance_pct=0.03,
        pledged_pct=0.0,
        has_upcoming_event=False,
        sector_stacking_risk=False,
        sector_overall_score=75.0,
        concerns=[],
        price_vs_50dma=6.2,  # > +5% extended move
        price_vs_20dma=3.0
    )
    # Should prevent chasing the top -> BUY_ON_PULLBACK
    assert action_extended == "BUY_ON_PULLBACK"

    # Price well below 20-DMA (-3%) -> WAIT_FOR_PULLBACK
    action_breakdown = classify_action(
        symbol="DIXON.NS",
        rank=1,
        total_candidates=10,
        composite_score=75.0,
        is_held=False,
        regime_state="RISK-ON",
        news_flagged=False,
        stop_distance_pct=0.03,
        pledged_pct=0.0,
        has_upcoming_event=False,
        sector_stacking_risk=False,
        sector_overall_score=75.0,
        concerns=[],
        price_vs_50dma=2.0,
        price_vs_20dma=-3.5
    )
    assert action_breakdown == "WAIT_FOR_PULLBACK"

    # Normal healthy setup near support -> BUY_NOW
    action_healthy = classify_action(
        symbol="DIXON.NS",
        rank=1,
        total_candidates=10,
        composite_score=75.0,
        is_held=False,
        regime_state="RISK-ON",
        news_flagged=False,
        stop_distance_pct=0.03,
        pledged_pct=0.0,
        has_upcoming_event=False,
        sector_stacking_risk=False,
        sector_overall_score=75.0,
        concerns=[],
        price_vs_50dma=2.5,
        price_vs_20dma=0.5
    )
    assert action_healthy == "BUY_NOW"


def test_emergency_derisking_gate():
    # Normal: -1% DD -> no action
    d0, mult0, mode0 = check_emergency_derisking(-1.0)
    assert not d0
    assert mult0 == 1.0
    assert mode0 == "NORMAL"

    # Moderate DD: -3% -> trim 15%
    d1, mult1, mode1 = check_emergency_derisking(-3.0)
    assert d1
    assert mult1 == 0.85

    # Severe DD: -6% -> trim 35%
    d2, mult2, mode2 = check_emergency_derisking(-6.0)
    assert d2
    assert mult2 == 0.65

    # Crisis DD: -9% -> Halve equity exposure
    d3, mult3, mode3 = check_emergency_derisking(-9.0)
    assert d3
    assert mult3 == 0.50
    assert mode3 == "HALVE_EXPOSURE"


def test_sharpe_ranked_top3():
    c1 = evaluate_decision("SYM1", 1, 10, 0.4, 80.0, 5.0, False, None, 0.03, 0.0, False, False, False, "RISK-ON")
    c2 = evaluate_decision("SYM2", 2, 10, 0.35, 75.0, 4.0, False, None, 0.04, 0.0, False, False, False, "RISK-ON")
    c3 = evaluate_decision("SYM3", 3, 10, 0.30, 70.0, 3.0, False, None, 0.05, 0.0, False, False, False, "RISK-ON")
    c4 = evaluate_decision("SYM4", 4, 10, 0.25, 65.0, 2.0, False, None, 0.06, 0.0, False, False, False, "RISK-ON")

    top3 = rank_by_expected_sharpe([c1, c2, c3, c4], top_n=3)
    assert len(top3) <= 3
    assert top3[0].symbol == "SYM1"


def test_sector_concentration_prewarning():
    total, comps, concerns, missing = compute_composite_score(
        regime_state="RISK-ON",
        momentum_pct=0.5,
        sector_stacking_risk=False,
        sector_concentration_pct=17.5  # between 15% and 20%
    )
    assert any("pre-warning" in c for c in concerns)


def test_macro_freshness_decay():
    # Stale macro data from 5 days ago
    stale_macro = {
        "nifty_sectors": [type("SectorQuote", (), {"change_pct": 1.5, "data_date": None})],
        "data_age_days": 5.0
    }
    score, conf = get_institutional_score_with_staleness(stale_macro)
    assert conf < 1.0  # Decayed
    assert score > 50.0  # Still reflects bullish base, but decayed towards 50


def test_vix_spike_and_tail_risk_hedge():
    # VIX spike to 36.0 -> emergency
    spike = monitor_vix_spike(vix_level=36.0, prev_vix=28.0)
    assert spike["emergency_mode_triggered"]
    assert spike["status"] == "SPIKE_EMERGENCY"

    # Tail risk hedge
    assert should_hedge_portfolio(regime_score=40.0, vix=18.0)
    assert should_hedge_portfolio(regime_score=60.0, vix=22.0)
    assert not should_hedge_portfolio(regime_score=70.0, vix=14.0)

    hedge = calculate_hedge_size(total_capital=1000000.0, portfolio_beta=1.3, vix=22.0)
    assert hedge["hedge_capital_inr"] > 20000.0
    assert "recommended_instrument" in hedge


def test_corporate_action_adjustment():
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "Open": [2000.0] * 10,
        "High": [2050.0] * 10,
        "Low": [1980.0] * 10,
        "Close": [2020.0] * 10,
        "Volume": [100000] * 10
    }, index=dates)

    # 1:2 split on day 6 (index 5)
    actions = [{"date": str(dates[5].date()), "type": "SPLIT", "ratio": 2.0}]
    # Mock load_cached
    import data.fetch as fetch_mod
    orig_load = fetch_mod.load_cached
    fetch_mod.load_cached = lambda s: df
    try:
        adj_df = load_cached_adjusted("MOCK.NS", corporate_actions=actions)
        # Pre-split close should be halved (2020 / 2 = 1010)
        assert adj_df["Close"].iloc[0] == 1010.0
        # Post-split close unchanged
        assert adj_df["Close"].iloc[6] == 2020.0
        # Pre-split volume doubled
        assert adj_df["Volume"].iloc[0] == 200000
    finally:
        fetch_mod.load_cached = orig_load


def test_portfolio_manager_tracking_and_tax():
    port = Portfolio(initial_capital=1000000.0)
    pos = port.add_position(
        symbol="RELIANCE.NS",
        entry_price=2800.0,
        quantity=100,
        sector="Oil & Gas",
        atr_at_entry=35.0
    )
    assert pos.symbol == "RELIANCE.NS"
    assert port.cash == 720000.0
    assert port.nav == 1000000.0

    # Update price to 3000 (+7.1%) and aged 340 days
    port.update_position_price("RELIANCE.NS", current_price=3000.0, holding_days=340)
    assert port.nav == 1020000.0
    assert pos.unrealized_pnl == 20000.0

    # Sector exposure
    con = port.get_concentration_by_sector()
    assert "Oil & Gas" in con
    assert con["Oil & Gas"] > 25.0

    # Tax optimization candidate (340 days is 25 days away from 365)
    tax_cands = port.get_tax_optimization_candidates(threshold_days=30)
    assert len(tax_cands) == 1
    assert tax_cands[0]["days_to_ltcg"] == 25
    assert tax_cands[0]["tax_savings_estimate_inr"] == pytest.approx(1500.0)


def test_database_signal_tracking():
    sig_id = log_decision_signal({
        "symbol": "TCS.NS",
        "overall_score": 78.5,
        "suggested_action": "BUY_NOW",
        "regime": "RISK-ON",
        "entry_price": 4100.0,
        "stop_loss": 3980.0,
        "target_price": 4350.0
    })
    assert sig_id > 0

    ok = record_signal_outcome(sig_id, exit_price=4300.0, actual_outcome_pct=4.88, was_correct=True)
    assert ok

    hit = SignalDB.get_action_hitrate("BUY_NOW")
    assert hit["total_signals"] >= 1
    assert hit["winning_signals"] >= 1


def test_api_backtest_queue_and_rate_limiter():
    # 1. Test in-memory rate limiter
    limiter = SimpleRateLimiter(max_requests=2, window_sec=10.0)
    assert limiter.is_allowed("127.0.0.1")
    assert limiter.is_allowed("127.0.0.1")
    assert not limiter.is_allowed("127.0.0.1")  # Rate limit exceeded

    # 2. Test queued backtest endpoints
    client = TestClient(app)
    resp = client.post("/api/backtest/queue/submit", json={"symbols": ["RELIANCE.NS"]})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert job_id is not None

    status_resp = client.get(f"/api/backtest/queue/status/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] in ["QUEUED", "RUNNING", "COMPLETED"]


def test_intraday_flow_divergence():
    # 1. Bearish Distribution: Price up +0.5% but FII dumping -1500 Cr
    div1 = detect_flow_divergence(fii_net_crores=-1500.0, dii_net_crores=200.0, price_change_pct=0.6)
    assert div1["divergence_type"] == "BEARISH_DISTRIBUTION"
    assert div1["alert_triggered"]
    assert div1["signal_bias"] == "BEARISH_REVERSAL_RISK"

    # 2. Bullish Springboard: Price down -0.5% but institutional accumulation +1200 Cr
    div2 = detect_flow_divergence(fii_net_crores=800.0, dii_net_crores=600.0, price_change_pct=-0.4)
    assert div2["divergence_type"] == "BULLISH_DIVERGENCE"
    assert div2["alert_triggered"]
    assert div2["signal_bias"] == "BULLISH_ACCUMULATION"


