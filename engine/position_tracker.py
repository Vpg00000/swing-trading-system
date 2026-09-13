"""
Portfolio Position Tracker & P&L Engine (Phase 3 Task B).

Calculates:
- Unrealized P&L (INR & %)
- Realized P&L from execution logs & trade history
- Portfolio cost basis
- Daily change P&L & %
- Asset allocation % per sector
- Portfolio Sharpe & Sortino ratios
- Live holdings reconciliation with orders & trades
"""

from __future__ import annotations
import math
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np


class PositionTracker:
    """
    PositionTracker manages live holdings, active positions, orders, and execution logs.
    It calculates key risk/performance metrics (P&L, Sharpe, Sortino, Sector allocation)
    and reconciles holdings against trade logs.
    """

    def __init__(
        self,
        holdings: Optional[List[Dict[str, Any]]] = None,
        positions: Optional[List[Dict[str, Any]]] = None,
        orders: Optional[List[Dict[str, Any]]] = None,
        trades: Optional[List[Dict[str, Any]]] = None,
        cash: float = 0.0,
        historical_returns: Optional[List[float]] = None,
        sector_map: Optional[Dict[str, str]] = None,
        risk_free_rate: float = 0.05
    ):
        self.holdings = holdings or []
        self.positions = positions or []
        self.orders = orders or []
        self.trades = trades or []
        self.cash = float(cash)
        self.historical_returns = historical_returns or []
        self.sector_map = sector_map or {}
        self.risk_free_rate = float(risk_free_rate)

        # Normalize holdings/positions into active_positions
        self._active_positions = self._normalize_active_positions()

    def _get_sector(self, symbol: str) -> str:
        if symbol in self.sector_map:
            return self.sector_map[symbol]
        try:
            from engine.correlation import get_sector
            sec = get_sector(symbol)
            if sec and sec != "Unknown":
                return sec
        except Exception:
            pass
        return "Unassigned"

    def _normalize_active_positions(self) -> List[Dict[str, Any]]:
        """
        Combines holdings and open positions into a standard active positions list.
        """
        combined: Dict[str, Dict[str, Any]] = {}
        items = list(self.holdings) + list(self.positions)

        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol") or item.get("trading_symbol") or item.get("tradingsymbol") or item.get("ticker")
            if not symbol:
                continue

            qty = float(item.get("quantity") or item.get("qty") or item.get("netqty") or item.get("shares") or 0.0)
            if qty <= 0 and item.get("status") != "OPEN":
                # Skip zero/negative non-open items unless explicitly specified
                continue

            cost_price = float(
                item.get("cost_price") or item.get("average_price") or item.get("avg_price")
                or item.get("buy_price") or item.get("entry_price") or item.get("price") or 0.0
            )
            current_price = float(
                item.get("current_price") or item.get("last_price") or item.get("ltp")
                or item.get("close") or item.get("price") or cost_price
            )
            prev_close = float(
                item.get("previous_close") or item.get("prev_close") or item.get("close_price") or current_price
            )
            sector = item.get("sector") or self._get_sector(symbol)

            if symbol in combined:
                # Merge quantities and weighted average cost price
                existing = combined[symbol]
                total_qty = existing["quantity"] + qty
                if total_qty > 0:
                    merged_cost = ((existing["quantity"] * existing["cost_price"]) + (qty * cost_price)) / total_qty
                else:
                    merged_cost = cost_price
                combined[symbol]["quantity"] = total_qty
                combined[symbol]["cost_price"] = merged_cost
                combined[symbol]["current_price"] = current_price
                combined[symbol]["previous_close"] = prev_close
            else:
                combined[symbol] = {
                    "symbol": symbol,
                    "quantity": qty,
                    "cost_price": cost_price,
                    "current_price": current_price,
                    "previous_close": prev_close,
                    "sector": sector
                }

        active = []
        for symbol, pos in combined.items():
            qty = pos["quantity"]
            cost_price = pos["cost_price"]
            curr_price = pos["current_price"]
            prev_close = pos["previous_close"]

            cost_basis = qty * cost_price
            current_value = qty * curr_price
            unrealized_pnl = current_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

            daily_pnl = qty * (curr_price - prev_close)
            prev_val = qty * prev_close
            daily_pct = (daily_pnl / prev_val * 100.0) if prev_val > 0 else 0.0

            pos.update({
                "cost_basis": round(cost_basis, 2),
                "current_value": round(current_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "daily_change_pnl": round(daily_pnl, 2),
                "daily_change_pct": round(daily_pct, 2),
            })
            active.append(pos)

        return active

    def calculate_cost_basis(self) -> float:
        """Calculates total portfolio cost basis of active positions."""
        total = sum(p["cost_basis"] for p in self._active_positions)
        return round(total, 2)

    def calculate_unrealized_pnl(self) -> Tuple[float, float]:
        """Calculates total unrealized P&L in INR and %."""
        total_pnl = sum(p["unrealized_pnl"] for p in self._active_positions)
        cost_basis = self.calculate_cost_basis()
        pct = (total_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        return round(total_pnl, 2), round(pct, 2)

    def calculate_realized_pnl(self) -> float:
        """
        Calculates realized P&L from executed trades / closed positions.
        """
        realized_total = 0.0
        explicit_pnl_sum = 0.0
        has_explicit = False

        for item in self.trades + self.positions:
            if isinstance(item, dict) and "realized_pnl" in item and item["realized_pnl"] is not None:
                explicit_pnl_sum += float(item["realized_pnl"])
                has_explicit = True

        if has_explicit and explicit_pnl_sum != 0.0:
            return round(explicit_pnl_sum, 2)

        # Match BUY/SELL trades per symbol to compute realized P&L
        trades_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for trade in self.trades:
            if not isinstance(trade, dict):
                continue
            sym = trade.get("symbol") or trade.get("trading_symbol")
            if sym:
                trades_by_symbol.setdefault(sym, []).append(trade)

        for sym, sym_trades in trades_by_symbol.items():
            buy_lots: List[Dict[str, float]] = []
            for t in sym_trades:
                side = str(t.get("side") or t.get("transaction_type") or t.get("action") or "").strip().upper()
                qty = float(t.get("quantity") or t.get("qty") or 0.0)
                price = float(t.get("price") or t.get("average_price") or t.get("exec_price") or 0.0)

                is_buy = side in ["BUY", "B", "BUY_ORDER"] or (not side and qty > 0)
                is_sell = side in ["SELL", "S", "SELL_ORDER"] or (not side and qty < 0)

                if is_buy:
                    buy_lots.append({"qty": abs(qty), "price": price})
                elif is_sell:
                    sell_qty = abs(qty)
                    while sell_qty > 0 and buy_lots:
                        lot = buy_lots[0]
                        matched_qty = min(sell_qty, lot["qty"])
                        pnl = matched_qty * (price - lot["price"])
                        realized_total += pnl
                        sell_qty -= matched_qty
                        lot["qty"] -= matched_qty
                        if lot["qty"] <= 1e-6:
                            buy_lots.pop(0)

        return round(realized_total, 2)


    def calculate_daily_change(self) -> Tuple[float, float]:
        """Calculates total daily change P&L in INR and %."""
        total_daily_pnl = sum(p["daily_change_pnl"] for p in self._active_positions)
        total_current_val = sum(p["current_value"] for p in self._active_positions)
        total_prev_val = total_current_val - total_daily_pnl
        daily_pct = (total_daily_pnl / total_prev_val * 100.0) if total_prev_val > 0 else 0.0
        return round(total_daily_pnl, 2), round(daily_pct, 2)

    def calculate_sector_allocation(self) -> Dict[str, float]:
        """Calculates allocation % per sector (including Cash)."""
        holdings_value = sum(p["current_value"] for p in self._active_positions)
        nav = holdings_value + self.cash

        if nav <= 0:
            return {}

        sector_totals: Dict[str, float] = {}
        for p in self._active_positions:
            sec = p.get("sector") or "Unassigned"
            sector_totals[sec] = sector_totals.get(sec, 0.0) + p["current_value"]

        allocations: Dict[str, float] = {}
        for sec, val in sector_totals.items():
            allocations[sec] = round((val / nav) * 100.0, 2)

        if self.cash > 0:
            allocations["Cash"] = round((self.cash / nav) * 100.0, 2)

        return allocations

    def calculate_sharpe_ratio(self, returns: Optional[List[float]] = None) -> float:
        """
        Calculates annualized Sharpe Ratio.
        Sharpe = (mean_return - rf_daily) / std_return * sqrt(252)
        """
        rets = returns if returns is not None else self.historical_returns
        if not rets or len(rets) < 2:
            return 0.0

        arr = np.array(rets, dtype=float)
        rf_daily = (1.0 + self.risk_free_rate) ** (1.0 / 252.0) - 1.0
        std = np.std(arr, ddof=1)

        if std <= 1e-8:
            return 0.0

        excess_mean = np.mean(arr) - rf_daily
        sharpe = (excess_mean / std) * math.sqrt(252)
        return round(float(sharpe), 4)

    def calculate_sortino_ratio(self, returns: Optional[List[float]] = None) -> float:
        """
        Calculates annualized Sortino Ratio.
        Sortino = (mean_return - rf_daily) / downside_std * sqrt(252)
        """
        rets = returns if returns is not None else self.historical_returns
        if not rets or len(rets) < 2:
            return 0.0

        arr = np.array(rets, dtype=float)
        rf_daily = (1.0 + self.risk_free_rate) ** (1.0 / 252.0) - 1.0
        excess = arr - rf_daily
        downside = excess[excess < 0]

        if len(downside) == 0:
            mean_excess = float(np.mean(excess))
            return round(float((mean_excess / 1e-4) * math.sqrt(252)), 4) if mean_excess > 0 else 0.0

        downside_std = math.sqrt(np.mean(downside ** 2))
        if downside_std <= 1e-8:
            return 0.0

        excess_mean = float(np.mean(excess))
        sortino = (excess_mean / downside_std) * math.sqrt(252)
        return round(float(sortino), 4)

    def reconcile_holdings_with_orders(
        self,
        holdings: Optional[List[Dict[str, Any]]] = None,
        orders: Optional[List[Dict[str, Any]]] = None,
        trades: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Reconciles live holdings with pending/executed orders and execution logs.
        """
        h_list = holdings if holdings is not None else self.holdings
        o_list = orders if orders is not None else self.orders
        t_list = trades if trades is not None else self.trades

        discrepancies = []
        net_trades_qty: Dict[str, float] = {}
        for t in t_list:
            if not isinstance(t, dict):
                continue
            sym = t.get("symbol") or t.get("trading_symbol")
            if not sym:
                continue
            side = str(t.get("side") or t.get("transaction_type") or "").upper()
            qty = float(t.get("quantity") or t.get("qty") or 0.0)
            if side in ["BUY", "B"] or qty > 0:
                net_trades_qty[sym] = net_trades_qty.get(sym, 0.0) + abs(qty)
            elif side in ["SELL", "S"] or qty < 0:
                net_trades_qty[sym] = net_trades_qty.get(sym, 0.0) - abs(qty)

        for h in h_list:
            if not isinstance(h, dict):
                continue
            sym = h.get("symbol") or h.get("trading_symbol")
            if not sym:
                continue
            h_qty = float(h.get("quantity") or h.get("qty") or 0.0)

            if sym in net_trades_qty:
                t_qty = net_trades_qty[sym]
                diff = h_qty - t_qty
                if abs(diff) > 1e-4:
                    discrepancies.append({
                        "symbol": sym,
                        "holding_quantity": h_qty,
                        "executed_trade_quantity": t_qty,
                        "discrepancy": round(diff, 4),
                        "reason": f"Live holding qty ({h_qty}) differs from net executed trade qty ({t_qty})"
                    })

        pending_orders = [
            o for o in o_list if isinstance(o, dict) and
            str(o.get("status", "")).lower() in ["pending", "open", "trigger_pending"]
        ]

        return {
            "is_reconciled": len(discrepancies) == 0,
            "discrepancies_count": len(discrepancies),
            "discrepancies": discrepancies,
            "pending_orders_count": len(pending_orders),
            "total_executed_trades": len(t_list),
            "reconciled_holdings_count": len(h_list)
        }

    def get_summary(self) -> Dict[str, Any]:
        """Returns complete portfolio summary, active positions, realized P&L, and asset allocation."""
        cost_basis = self.calculate_cost_basis()
        unrealized_pnl, unrealized_pnl_pct = self.calculate_unrealized_pnl()
        realized_pnl = self.calculate_realized_pnl()
        daily_change_pnl, daily_change_pct = self.calculate_daily_change()
        sector_allocation = self.calculate_sector_allocation()
        sharpe = self.calculate_sharpe_ratio()
        sortino = self.calculate_sortino_ratio()

        holdings_value = sum(p["current_value"] for p in self._active_positions)
        nav = round(holdings_value + self.cash, 2)

        active_positions = []
        for p in self._active_positions:
            pos_copy = dict(p)
            pos_copy["allocation_pct"] = round((p["current_value"] / nav * 100.0), 2) if nav > 0 else 0.0
            active_positions.append(pos_copy)

        reconciliation = self.reconcile_holdings_with_orders()

        try:
            from engine.portfolio_optimizer import calculate_cvar_95
            cvar_95 = calculate_cvar_95(self.historical_returns)
        except Exception:
            cvar_95 = 0.025

        return {
            "total_value": nav,
            "nav": nav,
            "holdings_value": round(holdings_value, 2),
            "total_cost_basis": cost_basis,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "realized_pnl": realized_pnl,
            "daily_change_pnl": daily_change_pnl,
            "daily_change_pct": daily_change_pct,
            "cash": round(self.cash, 2),
            "active_positions": active_positions,
            "sector_allocation": sector_allocation,
            "asset_allocation": sector_allocation,
            "metrics": {
                "sharpe_ratio": sharpe,
                "sortino_ratio": sortino,
                "cvar_95": cvar_95
            },
            "reconciliation": reconciliation,
            "holdings": self.holdings,
            "positions": self.positions,
            "orders": self.orders,
            "trades": self.trades,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }


def get_portfolio_summary(
    holdings: Optional[List[Dict[str, Any]]] = None,
    positions: Optional[List[Dict[str, Any]]] = None,
    orders: Optional[List[Dict[str, Any]]] = None,
    trades: Optional[List[Dict[str, Any]]] = None,
    cash: Optional[float] = None,
    historical_returns: Optional[List[float]] = None,
    sector_map: Optional[Dict[str, str]] = None,
    risk_free_rate: float = 0.05
) -> Dict[str, Any]:
    """
    Exposes helper function get_portfolio_summary().
    If holdings/positions are not explicitly provided, attempts to fetch state from DB/broker.
    """
    if holdings is None and positions is None:
        try:
            from engine.portfolio_manager import fetch_and_store_portfolio_state
            state = fetch_and_store_portfolio_state() or {}
            holdings = state.get("holdings", [])
            positions = state.get("positions", [])
            orders = state.get("orders", [])
            trades = state.get("trades", [])
            if cash is None:
                cash = float(state.get("cash", 0.0))
        except Exception as exc:
            logging.warning(f"Could not fetch portfolio state automatically: {exc}")

    if holdings is None:
        holdings = []
    if positions is None:
        positions = []
    if orders is None:
        orders = []
    if trades is None:
        trades = []
    if cash is None:
        cash = 0.0

    tracker = PositionTracker(
        holdings=holdings,
        positions=positions,
        orders=orders,
        trades=trades,
        cash=cash,
        historical_returns=historical_returns,
        sector_map=sector_map,
        risk_free_rate=risk_free_rate
    )
    return tracker.get_summary()
