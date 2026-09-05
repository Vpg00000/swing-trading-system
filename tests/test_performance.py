import time
import pytest
from fastapi.testclient import TestClient
from web_server import app
from data.database import get_connection

@pytest.fixture
def client():
    return TestClient(app)

def test_database_cold_load_latency():
    start_time = time.perf_counter()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    end_time = time.perf_counter()
    cold_load_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert cold_load_latency < 50
    print(f"Database cold load latency: {cold_load_latency:.2f} ms")

def test_database_warm_load_latency():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    conn.close()

    start_time = time.perf_counter()
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT name FROM sqlite_master WHERE type='table';")
    conn2.close()
    end_time = time.perf_counter()
    warm_load_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert warm_load_latency < 50
    print(f"Database warm load latency: {warm_load_latency:.2f} ms")

def test_database_500_stock_query_latency():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    conn.close()

    start_time = time.perf_counter()
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT * FROM stock_grid LIMIT 500;")
    stocks = cursor2.fetchall()
    conn2.close()
    end_time = time.perf_counter()
    query_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert query_latency < 100
    print(f"Database 500-stock query latency: {query_latency:.2f} ms")

def test_database_filtered_query_latency():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    conn.close()

    start_time = time.perf_counter()
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT * FROM stock_grid WHERE sector = 'Technology' LIMIT 500;")
    stocks = cursor2.fetchall()
    conn2.close()
    end_time = time.perf_counter()
    query_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert query_latency < 100
    print(f"Database filtered query latency: {query_latency:.2f} ms")

def test_database_sorted_query_latency():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    conn.close()

    start_time = time.perf_counter()
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT * FROM stock_grid ORDER BY market_cap_cr DESC LIMIT 500;")
    stocks = cursor2.fetchall()
    conn2.close()
    end_time = time.perf_counter()
    query_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert query_latency < 100
    print(f"Database sorted query latency: {query_latency:.2f} ms")

def test_http_api_cold_load_latency(client):
    start_time = time.perf_counter()
    res = client.get('/api/health')
    end_time = time.perf_counter()
    cold_load_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert res.status_code == 200
    assert cold_load_latency < 200
    print(f"HTTP API cold load latency: {cold_load_latency:.2f} ms")

def test_http_api_warm_load_latency(client):
    client.get('/api/health')
    start_time = time.perf_counter()
    res = client.get('/api/health')
    end_time = time.perf_counter()
    warm_load_latency = (end_time - start_time) * 1000  # Convert to milliseconds
    assert res.status_code == 200
    assert warm_load_latency < 200
    print(f"HTTP API warm load latency: {warm_load_latency:.2f} ms")

def test_http_api_query_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res = client.get('/api/health')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 200
    print(f"HTTP API query response time - Median: {median:.2f} ms")

def test_http_api_500_stock_query_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res = client.get('/api/grid/stocks?limit=500')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 200
    print(f"HTTP API 500-stock query response time - Median: {median:.2f} ms")

def test_http_api_filtered_query_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res = client.get('/api/grid/stocks?sector=Technology&limit=500')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 200
    print(f"HTTP API filtered query response time - Median: {median:.2f} ms")

def test_http_api_sorted_query_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res = client.get('/api/grid/stocks?sort=market_cap&order=desc&limit=500')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 200
    print(f"HTTP API sorted query response time - Median: {median:.2f} ms")

def test_http_api_detail_page_query_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res1 = client.get('/api/grid/stocks/1')
        res2 = client.get('/api/grid/stocks/1/financials')
        res3 = client.get('/api/grid/stocks/1/news')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 300
    print(f"HTTP API detail page query response time - Median: {median:.2f} ms")

def test_http_api_dashboard_load_response_time(client):
    execution_times = []
    for _ in range(20):
        start_time = time.perf_counter()
        res1 = client.get('/api/grid/stocks?limit=10')
        res2 = client.get('/api/grid/stocks?sort=market_cap&order=desc&limit=5')
        res3 = client.get('/api/grid/stocks?sector=Technology&limit=5')
        res4 = client.get('/api/grid/stocks?sector=Healthcare&limit=5')
        res5 = client.get('/api/grid/stocks?sector=Financials&limit=5')
        end_time = time.perf_counter()
        execution_times.append((end_time - start_time) * 1000)  # Convert to milliseconds
    execution_times.sort()
    median = execution_times[len(execution_times) // 2]
    assert median < 400
    print(f"HTTP API dashboard load response time - Median: {median:.2f} ms")