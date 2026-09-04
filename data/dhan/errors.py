"""
Dhan API exception classes.
"""

class DhanError(Exception):
    """Base exception for all Dhan API errors."""
    pass

class DhanAuthenticationError(DhanError):
    """Raised when authentication fails or access token is expired."""
    pass

class DhanRateLimitError(DhanError):
    """Raised when Dhan API rate limits are exceeded."""
    pass

class DhanAPIError(DhanError):
    """Raised when Dhan API returns an error response."""
    def __init__(self, message: str, status_code: int = 400, error_code: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
