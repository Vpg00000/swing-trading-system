"""
Unit tests for Algorithmic Execution Engine & Smart Pacing (Phase 20 - Tasks T-245 to T-254).
"""

import pytest
import time
from engine.algo_execution import (
    AlgoExecutionEngine,
    AlgoType,
    AlgoStatus,
    ChildOrderStatus,
    calculate_implementation_shortfall,
    generate_twap_slices,
    generate_vwap_slices,
    generate_iceberg_slice,
    evaluate_sniper_trigger,
    OrderPacer
)


def test_t245_twap_slice_calculations():
    """T-245 & T-254: Verify TWAP slice generation and integer distribution."""
    parent_id = "ALGO_TWAP_TEST"
    slices = generate_twap_slices(
        parent_id=parent_id,
        symbol="RELIANCE.NS",
        side="BUY",
        total_quantity=100,
        arrival_price=2850.0,
        duration_seconds=300,
        n_slices=5
    )
    assert len(slices) == 5
    total_slice_qty = sum(s.quantity for s in slices)
    assert total_slice_qty == 100
    assert slices[0].quantity == 20
    assert slices[4].quantity == 20
    assert slices[0].parent_id == parent_id

    # Test remainder distribution (103 qty / 5 slices)
    slices_rem = generate_twap_slices(
        parent_id=parent_id,
        symbol="RELIANCE.NS",
        side="BUY",
        total_quantity=103,
        arrival_price=2850.0,
        duration_seconds=300,
        n_slices=5
    )
    assert len(slices_rem) == 5
    assert sum(s.quantity for s in slices_rem) == 103
    assert slices_rem[0].quantity == 21
    assert slices_rem[1].quantity == 21
    assert slices_rem[2].quantity == 21
    assert slices_rem[3].quantity == 20
    assert slices_rem[4].quantity == 20


def test_t246_vwap_volume_curve_slicing():
    """T-246 & T-254: Verify VWAP slice generation matching market volume profile."""
    profile = [0.40, 0.10, 0.10, 0.40]  # U-shaped intraday volume curve
    slices = generate_vwap_slices(
        parent_id="ALGO_VWAP_TEST",
        symbol="TCS.NS",
        side="BUY",
        total_quantity=1000,
        arrival_price=3500.0,
        volume_profile=profile,
        duration_seconds=600
    )
    assert len(slices) == 4
    assert sum(s.quantity for s in slices) == 1000
    assert slices[0].quantity == 400
    assert slices[1].quantity == 100
    assert slices[2].quantity == 100
    assert slices[3].quantity == 400


def test_t247_iceberg_slice_generator():
    """T-247 & T-254: Verify Iceberg hidden child order release."""
    child = generate_iceberg_slice(
        parent_id="ALGO_ICE_TEST",
        symbol="INFY.NS",
        side="BUY",
        remaining_quantity=500,
        visible_quantity=100,
        arrival_price=1500.0,
        variance_pct=0.0
    )
    assert child is not None
    assert child.quantity == 100
    assert child.is_hidden is True
    assert child.symbol == "INFY.NS"


def test_t248_sniper_trigger_logic():
    """T-248 & T-254: Verify Sniper trigger threshold evaluation."""
    # BUY order triggers when market price <= trigger_price
    assert evaluate_sniper_trigger("BUY", current_market_price=2490.0, trigger_price=2500.0) is True
    assert evaluate_sniper_trigger("BUY", current_market_price=2510.0, trigger_price=2500.0) is False

    # SELL order triggers when market price >= trigger_price
    assert evaluate_sniper_trigger("SELL", current_market_price=2510.0, trigger_price=2500.0) is True
    assert evaluate_sniper_trigger("SELL", current_market_price=2490.0, trigger_price=2500.0) is False


def test_t249_implementation_shortfall_calculation():
    """T-249 & T-254: Verify Implementation Shortfall tracking vs arrival price."""
    # BUY: Arrival = 100, Avg Fill = 102, Qty = 100 -> Loss of ₹200 (200 bps)
    is_curr, is_bps = calculate_implementation_shortfall(
        side="BUY", arrival_price=100.0, avg_fill_price=102.0, filled_quantity=100, explicit_costs=0.0
    )
    assert is_curr == 200.0
    assert is_bps == 200.0

    # SELL: Arrival = 100, Avg Fill = 98, Qty = 100 -> Loss of ₹200 (200 bps)
    is_curr_sell, is_bps_sell = calculate_implementation_shortfall(
        side="SELL", arrival_price=100.0, avg_fill_price=98.0, filled_quantity=100, explicit_costs=0.0
    )
    assert is_curr_sell == 200.0
    assert is_bps_sell == 200.0


def test_t252_sebi_order_pacer():
    """T-252: Verify order pacer jitter & participation rate cap."""
    pacer = OrderPacer(min_delay_ms=500, max_participation_pct=0.10)
    now = time.time()
    next_t = pacer.calculate_next_execution_time(now)
    assert next_t >= now + 0.5

    # Participation cap: max 10% of 1000 volume = 100 qty
    capped_qty = pacer.cap_slice_quantity(desired_qty=250, market_volume_window=1000)
    assert capped_qty == 100


def test_t250_t253_algo_execution_engine_controls():
    """T-250 & T-253: Verify Algo Control Engine start/pause/resume/kill and hierarchy tree."""
    engine = AlgoExecutionEngine()
    parent = engine.start_algo(
        algo_type=AlgoType.TWAP,
        symbol="HDFCBANK.NS",
        side="BUY",
        total_quantity=500,
        arrival_price=1600.0,
        params={"n_slices": 5}
    )
    algo_id = parent.algo_id
    assert algo_id in engine.active_algos
    assert parent.status == AlgoStatus.ACTIVE

    # Test Hierarchy Tree
    tree = engine.get_hierarchy_tree(algo_id)
    assert tree["algo_id"] == algo_id
    assert len(tree["child_orders"]) == 5

    # Test Pause
    assert engine.pause_algo(algo_id) is True
    assert engine.active_algos[algo_id].status == AlgoStatus.PAUSED

    # Test Resume
    assert engine.resume_algo(algo_id) is True
    assert engine.active_algos[algo_id].status == AlgoStatus.ACTIVE

    # Test Fill Child Slice
    first_child_id = parent.child_orders[0].slice_id
    engine.fill_child_order(algo_id, first_child_id, fill_price=1602.0)
    assert parent.filled_quantity == 100
    assert parent.avg_fill_price == 1602.0
    assert parent.child_orders[0].status == ChildOrderStatus.FILLED

    # Test Kill
    assert engine.kill_algo(algo_id) is True
    assert algo_id not in engine.active_algos
    assert algo_id in engine.completed_algos
    assert engine.completed_algos[algo_id].status == AlgoStatus.KILLED
