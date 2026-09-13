"""
Shared NSE session/request helper -- single source of truth for the browser
headers and JSON-fetch pattern used by every module that hits
nseindia.com/api directly (corporate actions, insider trades, bulk/block
deals, pledge, shareholding). No login/session cookie is required for these
endpoints (confirmed empirically); if NSE's WAF starts requiring one, the
fallback is a GET to nseindia.com first to harvest cookies into the same
requests.Session before calling the API.
"""

import requests

BASE_URL = "https://www.nseindia.com/api"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def nse_get(session: requests.Session, path: str, params: dict, referer: str,
            timeout: int = 15) -> list | dict:
    """GET a nseindia.com/api/{path} endpoint. Returns [] if the response
    isn't the expected list/dict shape (NSE sometimes returns an error object
    instead of data -- callers should treat that the same as "no results")."""
    session.headers["Referer"] = referer
    resp = session.get(f"{BASE_URL}/{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, (list, dict)):
        return []
    return data
