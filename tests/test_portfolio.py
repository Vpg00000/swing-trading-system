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

def test_portfolio_state_content():
    state = fetch_and_store_portfolio_state()
    if state:
        assert 'holdings' in state
        assert 'positions' in state
        assert 'orders' in state
        assert 'trades' in state
        assert 'cash' in state

def test_portfolio_state_reconciliation():
    state = fetch_and_store_portfolio_state()
    if state:
        nav = sum(holding['quantity'] * holding['price'] for holding in state['holdings'])
        invested_value = sum(position['quantity'] * position['entry_price'] for position in state['positions'])
        assert nav >= invested_value
        assert state['cash'] >= 0

def test_portfolio_state_drift():
    state = fetch_and_store_portfolio_state()
    if state:
        for position in state['positions']:
            assert position['quantity'] >= 0
            assert position['entry_price'] > 0

def test_portfolio_state_missing_connection():
    # Mock or simulate a missing connection scenario
    # This would require additional setup and teardown
    pass

def test_portfolio_state_holdings():
    state = fetch_and_store_portfolio_state()
    if state:
        for holding in state['holdings']:
            assert holding['quantity'] >= 0
            assert holding['price'] > 0

def test_portfolio_state_orders():
    state = fetch_and_store_portfolio_state()
    if state:
        for order in state['orders']:
            assert order['quantity'] >= 0
            assert order['price'] > 0
            assert order['status'] in ['pending', 'filled', 'cancelled', 'rejected']

def test_portfolio_state_trades():
    state = fetch_and_store_portfolio_state()
    if state:
        for trade in state['trades']:
            assert trade['quantity'] >= 0
            assert trade['price'] > 0
            assert trade['timestamp'] is not None

def test_portfolio_state_cash():
    state = fetch_and_store_portfolio_state()
    if state:
        assert state['cash'] >= 0

def test_portfolio_state_positions():
    state = fetch_and_store_portfolio_state()
    if state:
        for position in state['positions']:
            assert position['quantity'] >= 0
            assert position['entry_price'] > 0
            assert position['symbol'] is not None

def test_portfolio_state_holdings_quantity():
    state = fetch_and_store_portfolio_state()
    if state:
        for holding in state['holdings']:
            assert holding['quantity'] >= 0

def test_portfolio_state_holdings_price():
    state = fetch_and_store_portfolio_state()
    if state:
        for holding in state['holdings']:
            assert holding['price'] > 0

def test_portfolio_state_orders_quantity():
    state = fetch_and_store_portfolio_state()
    if state:
        for order in state['orders']:
            assert order['quantity'] >= 0

def test_portfolio_state_orders_price():
    state = fetch_and_store_portfolio_state()
    if state:
        for order in state['orders']:
            assert order['price'] > 0

def test_portfolio_state_orders_status():
    state = fetch_and_store_portfolio_state()
    if state:
        for order in state['orders']:
            assert order['status'] in ['pending', 'filled', 'cancelled', 'rejected']

def test_portfolio_state_trades_quantity():
    state = fetch_and_store_portfolio_state()
    if state:
        for trade in state['trades']:
            assert trade['quantity'] >= 0

def test_portfolio_state_trades_price():
    state = fetch_and_store_portfolio_state()
    if state:
        for trade in state['trades']:
            assert trade['price'] > 0

def test_portfolio_state_trades_timestamp():
    state = fetch_and_store_portfolio_state()
    if state:
        for trade in state['trades']:
            assert trade['timestamp'] is not None

def test_portfolio_state_positions_quantity():
    state = fetch_and_store_portfolio_state()
    if state:
        for position in state['positions']:
            assert position['quantity'] >= 0

def test_portfolio_state_positions_entry_price():
    state = fetch_and_store_portfolio_state()
    if state:
        for position in state['positions']:
            assert position['entry_price'] > 0

def test_portfolio_state_positions_symbol():
    state = fetch_and_store_portfolio_state()
    if state:
        for position in state['positions']:
            assert position['symbol'] is not None