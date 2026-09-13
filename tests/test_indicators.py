import unittest
import json
from engine.indicators import compute_indicators, compute_all, IndicatorResult

class TestIndicators(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open('tests/fixtures/tradingview_indicators.json') as f:
            cls.fixtures = json.load(f)

    def test_indicator_result_structure(self):
        """TASK-147: Verify technical indicator calculations return valid structured result."""
        result = compute_indicators("NIFTY")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, IndicatorResult)
        self.assertIsNotNone(result.symbol)
        self.assertGreaterEqual(result.rsi, 0.0)
        self.assertLessEqual(result.rsi, 100.0)

    def test_compute_all_batch(self):
        """TASK-147: Verify batch indicator computation engine."""
        results = compute_all()
        self.assertIsInstance(results, dict)
        self.assertGreater(len(results), 0)

    def test_sma(self):
        """TASK-147: Verify SMA calculation against TradingView fixture."""
        fixture = self.fixtures['SMA']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.sma, fixture['sma'], delta=1e-5)

    def test_ema(self):
        """TASK-147: Verify EMA calculation against TradingView fixture."""
        fixture = self.fixtures['EMA']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.ema, fixture['ema'], delta=1e-5)

    def test_rsi(self):
        """TASK-147: Verify RSI calculation against TradingView fixture."""
        fixture = self.fixtures['RSI']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.rsi, fixture['rsi'], delta=1e-5)

    def test_macd(self):
        """TASK-147: Verify MACD calculation against TradingView fixture."""
        fixture = self.fixtures['MACD']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.macd, fixture['macd'], delta=1e-5)
        self.assertAlmostEqual(result.macd_signal, fixture['macd_signal'], delta=1e-5)
        self.assertAlmostEqual(result.macd_histogram, fixture['macd_histogram'], delta=1e-5)

    def test_atr(self):
        """TASK-147: Verify ATR calculation against TradingView fixture."""
        fixture = self.fixtures['ATR']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.atr, fixture['atr'], delta=1e-5)

    def test_bollinger_bands(self):
        """TASK-147: Verify Bollinger Bands calculation against TradingView fixture."""
        fixture = self.fixtures['BollingerBands']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.bollinger_upper, fixture['bollinger_upper'], delta=1e-5)
        self.assertAlmostEqual(result.bollinger_middle, fixture['bollinger_middle'], delta=1e-5)
        self.assertAlmostEqual(result.bollinger_lower, fixture['bollinger_lower'], delta=1e-5)

    def test_supertrend(self):
        """TASK-147: Verify Supertrend calculation against TradingView fixture."""
        fixture = self.fixtures['Supertrend']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.supertrend, fixture['supertrend'], delta=1e-5)

    def test_adx(self):
        """TASK-147: Verify ADX calculation against TradingView fixture."""
        fixture = self.fixtures['ADX']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.adx, fixture['adx'], delta=1e-5)
        self.assertAlmostEqual(result.adx_plus, fixture['adx_plus'], delta=1e-5)
        self.assertAlmostEqual(result.adx_minus, fixture['adx_minus'], delta=1e-5)

    def test_vwap(self):
        """TASK-147: Verify VWAP calculation against TradingView fixture."""
        fixture = self.fixtures['VWAP']
        result = compute_indicators(fixture['symbol'], ohlcv=fixture['ohlcv'])
        self.assertAlmostEqual(result.vwap, fixture['vwap'], delta=1e-5)

    def test_empty_input(self):
        """TASK-147: Verify indicator calculations handle empty input."""
        result = compute_indicators("NIFTY", ohlcv=[])
        self.assertIsNotNone(result)
        self.assertIsInstance(result, IndicatorResult)

    def test_insufficient_history(self):
        """TASK-147: Verify indicator calculations handle insufficient bar history."""
        fixture = self.fixtures['SMA']
        short_ohlcv = fixture['ohlcv'][:10]  # Use only first 10 bars
        result = compute_indicators(fixture['symbol'], ohlcv=short_ohlcv)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, IndicatorResult)

    def test_constant_price_series(self):
        """TASK-147: Verify indicator calculations handle constant price series."""
        constant_ohlcv = [{'open': 100, 'high': 100, 'low': 100, 'close': 100, 'volume': 1000} for _ in range(100)]
        result = compute_indicators("NIFTY", ohlcv=constant_ohlcv)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, IndicatorResult)

if __name__ == '__main__':
    unittest.main()