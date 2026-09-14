"""
tests/test_scoring_engine.py — Unit tests for Transparent Scoring Engine & Indicator Integrity Module.

Adheres strictly to:
- Rules 1–4 & Tasks 161–180 (Phases 10 & 11)
- Indicator warm-up checking (no zeros for uncomputed indicators).
- RSI & ATR boundary validation.
- Missing delivery normalization & coverage calculation (no false BUY signals).
- Deterministic 100-point factor breakdown.
- Explicit source="MODEL_GENERATED" tagging.
"""

import unittest
import pandas as pd
import numpy as np
from engine.scoring_engine import (
    TransparentScoringEngine,
    calculate_transparent_score,
    score_stock,
    check_warmup,
    validate_rsi,
    validate_atr,
    validate_indicator_warmup,
    compute_indicators_with_integrity,
    IndicatorIntegrityValidator,
    DEFAULT_WEIGHTS,
    STRATEGY_VERSION,
    FactorScore,
    TargetStopLoss,
    TransparentScoreResult,
)


class TestIndicatorIntegrity(unittest.TestCase):
    """Verifies Rules 1–2 and Tasks 161–174: Warm-up and boundary validations."""

    def test_indicator_warmup_short_histories_no_zeros(self):
        """
        Rule 1 & Tasks 161–174:
        - History < 200 bars: EMA200 is None (UNKNOWN), NEVER 0!
        - History < 50 bars: EMA50 is None, NEVER 0!
        - History < 14 bars: RSI and ATR are None, NEVER 0!
        """
        # Case 1: 10 bars (< 14 bars)
        dates = pd.date_range("2026-01-01", periods=10, freq="D")
        df_10 = pd.DataFrame({
            "Close": [100.0 + i for i in range(10)],
            "High": [102.0 + i for i in range(10)],
            "Low": [99.0 + i for i in range(10)],
            "Volume": [1000] * 10,
        }, index=dates)

        res_10 = compute_indicators_with_integrity(df_10)
        self.assertIsNone(res_10["ema200"], "EMA200 must be None when bars < 200, NEVER 0")
        self.assertIsNone(res_10["ema50"], "EMA50 must be None when bars < 50, NEVER 0")
        self.assertIsNone(res_10["rsi"], "RSI must be None when bars < 14, NEVER 0")
        self.assertIsNone(res_10["atr"], "ATR must be None when bars < 14, NEVER 0")
        self.assertNotEqual(res_10["ema200"], 0.0)
        self.assertNotEqual(res_10["ema50"], 0.0)
        self.assertNotEqual(res_10["rsi"], 0.0)
        self.assertNotEqual(res_10["atr"], 0.0)

        # Case 2: 30 bars (>= 14, < 50)
        dates_30 = pd.date_range("2026-01-01", periods=30, freq="D")
        df_30 = pd.DataFrame({
            "Close": [100.0 + (i % 5) for i in range(30)],
            "High": [102.0 + (i % 5) for i in range(30)],
            "Low": [98.0 + (i % 5) for i in range(30)],
            "Volume": [1000] * 30,
        }, index=dates_30)

        res_30 = compute_indicators_with_integrity(df_30)
        self.assertIsNone(res_30["ema200"])
        self.assertIsNone(res_30["ema50"])
        self.assertIsNotNone(res_30["rsi"], "RSI should be computed for >= 14 bars")
        self.assertIsNotNone(res_30["atr"], "ATR should be computed for >= 14 bars")
        self.assertGreaterEqual(res_30["rsi"], 0.0)
        self.assertLessEqual(res_30["rsi"], 100.0)
        self.assertGreater(res_30["atr"], 0.0)

        # Case 3: 100 bars (>= 50, < 200)
        dates_100 = pd.date_range("2026-01-01", periods=100, freq="D")
        df_100 = pd.DataFrame({
            "Close": [100.0 + i * 0.5 for i in range(100)],
            "High": [102.0 + i * 0.5 for i in range(100)],
            "Low": [98.0 + i * 0.5 for i in range(100)],
            "Volume": [1000] * 100,
        }, index=dates_100)

        res_100 = compute_indicators_with_integrity(df_100)
        self.assertIsNone(res_100["ema200"], "EMA200 must be None for < 200 bars")
        self.assertIsNotNone(res_100["ema50"], "EMA50 must be computed for >= 50 bars")
        self.assertGreater(res_100["ema50"], 0.0)
        self.assertIsNotNone(res_100["rsi"])
        self.assertIsNotNone(res_100["atr"])

        # Case 4: 250 bars (>= 200)
        dates_250 = pd.date_range("2026-01-01", periods=250, freq="D")
        df_250 = pd.DataFrame({
            "Close": [100.0 + i * 0.2 for i in range(250)],
            "High": [103.0 + i * 0.2 for i in range(250)],
            "Low": [97.0 + i * 0.2 for i in range(250)],
            "Volume": [1000] * 250,
        }, index=dates_250)

        res_250 = compute_indicators_with_integrity(df_250)
        self.assertIsNotNone(res_250["ema200"], "EMA200 must be computed for >= 200 bars")
        self.assertIsNotNone(res_250["ema50"])
        self.assertIsNotNone(res_250["rsi"])
        self.assertIsNotNone(res_250["atr"])

    def test_indicator_warmup_dict_validation(self):
        """Verify warm-up dictionary validation sets uncomputed indicators to None (not 0)."""
        raw_indicators = {
            "ema200": 150.0,
            "ema50": 160.0,
            "rsi": 65.0,
            "atr": 4.5,
        }
        # If bar count is 40 bars:
        sanitized = validate_indicator_warmup(40, raw_indicators)
        self.assertIsNone(sanitized["ema200"], "EMA200 must be None")
        self.assertIsNone(sanitized["ema50"], "EMA50 must be None")
        self.assertEqual(sanitized["rsi"], 65.0)
        self.assertEqual(sanitized["atr"], 4.5)

        # If bar count is 8 bars:
        sanitized_8 = validate_indicator_warmup(8, raw_indicators)
        self.assertIsNone(sanitized_8["ema200"])
        self.assertIsNone(sanitized_8["ema50"])
        self.assertIsNone(sanitized_8["rsi"])
        self.assertIsNone(sanitized_8["atr"])

    def test_check_warmup_helper(self):
        """Verify check_warmup returns correct booleans."""
        self.assertFalse(check_warmup(199, "EMA200"))
        self.assertTrue(check_warmup(200, "EMA200"))
        self.assertFalse(check_warmup(49, "EMA50"))
        self.assertTrue(check_warmup(50, "EMA50"))
        self.assertFalse(check_warmup(13, "RSI"))
        self.assertTrue(check_warmup(14, "RSI"))
        self.assertFalse(check_warmup(13, "ATR"))
        self.assertTrue(check_warmup(14, "ATR"))

    def test_rsi_boundary_validation(self):
        """Rule 2: RSI strictly between 0 and 100."""
        self.assertEqual(validate_rsi(0.0), 0.0)
        self.assertEqual(validate_rsi(50.5), 50.5)
        self.assertEqual(validate_rsi(100.0), 100.0)
        self.assertIsNone(validate_rsi(-1.0))
        self.assertIsNone(validate_rsi(105.0))
        self.assertIsNone(validate_rsi(float("nan")))
        self.assertIsNone(validate_rsi(None))

        with self.assertRaises(ValueError):
            validate_rsi(-5.0, strict=True)
        with self.assertRaises(ValueError):
            validate_rsi(100.1, strict=True)

    def test_atr_boundary_validation(self):
        """Rule 2: ATR must be >= 0."""
        self.assertEqual(validate_atr(0.0), 0.0)
        self.assertEqual(validate_atr(15.25), 15.25)
        self.assertIsNone(validate_atr(-0.5))
        self.assertIsNone(validate_atr(float("nan")))
        self.assertIsNone(validate_atr(None))

        with self.assertRaises(ValueError):
            validate_atr(-2.0, strict=True)


