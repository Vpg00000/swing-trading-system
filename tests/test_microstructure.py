import pytest
from data.microstructure import calculate_order_book_imbalance

def test_calculate_order_book_imbalance_zero_volume():
    bids = [{"quantity": 0}]
    asks = [{"quantity": 0}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_100_percent_bids():
    bids = [{"quantity": 100}]
    asks = [{"quantity": 0}]
    assert calculate_order_book_imbalance(bids, asks) == 1.0

def test_calculate_order_book_imbalance_100_percent_asks():
    bids = [{"quantity": 0}]
    asks = [{"quantity": 100}]
    assert calculate_order_book_imbalance(bids, asks) == -1.0

def test_calculate_order_book_imbalance_balanced_order_book():
    bids = [{"quantity": 50}]
    asks = [{"quantity": 50}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_partial_depth_data():
    bids = [{"quantity": 10}, {"quantity": 20}]
    asks = [{"quantity": 30}]
    assert calculate_order_book_imbalance(bids, asks) == 0.0

def test_calculate_order_book_imbalance_variable_depth_input():
    bids = [{"quantity": 10}]
    asks = [{"quantity": 20}, {"quantity": 30}]
    assert calculate_order_book_imbalance(bids, asks) == -0.667