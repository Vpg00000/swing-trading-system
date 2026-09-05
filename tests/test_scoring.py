import unittest
from engine.priced_in import PricedInResult
from engine.scoring import (
    calculate_opportunity_score,
    score_opportunity,
    CompositeOpportunityScorer,
    DEFAULT_WEIGHTS,
    ScoreBreakdown,
    OpportunityScoreResult,
)


class TestScoringEngine(unittest.TestCase):

    def test_default_weights_sum_to_100(self):
        self.assertEqual(sum(DEFAULT_WEIGHTS.values()), 100.0)

    def test_full_score_calculation(self):
        res = calculate_opportunity_score(
            symbol="RELIANCE.NS",
            technical=1.0,
            regime=1.0,
            flow=1.0,
            sector=1.0,
            fundamental=1.0,
            forensic=1.0,
            priced_in=1.0,
        )
        self.assertEqual(res.symbol, "RELIANCE.NS")
        self.assertEqual(res.total_score, 100.0)
        self.assertEqual(res.rank_grade, "STRONG_BUY")
        self.assertEqual(res.score_breakdown.technical, 20.0)
        self.assertEqual(res.score_breakdown.regime, 15.0)
        self.assertEqual(res.score_breakdown.flow, 15.0)
        self.assertEqual(res.score_breakdown.sector, 15.0)
        self.assertEqual(res.score_breakdown.fundamental, 15.0)
        self.assertEqual(res.score_breakdown.forensic, 10.0)
        self.assertEqual(res.score_breakdown.priced_in, 10.0)
        self.assertEqual(res.score_breakdown.total(), res.total_score)

    def test_zero_score_calculation(self):
        res = calculate_opportunity_score(
            symbol="INFY.NS",
            technical=0.0,
            regime=0.0,
            flow=0.0,
            sector=0.0,
            fundamental=0.0,
            forensic=0.0,
            priced_in=0.0,
        )
        self.assertEqual(res.total_score, 0.0)
        self.assertEqual(res.rank_grade, "AVOID")
        self.assertEqual(res.score_breakdown.total(), 0.0)

    def test_score_breakdown_reproducibility(self):
        inputs = {
            "symbol": "TCS.NS",
            "technical": 80.0,
            "regime": "BULLISH",
            "flow": 0.5,
            "sector": {"score": 90.0},
            "fundamental": 0.8,
            "forensic": 1.0,
            "priced_in": PricedInResult(
                symbol="TCS.NS",
                current_move_pct=2.0,
                historical_median_pct=5.0,
                comparable_events_count=10,
                status="UNDERPRICED",
                confidence=0.9,
            ),
        }
        res1 = calculate_opportunity_score(**inputs)
        res2 = calculate_opportunity_score(**inputs)

        self.assertEqual(res1.total_score, res2.total_score)
        self.assertEqual(res1.score_breakdown, res2.score_breakdown)
        self.assertEqual(res1.rank_grade, res2.rank_grade)
        self.assertEqual(res1.score_breakdown.total(), res1.total_score)

    def test_priced_in_integration(self):
        pi_underpriced = PricedInResult(
            symbol="HDFCBANK.NS",
            current_move_pct=1.0,
            historical_median_pct=4.0,
            comparable_events_count=8,
            status="UNDERPRICED",
            confidence=0.85,
        )
        res_under = calculate_opportunity_score("HDFCBANK.NS", priced_in=pi_underpriced)
        self.assertEqual(res_under.score_breakdown.priced_in, 10.0)

        pi_fully = PricedInResult(
            symbol="HDFCBANK.NS",
            current_move_pct=8.0,
            historical_median_pct=4.0,
            comparable_events_count=8,
            status="FULLY_PRICED",
            confidence=0.85,
        )
        res_fully = calculate_opportunity_score("HDFCBANK.NS", priced_in=pi_fully)
        self.assertEqual(res_fully.score_breakdown.priced_in, 2.0)

    def test_string_and_dict_inputs(self):
        res = calculate_opportunity_score(
            symbol="SBIN.NS",
            technical="STRONG",
            regime="BULLISH",
            flow="MODERATE_BULLISH",
            sector="NEUTRAL",
            fundamental={"normalized_score": 0.8},
            forensic="VERY_HIGH",
            priced_in={"status": "UNDERPRICED", "confidence": 0.9},
        )
        self.assertGreater(res.total_score, 70.0)
        self.assertIn(res.rank_grade, ["STRONG_BUY", "BUY"])

    def test_grade_boundaries(self):
        # 85 pts -> STRONG_BUY
        res1 = calculate_opportunity_score("STK.NS", technical=1.0, regime=1.0, flow=1.0, sector=1.0, fundamental=0.5, forensic=0.5, priced_in=0.5)
        self.assertEqual(res1.rank_grade, "STRONG_BUY")

        # 60 pts -> HOLD
        res2 = calculate_opportunity_score("STK.NS", technical=0.6, regime=0.6, flow=0.6, sector=0.6, fundamental=0.6, forensic=0.6, priced_in=0.6)
        self.assertEqual(res2.rank_grade, "HOLD")

    def test_class_scorer_and_alias(self):
        scorer = CompositeOpportunityScorer()
        res1 = scorer.score("ICICIBANK.NS", technical=0.8, regime=0.7)
        res2 = score_opportunity("ICICIBANK.NS", technical=0.8, regime=0.7)
        self.assertEqual(res1.total_score, res2.total_score)

    def test_export_dict(self):
        res = calculate_opportunity_score("BHARTIARTL.NS", technical=0.5)
        d = res.to_dict()
        self.assertIn("total_score", d)
        self.assertIn("score_breakdown", d)
        self.assertIn("rank_grade", d)
        self.assertEqual(res.score_breakdown.as_dict()["technical"], 10.0)


if __name__ == "__main__":
    unittest.main()
