"""
Unit tests for Corporate Filings & XBRL Parser Engine (TASK-055).
Verifies CorporateFilingsParser class, XBRL parsing, caching, sentiment flagging, and /api/filings endpoint.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from data.xbrl_parser import (
    CorporateFilingsParser,
    get_latest_filings,
    parse_xbrl_financial_statement,
)
from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_categorize_filing():
    parser = CorporateFilingsParser()
    assert parser.categorize_filing("Q2 Financial Results & Audited Financial Statements") == "Financial Results"
    assert parser.categorize_filing("Outcome of Board Meeting held on Sept 10, 2026") == "Board Meeting"
    assert parser.categorize_filing("SEBI PIT Disclosure: Promoter acquired 50,000 equity shares") == "Insider Disclosures"
    assert parser.categorize_filing("Board approves Interim Dividend and Bonus Shares") == "Corporate Actions"
    assert parser.categorize_filing("Secures ₹1,200 Cr International Pipe Order") == "Orders & Deals"
    assert parser.categorize_filing("Investor Presentation & Earnings Concall Transcript") == "Investor Presentation"


def test_sentiment_analysis():
    parser = CorporateFilingsParser()
    assert parser.analyze_sentiment("Secures Rs 2,400 Cr expansion contract", category="Orders & Deals") == "BULLISH"
    assert parser.analyze_sentiment("Net profit increases 25% YoY with record revenue") == "BULLISH"
    assert parser.analyze_sentiment("Net loss recorded due to plant shutdown and penalty") == "BEARISH"
    assert parser.analyze_sentiment("Notice of Board Meeting to consider Q2 results") == "NEUTRAL"
    assert parser.analyze_sentiment("Promoter entity acquired 150,000 shares", category="Insider Disclosures") == "BULLISH"


def test_get_filings_structure_and_filtering():
    filings = get_latest_filings(limit=10)
    assert isinstance(filings, list)
    assert len(filings) > 0

    for f in filings:
        assert "symbol" in f
        assert "category" in f
        assert "subject" in f
        assert "date" in f
        assert "sentiment_flag" in f
        assert f["sentiment_flag"] in ["BULLISH", "BEARISH", "NEUTRAL"]

    # Test category filtering
    bm_filings = get_latest_filings(limit=10, category="Board Meeting")
    for f in bm_filings:
        assert "board meeting" in f["category"].lower()

    # Test limit constraint
    limited_filings = get_latest_filings(limit=3)
    assert len(limited_filings) <= 3


def test_caching_mechanism(tmp_path):
    test_cache_file = tmp_path / "test_filings_cache.json"
    parser = CorporateFilingsParser(cache_file=test_cache_file, cache_ttl=60)

    # First call - creates cache file
    filings1 = parser.get_filings(limit=5)
    assert test_cache_file.exists()

    # Read cached data directly from file
    cached_content = test_cache_file.read_text(encoding="utf-8")
    assert "RELIANCE.NS" in cached_content or len(filings1) > 0

    # Second call - uses disk or memory cache
    filings2 = parser.get_filings(limit=5)
    assert len(filings1) == len(filings2)


def test_xbrl_financial_statement_parser():
    json_payload = '{"revenue": 12500.50, "net_profit": 3200.0, "ebitda": 4500.0, "auditor_qualification": false}'
    res = parse_xbrl_financial_statement(json_payload)

    assert res["revenue_inr_cr"] == 12500.50
    assert res["net_profit_inr_cr"] == 3200.0
    assert res["ebitda_inr_cr"] == 4500.0
    assert res["auditor_qualification"] is False
    assert res["status"] == "PARSED"

    # Test text/regex fallback
    text_payload = "Quarterly Revenue: 8,500.00 Cr, Net Profit: 1,450.50 Cr"
    res_text = parse_xbrl_financial_statement(text_payload)
    assert res_text["revenue_inr_cr"] == 8500.00
    assert res_text["net_profit_inr_cr"] == 1450.50


def test_api_filings_endpoint(client):
    response = client.get("/api/filings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert "symbol" in first
    assert "category" in first
    assert "subject" in first
    assert "date" in first
    assert "sentiment_flag" in first
    assert first["sentiment_flag"] in ["BULLISH", "BEARISH", "NEUTRAL"]

    # Test query params
    filtered_res = client.get("/api/filings?limit=2&category=Board Meeting")
    assert filtered_res.status_code == 200
    filtered_data = filtered_res.json()
    assert isinstance(filtered_data, list)
    assert len(filtered_data) <= 2
    for item in filtered_data:
        assert "board meeting" in item["category"].lower()
