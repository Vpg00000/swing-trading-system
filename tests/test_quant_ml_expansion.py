"""
Comprehensive Pytest Test Suite for Quant ML & Risk Expansion Tasks:
- TASK-046: ML Signals Expansion Predictor (engine/ml_signals.py)
- TASK-047: ATR/GARCH Volatility Trailing Stop Loss Engine (engine/portfolio_optimizer.py)
- TASK-048: Factor Exposure & Style Tilt Calculator (engine/portfolio_optimizer.py)
- TASK-049: Institutional Dark Pool / Block Trade Volume Anomaly Detector (data/microstructure.py)
- TASK-050: Nifty Options Tail-Risk Hedging Engine (engine/options_hedge.py)
"""

import pytest
import numpy as np
import pandas as pd

# Imports from engine and data modules
from engine.ml_signals import (
    compute_technical_features,
    generate_expansion_labels,
    MomentumExpansionPredictor,
    predict_expansion_probability,
    train_expansion_model,
)
from engine.portfolio_optimizer import (
    calculate_garch_volatility,
    calculate_atr_garch_trailing_stop,
    calculate_factor_exposures,
)
from data.microstructure import (
    detect_dark_pool_block_anomalies,
    InstitutionalBlockDetector,
)
from engine.options_hedge import (
    bs_option_price,
    calculate_tail_risk_hedge,
    OptionsTailRiskHedgeEngine,
)


# ── Helper Fixture: Synthetic OHLCV Market Data ──────────────────────────────

