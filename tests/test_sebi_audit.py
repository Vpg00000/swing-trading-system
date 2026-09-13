"""
Unit tests for Phase 5 Task A: SEBI Audit Trail Logger.
Verifies append-only SHA-256 hash chaining, tamper protection, and GET /api/audit-trail endpoint.
"""

import hashlib
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from engine.security import SEBIAuditLogger, log_sebi_audit, DB_PATH
from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_sebi_audit_log_creation_and_hash_chain(tmp_path):
    """Verifies entry logging, structure, SHA-256 hash calculation, and hash chaining."""
    db_file = tmp_path / "test_sebi_audit.db"
    logger = SEBIAuditLogger(db_path=db_file)

    # Log 1st entry via helper function
    entry1 = log_sebi_audit("ORDER_PLACED", "USER_101", {"symbol": "TATASTEEL.NS", "quantity": 100, "price": 150.0}, db_path=db_file)
    assert entry1["id"] == 1
    assert entry1["action"] == "ORDER_PLACED"
    assert entry1["user_id"] == "USER_101"
    assert entry1["previous_hash"] == "0" * 64

    # Verify entry1 SHA-256 hash calculation
    payload1 = f"{entry1['id']}{entry1['timestamp']}{entry1['action']}{entry1['user_id']}{entry1['details_json']}{entry1['previous_hash']}"
    expected_hash1 = hashlib.sha256(payload1.encode("utf-8")).hexdigest()
    assert entry1["current_hash"] == expected_hash1

    # Log 2nd entry via class method
    entry2 = logger.log("ORDER_EXECUTED", "USER_101", {"order_id": "ORD_001", "executed_qty": 100})
    assert entry2["id"] == 2
    assert entry2["previous_hash"] == entry1["current_hash"]

    payload2 = f"{entry2['id']}{entry2['timestamp']}{entry2['action']}{entry2['user_id']}{entry2['details_json']}{entry2['previous_hash']}"
    expected_hash2 = hashlib.sha256(payload2.encode("utf-8")).hexdigest()
    assert entry2["current_hash"] == expected_hash2

    # Log 3rd entry
    entry3 = logger.log("ORDER_CANCELLED", "USER_102", "User requested cancellation")
    assert entry3["id"] == 3
    assert entry3["previous_hash"] == entry2["current_hash"]

    # Verify integrity of untampered chain
    assert logger.verify_integrity() is True


def test_sebi_audit_tamper_protection(tmp_path):
    """Verifies that tampering with database records breaks integrity check."""
    db_file = tmp_path / "test_tamper_audit.db"
    logger = SEBIAuditLogger(db_path=db_file)

    logger.log("ACTION_1", "USER_A", {"data": 100})
    logger.log("ACTION_2", "USER_B", {"data": 200})
    logger.log("ACTION_3", "USER_C", {"data": 300})

    assert logger.verify_integrity() is True

    # Tamper with details_json of entry 2 in SQLite table
    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE sebi_audit_trail SET details_json = '{\"data\": 9999}' WHERE id = 2")

    # Verification must return False after tampering
    assert logger.verify_integrity() is False


def test_sebi_audit_api_endpoint(tmp_path, monkeypatch, client):
    """Tests GET /api/audit-trail endpoint."""
    test_db = tmp_path / "api_audit.db"
    monkeypatch.setattr("engine.security.DB_PATH", test_db)

    # Log entry using monkeypatched DB_PATH
    log_sebi_audit("SYSTEM_EVENT", "SYS_ADMIN", {"status": "HEALTHY"})

    response = client.get("/api/audit-trail")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert data["integrity_valid"] is True
    assert data["verification_status"] == "VERIFIED"
    assert len(data["audit_logs"]) >= 1
    assert data["audit_logs"][0]["action"] == "SYSTEM_EVENT"
    assert data["audit_logs"][0]["user_id"] == "SYS_ADMIN"
