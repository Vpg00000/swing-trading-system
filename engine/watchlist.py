"""
Watchlist Engine & Custom Lists Management.

Provides CRUD operations for stock watchlists stored in SQLite (data/system.db).
Supports default watchlists ('Nifty 50', 'Breakout Candidates', 'High RSI', 'My Favorites')
and enriches watchlist items with live market metrics from stock_grid.
"""

import sqlite3
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "system.db"

DEFAULT_WATCHLISTS = {
    "Nifty 50": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "SBIN", "LTIM", "ITC", "LT"],
    "Breakout Candidates": ["TATAMOTORS", "SBIN", "ICICIBANK", "BHARTIARTL"],
    "High RSI": ["INFY", "TCS", "RELIANCE", "LTIM"],
    "My Favorites": ["RELIANCE", "TCS"]
}


class WatchlistManager:
    """Manages custom stock watchlists stored in SQLite database."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        """Create watchlists table and seed default watchlists if empty."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    symbol TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, symbol)
                );
            """)
            conn.commit()

        self._seed_default_watchlists()

    def _seed_default_watchlists(self):
        """Seed default watchlists if they don't already exist."""
        existing = set(self.get_watchlist_names())
        with self._get_connection() as conn:
            for name, symbols in DEFAULT_WATCHLISTS.items():
                if name not in existing:
                    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    if symbols:
                        for sym in symbols:
                            conn.execute(
                                "INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)",
                                (name, sym.upper(), now)
                            )
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)",
                            (name, None, now)
                        )
            conn.commit()

    def get_watchlist_names(self) -> List[str]:
        """Return list of distinct watchlist names."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT name FROM watchlists ORDER BY id ASC").fetchall()
            return [row["name"] for row in rows if row["name"]]

    def _fetch_stock_metrics(self, conn: sqlite3.Connection, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch stock metrics from stock_grid table for given symbols."""
        if not symbols:
            return {}
        metrics_map = {}
        try:
            placeholders = ",".join(["?"] * len(symbols))
            rows = conn.execute(
                f"SELECT symbol, close, change_pct, composite_score, action, volume FROM stock_grid WHERE symbol IN ({placeholders})",
                symbols
            ).fetchall()
            for r in rows:
                metrics_map[r["symbol"].upper()] = {
                    "ltp": float(r["close"]) if r["close"] is not None else 0.0,
                    "change_pct": float(r["change_pct"]) if r["change_pct"] is not None else 0.0,
                    "score": float(r["composite_score"]) if r["composite_score"] is not None else 0.0,
                    "signal": str(r["action"]) if r["action"] is not None else "NEUTRAL",
                    "volume": int(r["volume"]) if r["volume"] is not None else 0,
                }
        except sqlite3.OperationalError:
            # stock_grid table might not exist in SQLite DB
            pass
        return metrics_map

    def get_user_watchlists(self, name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch custom watchlists. If name is specified, return only that watchlist.
        Returns a dictionary mapping watchlist name to list of items.
        Each item contains: symbol, ltp, change_pct, score, signal, volume, added_at.
        """
        with self._get_connection() as conn:
            if name:
                rows = conn.execute(
                    "SELECT name, symbol, added_at FROM watchlists WHERE name = ? ORDER BY id ASC",
                    (name,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT name, symbol, added_at FROM watchlists ORDER BY id ASC"
                ).fetchall()

            if not rows and name:
                return {}

            wl_items: Dict[str, List[Dict[str, Any]]] = {}
            all_symbols = set()
            for r in rows:
                wl_name = r["name"]
                if wl_name not in wl_items:
                    wl_items[wl_name] = []
                if r["symbol"]:
                    all_symbols.add(r["symbol"].upper())

            metrics_map = self._fetch_stock_metrics(conn, list(all_symbols))

            for r in rows:
                wl_name = r["name"]
                sym = r["symbol"]
                if not sym:
                    continue
                sym_upper = sym.upper()
                m = metrics_map.get(sym_upper, {})
                item = {
                    "symbol": sym_upper,
                    "ltp": m.get("ltp", 0.0),
                    "change_pct": m.get("change_pct", 0.0),
                    "score": m.get("score", 0.0),
                    "signal": m.get("signal", "NEUTRAL"),
                    "volume": m.get("volume", 0),
                    "added_at": r["added_at"] or ""
                }
                if not any(x["symbol"] == sym_upper for x in wl_items[wl_name]):
                    wl_items[wl_name].append(item)

            return wl_items

    def create_watchlist(self, name: str, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new custom watchlist with optional list of symbols."""
        name = name.strip()
        if not name:
            raise ValueError("Watchlist name cannot be empty")

        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            if symbols:
                for sym in symbols:
                    sym_clean = sym.strip().upper()
                    if sym_clean:
                        conn.execute(
                            "INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)",
                            (name, sym_clean, now)
                        )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)",
                    (name, None, now)
                )
            conn.commit()

        watchlists = self.get_user_watchlists(name=name)
        return {
            "name": name,
            "items": watchlists.get(name, [])
        }

    def add_symbol(self, name: str, symbol: str) -> Dict[str, Any]:
        """Add a stock symbol to a watchlist."""
        name = name.strip()
        symbol = symbol.strip().upper()
        if not name or not symbol:
            raise ValueError("Name and symbol must be non-empty")

        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("DELETE FROM watchlists WHERE name = ? AND symbol IS NULL", (name,))
            conn.execute(
                "INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)",
                (name, symbol, now)
            )
            conn.commit()

        watchlists = self.get_user_watchlists(name=name)
        return {
            "name": name,
            "items": watchlists.get(name, [])
        }

    def remove_symbol(self, name: str, symbol: str) -> bool:
        """Remove a stock symbol from a watchlist."""
        name = name.strip()
        symbol = symbol.strip().upper()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM watchlists WHERE name = ? AND symbol = ?", (name, symbol))
            conn.commit()
            removed = cursor.rowcount > 0

            count_row = conn.execute("SELECT COUNT(*) as cnt FROM watchlists WHERE name = ?", (name,)).fetchone()
            if count_row and count_row["cnt"] == 0:
                now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("INSERT OR IGNORE INTO watchlists (name, symbol, added_at) VALUES (?, ?, ?)", (name, None, now))
                conn.commit()
            return removed

    def delete_watchlist(self, name: str) -> bool:
        """Delete an entire watchlist by name."""
        name = name.strip()
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM watchlists WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0


def get_user_watchlists(name: Optional[str] = None, db_path: Optional[Union[str, Path]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Helper function to fetch user watchlists."""
    mgr = WatchlistManager(db_path=db_path)
    return mgr.get_user_watchlists(name=name)


def add_to_watchlist(name: str, symbol: str, db_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Helper function to add a symbol to a watchlist."""
    mgr = WatchlistManager(db_path=db_path)
    return mgr.add_symbol(name=name, symbol=symbol)


def remove_from_watchlist(name: str, symbol: str, db_path: Optional[Union[str, Path]] = None) -> bool:
    """Helper function to remove a symbol from a watchlist."""
    mgr = WatchlistManager(db_path=db_path)
    return mgr.remove_symbol(name=name, symbol=symbol)


def create_watchlist(name: str, symbols: Optional[List[str]] = None, db_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Helper function to create a new watchlist."""
    mgr = WatchlistManager(db_path=db_path)
    return mgr.create_watchlist(name=name, symbols=symbols)


def delete_watchlist(name: str, db_path: Optional[Union[str, Path]] = None) -> bool:
    """Helper function to delete a watchlist."""
    mgr = WatchlistManager(db_path=db_path)
    return mgr.delete_watchlist(name=name)
