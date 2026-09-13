import json
import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union
from data.dhan.client import DhanClient
from data.dhan.holdings import get_holdings, get_positions, get_orders, get_trades, get_cash
from data.database import get_connection, upsert_portfolio_snapshot

class PortfolioManager:
    def __init__(self):
        self.client = DhanClient()

    def fetch_and_store_portfolio(self):
        holdings = get_holdings(self.client)
        if not holdings:
            return None

        positions = get_positions(self.client)
        orders = get_orders(self.client)
        trades = get_trades(self.client)
        cash = get_cash(self.client)

        portfolio_state = {
            "holdings": holdings,
            "positions": positions,
            "orders": orders,
            "trades": trades,
            "cash": cash,
            "timestamp": datetime.datetime.now().isoformat()
        }

        return self.store_portfolio_state(portfolio_state)

    def aggregate_portfolio_state(self, holdings, positions, orders, trades, cash):
        return {
            "holdings": holdings,
            "positions": positions,
            "orders": orders,
            "trades": trades,
            "cash": cash,
            "timestamp": datetime.datetime.now().isoformat()
        }

    def reconcile_portfolio(self, portfolio_state):
        holdings = portfolio_state.get('holdings', [])
        positions = portfolio_state.get('positions', [])
        orders = portfolio_state.get('orders', [])
        trades = portfolio_state.get('trades', [])
        cash = portfolio_state.get('cash', 0.0)

        # Calculate net asset value (NAV)
        nav = sum(holding.get('quantity', 0) * holding.get('price', 0.0) for holding in holdings) + cash

        # Calculate total invested value
        total_invested = sum(trade.get('quantity', 0) * trade.get('price', 0.0) for trade in trades)

        # Calculate realized P&L
        realized_pnl = sum(trade.get('quantity', 0) * (trade.get('price', 0.0) - trade.get('average_price', 0.0)) for trade in trades)

        # Calculate unrealized P&L
        unrealized_pnl = 0.0
        for holding in holdings:
            h_sym = holding.get('symbol')
            h_qty = holding.get('quantity', 0)
            h_price = holding.get('price', 0.0)
            matching_trades = [t for t in trades if t.get('symbol') == h_sym]
            if matching_trades:
                traded_qty = sum(t.get('quantity', 0) for t in matching_trades)
                avg_trade_price = sum(t.get('quantity', 0) * t.get('average_price', t.get('price', 0.0)) for t in matching_trades) / traded_qty if traded_qty > 0 else h_price
                unrealized_pnl += (h_qty - traded_qty) * (h_price - avg_trade_price)
            else:
                cost_p = holding.get('cost_price', holding.get('average_price', h_price))
                unrealized_pnl += h_qty * (h_price - cost_p)


        # Calculate position drift
        position_drift = sum(abs(position['quantity'] - sum(trade['quantity'] for trade in trades if trade['symbol'] == position['symbol'])) for position in positions)

        # Calculate quantity drift
        quantity_drift = sum(abs(holding['quantity'] - sum(trade['quantity'] for trade in trades if trade['symbol'] == holding['symbol'])) for holding in holdings)

        # Calculate weight drift
        weight_drift = sum(abs(holding['quantity'] * holding['price'] - sum(trade['quantity'] * trade['price'] for trade in trades if trade['symbol'] == holding['symbol'])) for holding in holdings)

        # Calculate capacity
        capacity = sum(holding['quantity'] * holding['price'] for holding in holdings)

        # Calculate cash reserve
        cash_reserve = cash

        return {
            "nav": nav,
            "total_invested": total_invested,
            "cash": cash,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "position_drift": position_drift,
            "quantity_drift": quantity_drift,
            "weight_drift": weight_drift,
            "capacity": capacity,
            "cash_reserve": cash_reserve,
            "timestamp": datetime.datetime.now().isoformat()
        }

    def store_portfolio_state(self, portfolio_state):
        conn = get_connection()
        cursor = conn.cursor()

        # Using prepared statements to avoid SQL injection
        prepared = {
            'holdings': json.dumps(portfolio_state.get('holdings', [])),
            'positions': json.dumps(portfolio_state.get('positions', [])),
            'orders': json.dumps(portfolio_state.get('orders', [])),
            'trades': json.dumps(portfolio_state.get('trades', [])),
            'cash': portfolio_state.get('cash', 0.0),
            'timestamp': portfolio_state.get('timestamp', datetime.datetime.now().isoformat())
        }

        cursor.execute("""
            INSERT INTO portfolio_snapshots
            (holdings, positions, orders, trades, cash, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, tuple(prepared.values()))

        conn.commit()
        conn.close()

def fetch_and_store_portfolio_state():
    manager = PortfolioManager()
    return manager.fetch_and_store_portfolio()

def reconcile_portfolio_state(portfolio_state=None):
    manager = PortfolioManager()
    if portfolio_state is None:
        portfolio_state = manager.fetch_and_store_portfolio() or {}
    return manager.reconcile_portfolio(portfolio_state)

def generate_portfolio_snapshot(portfolio_state=None):
    manager = PortfolioManager()
    if portfolio_state is None:
        portfolio_state = manager.fetch_and_store_portfolio() or {}
    return manager.aggregate_portfolio_state(
        portfolio_state.get('holdings', []),
        portfolio_state.get('positions', []),
        portfolio_state.get('orders', []),
        portfolio_state.get('trades', []),
        portfolio_state.get('cash', 0.0)
    )

def aggregate_multi_account_portfolios(account_states: list[dict]) -> dict:
    """TASK-059: Multi-Broker Family Demat Account Portfolio Aggregator."""
    combined_holdings = {}
    total_cash = 0.0
    total_value = 0.0

    for acc in account_states:
        acc_name = acc.get("account_name", acc.get("broker", "PRIMARY_ACCOUNT"))
        cash = acc.get("cash", acc.get("cash_inr", 0.0))
        total_cash += cash

        for h in acc.get("holdings", []):
            sym = h.get("symbol", "UNKNOWN")
            qty = h.get("quantity", 0)
            price = h.get("price", h.get("current_price", 0.0))
            val = qty * price
            total_value += val

            if sym not in combined_holdings:
                combined_holdings[sym] = {
                    "symbol": sym,
                    "quantity": 0,
                    "total_value_inr": 0.0,
                    "current_price": price,
                    "accounts": []
                }
            combined_holdings[sym]["quantity"] += qty
            combined_holdings[sym]["total_value_inr"] += val
            combined_holdings[sym]["accounts"].append({"account": acc_name, "quantity": qty})

    total_portfolio_nav = total_cash + total_value

    return {
        "account_count": len(account_states),
        "total_cash_inr": round(total_cash, 2),
        "total_holdings_value_inr": round(total_value, 2),
        "total_portfolio_nav_inr": round(total_portfolio_nav, 2),
        "unique_symbols_count": len(combined_holdings),
        "holdings": list(combined_holdings.values())
    }


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: int
    entry_date: Any
    holding_days: int = 0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    atr_at_entry: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    tax_status: str = "STCG"
    sector: str = "Unknown"
    is_core_momentum: bool = True

    def update_price(self, current_price: float):
        self.current_price = current_price
        self.unrealized_pnl = round((current_price - self.entry_price) * self.quantity, 2)
        self.unrealized_pnl_pct = round(((current_price / self.entry_price) - 1.0) * 100.0, 2) if self.entry_price > 0 else 0.0
        if self.holding_days >= 365:
            self.tax_status = "LTCG"
        else:
            self.tax_status = f"STCG_{365 - self.holding_days}D_TO_LTCG"


class Portfolio:
    """
    Real-time portfolio tracker and quantitative risk manager.
    Tracks NAV, sector concentrations, emergency drawdown status, and tax transitions.
    """
    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.nav = initial_capital
        self.peak_nav = initial_capital

    def add_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        entry_date: Any = None,
        atr_at_entry: float = 0.0,
        stop_price: float = 0.0,
        target_price: float = 0.0,
        sector: str = "Unknown",
        is_core_momentum: bool = True
    ) -> Position:
        cost = entry_price * quantity
        self.cash -= cost
        pos = Position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            entry_date=entry_date or datetime.date.today(),
            current_price=entry_price,
            atr_at_entry=atr_at_entry,
            stop_price=stop_price,
            target_price=target_price,
            sector=sector,
            is_core_momentum=is_core_momentum
        )
        self.positions[symbol] = pos
        self.recalculate_nav()
        return pos

    def update_position_price(self, symbol: str, current_price: float, holding_days: Optional[int] = None):
        if symbol in self.positions:
            pos = self.positions[symbol]
            if holding_days is not None:
                pos.holding_days = holding_days
            pos.update_price(current_price)
            self.recalculate_nav()

    def recalculate_nav(self) -> float:
        pos_val = sum(p.quantity * (p.current_price if p.current_price > 0 else p.entry_price) for p in self.positions.values())
        self.nav = round(self.cash + pos_val, 2)
        if self.nav > self.peak_nav:
            self.peak_nav = self.nav
        return self.nav

    def get_drawdown_pct(self) -> float:
        if self.peak_nav <= 0:
            return 0.0
        return round(((self.nav - self.peak_nav) / self.peak_nav) * 100.0, 2)

    def get_concentration_by_sector(self) -> Dict[str, float]:
        sector_vals: Dict[str, float] = {}
        for p in self.positions.values():
            val = p.quantity * (p.current_price if p.current_price > 0 else p.entry_price)
            sector_vals[p.sector] = sector_vals.get(p.sector, 0.0) + val
        if self.nav <= 0:
            return {}
        return {sec: round((val / self.nav) * 100.0, 2) for sec, val in sector_vals.items()}

    def get_tax_optimization_candidates(self, threshold_days: int = 30) -> List[Dict[str, Any]]:
        candidates = []
        for p in self.positions.values():
            days_left = 365 - p.holding_days
            if 0 < days_left <= threshold_days and p.unrealized_pnl > 0:
                candidates.append({
                    "symbol": p.symbol,
                    "holding_days": p.holding_days,
                    "days_to_ltcg": days_left,
                    "unrealized_pnl": p.unrealized_pnl,
                    "tax_savings_estimate_inr": round(p.unrealized_pnl * (0.20 - 0.125), 2),
                    "recommendation": f"Hold {days_left} more days to qualify for 12.5% LTCG"
                })
        return candidates


if __name__ == "__main__":
    portfolio_state = fetch_and_store_portfolio_state()
    print(portfolio_state)