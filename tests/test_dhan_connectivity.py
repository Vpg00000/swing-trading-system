import unittest
from unittest.mock import MagicMock
from data.dhan.client import DhanClient
from data.dhan.market_data import get_ltp, get_ohlc
from data.dhan.errors import DhanError


class TestDhanConnectivity(unittest.TestCase):

    def setUp(self):
        self.mock_sdk = MagicMock()

    def test_get_ltp_success(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        self.mock_sdk.get_ltp.return_value = {
            'status': 'success',
            'data': {'NSE_EQ': {'RELIANCE': {'last_price': 2900.0}}}
        }

        result = get_ltp(['RELIANCE'], client)
        self.assertEqual(result, {'RELIANCE': 2900.0})

    def test_get_ltp_failure(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        self.mock_sdk.get_ltp.return_value = {'status': 'failure', 'data': {}}

        with self.assertRaises(ValueError):
            get_ltp(['RELIANCE'], client)

    def test_get_ltp_exception(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        self.mock_sdk.get_ltp.side_effect = Exception('Network error')

        with self.assertRaises(DhanError):
            get_ltp(['RELIANCE'], client)

    def test_get_ohlc_success(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        expected_data = {
            'status': 'success',
            'data': {'NSE_EQ': [{'date': '2023-04-01', 'open': 2800.0, 'high': 2900.0, 'low': 2700.0, 'close': 2850.0, 'volume': 1000000}]}
        }
        self.mock_sdk.historical_daily_data.return_value = expected_data

        result = get_ohlc('RELIANCE', '1D', '2023-04-01', '2023-04-01', client)
        self.assertEqual(result, expected_data)

    def test_get_ohlc_failure(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        self.mock_sdk.historical_daily_data.return_value = {'status': 'failure', 'data': {}}

        result = get_ohlc('RELIANCE', '1D', '2023-04-01', '2023-04-01', client)
        self.assertEqual(result, {'status': 'failure', 'data': {}})

    def test_get_ohlc_exception(self):
        client = DhanClient()
        client._sdk = self.mock_sdk
        self.mock_sdk.historical_daily_data.side_effect = Exception('Network error')

        with self.assertRaises(DhanError):
            get_ohlc('RELIANCE', '1D', '2023-04-01', '2023-04-01', client)


if __name__ == '__main__':
    unittest.main()