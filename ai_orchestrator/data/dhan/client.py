import requests
import json
from datetime import datetime
from typing import Dict, List, Optional, Union
from ai_orchestrator.data.dhan.auth import DhanAuth
from ai_orchestrator.data.dhan.exceptions import DhanAPIError, DhanAuthError
from ai_orchestrator.data.dhan.models import Holding, Position, Order, Trade, Cash
from ai_orchestrator.data.dhan.utils import validate_data, validate_response

class DhanClient:
    """
    A client for interacting with the Dhan API to fetch and manage holdings, positions, orders, trades, and cash.
    """

    def __init__(self, client_id: str, access_token: str, base_url: str = "https://api.dhan.co"):
        """
        Initialize the DhanClient with the provided client ID, access token, and base URL.

        Args:
            client_id (str): The client ID for the Dhan API.
            access_token (str): The access token for the Dhan API.
            base_url (str, optional): The base URL for the Dhan API. Defaults to "https://api.dhan.co".
        """
        self.client_id = client_id
        self.access_token = access_token
        self.base_url = base_url
        self.auth = DhanAuth(client_id, access_token, base_url)

    def _make_request(self, endpoint: str, method: str = 'GET', params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """
        Make a request to the Dhan API.

        Args:
            endpoint (str): The API endpoint to call.
            method (str, optional): The HTTP method to use. Defaults to 'GET'.
            params (Optional[Dict], optional): The query parameters for the request. Defaults to None.
            data (Optional[Dict], optional): The JSON data to send with the request. Defaults to None.

        Returns:
            Dict: The JSON response from the API.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }

        try:
            response = requests.request(method, url, headers=headers, params=params, json=data)
            response.raise_for_status()
            response_data = response.json()
            validate_response(response_data)
            return response_data
        except requests.exceptions.HTTPError as e:
            error_data = e.response.json()
            if e.response.status_code == 401:
                raise DhanAuthError(f"Authentication failed: {error_data.get('message', 'Unknown error')}")
            raise DhanAPIError(f"API request failed: {error_data.get('message', 'Unknown error')}")
        except requests.exceptions.RequestException as e:
            raise DhanAPIError(f"Request failed: {str(e)}")

    def get_holdings(self) -> List[Holding]:
        """
        Fetch the current holdings from the Dhan API.

        Returns:
            List[Holding]: A list of Holding objects representing the current holdings.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        endpoint = "/holdings"
        response_data = self._make_request(endpoint)
        holdings_data = response_data.get('data', {}).get('holdings', [])
        validate_data(holdings_data, Holding)
        return [Holding(**holding) for holding in holdings_data]

    def get_positions(self) -> List[Position]:
        """
        Fetch the current positions from the Dhan API.

        Returns:
            List[Position]: A list of Position objects representing the current positions.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        endpoint = "/positions"
        response_data = self._make_request(endpoint)
        positions_data = response_data.get('data', {}).get('positions', [])
        validate_data(positions_data, Position)
        return [Position(**position) for position in positions_data]

    def get_orders(self, status: Optional[str] = None) -> List[Order]:
        """
        Fetch the orders from the Dhan API.

        Args:
            status (Optional[str], optional): The status of the orders to fetch. Defaults to None.

        Returns:
            List[Order]: A list of Order objects representing the orders.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        endpoint = "/orders"
        params = {'status': status} if status else None
        response_data = self._make_request(endpoint, params=params)
        orders_data = response_data.get('data', {}).get('orders', [])
        validate_data(orders_data, Order)
        return [Order(**order) for order in orders_data]

    def get_trades(self, from_date: Optional[datetime] = None, to_date: Optional[datetime] = None) -> List[Trade]:
        """
        Fetch the trades from the Dhan API.

        Args:
            from_date (Optional[datetime], optional): The start date for the trades. Defaults to None.
            to_date (Optional[datetime], optional): The end date for the trades. Defaults to None.

        Returns:
            List[Trade]: A list of Trade objects representing the trades.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        endpoint = "/trades"
        params = {}
        if from_date:
            params['from_date'] = from_date.strftime('%Y-%m-%d')
        if to_date:
            params['to_date'] = to_date.strftime('%Y-%m-%d')
        response_data = self._make_request(endpoint, params=params)
        trades_data = response_data.get('data', {}).get('trades', [])
        validate_data(trades_data, Trade)
        return [Trade(**trade) for trade in trades_data]

    def get_cash(self) -> Cash:
        """
        Fetch the cash balance from the Dhan API.

        Returns:
            Cash: A Cash object representing the cash balance.

        Raises:
            DhanAPIError: If the API request fails.
            DhanAuthError: If the authentication fails.
        """
        endpoint = "/cash"
        response_data = self._make_request(endpoint)
        cash_data = response_data.get('data', {})
        validate_data(cash_data, Cash)
        return Cash(**cash_data)

    def verify_holdings(self, expected_holdings: List[Holding]) -> bool:
        """
        Verify the actual holdings against the expected holdings.

        Args:
            expected_holdings (List[Holding]): The expected holdings to verify against.

        Returns:
            bool: True if the actual holdings match the expected holdings, False otherwise.
        """
        actual_holdings = self.get_holdings()
        return sorted(actual_holdings, key=lambda x: x.security_id) == sorted(expected_holdings, key=lambda x: x.security_id)

    def verify_positions(self, expected_positions: List[Position]) -> bool:
        """
        Verify the actual positions against the expected positions.

        Args:
            expected_positions (List[Position]): The expected positions to verify against.

        Returns:
            bool: True if the actual positions match the expected positions, False otherwise.
        """
        actual_positions = self.get_positions()
        return sorted(actual_positions, key=lambda x: x.security_id) == sorted(expected_positions, key=lambda x: x.security_id)

    def verify_orders(self, expected_orders: List[Order]) -> bool:
        """
        Verify the actual orders against the expected orders.

        Args:
            expected_orders (List[Order]): The expected orders to verify against.

        Returns:
            bool: True if the actual orders match the expected orders, False otherwise.
        """
        actual_orders = self.get_orders()
        return sorted(actual_orders, key=lambda x: x.order_id) == sorted(expected_orders, key=lambda x: x.order_id)

    def verify_trades(self, expected_trades: List[Trade]) -> bool:
        """
        Verify the actual trades against the expected trades.

        Args:
            expected_trades (List[Trade]): The expected trades to verify against.

        Returns:
            bool: True if the actual trades match the expected trades, False otherwise.
        """
        actual_trades = self.get_trades()
        return sorted(actual_trades, key=lambda x: x.trade_id) == sorted(expected_trades, key=lambda x: x.trade_id)

    def verify_cash(self, expected_cash: Cash) -> bool:
        """
        Verify the actual cash balance against the expected cash balance.

        Args:
            expected_cash (Cash): The expected cash balance to verify against.

        Returns:
            bool: True if the actual cash balance matches the expected cash balance, False otherwise.
        """
        actual_cash = self.get_cash()
        return actual_cash == expected_cash