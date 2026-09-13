"""
Unit and Integration Tests for Multi-Broker Architecture (Phase 19: T-235 to T-244)
and Market Microstructure Additions (Phase 18: T-225 to T-234).
"""

import pytest
import os
import sqlite3
from pathlib import Path
from engine.broker_interface import (
    BaseBroker,
    KiteBroker,
    UpstoxBroker,
    AngelBroker,
    DhanBrokerWrapper,
    SmartOrderRouter,
    MultiBrokerAggregator,
    BrokerFailoverManager,
    BrokerCredentialVault,
    get_all_brokers_status,
)
from data.microstructure import (
    calculate_spread_and_imbalance_metrics,
    estimate_slippage,
    calculate_vpin,
    VPINCalculator,
    detect_iceberg_orders,
    IcebergOrderDetector,
    get_vah_val_overlays,
    generate_depth_heatmap,
)


def test_kite_broker_adapter():
    kb = KiteBroker(api_key="test_key", access_token="test_token")
    assert kb.broker_name == "zerodha"
    assert kb.is_paper_trading() is True

    prof = kb.get_profile()
    assert prof["user_type"] == "individual"

    margins = kb.get_margins()
    assert "equity" in margins
    assert margins["equity"]["available_margin"] > 0

    quote = kb.get_quote("RELIANCE.NS")
    assert quote["last_price"] > 0

    depth = kb.get_depth("RELIANCE.NS")
    assert len(depth["bids"]) == 5
    assert len(depth["asks"]) == 5

    res = kb.place_order(symbol="RELIANCE.NS", qty=10, order_type="MARKET", side="BUY", price=2500.0)
    assert res["status"] == "SUCCESS"
    assert res["paper_trading"] is True

    orders = kb.get_orders()
    assert len(orders) >= 1
    assert orders[-1]["symbol"] == "RELIANCE.NS"


def test_upstox_broker_adapter():
    ub = UpstoxBroker(api_key="up_key", access_token="up_token")
    assert ub.broker_name == "upstox"
    assert ub.is_paper_trading() is True

    margins = ub.get_margins()
    assert margins["equity"]["net"] > 0

    res = ub.place_order(symbol="TCS.NS", qty=5, order_type="LIMIT", side="BUY", price=3400.0)
    assert res["status"] == "SUCCESS"
    assert res["paper_trading"] is True


def test_angel_broker_adapter():
    ab = AngelBroker(api_key="angel_key", jwt_token="jwt_token")
    assert ab.broker_name == "angelone"
    assert ab.is_paper_trading() is True

    prof = ab.get_profile()
    assert prof["broker"] == "Angel One SmartAPI"

    res = ab.place_order(symbol="INFY.NS", qty=15, order_type="MARKET", side="SELL", price=1500.0)
    assert res["status"] == "SUCCESS"


def test_dhan_broker_wrapper():
    db = DhanBrokerWrapper(client_id="dhan_id", access_token="dhan_token")
    assert db.broker_name == "dhan"
    assert db.get_latency_ms() > 0


def test_paper_trading_mode_toggle():
    kb = KiteBroker()
    assert kb.is_paper_trading() is True

    kb.set_paper_trading(False)
    assert kb.is_paper_trading() is False

    res = kb.place_order(symbol="RELIANCE.NS", qty=10, order_type="MARKET", side="BUY")
    assert res["paper_trading"] is False

    kb.set_paper_trading(True)
    assert kb.is_paper_trading() is True


def test_smart_order_router():
    kb = KiteBroker()
    ub = UpstoxBroker()
    ab = AngelBroker()
    db = DhanBrokerWrapper()

    # Give Zerodha best latency
    kb.set_latency(40.0)
    ub.set_latency(120.0)
    ab.set_latency(150.0)
    db.set_latency(80.0)

    sor = SmartOrderRouter([kb, ub, ab, db])

    winner, route_log = sor.select_optimal_broker(symbol="RELIANCE.NS", qty=10, order_type="MARKET", side="BUY")
    assert winner.broker_name == "zerodha"
    assert route_log["chosen_broker"] == "zerodha"

    res = sor.route_and_execute(symbol="RELIANCE.NS", qty=10, order_type="MARKET", side="BUY")
    assert res["status"] == "SUCCESS"
    assert "routing_info" in res


