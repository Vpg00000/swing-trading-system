import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure root directory is in path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import engine.sector_score as sector_score_module
from engine.sector_score import (
    SectorScore,
    compute_commodity_impact,
    score_sectors,
    _return_over,
    _above_dma,
)
from web_server import app


def _generate_price_series(start_price: float, return_pct: float, num_days: int = 60) -> pd.DataFrame:
    """Helper to generate a deterministic daily price DataFrame."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=num_days, freq="B")
    end_price = start_price * (1.0 + return_pct / 100.0)
    prices = np.linspace(start_price, end_price, num_days)
    volumes = np.full(num_days, 1000000.0)
    df = pd.DataFrame(
        {
            "Open": prices * 0.99,
            "High": prices * 1.01,
            "Low": prices * 0.98,
            "Close": prices,
            "Volume": volumes,
        },
        index=dates,
    )
    return df


class TestSectorScoring(unittest.TestCase):

    def test_return_over_calculation(self):
        df = _generate_price_series(100.0, 10.0, num_days=60)
        ret = _return_over(df, 20)
        self.assertIsNotNone(ret)
        # Expected return over 20-day window
        expected = float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1)
        self.assertAlmostEqual(ret, expected, places=5)

    def test_above_dma_calculation(self):
        # Strictly increasing prices -> last price is above mean
        df_up = _generate_price_series(100.0, 10.0, num_days=60)
        self.assertTrue(_above_dma(df_up, 20))

        # Strictly decreasing prices -> last price is below mean
        df_down = _generate_price_series(100.0, -10.0, num_days=60)
        self.assertFalse(_above_dma(df_down, 20))

    def test_compute_commodity_impact(self):
        class Quote:
            def __init__(self, name, change_pct):
                self.name = name
                self.change_pct = change_pct

        macro_brent_up = {"commodities": [Quote("Brent Crude", 2.5), Quote("Copper", 0.0)]}
        macro_copper_up = {"commodities": [Quote("Brent Crude", 0.0), Quote("Copper", 2.0)]}
        macro_brent_down = {"commodities": [Quote("Brent Crude", -2.5), Quote("Copper", 0.0)]}

        # Crude up -> Energy tailwind, Industrials headwind
        self.assertEqual(compute_commodity_impact("Energy", macro_brent_up), "TAILWIND")
        self.assertEqual(compute_commodity_impact("Industrials", macro_brent_up), "HEADWIND")
        self.assertEqual(compute_commodity_impact("Consumer Cyclical", macro_brent_up), "HEADWIND")

        # Copper up -> Basic Materials tailwind
        self.assertEqual(compute_commodity_impact("Basic Materials", macro_copper_up), "TAILWIND")

        # Crude down -> Energy headwind, Industrials/Consumer Cyclical tailwind
        self.assertEqual(compute_commodity_impact("Energy", macro_brent_down), "HEADWIND")
        self.assertEqual(compute_commodity_impact("Industrials", macro_brent_down), "TAILWIND")

        # Neutral case
        self.assertEqual(compute_commodity_impact("Technology", macro_brent_up), "NEUTRAL")

    @patch("engine.sector_score.load_cached")
    @patch("engine.sector_score.get_sector")
    def test_score_sectors_ranking_and_data_flow(self, mock_get_sector, mock_load_cached):
        # Mock universe mapping
        series_nifty = _generate_price_series(18000.0, 2.0, 60)
        symbol_map = {
            "^NSEI": series_nifty,
            "nifty": series_nifty,
            "RELIANCE.NS": _generate_price_series(2400.0, 10.0, 60),  # Energy
            "TCS.NS": _generate_price_series(3200.0, -5.0, 60),       # Technology
            "INFY.NS": _generate_price_series(1400.0, -2.0, 60),      # Technology
            "TATASTEEL.NS": _generate_price_series(110.0, 15.0, 60),  # Basic Materials
        }

        sector_map = {
            "RELIANCE.NS": "Energy",
            "TCS.NS": "Technology",
            "INFY.NS": "Technology",
            "TATASTEEL.NS": "Basic Materials",
        }

        mock_load_cached.side_effect = lambda symbol: symbol_map.get(symbol)
        mock_get_sector.side_effect = lambda symbol: sector_map.get(symbol)

        macro_data = {"commodities": []}
        results = score_sectors(symbols=list(sector_map.keys()), macro=macro_data)

        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

        # Check sorting by overall score (descending)
        scores = [s.overall_score for s in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

        # Check structure of SectorScore
        for s in results:
            self.assertIsInstance(s, SectorScore)
            self.assertIsInstance(s.sector, str)
            self.assertIsInstance(s.return_20d, float)
            self.assertIsInstance(s.rs_vs_nifty, float)
            self.assertIsInstance(s.breadth_above_20dma, float)
            self.assertIsInstance(s.breadth_above_50dma, float)
            self.assertIn(s.commodity_impact, ["TAILWIND", "HEADWIND", "NEUTRAL"])
            self.assertTrue(0.0 <= s.overall_score <= 100.0)

        # High return sectors (Basic Materials 15%, Energy 10%) should rank above Tech (-3.5% avg)
        sector_names = [s.sector for s in results]
        self.assertIn("Basic Materials", sector_names)
        self.assertIn("Energy", sector_names)
        self.assertIn("Technology", sector_names)
        self.assertLess(sector_names.index("Basic Materials"), sector_names.index("Technology"))


class TestSectorsAPI(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    @patch("engine.sector_score.score_sectors")
    def test_api_sectors_endpoint_success(self, mock_score_sectors):
        mock_score_sectors.return_value = [
            SectorScore(
                sector="Basic Materials",
                return_20d=12.5,
                rs_vs_nifty=10.5,
                breadth_above_20dma=100.0,
                breadth_above_50dma=100.0,
                commodity_impact="TAILWIND",
                overall_score=92.5,
            ),
            SectorScore(
                sector="Technology",
                return_20d=-3.0,
                rs_vs_nifty=-5.0,
                breadth_above_20dma=30.0,
                breadth_above_50dma=20.0,
                commodity_impact="NEUTRAL",
                overall_score=35.0,
            ),
        ]

        response = self.client.get("/api/sectors")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("timestamp", data)
        self.assertIn("count", data)
        self.assertIn("sectors", data)

        sectors = data["sectors"]
        self.assertEqual(len(sectors), 2)

        top_sector = sectors[0]
        self.assertEqual(top_sector["rank"], 1)
        self.assertEqual(top_sector["sector"], "Basic Materials")
        self.assertEqual(top_sector["overall_score"], 92.5)
        self.assertEqual(top_sector["return_20d"], 12.5)
        self.assertEqual(top_sector["rs_vs_nifty"], 10.5)
        self.assertEqual(top_sector["breadth"]["above_20dma"], 100.0)
        self.assertEqual(top_sector["commodity_impact"], "TAILWIND")

    @patch("engine.sector_score.score_sectors")
    def test_api_sectors_endpoint_error_handling(self, mock_score_sectors):
        mock_score_sectors.side_effect = Exception("Market data processing failure")

        response = self.client.get("/api/sectors")
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertIn("detail", data)


if __name__ == "__main__":
    unittest.main()