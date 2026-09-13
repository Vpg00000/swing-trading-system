"""
tests/test_news_and_tax.py — Unit Tests for News Aggregator & Tax Dashboard (Phase 3 Task D).
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from engine.news_aggregator import NewsAggregator, get_latest_news, Article
from engine.tax_calculator import TaxCalculator, calculate_tax_summary, identify_tax_loss_harvesting_candidates
from web_server import app


# ── NEWS AGGREGATOR TESTS ───────────────────────────────────────────────────

def test_news_aggregator_sentiment_scoring():
    agg = NewsAggregator()

    bullish_text = "Reliance Industries reports 25% jump in Q1 net profit, rally continues."
    sentiment, score = agg.score_sentiment(bullish_text)
    assert sentiment == "BULLISH"
    assert score > 0.0

    bearish_text = "HDFC Bank faces steep loss and margin contraction amid probe."
    sentiment, score = agg.score_sentiment(bearish_text)
    assert sentiment == "BEARISH"
    assert score < 0.0

    neutral_text = "Company schedules board meeting to discuss routine financial statements."
    sentiment, score = agg.score_sentiment(neutral_text)
    assert sentiment == "NEUTRAL"
    assert score == 0.0


def test_news_aggregator_symbol_sector_detection():
    agg = NewsAggregator()

    symbols, sector = agg.detect_symbols_and_sector("TCS wins major cloud transformation deal in IT space.")
    assert "TCS" in symbols
    assert sector == "IT"

    symbols, sector = agg.detect_symbols_and_sector("Reliance Oil and Gas division expands green energy capacity.")
    assert "RELIANCE" in symbols
    assert sector == "Energy"


def test_news_aggregator_rss_xml_parsing():
    agg = NewsAggregator()
    sample_rss_xml = b"""<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
    <channel>
        <title>Markets News</title>
        <link>https://example.com</link>
        <item>
            <title>Infosys Posts Strong Revenue Growth; IT Stocks Soar</title>
            <description>Infosys reported positive Q2 guidance with software deal momentum.</description>
            <link>https://example.com/infosys-q2</link>
            <pubDate>Thu, 10 Sep 2026 10:00:00 GMT</pubDate>
        </item>
    </channel>
    </rss>"""

    mock_response = MagicMock()
    mock_response.read.return_value = sample_rss_xml
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        articles = agg.parse_rss_feed("https://example.com/rss.xml")
        assert len(articles) == 1
        art = articles[0]
        assert "Infosys" in art["title"]
        assert art["sentiment"] == "BULLISH"
        assert "INFY" in art["symbols"] or "IT" in art["sector"]


def test_news_aggregator_fetch_and_filter():
    agg = NewsAggregator()
    all_articles = agg.fetch_articles()
    assert len(all_articles) > 0

    # Test filter by symbol
    reliance_articles = agg.filter_news(all_articles, symbol="RELIANCE", limit=10)
    assert len(reliance_articles) > 0
    for art in reliance_articles:
        assert "RELIANCE" in art["symbols"] or "RELIANCE" in art["title"].upper() or "RELIANCE" in art["summary"].upper()

    # Test filter by sector
    it_articles = agg.filter_news(all_articles, sector="IT", limit=10)
    assert len(it_articles) > 0

    # Test get_latest_news helper
    latest = get_latest_news(limit=5)
    assert len(latest) <= 5


# ── TAX CALCULATOR TESTS ───────────────────────────────────────────────────

def test_tax_calculator_liability_stcg_and_ltcg():
    calc = TaxCalculator(stcg_rate=0.20, ltcg_rate=0.125, ltcg_exemption_limit=125_000.0)

    realized_trades = [
        {"symbol": "TCS.NS", "pnl": 50_000.0, "holding_days": 180},       # STCG gain Rs 50k
        {"symbol": "INFY.NS", "pnl": -10_000.0, "holding_days": 90},       # STCG loss Rs 10k -> Net STCG Rs 40k @ 20% = Rs 8,000 tax
        {"symbol": "RELIANCE.NS", "pnl": 225_000.0, "holding_days": 400},  # LTCG gain Rs 225k -> Exemption Rs 125k -> Taxable LTCG Rs 100k @ 12.5% = Rs 12,500 tax
    ]

    liability = calc.calculate_tax_liability(realized_trades)

    assert liability["net_stcg_gain_inr"] == 40_000.0
    assert liability["stcg_tax_liability_inr"] == 8_000.0  # 40,000 * 0.20
    assert liability["net_ltcg_gain_inr"] == 225_000.0
    assert liability["ltcg_exemption_used_inr"] == 125_000.0
    assert liability["taxable_ltcg_gain_inr"] == 100_000.0
    assert liability["ltcg_tax_liability_inr"] == 12_500.0  # 100,000 * 0.125
    assert liability["total_tax_liability_inr"] == 20_500.0  # 8,000 + 12,500


def test_tax_calculator_ltcg_below_exemption_threshold():
    calc = TaxCalculator(stcg_rate=0.20, ltcg_rate=0.125, ltcg_exemption_limit=125_000.0)

    realized_trades = [
        {"symbol": "HDFCBANK.NS", "pnl": 100_000.0, "holding_days": 500},  # LTCG gain Rs 100k (< 125k threshold)
    ]

    liability = calc.calculate_tax_liability(realized_trades)

    assert liability["net_ltcg_gain_inr"] == 100_000.0
    assert liability["ltcg_exemption_used_inr"] == 100_000.0
    assert liability["taxable_ltcg_gain_inr"] == 0.0
    assert liability["ltcg_tax_liability_inr"] == 0.0
    assert liability["total_tax_liability_inr"] == 0.0


def test_tax_loss_harvesting():
    calc = TaxCalculator(stcg_rate=0.20, ltcg_rate=0.125)

    holdings = [
        {"symbol": "TATAMOTORS.NS", "quantity": 100, "buy_price": 1000.0, "current_price": 800.0, "holding_days": 120},  # Loss Rs 20k STCG
        {"symbol": "SBIN.NS", "quantity": 50, "buy_price": 600.0, "current_price": 700.0, "holding_days": 200},          # Profit Rs 5k
        {"symbol": "WIPRO.NS", "quantity": 200, "buy_price": 500.0, "current_price": 400.0, "holding_days": 450},        # Loss Rs 20k LTCG
    ]

    res = calc.calculate_tax_loss_harvesting(holdings, realized_stcg_gains=30_000.0, realized_ltcg_gains=200_000.0)

    assert res["candidate_count"] == 2
    assert res["total_harvestable_stcg_loss_inr"] == 20_000.0
    assert res["total_harvestable_ltcg_loss_inr"] == 20_000.0
    # Estimated savings: (20,000 * 0.20) + (20,000 * 0.125) = 4,000 + 2,500 = 6,500
    assert res["estimated_total_tax_savings_inr"] == 6_500.0


def test_calculate_tax_summary_helper():
    summary = calculate_tax_summary()
    assert "tax_liability" in summary
    assert "tax_loss_harvesting" in summary
    assert "summary" in summary
    assert summary["summary"]["stcg_tax_inr"] >= 0.0
    assert summary["summary"]["ltcg_tax_inr"] >= 0.0


# ── FASTAPI WEB ENDPOINT TESTS ───────────────────────────────────────────────

client = TestClient(app)

def test_api_news_endpoint():
    response = client.get("/api/news?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "news" in data
    assert isinstance(data["news"], list)


def test_api_tax_endpoint():
    response = client.get("/api/tax")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "tax" in data
    assert "tax_liability" in data["tax"]
    assert "tax_loss_harvesting" in data["tax"]
