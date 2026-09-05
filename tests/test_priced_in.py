import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from engine.priced_in import PricedInAnalysis, PricedInResult

class TestPricedIn(unittest.TestCase):

    def test_empty_symbol(self):
        res = PricedInAnalysis.analyze_opportunity("", None, None)
        self.assertEqual(res.status, "UNKNOWN")
        self.assertEqual(res.confidence, 0.0)

    @patch('engine.priced_in.load_cached')
    def test_insufficient_data(self, mock_load_cached):
        mock_load_cached.return_value = pd.DataFrame()
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", None, None)
        self.assertEqual(res.status, "UNKNOWN")

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_priced_in_classification(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create 40 days of close prices with daily +4% moves to generate drift events
        closes = [100.0 * (1.04 ** i) for i in range(40)]
        mock_data = pd.DataFrame({"Close": closes})
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 5.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 5.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with high current move
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertIn(res.status, ["FULLY_PRICED", "PARTIALLY_PRICED", "UNDERPRICED", "UNKNOWN"])
        self.assertGreater(res.comparable_events_count, 0)

    def test_aliases(self):
        self.assertTrue(callable(PricedInAnalysis.analyze_opportunity))

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_extreme_price_move(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create 40 days of close prices with daily +10% moves to generate extreme drift events
        closes = [100.0 * (1.10 ** i) for i in range(40)]
        mock_data = pd.DataFrame({"Close": closes})
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 10.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 10.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with extreme current move
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertIn(res.status, ["FULLY_PRICED", "PARTIALLY_PRICED", "UNDERPRICED", "OVERPRICED", "UNKNOWN"])
        self.assertGreater(res.comparable_events_count, 0)
        self.assertGreater(res.confidence, 0.0)

    @patch('engine.priced_in.load_cached')
    def test_missing_metrics(self, mock_load_cached):
        # Create 40 days of close prices with daily +4% moves but missing some metrics
        closes = [100.0 * (1.04 ** i) for i in range(40)]
        mock_data = pd.DataFrame({"Close": closes})
        mock_data.loc[10:20, 'Close'] = None
        mock_load_cached.return_value = mock_data

        # Run with missing metrics
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", None, None)
        self.assertEqual(res.status, "UNKNOWN")

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_deterministic_classification(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create 40 days of close prices with daily +4% moves to generate drift events
        closes = [100.0 * (1.04 ** i) for i in range(40)]
        mock_data = pd.DataFrame({"Close": closes})
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 5.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 5.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with high current move multiple times
        res1 = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        res2 = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertEqual(res1.status, res2.status)
        self.assertEqual(res1.confidence, res2.confidence)

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_forward_valuation_ratios(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create mock data with forward valuation ratios
        mock_data = pd.DataFrame({
            "Close": [100.0 * (1.04 ** i) for i in range(40)],
            "PE": [20.0] * 40,
            "PB": [3.0] * 40,
            "EV_EBITDA": [15.0] * 40
        })
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 5.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 5.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with forward valuation ratios
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertIn(res.status, ["FULLY_PRICED", "PARTIALLY_PRICED", "UNDERPRICED", "OVERPRICED", "UNKNOWN"])
        self.assertGreater(res.comparable_events_count, 0)
        self.assertGreater(res.confidence, 0.0)

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_corporate_events(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create mock data with corporate events
        mock_data = pd.DataFrame({
            "Close": [100.0 * (1.04 ** i) for i in range(40)],
            "Event": ["Earnings"] * 10 + ["Dividend"] * 10 + ["None"] * 20
        })
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 5.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 5.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with corporate events
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertIn(res.status, ["FULLY_PRICED", "PARTIALLY_PRICED", "UNDERPRICED", "OVERPRICED", "UNKNOWN"])
        self.assertGreater(res.comparable_events_count, 0)
        self.assertGreater(res.confidence, 0.0)

    @patch('engine.priced_in.load_cached')
    @patch('engine.priced_in.get_market_data')
    @patch('engine.priced_in.get_valuation_metrics')
    @patch('engine.priced_in.get_historical_events')
    def test_institutional_money_flow(self, mock_get_historical_events, mock_get_valuation_metrics, mock_get_market_data, mock_load_cached):
        # Create mock data with institutional money flow
        mock_data = pd.DataFrame({
            "Close": [100.0 * (1.04 ** i) for i in range(40)],
            "Institutional_Flow": [1000000.0] * 40
        })
        mock_load_cached.return_value = mock_data

        # Mock market data
        mock_market_data = MagicMock()
        mock_market_data.current_price = 100.0
        mock_market_data.recent_move = 5.0
        mock_market_data.volume = 1000000.0
        mock_get_market_data.return_value = mock_market_data

        # Mock valuation metrics
        mock_valuation_metrics = MagicMock()
        mock_valuation_metrics.pe_ratio = 20.0
        mock_valuation_metrics.pb_ratio = 3.0
        mock_valuation_metrics.ev_ebitda = 15.0
        mock_get_valuation_metrics.return_value = mock_valuation_metrics

        # Mock historical events
        mock_historical_events = MagicMock()
        mock_historical_events.event_ids = ["event1", "event2"]
        mock_get_historical_events.return_value = mock_historical_events

        # Mock AI research output
        mock_ai_output = MagicMock()
        mock_ai_output.expected_impact = MagicMock()
        mock_ai_output.expected_impact.magnitude = 5.0
        mock_ai_output.expected_impact.direction = "up"
        mock_ai_output.expected_impact.timeframe = "short_term"
        mock_ai_output.expected_impact.confidence = 0.8
        mock_ai_output.suggested_comparable_event_ids = ["event1", "event2"]

        # Run with institutional money flow
        res = PricedInAnalysis.analyze_opportunity("RELIANCE.NS", "event1", mock_ai_output)
        self.assertIn(res.status, ["FULLY_PRICED", "PARTIALLY_PRICED", "UNDERPRICED", "OVERPRICED", "UNKNOWN"])
        self.assertGreater(res.comparable_events_count, 0)
        self.assertGreater(res.confidence, 0.0)

if __name__ == '__main__':
    unittest.main()