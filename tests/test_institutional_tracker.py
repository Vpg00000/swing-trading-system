"""
Unit tests for data/institutional_tracker.py (Phase 23 tasks).
"""

import os
import pytest
import pandas as pd
from data.institutional_tracker import (
    fetch_nse_bulk_block_deals,
    save_bulk_block_deals_to_db,
    get_historical_bulk_block_deals,
    forecast_fii_dii_flows,
    parse_pit_disclosures,
    calculate_smart_money_index,
    detect_dark_pool_transactions,
    compute_nifty500_accumulation_distribution,
    check_and_send_block_deal_alerts,
    export_bulk_deals_data
)


def test_fetch_and_save_bulk_deals():
    deals = fetch_nse_bulk_block_deals(deal_type="bulk")
    assert len(deals) > 0
    assert any(d["is_marquee_fund"] == 1 for d in deals)

    saved_count = save_bulk_block_deals_to_db(deals)
    assert saved_count > 0

    retrieved = get_historical_bulk_block_deals(symbol="RELIANCE")
    assert len(retrieved) > 0
    assert retrieved[0]["symbol"] == "RELIANCE"


def test_forecast_fii_dii_flows():
    res = forecast_fii_dii_flows(horizon_days=5)
    assert res["forecast_horizon_days"] == 5
    assert "fii_trend" in res
    assert "dii_trend" in res
    assert len(res["forecast_details"]) == 5
    assert "predicted_combined_net_cr" in res["forecast_details"][0]


def test_parse_pit_disclosures():
    disclosures = [
        {
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "person_name": "Mukesh Ambani",
            "person_category": "PROMOTER",
            "transaction_type": "BUY",
            "mode_of_acquisition": "OPEN_MARKET",
            "val_securities_cr": 25.0,
            "post_pledge_pct": 0.0
        },
        {
            "symbol": "ABC_CORP",
            "person_category": "PROMOTER_GROUP",
            "transaction_type": "PLEDGE_CREATE",
            "mode_of_acquisition": "PLEDGE",
            "val_securities_cr": 50.0,
            "post_pledge_pct": 35.0
        }
    ]

    alerts = parse_pit_disclosures(disclosures)
    assert len(alerts) == 2
    assert alerts[0]["is_high_alert"]
    assert "PROMOTER_OPEN_MARKET_BUY" in alerts[0]["alert_reason"]
    assert alerts[1]["is_high_alert"]
    assert "HIGH_PROMOTER_PLEDGE_CREATED" in alerts[1]["alert_reason"]


def test_calculate_smart_money_index():
    bars = [
        {"timestamp": "09:15:00", "open": 100.0, "high": 102.0, "low": 99.5, "close": 101.5},
        {"timestamp": "09:30:00", "open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5},
        {"timestamp": "15:00:00", "open": 103.0, "high": 106.0, "low": 102.8, "close": 105.5},
        {"timestamp": "15:30:00", "open": 105.5, "high": 107.0, "low": 105.0, "close": 106.8}
    ]

    smi_res = calculate_smart_money_index(bars)
    assert smi_res["smi_value"] > 0
    assert "smi_signal" in smi_res


def test_detect_dark_pool_transactions():
    trades = [
        {"symbol": "INFY", "quantity": 100000, "trade_price": 1800.0, "type": "OFF_MARKET"},
        {"symbol": "TCS", "quantity": 100, "trade_price": 4000.0, "type": "NORMAL"}
    ]

    hits = detect_dark_pool_transactions(trades)
    assert len(hits) == 1
    assert hits[0]["symbol"] == "INFY"
    assert hits[0]["detection_type"] == "DARK_POOL_OFF_MARKET_BLOCK"


def test_compute_nifty500_accumulation_distribution():
    scores = compute_nifty500_accumulation_distribution(["RELIANCE", "TCS", "INFY"])
    assert len(scores) == 3
    assert 0 <= scores[0]["accumulation_distribution_score"] <= 100


def test_check_and_send_block_deal_alerts():
    deals = [
        {"symbol": "RELIANCE", "deal_value_cr": 50.0, "client_name": "SBI MF", "buy_sell": "BUY"},
        {"symbol": "WIPRO", "deal_value_cr": 2.0, "client_name": "RETAIL", "buy_sell": "SELL"}
    ]

    alerts = check_and_send_block_deal_alerts(deals, watched_symbols=["RELIANCE"], min_deal_cr=10.0)
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "RELIANCE"


def test_export_bulk_deals_data(tmp_path):
    csv_file = str(tmp_path / "deals.csv")
    out_path = export_bulk_deals_data(format_type="csv", output_path=csv_file)
    assert os.path.exists(out_path)