def test_multi_broker_aggregator():
    kb = KiteBroker()
    ub = UpstoxBroker()
    ab = AngelBroker()
    db = DhanBrokerWrapper()

    agg = MultiBrokerAggregator([kb, ub, ab, db])
    res = agg.get_aggregated_account()

    assert res["connected_brokers_count"] == 4
    assert res["consolidated_cash_balance"] > 0
    assert len(res["broker_breakdown"]) == 4


def test_broker_failover_manager():
    primary = KiteBroker()
    secondary = UpstoxBroker()

    failover = BrokerFailoverManager(primary_broker=primary, secondary_brokers=[secondary], max_latency_threshold_ms=200.0)

    # Normal state
    primary.set_latency(50.0)
    hb = failover.check_heartbeats()
    assert hb["failover_active"] is False
    assert hb["active_broker"] == "zerodha"

    # Trip primary latency
    primary.set_latency(600.0)
    hb_degraded = failover.check_heartbeats()
    assert hb_degraded["failover_active"] is True
    assert failover.get_active_broker().broker_name == "upstox"


def test_broker_credential_vault_aes256(tmp_path):
    test_db = tmp_path / "test_system.db"
    vault = BrokerCredentialVault(db_path=test_db, master_key="test_secret_key_123")

    creds = {
        "api_key": "KITE_KEY_999",
        "api_secret": "SECRET_888",
        "access_token": "TOKEN_777",
    }

    saved = vault.save_credentials("zerodha", creds)
    assert saved is True

    configured = vault.list_configured_brokers()
    assert "zerodha" in configured

    fetched = vault.get_credentials("zerodha")
    assert fetched is not None
    assert fetched["api_key"] == "KITE_KEY_999"
    assert fetched["api_secret"] == "SECRET_888"


def test_broker_status_provider():
    status_list = get_all_brokers_status()
    assert len(status_list) >= 4
    for b_stat in status_list:
        assert "broker" in b_stat
        assert "latency_ms" in b_stat
        assert "ws_health" in b_stat
        assert "paper_trading" in b_stat


def test_microstructure_phase18_metrics():
    bids = [{"price": 100.0, "quantity": 1000}, {"price": 99.5, "quantity": 1500}]
    asks = [{"price": 100.5, "quantity": 800}, {"price": 101.0, "quantity": 1200}]

    metrics = calculate_spread_and_imbalance_metrics(bids, asks)
    assert metrics["buy_volume"] == 2500
    assert metrics["sell_volume"] == 2000
    assert metrics["spread_abs"] == 0.5
    assert metrics["top_bid"] == 100.0
    assert metrics["top_ask"] == 100.5

    slippage = estimate_slippage(bids, asks, order_size=500, side="BUY")
    assert slippage["side"] == "BUY"
    assert slippage["expected_vwap"] == 100.5
    assert slippage["slippage_inr"] == 0.0

    slippage_large = estimate_slippage(bids, asks, order_size=1500, side="BUY")
    assert slippage_large["expected_vwap"] > 100.5
    assert slippage_large["slippage_abs"] > 0.0

    # VPIN Toxicity
    trades = [
        {"price": 100.0, "quantity": 5000, "side": "BUY"},
        {"price": 100.2, "quantity": 6000, "side": "BUY"},
        {"price": 100.1, "quantity": 4000, "side": "BUY"},
    ]
    vpin = calculate_vpin(trades, bucket_size=5000.0, num_buckets=3)
    assert "vpin" in vpin
    assert vpin["vpin"] >= 0.0

    # Iceberg Detector
    ice_trades = [
        {"price": 100.0, "quantity": 3000, "side": "BUY", "timestamp": "10:00"},
        {"price": 100.0, "quantity": 3000, "side": "BUY", "timestamp": "10:01"},
        {"price": 100.0, "quantity": 3000, "side": "BUY", "timestamp": "10:02"},
    ]
    depth_snaps = [{"asks": [{"price": 100.0, "quantity": 1000}]}]
    iceberg_res = detect_iceberg_orders(ice_trades, depth_snapshots=depth_snaps)
    assert iceberg_res["icebergs_detected"] >= 1
    assert iceberg_res["iceberg_orders"][0]["price"] == 100.0

    # VAH/VAL Overlay
    overlay = get_vah_val_overlays(trades)
    assert "chart_overlays" in overlay
    assert "poc_line" in overlay["chart_overlays"]

    # Heatmap
    heatmap = generate_depth_heatmap(symbol="RELIANCE.NS")
    assert "matrix" in heatmap
    assert len(heatmap["matrix"]) > 0
