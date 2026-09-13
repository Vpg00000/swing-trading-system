import sqlite3
from datetime import datetime

class Backend:
    def __init__(self, db_path=':memory:'):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS Opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    position_size REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS Orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id INTEGER NOT NULL,
                    order_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (opportunity_id) REFERENCES Opportunities (id)
                )
            ''')
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS Trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    profit_loss REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (opportunity_id) REFERENCES Opportunities (id)
                )
            ''')

    def track_position(self, symbol, entry_price, stop_loss, take_profit, position_size):
        with self.conn:
            self.conn.execute('''
                INSERT INTO Opportunities (symbol, entry_price, stop_loss, take_profit, position_size, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, entry_price, stop_loss, take_profit, position_size, 'OPEN', datetime.now(), datetime.now()))

    def track_order(self, opportunity_id, order_type, price, quantity):
        with self.conn:
            self.conn.execute('''
                INSERT INTO Orders (opportunity_id, order_type, price, quantity, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (opportunity_id, order_type, price, quantity, 'PENDING', datetime.now()))

    def track_trade(self, opportunity_id, entry_price, exit_price, quantity):
        profit_loss = (exit_price - entry_price) * quantity
        with self.conn:
            self.conn.execute('''
                INSERT INTO Trades (opportunity_id, entry_price, exit_price, quantity, profit_loss, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (opportunity_id, entry_price, exit_price, quantity, profit_loss, datetime.now()))
            self.conn.execute('''
                UPDATE Opportunities SET status = 'CLOSED', updated_at = ? WHERE id = ?
            ''', (datetime.now(), opportunity_id))

    def get_current_positions(self):
        with self.conn:
            cursor = self.conn.execute('''
                SELECT * FROM Opportunities WHERE status = 'OPEN'
            ''')
            return cursor.fetchall()

    def get_recent_orders(self, limit=10):
        with self.conn:
            cursor = self.conn.execute('''
                SELECT * FROM Orders ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            return cursor.fetchall()

    def get_executed_trades(self, limit=10):
        with self.conn:
            cursor = self.conn.execute('''
                SELECT * FROM Trades ORDER BY created_at DESC LIMIT ?
            ''', (limit,))
            return cursor.fetchall()

    def close(self):
        self.conn.close()