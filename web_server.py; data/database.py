# web_server.py
from flask import Flask, request, jsonify
import time
from data.database import Database

app = Flask(__name__)
db = Database()

@app.route('/benchmark', methods=['GET'])
def benchmark():
    start_time = time.time()
    result = db.query("SELECT 1")
    end_time = time.time()
    latency = end_time - start_time
    return jsonify({"latency": latency})

if __name__ == '__main__':
    app.run(debug=True)

# database.py
import sqlite3
import time

class Database:
    def __init__(self, db_name='benchmark.db'):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS benchmark
                              (id INTEGER PRIMARY KEY, timestamp REAL)''')
        self.conn.commit()

    def query(self, query):
        start_time = time.time()
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        end_time = time.time()
        latency = end_time - start_time
        self._log_latency(latency)
        return result

    def _log_latency(self, latency):
        self.cursor.execute("INSERT INTO benchmark (timestamp) VALUES (?)", (latency,))
        self.conn.commit()

    def close(self):
        self.conn.close()