@pytest.fixture
def sample_ohlcv_data() -> pd.DataFrame:
    """Generates 120 bars of synthetic trend and momentum OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=120, freq="B")
    
    # Simulate trending prices with cyclical momentum
    base_price = 100.0
    returns = np.random.normal(0.001, 0.015, size=120)
    # Add a strong momentum trend section
    returns[40:70] += 0.005
    price_path = base_price * np.exp(np.cumsum(returns))
    
    highs = price_path * (1.0 + np.abs(np.random.normal(0.005, 0.003, size=120)))
    lows = price_path * (1.0 - np.abs(np.random.normal(0.005, 0.003, size=120)))
    opens = lows + (highs - lows) * np.random.uniform(0.2, 0.8, size=120)
    volumes = np.random.randint(50000, 200000, size=120).astype(float)
    # Volume spike during trend
    volumes[45:65] *= 2.5

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": price_path,
        "volume": volumes,
    }, index=dates)


# ── TASK-046: ML Signals Expansion Predictor Tests ─────────────────────────

def test_compute_technical_features(sample_ohlcv_data):
    features = compute_technical_features(sample_ohlcv_data)
    assert isinstance(features, pd.DataFrame)
    assert len(features) == len(sample_ohlcv_data)
    
    required_cols = [
        "rsi_14", "macd", "macd_signal", "macd_hist", "bb_pct_b",
        "atr_ratio", "vol_ratio_20", "ret_5d", "ret_10d", "ret_15d",
        "sma_20_ratio", "sma_50_ratio", "sma_200_ratio",
        "realized_vol_10d", "realized_vol_20d"
    ]
    for col in required_cols:
        assert col in features.columns, f"Missing feature column: {col}"

    assert not features.isna().any().any(), "Features DataFrame contains NaNs"


def test_generate_expansion_labels(sample_ohlcv_data):
    labels = generate_expansion_labels(sample_ohlcv_data, horizon_days=10, threshold_pct=0.03)
    assert isinstance(labels, pd.Series)
    assert len(labels) == len(sample_ohlcv_data)
    
    # Check valid labels are binary 0 or 1
    valid_labels = labels.dropna()
    assert set(valid_labels.unique()).issubset({0, 1})
    # Last horizon_days should be NaN due to lookahead boundary
    assert labels.iloc[-10:].isna().all()


def test_momentum_expansion_predictor_fit_predict(sample_ohlcv_data):
    predictor = MomentumExpansionPredictor(model_type="auto")
    metrics = predictor.fit(sample_ohlcv_data, horizon_days=10, threshold_pct=0.03)
    
    assert predictor.is_trained is True
    assert "roc_auc" in metrics
    assert metrics["roc_auc"] >= 0.50
    assert "active_model_type" in metrics

    # Test predict_proba
    probas = predictor.predict_proba(sample_ohlcv_data)
    assert isinstance(probas, np.ndarray)
    assert probas.shape == (len(sample_ohlcv_data), 2)
    assert np.all(probas >= 0.0) and np.all(probas <= 1.0)

    # Test predict_signal
    res = predictor.predict_signal(sample_ohlcv_data)
    assert "expansion_probability" in res
    assert 0.0 <= res["expansion_probability"] <= 1.0
    assert res["signal"] in ["STRONG_BUY", "BUY", "NEUTRAL", "AVOID"]
    assert "top_features" in res
    assert len(res["top_features"]) > 0


def test_predict_expansion_probability_wrapper(sample_ohlcv_data):
    res = predict_expansion_probability(sample_ohlcv_data)
    assert isinstance(res, dict)
    assert "expansion_probability" in res
    assert "signal" in res


# ── TASK-047: ATR/GARCH Volatility Trailing Stop Loss Engine Tests ───────────

def test_calculate_garch_volatility():
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.015, size=100)
    garch_res = calculate_garch_volatility(returns)
    
    assert "current_volatility" in garch_res
    assert "annualized_volatility" in garch_res
    assert "volatility_ratio" in garch_res
    assert garch_res["current_volatility"] > 0
    assert garch_res["annualized_volatility"] > 0
    assert garch_res["volatility_ratio"] > 0


def test_calculate_atr_garch_trailing_stop_normal(sample_ohlcv_data):
    current_price = float(sample_ohlcv_data["close"].iloc[-1])
    res = calculate_atr_garch_trailing_stop(
        data=sample_ohlcv_data,
        current_price=current_price,
        position_type="LONG",
        atr_period=14,
        base_atr_multiplier=2.0,
        vix_value=14.0
    )
    
    assert res["position_type"] == "LONG"
    assert res["stop_loss_price"] < current_price
    assert res["high_watermark"] >= current_price
    assert res["effective_multiplier"] >= 2.0
    assert res["regime"] == "NORMAL_VOLATILITY"


def test_calculate_atr_garch_trailing_stop_vix_expansion(sample_ohlcv_data):
    current_price = float(sample_ohlcv_data["close"].iloc[-1])
    
    stop_normal = calculate_atr_garch_trailing_stop(
        data=sample_ohlcv_data,
        current_price=current_price,
        vix_value=15.0,
        base_atr_multiplier=2.0
    )
    
    stop_high_vix = calculate_atr_garch_trailing_stop(
        data=sample_ohlcv_data,
        current_price=current_price,
        vix_value=30.0,
        base_atr_multiplier=2.0
    )
    
    # Effective multiplier and stop distance should widen during VIX spike
    assert stop_high_vix["effective_multiplier"] > stop_normal["effective_multiplier"]
    assert stop_high_vix["stop_loss_price"] < stop_normal["stop_loss_price"]
    assert stop_high_vix["regime"] in ["HIGH_VOLATILITY_EXPANSION", "EXTREME_VOLATILITY"]


def test_calculate_atr_garch_trailing_stop_short_position():
    prices = [100.0, 98.0, 95.0, 92.0, 90.0]
    res = calculate_atr_garch_trailing_stop(
        data=prices,
        current_price=90.0,
        position_type="SHORT",
        base_atr_multiplier=2.0
    )
    assert res["position_type"] == "SHORT"
    assert res["stop_loss_price"] > 90.0


# ── TASK-048: Factor Exposure & Style Tilt Calculator Tests ─────────────────

def test_calculate_factor_exposures_holding_weights():
    weights = {"RELIANCE": 0.4, "TCS": 0.3, "INFY": 0.3}
    asset_metrics = {
        "RELIANCE": {"momentum": 0.8, "value": 0.3, "quality": 0.7, "low_volatility": 0.4, "beta": 1.1},
        "TCS": {"momentum": 0.75, "value": 0.4, "quality": 0.85, "low_volatility": 0.6, "beta": 0.8},
        "INFY": {"momentum": 0.70, "value": 0.5, "quality": 0.80, "low_volatility": 0.5, "beta": 0.9},
    }

    res = calculate_factor_exposures(holding_weights=weights, asset_metrics=asset_metrics)
    assert "factor_exposures" in res
    exposures = res["factor_exposures"]
    
    assert exposures["Momentum"] > 0.70
    assert exposures["Quality"] > 0.70
    assert res["style_tilt"] in ["MOMENTUM_TILT", "QUALITY_TILT"]
    assert "factor_breakdown_chart" in res


def test_calculate_factor_exposures_regression():
    np.random.seed(42)
    n = 60
    f_mom = np.random.normal(0.001, 0.01, size=n)
    f_val = np.random.normal(0.0005, 0.008, size=n)
    f_mkt = np.random.normal(0.001, 0.012, size=n)
    
    # Portfolio return constructed with strong momentum tilt
    p_ret = 0.0002 + 0.6 * f_mom + 0.2 * f_val + 0.9 * f_mkt + np.random.normal(0, 0.002, size=n)

    factor_df = pd.DataFrame({"Momentum": f_mom, "Value": f_val, "Market_Beta": f_mkt})
    res = calculate_factor_exposures(portfolio_returns=p_ret, factor_matrix=factor_df)
    
    assert "factor_exposures" in res
    assert res["r_squared"] > 0.50
    assert res["factor_exposures"]["Momentum"] > 0.40


def test_calculate_factor_exposures_overconcentration_alert():
    weights = {"STOCK_A": 1.0}
    asset_metrics = {"STOCK_A": {"momentum": 0.95, "value": 0.1, "quality": 0.2, "low_volatility": 0.1, "beta": 1.45}}
    
    res = calculate_factor_exposures(holding_weights=weights, asset_metrics=asset_metrics)
    assert res["is_overconcentrated"] is True
    assert len(res["warnings"]) > 0
    assert "Momentum" in res["overconcentrated_factors"] or "Market_Beta" in res["overconcentrated_factors"]


# ── TASK-049: Institutional Dark Pool / Block Trade Anomaly Detector Tests ──

def test_detect_dark_pool_block_anomalies_empty():
    res = detect_dark_pool_block_anomalies([], avg_daily_volume=100000.0)
    assert res["anomaly_detected"] is False
    assert res["block_trades_count"] == 0


def test_detect_dark_pool_block_anomalies_large_block():
    trades = [
        {"price": 1000.0, "quantity": 15000, "side": "BUY", "timestamp": "09:30:00"},  # ₹1.5 Crore single trade
        {"price": 1000.5, "quantity": 200, "side": "BUY", "timestamp": "09:31:00"},
        {"price": 1001.0, "quantity": 150, "side": "SELL", "timestamp": "09:32:00"},
    ]
    res = detect_dark_pool_block_anomalies(trades, avg_daily_volume=500000.0, spot_price=1000.0)
    
    assert res["anomaly_detected"] is True
    assert res["block_trades_count"] >= 1
    assert res["total_block_value_inr"] >= 15_000_000.0
    assert res["institutional_stance"] == "INSTITUTIONAL_ACCUMULATION"
    assert len(res["alerts"]) > 0


def test_detect_dark_pool_block_anomalies_iceberg():
    trades = [
        {"price": 500.0, "quantity": 10000, "side": "BUY"},
        {"price": 500.1, "quantity": 10000, "side": "BUY"},
        {"price": 500.05, "quantity": 10000, "side": "BUY"},
    ]
    res = detect_dark_pool_block_anomalies(trades, avg_daily_volume=500000.0, spot_price=500.0)
    assert res["iceberg_accumulation_detected"] is True
    assert res["anomaly_score"] >= 30.0


def test_institutional_block_detector_class():
    detector = InstitutionalBlockDetector(min_block_value_inr=1_000_000.0)
    trades = [{"price": 100.0, "quantity": 20000, "side": "BUY"}]  # ₹20 Lakhs trade
    res = detector.analyze(trades, avg_daily_volume=200000.0, spot_price=100.0)
    assert res["block_trades_count"] == 1


# ── TASK-050: Nifty Options Tail-Risk Hedging Engine Tests ───────────────────

def test_bs_option_price_put():
    greeks = bs_option_price(
        spot=22000.0,
        strike=21000.0,
        time_to_expiry_years=30 / 365.0,
        risk_free_rate=0.065,
        volatility=0.20,
        option_type="PUT"
    )
    assert "price" in greeks
    assert greeks["price"] > 0
    assert greeks["delta"] < 0  # Put delta is negative
    assert greeks["gamma"] > 0
    assert greeks["vega"] > 0
    assert greeks["theta"] < 0


def test_calculate_tail_risk_hedge_no_trigger():
    # Low beta and normal VIX -> No hedge trigger
    res = calculate_tail_risk_hedge(
        portfolio_value_inr=5_000_000.0,
        portfolio_beta=0.70,
        nifty_spot=22000.0,
        india_vix=14.0
    )
    assert res["hedge_required"] is False
    assert res["num_lots"] == 0
    assert res["recommended_action"] == "NO_HEDGE_NEEDED"


def test_calculate_tail_risk_hedge_triggered():
    # High portfolio beta (1.20) and VIX spike (22.0) -> Tail risk hedge triggered
    res = calculate_tail_risk_hedge(
        portfolio_value_inr=10_000_000.0,
        portfolio_beta=1.20,
        nifty_spot=22000.0,
        india_vix=22.0,
        days_to_expiry=30,
        max_hedge_cost_pct=0.03
    )
    
    assert res["hedge_required"] is True
    assert res["recommended_action"] == "BUY_NIFTY_OTM_PUTS"
    assert res["recommended_strike"] is not None
    assert res["recommended_strike"] < 22000.0  # Out-of-the-money Put strike
    assert res["num_lots"] > 0
    assert res["num_contracts"] > 0
    assert res["total_hedge_cost"] > 0
    assert res["hedge_cost_pct"] <= 3.0  # Tail risk hedge cost capped at 3%
    assert res["max_tail_loss_capped"] is True
    assert "greeks" in res


def test_options_tail_risk_hedge_engine_class():
    engine = OptionsTailRiskHedgeEngine(beta_threshold=0.80, vix_threshold=16.0)
    res = engine.evaluate_portfolio_hedge(
        portfolio_value_inr=8_000_000.0,
        portfolio_beta=0.95,
        nifty_spot=22000.0,
        india_vix=19.0
    )
    assert res["hedge_required"] is True
    assert res["num_lots"] >= 1
