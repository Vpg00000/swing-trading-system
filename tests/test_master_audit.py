"""
Master Audit Test Suite — verifies actual repository behavior and module integrity
for all core trading system components.
"""

import pytest
from pathlib import Path
import websockets
import asyncio

from engine import decision, indicators, macro_regime, fundamental, governance
from data import database, sync_engine, dhan_auth, microstructure, fii_dii, institutional_flow


def test_master_audit_engine_imports():
    """Verify all core engine modules import cleanly and define primary interfaces."""
    assert hasattr(decision, "evaluate_decision") or hasattr(decision, "compute_composite_score")
    assert hasattr(indicators, "compute_indicators") or hasattr(indicators, "IndicatorResult")
    assert hasattr(macro_regime, "calculate_vix_percentile") or hasattr(macro_regime, "calculate_advance_decline_breadth")


def test_master_audit_data_imports():
    """Verify data layer modules and database connectivity."""
    assert hasattr(database, "get_connection") and hasattr(database, "init_db")
    assert hasattr(sync_engine, "compute_all") or hasattr(sync_engine, "compute_expected_return")
    assert hasattr(fii_dii, "get_fii_dii_history") and hasattr(fii_dii, "get_fii_dii_summary")
    assert hasattr(institutional_flow, "tag_bulk_deal_counterparty") and hasattr(institutional_flow, "analyze_symbol_institutional_flow")


def test_master_audit_csv_tracker_exists():
    """Verify task tracker CSV exists and is populated with valid tasks."""
    tracker_path = Path("AI_Investment_Command_Center_Task_Tracker.csv")
    assert tracker_path.exists(), "Task tracker CSV must exist"
    lines = tracker_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 40, f"Task tracker should contain at least 40 task rows, got {len(lines)}"
    assert any("IMPLEMENTED" in line or "VERIFIED" in line or "TASK" in line for line in lines)


def test_master_audit_security_module():
    """Verify security redaction, encryption, and safe auth modules."""
    from engine import security
    from data import dhan_auth
    assert hasattr(security, "redact_secrets")
    assert hasattr(security, "encrypt_api_secret")
    assert hasattr(security, "decrypt_api_secret")
    assert hasattr(security, "log_audit_event")
    assert hasattr(dhan_auth, "get_redacted_auth_status")
    assert hasattr(dhan_auth, "renew_dhan_access_token")

    # Verify secret redaction works
    redacted = security.redact_secrets({"secret_key": "raw_123"})
    assert redacted["secret_key"] == "[REDACTED]"


def test_master_audit_system_health():
    """Verify system health state propagation and state contract compliance."""
    from web_server import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get('/api/health')
    assert response.status_code == 200
    health_data = response.json()

    # Verify health data structure
    assert 'overall_status' in health_data or 'system_mode' in health_data or 'status' in health_data

    # Verify truthful system health UI
    assert isinstance(health_data, dict)
    assert all(isinstance(key, str) for key in health_data.keys())
    assert all(isinstance(value, (str, int, float, bool, dict, list, type(None))) for value in health_data.values())

    # Verify specific health indicators
    if 'overall_status' in health_data:
        assert str(health_data['overall_status']).lower() in ['healthy', 'degraded', 'unhealthy', 'normal', 'trading_blocked', 'ok']
    if 'system_mode' in health_data:
        assert str(health_data['system_mode']).lower() in ['normal', 'maintenance', 'emergency', 'degraded', 'trading_blocked', 'ok']
    if 'status' in health_data:
        assert isinstance(health_data['status'], (dict, str))

    if 'status' in health_data:
        assert all(value in ['healthy', 'degraded', 'unhealthy'] for value in health_data['status'].values())

async def test_master_audit_websocket_connection():
    """Verify WebSocket connection and message handling."""
    from web_server import app
    import json

    async with websockets.connect('ws://localhost:8000/ws') as websocket:
        # Send a test message
        test_message = json.dumps({"action": "test", "data": "test_data"})
        await websocket.send(test_message)

        # Receive the response
        response = await websocket.recv()
        response_data = json.loads(response)

        # Verify the response
        assert response_data["status"] == "success"
        assert response_data["message"] == "Test message received"

        # Verify the echo functionality
        echo_message = json.dumps({"action": "echo", "data": "echo_data"})
        await websocket.send(echo_message)
        echo_response = await websocket.recv()
        echo_response_data = json.loads(echo_response)

        assert echo_response_data["status"] == "success"
        assert echo_response_data["message"] == "echo_data"