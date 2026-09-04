"""
Unit tests for data/institutional_flow.py - TASK-010 Institutional Flow Engine.
Verifies marquee fund tagging, silent accumulation, ESOP filtering, free float calculations,
MF scheme dump flags, and symbol/market flow analysis.
"""

import pytest
from data.institutional_flow import (
    tag_bulk_deal_counterparty,
    detect_silent_accumulation,
    filter_esop_insider_transactions,
    calculate_effective_free_float,
    check_mf_scheme_dump,
    analyze_symbol_institutional_flow,
    get_market_institutional_flow_summary
)


def test_tag_bulk_deal_counterparty():
    res1 = tag_bulk_deal_counterparty("SBI MUTUAL FUND A/C MAGNUM COMBO")
    assert res1["is_marquee_fund"] is True
    assert res1["category"] == "MARQUEE_INSTITUTIONAL"

    res2 = tag_bulk_deal_counterparty("VANGUARD TOTAL STOCK MARKET INDEX FUND")
    assert res2["is_marquee_fund"] is True

    res3 = tag_bulk_deal_counterparty("RAMESH KUMAR SHARMA")
    assert res3["is_marquee_fund"] is False
    assert res3["category"] == "RETAIL_PROMOTER_OTHER"


def test_detect_silent_accumulation():
    # Silent accumulation: Delivery >= 65% and abs(price_change) <= 0.5%
    sa1 = detect_silent_accumulation(68.5, 0.20)
    assert sa1["is_silent_accumulation"] is True
    assert sa1["signal"] == "SILENT_ACCUMULATION_DETECTED"

    # High delivery but price expansion (> 0.5%) -> Not silent
    sa2 = detect_silent_accumulation(70.0, 2.5)
    assert sa2["is_silent_accumulation"] is False
    assert sa2["signal"] == "NORMAL"

    # Low delivery -> Not silent
    sa3 = detect_silent_accumulation(45.0, 0.10)
    assert sa3["is_silent_accumulation"] is False


def test_filter_esop_insider_transactions():
    assert filter_esop_insider_transactions("BUY", "ESOP ALLOTMENT") is False
    assert filter_esop_insider_transactions("BUY", "OFF MARKET TRANSFER") is False
    assert filter_esop_insider_transactions("PLEDGE CREATION", "PROMOTER") is False

    assert filter_esop_insider_transactions("MARKET PURCHASE", "PROMOTER GROUP") is True
    assert filter_esop_insider_transactions("MARKET SALE", "DESIGNATED PERSON") is True


def test_calculate_effective_free_float():
    ff1 = calculate_effective_free_float(promoter_pct=50.0, fii_pct=20.0, dii_pct=10.0)
    assert ff1["free_float_pct"] == 20.0
    assert ff1["is_illiquid"] is False
    assert ff1["warning"] == "LIQUID_FLOAT"

    ff2 = calculate_effective_free_float(promoter_pct=75.0, fii_pct=10.0, dii_pct=8.0)
    assert ff2["free_float_pct"] == 7.0
    assert ff2["is_illiquid"] is True
    assert ff2["warning"] == "ZERO_FREE_FLOAT_RISK"


def test_check_mf_scheme_dump():
    dump1 = check_mf_scheme_dump(current_scheme_count=10, prev_scheme_count=14)
    assert dump1["schemes_dropped"] == 4
    assert dump1["is_mf_dump"] is True
    assert dump1["warning"] == "MF_SCHEME_DUMP_WARNING"

    dump2 = check_mf_scheme_dump(current_scheme_count=12, prev_scheme_count=13)
    assert dump2["schemes_dropped"] == 1
    assert dump2["is_mf_dump"] is False
    assert dump2["warning"] == "STABLE"


def test_analyze_symbol_institutional_flow():
    analysis = analyze_symbol_institutional_flow("RELIANCE", delivery_pct=72.0, price_change_pct=0.15)
    assert isinstance(analysis, dict)
    assert analysis["symbol"] == "RELIANCE"
    assert "flow_score" in analysis
    assert "signal" in analysis
    assert analysis["silent_accumulation"]["is_silent_accumulation"] is True
    assert "free_float" in analysis


def test_get_market_institutional_flow_summary():
    summary = get_market_institutional_flow_summary(["RELIANCE", "TCS"])
    assert isinstance(summary, dict)
    assert "fii_dii_summary" in summary
    assert "fii_dii_history" in summary
    assert "top_symbol_flows" in summary
    assert summary["data_source"] == "NSE_OFFICIAL_REALTIME"
