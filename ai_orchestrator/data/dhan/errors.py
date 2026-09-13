import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DhanError(Exception):
    """Base class for Dhan-related errors."""
    pass

class AuthenticationError(DhanError):
    """Raised when authentication with Dhan fails."""
    def __init__(self, message: str, response: Optional[Dict[str, Any]] = None):
        self.response = response
        super().__init__(message)

class DataValidationError(DhanError):
    """Raised when data validation fails."""
    def __init__(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.data = data
        super().__init__(message)

class ReconciliationError(DhanError):
    """Raised when reconciliation fails."""
    def __init__(self, message: str, expected: Optional[Dict[str, Any]] = None, actual: Optional[Dict[str, Any]] = None):
        self.expected = expected
        self.actual = actual
        super().__init__(message)

def validate_holdings(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Validate holdings data."""
    if expected != actual:
        raise DataValidationError("Holdings data validation failed", {"expected": expected, "actual": actual})

def validate_positions(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Validate positions data."""
    if expected != actual:
        raise DataValidationError("Positions data validation failed", {"expected": expected, "actual": actual})

def validate_orders(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Validate orders data."""
    if expected != actual:
        raise DataValidationError("Orders data validation failed", {"expected": expected, "actual": actual})

def validate_trades(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Validate trades data."""
    if expected != actual:
        raise DataValidationError("Trades data validation failed", {"expected": expected, "actual": actual})

def validate_cash(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Validate cash data."""
    if expected != actual:
        raise DataValidationError("Cash data validation failed", {"expected": expected, "actual": actual})

def reconcile_data(expected: Dict[str, Any], actual: Dict[str, Any]) -> None:
    """Reconcile expected and actual data."""
    if expected != actual:
        raise ReconciliationError("Data reconciliation failed", expected, actual)