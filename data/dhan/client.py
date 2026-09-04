"""
Dhan API client wrapper -- stub layer, per the approved plan's Phase E.

Dhan was chosen over Zerodha Kite Connect specifically because Kite
Connect charges a monthly API subscription fee while Dhan's API is free --
this stub exists so the rest of the system (data/dhan/market_data.py,
data/dhan/holdings.py) has a stable interface to build against now, without
requiring live credentials yet. Per user's explicit choice: "Build as stub,
activate later" -- until real client_id/access_token are provided, every
call here returns None/empty rather than raising, so callers can fall back
to the existing yfinance EOD + manually-maintained config/portfolio.json
path (DESIGN.md's Phase 1 data source) with no code changes required on
their end.

Only exposes what a typical Dhan API plan actually offers (holdings, LTP,
OHLC) -- market depth and order placement are explicitly NOT wrapped here:
DESIGN.md and the user's own architecture pitch are unambiguous that this
system is recommendation-only and never auto-executes
(Dhan -> Python -> Claude -> Python -> Human -> Dhan, never
Claude -> Dhan directly).
"""

import os
import requests

try:
    from dhanhq import dhanhq as _dhanhq_sdk
except ImportError:
    _dhanhq_sdk = None


class DhanClient:
    """
    Thin wrapper around the official dhanhq SDK. Construct with explicit
    credentials, or leave both None to read from DHAN_CLIENT_ID /
    DHAN_ACCESS_TOKEN environment variables -- either way, `is_active()`
    tells callers whether this client can actually reach Dhan, so they can
    degrade gracefully instead of crashing when credentials aren't set up
    yet.
    """

    def __init__(self, client_id: str | None = None, access_token: str | None = None):
        self.client_id = client_id or os.environ.get("DHAN_CLIENT_ID")
        self.access_token = access_token or os.environ.get("DHAN_ACCESS_TOKEN")
        self._sdk = None

        if _dhanhq_sdk is not None and self.client_id and self.access_token:
            try:
                from dhanhq import DhanContext
                context = DhanContext(client_id=self.client_id, access_token=self.access_token)
                self._sdk = _dhanhq_sdk(context)
            except Exception:
                self._sdk = None

    def is_active(self) -> bool:
        """False until the dhanhq package is installed AND real credentials
        are supplied -- callers should check this before relying on any
        Dhan-sourced data and fall back to the yfinance/manual-portfolio
        path otherwise."""
        return self._sdk is not None

    @property
    def sdk(self):
        """Raw SDK handle for market_data.py / holdings.py to call directly
        -- None if not active."""
        return self._sdk

    def get_ltp(self, instrument_id: str) -> float | None:
        if not self.is_active():
            return None

        url = f"https://api.dhan.com/market_data/ltp?instrument_id={instrument_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json().get("ltp")
        return None


if __name__ == "__main__":
    client = DhanClient()
    if client.is_active():
        print("Dhan client is active (credentials + SDK present).")
        instrument_id = "test_instrument_id"  # Replace with actual instrument ID
        ltp = client.get_ltp(instrument_id)
        print(f"LTP for instrument {instrument_id}: {ltp}")
    else:
        reason = "dhanhq package not installed" if _dhanhq_sdk is None else \
            "DHAN_CLIENT_ID/DHAN_ACCESS_TOKEN not set"
        print(f"Dhan client is a stub ({reason}). "
              "Falling back to yfinance EOD + config/portfolio.json is expected for now.")