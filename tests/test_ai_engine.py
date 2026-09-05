import pytest
from engine.ai_engine import calculate_dynamic_weights, ResearchOutputSchema

def test_schema_adherence():
    output = calculate_dynamic_weights("BULL")
    assert ResearchOutputSchema(**output)

def test_provenance_verification():
    output = calculate_dynamic_weights("BULL")
    assert "input_evidence" in output

def test_invalid_output_rejection():
    with pytest.raises(ValueError):
        calculate_dynamic_weights("INVALID")