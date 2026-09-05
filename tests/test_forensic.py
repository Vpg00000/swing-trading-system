import pytest
from engine.forensic import calculate_beneish_m_score, calculate_altman_z_score
from engine.governance import compute_governance_score

def test_beneish_m_score():
    assert calculate_beneish_m_score(dsri=1.0, gmi=1.0, aqi=1.0, sgi=1.0, depi=1.0, sgai=1.0, lvgi=1.0, tata=0.0) == {
        "m_score": -1.83,
        "is_manipulator": False,
        "status": "SAFE"
    }
    assert calculate_beneish_m_score(dsri=1.2, gmi=1.5, aqi=1.1, sgi=1.1, depi=1.1, sgai=0.9, lvgi=1.1, tata=0.1) == {
        "m_score": -0.72,
        "is_manipulator": True,
        "status": "MANIPULATION_RISK"
    }

def test_altman_z_score():
    assert calculate_altman_z_score(working_cap_to_assets=0.05, retained_earnings_to_assets=0.05, ebit_to_assets=0.02, market_cap_to_liabilities=0.2, sales_to_assets=0.4) == {
        "z_score": 0.72,
        "zone": "DISTRESS_ZONE",
        "is_distressed": True
    }
    assert calculate_altman_z_score(working_cap_to_assets=2.0, retained_earnings_to_assets=1.0, ebit_to_assets=1.0, market_cap_to_liabilities=1.0, sales_to_assets=1.0) == {
        "z_score": 8.7,
        "zone": "SAFE_ZONE",
        "is_distressed": False
    }

def test_compute_governance_score():
    score = compute_governance_score(symbol="AAPL", pledged_pct=30.0, promoter_pct=10.0)
    assert score.total_100 == 80.0
    assert score.total_5 == 4.0
    assert "pledge 30.0% (HIGH -15)" in score.deductions

    score = compute_governance_score(symbol="AAPL", pledged_pct=60.0, promoter_pct=10.0)
    assert score.total_100 == 65.0
    assert score.total_5 == 3.25
    assert "pledge 60.0% (CRITICAL -30)" in score.deductions

    score = compute_governance_score(symbol="AAPL", pledged_pct=None, promoter_pct=15.0)
    assert score.total_100 == 100.0
    assert score.total_5 == 5.0
    assert "pledge_pct" in score.missing

    score = compute_governance_score(symbol="AAPL", pledged_pct=10.0, promoter_pct=5.0)
    assert score.total_100 == 90.0
    assert score.total_5 == 4.5
    assert "low promoter holding 5.0% (-5)" in score.deductions