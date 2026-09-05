"""
Unit and Integration Tests for AI Consensus, Ollama Router & Concall Guidance (TASK-061 to TASK-065).
"""

import pytest
from engine.ai_engine import (
    query_local_ollama_fallback,
    extract_concall_guidance,
    resolve_multi_agent_consensus,
)
from engine.trade_journal import classify_trade_post_mortem_mistakes


def test_task061_local_ollama_fallback():
    res = query_local_ollama_fallback("Analyze RELIANCE swing setup", model="qwen2.5-coder:7b")
    assert res["status"] in ["SUCCESS", "DEGRADED"]
    assert res["provider"] == "OLLAMA_LOCAL"
    assert res["is_fallback"] is True


def test_task062_concall_guidance_extractor():
    transcript = "We see strong growth and robust expansion with higher capex targets for FY27."
    res = extract_concall_guidance(transcript)

    assert res["guidance_stance"] == "BULLISH_GUIDANCE"
    assert res["sentiment_score"] > 0.0
    assert res["capex_mentioned"] is True


def test_task063_trade_post_mortem_classifier():
    trades = [
        {"entry_price": 100.0, "exit_price": 95.0, "stop_loss": 99.5, "realized_pnl": -5.0}, # Tight stop
        {"entry_price": 200.0, "exit_price": 220.0, "stop_loss": 180.0, "realized_pnl": 20.0, "holding_days": 10}, # Clean
    ]
    res = classify_trade_post_mortem_mistakes(trades)

    assert res["total_trades_reviewed"] == 2
    assert "TOO_TIGHT_STOP_LOSS" in res["mistake_breakdown"]
    assert res["mistake_breakdown"]["TOO_TIGHT_STOP_LOSS"] == 1


def test_task064_multi_agent_consensus_resolver():
    models = {
        "GEMINI_3_6_FLASH": {"signal": "BUY", "score": 85.0},
        "DEEPSEEK_R1": {"signal": "BUY", "score": 82.0},
        "LOCAL_QWEN": {"signal": "BUY", "score": 88.0},
    }
    res = resolve_multi_agent_consensus(models)

    assert res["consensus_signal"] == "BUY"
    assert res["is_unanimous"] is True
    assert res["consensus_score"] == 85.0
    assert len(res["contradictions"]) == 0
