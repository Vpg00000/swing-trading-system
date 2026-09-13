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
from engine.decision import evaluate_decision, classify_action
from engine.momentum import (
    compute_volume_weighted_momentum,
    relative_strength_within_sector,
    calculate_beta_adjusted_size,
    Candidate
)
from engine.scoring import (
    calculate_mean_reversion_score,
    calculate_confluence_score
)
from engine.backtest import run_standard_momentum_backtest
from web_server import app


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

