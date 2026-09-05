import sqlite3
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

class SyncEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY,
                quantity REAL,
                cost_basis REAL,
                last_updated TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                quantity REAL,
                entry_price REAL,
                last_updated TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT,
                quantity REAL,
                price REAL,
                order_type TEXT,
                status TEXT,
                timestamp TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT,
                quantity REAL,
                price REAL,
                trade_type TEXT,
                timestamp TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS cash_balance (
                id INTEGER PRIMARY KEY,
                balance REAL,
                last_updated TIMESTAMP
            )
        ''')
        self.conn.commit()

    def verify_holdings(self, broker_data: List[Dict]) -> Tuple[bool, List[Dict]]:
        discrepancies = []
        for item in broker_data:
            self.cursor.execute('''
                SELECT quantity, cost_basis FROM holdings WHERE symbol = ?
            ''', (item['symbol'],))
            result = self.cursor.fetchone()
            if result is None or abs(result[0] - item['quantity']) > 1e-6 or abs(result[1] - item['cost_basis']) > 1e-6:
                discrepancies.append(item)
        return len(discrepancies) == 0, discrepancies

    def check_positions(self, broker_data: List[Dict]) -> Tuple[bool, List[Dict]]:
        discrepancies = []
        for item in broker_data:
            self.cursor.execute('''
                SELECT quantity, entry_price FROM positions WHERE symbol = ?
            ''', (item['symbol'],))
            result = self.cursor.fetchone()
            if result is None or abs(result[0] - item['quantity']) > 1e-6 or abs(result[1] - item['entry_price']) > 1e-6:
                discrepancies.append(item)
        return len(discrepancies) == 0, discrepancies

    def review_orders(self, broker_data: List[Dict]) -> Tuple[bool, List[Dict]]:
        discrepancies = []
        for item in broker_data:
            self.cursor.execute('''
                SELECT quantity, price, order_type, status FROM orders WHERE order_id = ?
            ''', (item['order_id'],))
            result = self.cursor.fetchone()
            if result is None or abs(result[0] - item['quantity']) > 1e-6 or abs(result[1] - item['price']) > 1e-6 or result[2] != item['order_type'] or result[3] != item['status']:
                discrepancies.append(item)
        return len(discrepancies) == 0, discrepancies

    def ensure_trades_recorded(self, broker_data: List[Dict]) -> Tuple[bool, List[Dict]]:
        discrepancies = []
        for item in broker_data:
            self.cursor.execute('''
                SELECT quantity, price, trade_type FROM trades WHERE trade_id = ?
            ''', (item['trade_id'],))
            result = self.cursor.fetchone()
            if result is None or abs(result[0] - item['quantity']) > 1e-6 or abs(result[1] - item['price']) > 1e-6 or result[2] != item['trade_type']:
                discrepancies.append(item)
        return len(discrepancies) == 0, discrepancies

    def confirm_cash_balance(self, broker_balance: float) -> Tuple[bool, float]:
        self.cursor.execute('''
            SELECT balance FROM cash_balance ORDER BY last_updated DESC LIMIT 1
        ''')
        result = self.cursor.fetchone()
        if result is None:
            return False, 0.0
        system_balance = result[0]
        return abs(system_balance - broker_balance) < 1e-6, system_balance

    def update_holdings(self, holdings_data: List[Dict]):
        for item in holdings_data:
            self.cursor.execute('''
                INSERT OR REPLACE INTO holdings (symbol, quantity, cost_basis, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (item['symbol'], item['quantity'], item['cost_basis'], datetime.now()))
        self.conn.commit()

    def update_positions(self, positions_data: List[Dict]):
        for item in positions_data:
            self.cursor.execute('''
                INSERT OR REPLACE INTO positions (symbol, quantity, entry_price, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (item['symbol'], item['quantity'], item['entry_price'], datetime.now()))
        self.conn.commit()

    def update_orders(self, orders_data: List[Dict]):
        for item in orders_data:
            self.cursor.execute('''
                INSERT OR REPLACE INTO orders (order_id, symbol, quantity, price, order_type, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (item['order_id'], item['symbol'], item['quantity'], item['price'], item['order_type'], item['status'], datetime.strptime(item['timestamp'], '%Y-%m-%d %H:%M:%S')))
        self.conn.commit()

    def update_trades(self, trades_data: List[Dict]):
        for item in trades_data:
            self.cursor.execute('''
                INSERT OR REPLACE INTO trades (trade_id, symbol, quantity, price, trade_type, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item['trade_id'], item['symbol'], item['quantity'], item['price'], item['trade_type'], datetime.strptime(item['timestamp'], '%Y-%m-%d %H:%M:%S')))
        self.conn.commit()

    def update_cash_balance(self, balance: float):
        self.cursor.execute('''
            INSERT INTO cash_balance (balance, last_updated)
            VALUES (?, ?)
        ''', (balance, datetime.now()))
        self.conn.commit()

    def close(self):
        self.conn.close()

class LiveFeed:
    def __init__(self, sync_engine: SyncEngine, broker_api):
        self.sync_engine = sync_engine
        self.broker_api = broker_api

    def sync_data(self):
        start_time = time.time()

        # Verify holdings
        broker_holdings = self.broker_api.get_holdings()
        holdings_status, holdings_discrepancies = self.sync_engine.verify_holdings(broker_holdings)
        if not holdings_status:
            self.sync_engine.update_holdings(broker_holdings)

        # Check positions
        broker_positions = self.broker_api.get_positions()
        positions_status, positions_discrepancies = self.sync_engine.check_positions(broker_positions)
        if not positions_status:
            self.sync_engine.update_positions(broker_positions)

        # Review orders
        broker_orders = self.broker_api.get_orders()
        orders_status, orders_discrepancies = self.sync_engine.review_orders(broker_orders)
        if not orders_status:
            self.sync_engine.update_orders(broker_orders)

        # Ensure trades are recorded
        broker_trades = self.broker_api.get_trades()
        trades_status, trades_discrepancies = self.sync_engine.ensure_trades_recorded(broker_trades)
        if not trades_status:
            self.sync_engine.update_trades(broker_trades)

        # Confirm cash balance
        broker_balance = self.broker_api.get_cash_balance()
        balance_status, system_balance = self.sync_engine.confirm_cash_balance(broker_balance)
        if not balance_status:
            self.sync_engine.update_cash_balance(broker_balance)

        end_time = time.time()
        print(f"Data synchronization completed in {end_time - start_time:.2f} seconds")

        return {
            'holdings': holdings_discrepancies,
            'positions': positions_discrepancies,
            'orders': orders_discrepancies,
            'trades': trades_discrepancies,
            'cash_balance': system_balance if balance_status else broker_balance
        }