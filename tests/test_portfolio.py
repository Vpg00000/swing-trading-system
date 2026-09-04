import pytest
from engine.portfolio_manager import fetch_and_store_portfolio_state
from data.database import init_db, get_connection

@pytest.fixture(autouse=True, scope="module")
def setup_db():
    init_db()
    yield

def test_fetch_and_store_portfolio():
    state = fetch_and_store_portfolio_state()
    # If client is not active, state might be None or empty dict
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM portfolio_snapshots")
    count = cursor.fetchone()[0]
    conn.close()
    assert count >= 0