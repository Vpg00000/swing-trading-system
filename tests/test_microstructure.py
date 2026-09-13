import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from data.microstructure import (
    NSEBhavcopyFetcher,
    VolumeProfileCalculator,
    BlockDealDetector,
    get_top_deliveries,
    get_symbol_microstructure,
    calculate_order_book_imbalance,
    calculate_bid_ask_spread,
    check_circuit_limit_risk,
    calculate_block_deal_premium,
    is_market_maker_spread_widened,
)
from web_server import app


# ─────────────────────────────────────────────────────────────
# 1. Existing OBI & Microstructure Calculation Tests
# ─────────────────────────────────────────────────────────────

def test_calculate_order_book_imbalance_zero_volume():
    bids = [{"quantity": 0}]
    asks = [{"quantity": 0}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_100_percent_bids():
    bids = [{"quantity": 100}]
    asks = [{"quantity": 0}]
    assert calculate_order_book_imbalance(bids, asks) == 1.0

def test_calculate_order_book_imbalance_100_percent_asks():
    bids = [{"quantity": 0}]
    asks = [{"quantity": 100}]
    assert calculate_order_book_imbalance(bids, asks) == -1.0

def test_calculate_order_book_imbalance_balanced_order_book():
    bids = [{"quantity": 50}]
    asks = [{"quantity": 50}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_partial_depth_data():
    bids = [{"quantity": 10}, {"quantity": 20}]
    asks = [{"quantity": 30}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_variable_depth_input():
    bids = [{"quantity": 10}]
    asks = [{"quantity": 20}, {"quantity": 30}]
    assert calculate_order_book_imbalance(bids, asks) == -0.667

def test_bid_ask_spread_and_circuit_risk():
    spread = calculate_bid_ask_spread(100.0, 101.0)
    assert spread["mid_price"] == 100.5
    assert spread["spread_abs"] == 1.0
    assert spread["spread_pct"] > 0

    circuit = check_circuit_limit_risk(199.0, 200.0, 160.0, threshold_pct=1.0)
    assert circuit["near_circuit"] is True
    assert circuit["reason"] == "NEAR_UPPER_CIRCUIT"


# ─────────────────────────────────────────────────────────────
# 2. NSEBhavcopyFetcher Tests
# ─────────────────────────────────────────────────────────────

def test_bhavcopy_fetcher_instantiation():
    fetcher = NSEBhavcopyFetcher()
    assert fetcher is not None
    assert fetcher.cache_dir.exists()

def test_bhavcopy_fetcher_delivery_data():
    fetcher = NSEBhavcopyFetcher()
    deliv = fetcher.get_delivery_data("RELIANCE.NS")
    assert isinstance(deliv, dict)
    assert "symbol" in deliv
    assert "traded_qty" in deliv
    assert "delivered_qty" in deliv
    assert "delivery_pct" in deliv

def test_bhavcopy_fetcher_top_deliveries():
    fetcher = NSEBhavcopyFetcher()
    top = fetcher.get_top_deliveries(limit=5)
    assert isinstance(top, list)
    assert len(top) <= 5
    if len(top) > 0:
        assert "symbol" in top[0]
        assert "delivery_pct" in top[0]


# ─────────────────────────────────────────────────────────────
# 3. VolumeProfileCalculator Tests
# ─────────────────────────────────────────────────────────────

def test_volume_profile_calculator_basic():
    calculator = VolumeProfileCalculator(num_bins=10, value_area_pct=0.70)
    df = pd.DataFrame({
        "High": [105.0, 106.0, 104.0, 108.0],
        "Low": [99.0, 100.0, 98.0, 101.0],
        "Close": [102.0, 104.0, 100.0, 107.0],
        "Volume": [10000, 15000, 12000, 25000]
    })
    res = calculator.calculate(df)
    assert "poc" in res
    assert "vah" in res
    assert "val" in res
    assert res["total_volume"] == 62000.0
    assert res["vah"] >= res["poc"] >= res["val"]
    assert len(res["profile"]) == 10

def test_volume_profile_calculator_list_input():
    calculator = VolumeProfileCalculator(num_bins=5)
    ohlcv_list = [
        {"high": 50.0, "low": 45.0, "close": 48.0, "volume": 1000},
        {"high": 52.0, "low": 48.0, "close": 51.0, "volume": 2000},
    ]
    res = calculator.calculate(ohlcv_list)
    assert res["total_volume"] == 3000.0
    assert res["vah"] >= res["val"]

def test_volume_profile_calculator_empty():
    calculator = VolumeProfileCalculator()
    res = calculator.calculate([])
    assert res["poc"] == 0.0
    assert res["total_volume"] == 0.0
    assert res["profile"] == []


# ─────────────────────────────────────────────────────────────
# 4. BlockDealDetector Tests
# ─────────────────────────────────────────────────────────────

def test_block_deal_detector():
    detector = BlockDealDetector(min_block_value_inr=1_000_000.0)
    trades = [
        {"price": 500.0, "quantity": 10000, "side": "BUY", "timestamp": "10:00:00"}, # 5,000,000 INR -> Block
        {"price": 500.5, "quantity": 10, "side": "SELL", "timestamp": "10:01:00"},
    ]
    res = detector.detect_block_deals(trades, avg_daily_volume=100000.0, spot_price=500.0)
    assert res["block_trades_count"] >= 1
    assert res["institutional_stance"] in ["INSTITUTIONAL_ACCUMULATION", "INSTITUTIONAL_DISTRIBUTION", "NEUTRAL"]
    assert len(res["block_details"]) >= 1

def test_block_deal_detector_empty():
    detector = BlockDealDetector()
    res = detector.detect_block_deals([])
    assert res["block_trades_count"] == 0
    assert res["anomaly_detected"] is False


# ─────────────────────────────────────────────────────────────
# 5. Helper Function Tests
# ─────────────────────────────────────────────────────────────

def test_get_top_deliveries_helper():
    top = get_top_deliveries(limit=3)
    assert isinstance(top, list)
    assert len(top) <= 3

def test_get_symbol_microstructure_helper():
    micro = get_symbol_microstructure("RELIANCE.NS")
    assert isinstance(micro, dict)
    assert micro["symbol"] == "RELIANCE.NS"
    assert "volume_profile" in micro
    assert "delivery" in micro
    assert "order_book_imbalance" in micro
    assert "bid_ask_spread" in micro
    assert "circuit_risk" in micro
    assert "block_deals" in micro
    assert micro["volume_profile"]["vah"] >= micro["volume_profile"]["val"]


# ─────────────────────────────────────────────────────────────
# 6. Web API Endpoint Tests
# ─────────────────────────────────────────────────────────────

def test_api_deliveries_endpoint():
    client = TestClient(app)
    response = client.get("/api/deliveries?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5

def test_api_microstructure_symbol_endpoint():
    client = TestClient(app)
    response = client.get("/api/microstructure/RELIANCE.NS")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "RELIANCE.NS"
    assert "volume_profile" in data
    assert "delivery" in data

def test_api_microstructure_query_endpoint():
    client = TestClient(app)
    response = client.get("/api/microstructure?symbol=TCS.NS")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "TCS.NS"
    assert "volume_profile" in data