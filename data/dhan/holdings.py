"""
Dhan holdings/positions sync -- stub layer, see data/dhan/client.py. Output
shape matches config/portfolio.json's existing holdings list
({"symbol", "value_inr", ...}) so engine/report.py can eventually consume
either source transparently, per the approved plan's Phase E integration
note -- this does not change report.py itself; that swap only happens once
get_holdings() is actually wired to real Dhan data and validated.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from data.dhan.client import DhanClient

import json
from data.dhan.market_data import get_ltp

PORTFOLIO_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "portfolio.json"

def get_holdings(client: DhanClient | None = None) -> list[dict] | None:
    """
    Fetches demat holdings from Dhan and formats them to match the system's expected schema.
    Merges local buy_date from portfolio.json if available.
    """
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        response = client.sdk.get_holdings()
    except Exception:
        return None

    if isinstance(response, dict):
        if response.get("status") == "failure" or "data" not in response:
            return None
        raw_holdings = response["data"]
    elif isinstance(response, list):
        raw_holdings = response
    else:
        return None

    # Load local portfolio.json to merge buy dates if they match the symbol
    local_holdings = {}
    if PORTFOLIO_PATH.exists():
        try:
            with open(PORTFOLIO_PATH) as f:
                p_data = json.load(f)
                local_holdings = {h["symbol"]: h for h in p_data.get("holdings", [])}
        except Exception:
            pass

    # Collect trading symbols to fetch current LTP
    symbols = []
    for h in raw_holdings:
        sym_name = h.get("tradingSymbol")
        if sym_name:
            sym = sym_name if sym_name.endswith(".NS") else f"{sym_name}.NS"
            symbols.append(sym)

    # Fetch live LTPs
    ltp_map = {}
    if symbols:
        try:
            ltp_map = get_ltp(symbols, client)
        except Exception:
            pass

    parsed = []
    for h in raw_holdings:
        sym_name = h.get("tradingSymbol")
        if not sym_name:
            continue

        sym = sym_name if sym_name.endswith(".NS") else f"{sym_name}.NS"
        qty = int(h.get("totalQty", 0))
        buy_price = float(h.get("avgCostPrice", 0.0))

        # Calculate current market value
        current_price = ltp_map.get(sym, buy_price)
        value_inr = qty * current_price

        holding_dict = {
            "symbol": sym,
            "quantity": qty,
            "buy_price": buy_price,
            "value_inr": round(value_inr, 2),
        }

        # Merge local metadata (like buy_date, sleeve) if it exists
        local_match = local_holdings.get(sym)
        if local_match:
            if "buy_date" in local_match:
                holding_dict["buy_date"] = local_match["buy_date"]
            if "sleeve" in local_match:
                holding_dict["sleeve"] = local_match["sleeve"]

        parsed.append(holding_dict)

    return parsed

def get_positions(client: DhanClient | None = None) -> list[dict] | None:
    """Fetches intraday/trading positions from Dhan."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        response = client.sdk.get_positions()
        if isinstance(response, dict):
            if response.get("status") == "failure" or "data" not in response:
                return None
            return response["data"]
        elif isinstance(response, list):
            return response
        return None
    except Exception:
        return None

def get_available_balance(client: DhanClient | None = None) -> float | None:
    """Fetches the available trading balance from Dhan, handling API spelling variance."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        funds = client.sdk.get_fund_limits()
        if isinstance(funds, dict):
            # If it's wrapped in status/data
            data = funds.get("data", {})
            if isinstance(data, dict) and data:
                for key in ("availabelBalance", "availableBalance"):
                    if key in data:
                        return float(data[key])
            # Direct response check
            for key in ("availabelBalance", "availableBalance"):
                if key in funds:
                    return float(funds[key])
        return None
    except Exception:
        return None

def get_orders(client: DhanClient | None = None) -> list[dict] | None:
    """Fetches active orders from Dhan."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        response = client.sdk.get_orders()
        if isinstance(response, dict):
            if response.get("status") == "failure" or "data" not in response:
                return None
            return response["data"]
        elif isinstance(response, list):
            return response
        return None
    except Exception:
        return None

def get_trades(client: DhanClient | None = None) -> list[dict] | None:
    """Fetches historical trades from Dhan."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        response = client.sdk.get_trades()
        if isinstance(response, dict):
            if response.get("status") == "failure" or "data" not in response:
                return None
            return response["data"]
        elif isinstance(response, list):
            return response
        return None
    except Exception:
        return None

def get_cash(client: DhanClient | None = None) -> float | None:
    """Fetches the available cash balance from Dhan."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        funds = client.sdk.get_fund_limits()
        if isinstance(funds, dict):
            # If it's wrapped in status/data
            data = funds.get("data", {})
            if isinstance(data, dict) and data:
                if "cashBalance" in data:
                    return float(data["cashBalance"])
            # Direct response check
            if "cashBalance" in funds:
                return float(funds["cashBalance"])
        return None
    except Exception:
        return None

def get_fund_limits(client: DhanClient | None = None) -> dict | None:
    """Fetches the fund limits from Dhan."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        funds = client.sdk.get_fund_limits()
        if isinstance(funds, dict):
            # If it's wrapped in status/data
            data = funds.get("data", {})
            if isinstance(data, dict) and data:
                return data
            # Direct response check
            return funds
        return None
    except Exception:
        return None

def get_portfolio_snapshot(client: DhanClient | None = None) -> dict | None:
    """Fetches a complete portfolio snapshot including holdings, positions, orders, trades, and cash balance."""
    client = client or DhanClient()
    if not client.is_active():
        return None

    try:
        holdings = get_holdings(client)
        positions = get_positions(client)
        orders = get_orders(client)
        trades = get_trades(client)
        cash = get_cash(client)

        snapshot = {
            "holdings": holdings,
            "positions": positions,
            "orders": orders,
            "trades": trades,
            "cash": cash
        }

        return snapshot
    except Exception:
        return None

if __name__ == "__main__":
    client = DhanClient()
    print(f"Dhan active: {client.is_active()}")
    holdings = get_holdings(client)
    positions = get_positions(client)
    available_balance = get_available_balance(client)
    orders = get_orders(client)
    trades = get_trades(client)
    cash = get_cash(client)
    fund_limits = get_fund_limits(client)
    portfolio_snapshot = get_portfolio_snapshot(client)

    if holdings is None:
        print("get_holdings() -> None (stub, falling back to config/portfolio.json)")
    else:
        print(f"get_holdings() -> {len(holdings)} holding(s)")

    if positions is None:
        print("get_positions() -> None")
    else:
        print(f"get_positions() -> {len(positions)} position(s)")

    if available_balance is None:
        print("get_available_balance() -> None")
    else:
        print(f"get_available_balance() -> {available_balance}")

    if orders is None:
        print("get_orders() -> None")
    else:
        print(f"get_orders() -> {len(orders)} order(s)")

    if trades is None:
        print("get_trades() -> None")
    else:
        print(f"get_trades() -> {len(trades)} trade(s)")

    if cash is None:
        print("get_cash() -> None")
    else:
        print(f"get_cash() -> {cash}")

    if fund_limits is None:
        print("get_fund_limits() -> None")
    else:
        print(f"get_fund_limits() -> {fund_limits}")

    if portfolio_snapshot is None:
        print("get_portfolio_snapshot() -> None")
    else:
        print("get_portfolio_snapshot() -> Portfolio snapshot generated successfully")