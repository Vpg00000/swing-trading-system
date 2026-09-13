"""
Unit tests for engine/sentiment_engine.py (Task T-293).
Tests Social Sentiment, News Parser, Correlation Score, Sentiment Spike Alerts,
Word Cloud Visual Generator, Earnings Transcript Tone Shift, and SQLite Alt-Data storage.
"""

import pytest
from engine.sentiment_engine import (
    analyze_social_sentiment,
    parse_financial_news_sentiment,
    calculate_social_price_correlation,
    detect_sentiment_spike,
    generate_word_cloud_data,
    detect_earnings_transcript_tone_shift,
    save_sentiment_record,
    get_sentiment_history
)


def test_analyze_social_sentiment():
    posts = [
        {"text": "$RELIANCE massive breakout! High volume target upside #bullish"},
        {"text": "Strong earnings for RELIANCE. Expanding margins multibagger buy"}
    ]
    res = analyze_social_sentiment(symbol="RELIANCE", posts=posts)
    assert res["symbol"] == "RELIANCE"
    assert res["composite_score"] > 0.0
    assert res["sentiment_label"] == "BULLISH"
    assert res["buzz_volume"] == 2


def test_parse_financial_news_sentiment():
    news = [
        {"headline": "TCS Revenue Jumped 15% YoY, Margin Expands", "symbol": "TCS", "source": "Moneycontrol"}
    ]
    parsed = parse_financial_news_sentiment(news)
    assert len(parsed) == 1
    assert parsed[0]["symbol"] == "TCS"
    assert parsed[0]["news_sentiment_score"] > 0
    assert parsed[0]["sentiment_label"] == "BULLISH"


def test_calculate_social_price_correlation():
    res = calculate_social_price_correlation(symbol="INFY")
    assert res["symbol"] == "INFY"
    assert -1.0 <= res["pearson_correlation"] <= 1.0
    assert "historical_series" in res


def test_detect_sentiment_spike():
    normal = detect_sentiment_spike(symbol="TCS", current_buzz_count=110, historical_buzz_counts=[100, 105, 110, 95])
    assert not normal["is_spike_anomaly"]

    spike = detect_sentiment_spike(symbol="TCS", current_buzz_count=500, historical_buzz_counts=[100, 105, 110, 95])
    assert spike["is_spike_anomaly"]
    assert spike["alert_status"] == "VIRAL_RETAIL_MOMENTUM_SPIKE"


def test_generate_word_cloud_data():
    corpus = ["RELIANCE breakout target high volume rally multibagger dividend growth"]
    cloud = generate_word_cloud_data(symbol="RELIANCE", text_corpus=corpus)
    assert len(cloud) > 0
    words = [item["text"] for item in cloud]
    assert "BREAKOUT" in words


def test_detect_earnings_transcript_tone_shift():
    curr = "We achieved robust revenue growth of 25% with expanding operating margins and record high orders."
    prev = "We navigated industry headwinds and cost inflation with cautious outlook and supply delays."
    shift = detect_earnings_transcript_tone_shift("RELIANCE", current_transcript=curr, previous_transcript=prev)
    assert shift["symbol"] == "RELIANCE"
    assert shift["tone_shift_pct"] > 0
    assert shift["status"] == "SIGNIFICANTLY_BULLISH_SHIFT"


def test_sentiment_sqlite_storage():
    record_id = save_sentiment_record(
        symbol="HDFCBANK",
        source="TEST_SUITE",
        composite_score=0.75,
        sentiment_label="BULLISH",
        buzz_volume=150,
        word_cloud_data=[{"text": "BULLISH", "weight": 5, "sentiment": "BULLISH"}],
        raw_metrics={"test": True}
    )
    assert record_id > 0

    history = get_sentiment_history(symbol="HDFCBANK", limit=10)
    assert len(history) > 0
    assert history[0]["symbol"] == "HDFCBANK"
    assert history[0]["composite_score"] == 0.75