class TestTransparentScoringEngine(unittest.TestCase):
    """Verifies Rules 3–4 and Tasks 175–180: Transparent scoring, normalization, classification, determinism."""

    def setUp(self):
        self.engine = TransparentScoringEngine()

    def test_weight_architecture(self):
        """Verify 100-point configurable weight architecture."""
        expected_weights = {
            "trend": 20.0,
            "momentum": 20.0,
            "volume": 20.0,
            "delivery": 15.0,
            "fundamentals": 15.0,
            "risk_reward": 10.0,
        }
        self.assertEqual(DEFAULT_WEIGHTS, expected_weights)
        self.assertEqual(sum(DEFAULT_WEIGHTS.values()), 100.0)

    def test_missing_delivery_normalization_no_false_buy(self):
        """
        Rule 3 & Tasks 175–179:
        - UNKNOWN ≠ PASS and UNKNOWN ≠ FAIL.
        - If delivery is None (UNKNOWN), do NOT assign 0 and do NOT award unearned points.
        - Normalize valid component scores by available weight:
          final_score = (sum_of_available_points / sum_of_available_max_weights) * 100.
        - Verify explicit Data Coverage % = 85.0%.
        - Verify missing delivery normalizes coverage without creating false BUY signals.
        """
        # Baseline stock with ALL components available earning 80% on each
        res_full = self.engine.score(
            symbol="TEST_FULL.NS",
            trend=16.0,          # 16 / 20 = 80%
            momentum=16.0,       # 16 / 20 = 80%
            volume=16.0,         # 16 / 20 = 80%
            delivery=12.0,       # 12 / 15 = 80%
            fundamentals=12.0,   # 12 / 15 = 80%
            risk_reward=8.0,     # 8 / 10 = 80%
        )
        self.assertEqual(res_full.available_points, 80.0)
        self.assertEqual(res_full.available_max_weights, 100.0)
        self.assertEqual(res_full.coverage_pct, 100.0)
        self.assertEqual(res_full.final_score, 80.0)
        self.assertEqual(res_full.classification, "BUY_NOW")

        # Now stock with MISSING DELIVERY (delivery=None / UNKNOWN)
        res_missing_del = self.engine.score(
            symbol="TEST_NO_DEL.NS",
            trend=16.0,
            momentum=16.0,
            volume=16.0,
            delivery=None,       # UNKNOWN
            fundamentals=12.0,
            risk_reward=8.0,
        )

        # 1. Delivery factor status must be UNKNOWN with points_earned=None
        del_factor = res_missing_del.breakdown["delivery"]
        self.assertEqual(del_factor.status, "UNKNOWN")
        self.assertIsNone(del_factor.points_earned)
        self.assertEqual(del_factor.max_points, 15.0)

        # 2. Points earned should ONLY sum available components: 16 + 16 + 16 + 12 + 8 = 68
        self.assertEqual(res_missing_del.available_points, 68.0)
        # 3. Available max weight = 100 - 15 = 85.0
        self.assertEqual(res_missing_del.available_max_weights, 85.0)
        # 4. Data coverage % = 85.0%
        self.assertEqual(res_missing_del.coverage_pct, 85.0)
        # 5. Normalized final score = (68 / 85) * 100 = 80.0
        # Not penalized to 68.0 (assigning 0) and not inflated to 83.0 (unearned points)!
        self.assertEqual(res_missing_del.final_score, 80.0)

        # 6. Verify missing delivery does NOT create false BUY signal when scores are mediocre:
        res_mediocre = self.engine.score(
            symbol="TEST_MEDIOCRE.NS",
            trend=10.0,          # 50%
            momentum=10.0,       # 50%
            volume=10.0,         # 50%
            delivery=None,       # UNKNOWN
            fundamentals=7.5,    # 50%
            risk_reward=5.0,     # 50%
        )
        self.assertEqual(res_mediocre.coverage_pct, 85.0)
        self.assertEqual(res_mediocre.final_score, 50.0)
        self.assertEqual(res_mediocre.classification, "WATCH")
        self.assertNotIn(res_mediocre.classification, ["BUY", "BUY_NOW"])

        # 7. Low coverage prevents BUY_NOW:
        # If coverage is < 70% (e.g. delivery, fundamentals, volume missing -> 50% coverage)
        # Even if available components score 100%, it should NOT trigger BUY_NOW!
        res_low_cov = self.engine.score(
            symbol="TEST_LOW_COV.NS",
            trend=20.0,          # 100%
            momentum=20.0,       # 100%
            volume=None,         # UNKNOWN
            delivery=None,       # UNKNOWN
            fundamentals=None,   # UNKNOWN
            risk_reward=10.0,    # 100%
        )
        self.assertEqual(res_low_cov.coverage_pct, 50.0)
        self.assertEqual(res_low_cov.final_score, 100.0)
        # Score is 100 >= 80, but coverage is 50% < 70% -> MUST BE BUY, NOT BUY_NOW!
        self.assertEqual(res_low_cov.classification, "BUY")
        self.assertNotEqual(res_low_cov.classification, "BUY_NOW")

    def test_deterministic_output(self):
        """
        Requirement 3:
        - Given the same input dict and strategy version, output is 100% deterministic and reproducible.
        """
        inputs = {
            "symbol": "RELIANCE.NS",
            "trend": 18.0,
            "momentum": 17.5,
            "volume": 15.0,
            "delivery": 12.0,
            "fundamentals": 13.5,
            "risk_reward": 8.0,
            "close": 2850.0,
            "atr": 45.0,
            "strategy_version": "Strategy v3.2",
            "timestamp": "2026-09-14T09:15:00Z",
        }

        res1 = calculate_transparent_score(**inputs)
        res2 = calculate_transparent_score(**inputs)

        self.assertEqual(res1.final_score, res2.final_score)
        self.assertEqual(res1.coverage_pct, res2.coverage_pct)
        self.assertEqual(res1.classification, res2.classification)
        self.assertEqual(res1.target_price, res2.target_price)
        self.assertEqual(res1.stop_loss, res2.stop_loss)
        self.assertEqual(res1.rr_ratio, res2.rr_ratio)
        self.assertEqual(res1.deterministic_hash, res2.deterministic_hash)
        self.assertEqual(res1.to_dict(), res2.to_dict())

    def test_target_and_stop_loss_provenance(self):
        """
        Rule 4:
        - Targets and stop losses must explicitly be tagged source="MODEL_GENERATED".
        """
        res = self.engine.score(
            symbol="INFY.NS",
            trend=15.0,
            momentum=15.0,
            volume=15.0,
            delivery=10.0,
            fundamentals=10.0,
            risk_reward=7.0,
            close=1800.0,
            atr=30.0,
        )

        self.assertEqual(res.source, "MODEL_GENERATED")
        self.assertIsNotNone(res.targets_and_stops)
        self.assertEqual(res.targets_and_stops.source, "MODEL_GENERATED")
        self.assertEqual(res.targets_and_stops.to_dict()["source"], "MODEL_GENERATED")
        # stop_loss = 1800 - 2 * 30 = 1740.0
        self.assertEqual(res.stop_loss, 1740.0)
        # risk = 60.0, target = 1800 + 2.2 * 60 = 1932.0
        self.assertEqual(res.target_price, 1932.0)
        self.assertEqual(res.rr_ratio, 2.2)

    def test_transparent_factor_breakdown(self):
        """Verify breakdown exposes points earned / max points for each factor."""
        res = self.engine.score(
            symbol="TCS.NS",
            trend=18.0,
            momentum=16.0,
            volume=14.0,
            delivery=11.0,
            fundamentals=12.0,
            risk_reward=8.0,
        )

        breakdown = res.breakdown
        self.assertIn("trend", breakdown)
        self.assertIn("momentum", breakdown)
        self.assertIn("volume", breakdown)
        self.assertIn("delivery", breakdown)
        self.assertIn("fundamentals", breakdown)
        self.assertIn("risk_reward", breakdown)

        for factor_name, expected_max in [
            ("trend", 20.0),
            ("momentum", 20.0),
            ("volume", 20.0),
            ("delivery", 15.0),
            ("fundamentals", 15.0),
            ("risk_reward", 10.0),
        ]:
            f = breakdown[factor_name]
            self.assertEqual(f.max_points, expected_max)
            self.assertEqual(f.status, "AVAILABLE")
            self.assertIsNotNone(f.points_earned)

    def test_classification_tiers(self):
        """Verify all classification tiers: BUY_NOW, BUY, WATCH, HOLD, EXIT."""
        # BUY_NOW: >= 80 and coverage >= 70%
        self.assertEqual(self.engine.classify(85.0, 75.0), "BUY_NOW")
        # BUY: >= 65
        self.assertEqual(self.engine.classify(70.0, 80.0), "BUY")
        self.assertEqual(self.engine.classify(85.0, 60.0), "BUY")  # score high, but low coverage
        # WATCH: >= 50
        self.assertEqual(self.engine.classify(55.0, 80.0), "WATCH")
        # HOLD: >= 40
        self.assertEqual(self.engine.classify(42.0, 80.0), "HOLD")
        # EXIT: < 40
        self.assertEqual(self.engine.classify(35.0, 80.0), "EXIT")


if __name__ == "__main__":
    unittest.main()
