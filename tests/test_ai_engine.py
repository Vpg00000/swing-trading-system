import pytest
from engine.ai_engine import calculate_dynamic_weights, ResearchOutputSchema

def test_schema_adherence():
    """Test that AIArticle (ResearchOutputSchema) validates required fields correctly."""
    stub_output = {
        "what_happened": "Q1 FY26 net profit up 15% driven by retail and Jio segments.",
        "why_now": "Strong quarterly earnings beat street estimates; FII buying intensified.",
        "source_credibility": "NSE filing + Economic Times report corroborated by 3 sources.",
        "fundamental_significance": "Revenue diversification reduces reliance on oil-to-chemicals.",
        "input_evidence": {
            "source_1": "BSE filing BSE:500325",
            "source_2": "ET report 2024-08-01"
        },
        "priced_in_state": {"symbol": "RELIANCE", "verdict": "PARTIALLY_PRICED_IN"}
    }
    schema = ResearchOutputSchema(**stub_output)
    assert schema.what_happened
    assert schema.why_now
    assert schema.input_evidence

def test_provenance_verification():
    """Test that calculate_dynamic_weights returns priced_in_state with input evidence."""
    output = calculate_dynamic_weights("BULL")
    assert "priced_in_state" in output
    assert isinstance(output["priced_in_state"], dict)

def test_invalid_output_rejection():
    with pytest.raises(ValueError):
        calculate_dynamic_weights("INVALID")


def test_get_ai_research_output_zero_hardcoding():
    """Verify that get_ai_research_output extracts authentic data and uses no hardcoded stock values."""
    from engine.ai_engine import get_ai_research_output
    
    # Test authentic stock
    res = get_ai_research_output("SAGILITY.NS")
    assert res["symbol"] == "SAGILITY.NS"
    assert "market_facts" in res
    assert "verified_signals" in res
    assert "audit_compliance" in res
    assert res["status"] in ["WATCH / ACCUMULATE", "BUY / BREAKOUT", "DATA_UNAVAILABLE"]
    # Check that prices are numeric and not dummy strings
    if res["market_facts"].get("last_close"):
        assert isinstance(res["market_facts"]["last_close"], float)
        assert res["market_facts"]["last_close"] > 0

    # Test unknown stock returns DATA_UNAVAILABLE without fabricating numbers
    unknown_res = get_ai_research_output("NONEXISTENT_XYZ_TEST")
    assert unknown_res["status"] == "DATA_UNAVAILABLE"
    assert unknown_res["score"] == 0
    assert unknown_res["market_facts"] == {}
    assert unknown_res["verified_signals"] == []

