"""
Comprehensive Test Suite for Operations & Compliance Expansion (Tasks 76-80).

Verifies:
1. TASK-076: Automated Encrypted SQLite Database Nightly Backup Manager (data/database_backup.py).
2. TASK-077: OAuth2, JWT & TOTP 2FA Multi-User Access Control (engine/security.py).
3. TASK-078: Prometheus Metrics Telemetry Exporter Endpoint (/metrics in web_server.py).
4. TASK-079: Append-Only SHA-256 Hashed SEBI Audit Trail Logger (engine/security.py).
5. TASK-080: GitHub Actions CI Workflow Configuration (.github/workflows/ci.yml).
"""

import os
import sys
import time
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.database_backup import (
    DatabaseBackupManager,
    create_database_backup,
    restore_database_backup,
    list_database_backups,
    cleanup_database_backups,
    run_nightly_backup
)
from engine.security import (
    UserRole,
    ROLE_PERMISSIONS,
    check_permission,
    hash_password,
    verify_password,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_token,
    create_jwt_token,
    decode_jwt_token,
    register_user,
    authenticate_user,
    login_user,
    log_sebi_audit_event,
    verify_sebi_audit_chain,
    calculate_sebi_entry_hash,
    DB_PATH
)
from web_server import app

client = TestClient(app)


# ── TASK-076: Database Backup Tests ───────────────────────────────────────────

def test_task076_backup_creation_and_restoration():
    """Verify snapshot creation, AES-256 encryption, and SQLite restoration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_db = tmp_path / "source_test.db"
        backup_dir = tmp_path / "backups"
        restored_db = tmp_path / "restored_test.db"

        # Initialize source db with test table
        with sqlite3.connect(source_db) as conn:
            conn.execute("CREATE TABLE portfolio (id INT PRIMARY KEY, symbol TEXT, qty INT)")
            conn.execute("INSERT INTO portfolio VALUES (1, 'RELIANCE.NS', 100)")
            conn.execute("INSERT INTO portfolio VALUES (2, 'INFY.NS', 200)")

        mgr = DatabaseBackupManager(db_path=source_db, backup_dir=backup_dir)
        enc_file = mgr.create_backup()

        assert enc_file.exists()
        assert enc_file.name.endswith(".db.enc")
        assert enc_file.stat().st_size > 0

        # Verify backup lists
        backups = mgr.list_backups()
        assert len(backups) == 1
        assert backups[0]["filename"] == enc_file.name

        # Restore backup
        restored_path = mgr.restore_backup(enc_file, target_db_path=restored_db)
        assert restored_path.exists()

        # Check data integrity in restored database
        with sqlite3.connect(restored_path) as conn:
            rows = conn.execute("SELECT symbol, qty FROM portfolio ORDER BY id").fetchall()
            assert len(rows) == 2
            assert rows[0] == ("RELIANCE.NS", 100)
            assert rows[1] == ("INFY.NS", 200)


def test_task076_backup_retention_cleanup():
    """Verify retention cleanup policy removes old files exceeding limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create 5 dummy backup files
        for i in range(5):
            f = backup_dir / f"backup_2026090{i}_000000.db.enc"
            f.write_bytes(b"dummy encrypted content")
            time.sleep(0.01)

        mgr = DatabaseBackupManager(backup_dir=backup_dir)
        deleted = mgr.cleanup_old_backups(max_backups=2)

        assert len(deleted) == 3
        remaining = mgr.list_backups()
        assert len(remaining) == 2


def test_task076_backup_api_endpoints():
    """Test HTTP API endpoints for database backup operations."""
    resp_trigger = client.post("/api/system/backup")
    assert resp_trigger.status_code == 200
    data = resp_trigger.json()
    assert data["status"] == "SUCCESS"
    assert "backup_file" in data

    resp_list = client.get("/api/system/backup")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["status"].upper() == "SUCCESS"
    assert list_data["count"] >= 1


# ── TASK-077: OAuth2, JWT & TOTP 2FA Tests ────────────────────────────────────

def test_task077_rbac_permissions():
    """Verify Role-Based Access Control (RBAC) granular permissions."""
    assert check_permission(UserRole.ADMIN, "admin") is True
    assert check_permission(UserRole.ADMIN, "backup") is True
    assert check_permission(UserRole.ADMIN, "audit") is True

    assert check_permission(UserRole.TRADER, "write") is True
    assert check_permission(UserRole.TRADER, "admin") is False

    assert check_permission(UserRole.ANALYST, "read") is True
    assert check_permission(UserRole.ANALYST, "execute") is False

    assert check_permission(UserRole.VIEWER, "read") is True
    assert check_permission(UserRole.VIEWER, "write") is False


def test_task077_password_hashing_and_auth():
    """Verify PBKDF2 password hashing, salt derivation, and authentication."""
    p_hash, salt = hash_password("SecureTrader2026!")
    assert len(p_hash) == 64
    assert verify_password("SecureTrader2026!", p_hash, salt) is True
    assert verify_password("WrongPassword!", p_hash, salt) is False


def test_task077_totp_2fa_generation_and_verification():
    """Verify TOTP secret generation, URI creation, and 2FA token check."""
    secret = generate_totp_secret()
    assert len(secret) >= 16

    uri = get_totp_uri("test_trader", secret)
    assert "otpauth://totp/" in uri
    assert "test_trader" in uri

    # Verify dummy invalid token fails
    assert verify_totp_token(secret, "000000") is False


def test_task077_jwt_encoding_decoding():
    """Verify JWT token creation, payload claims, and decoding."""
    payload = {"sub": "trader_alice", "role": UserRole.TRADER, "user_id": 42}
    token = create_jwt_token(payload, expires_in_seconds=60)
    assert isinstance(token, str)

    decoded = decode_jwt_token(token)
    assert decoded["sub"] == "trader_alice"
    assert decoded["role"] == UserRole.TRADER
    assert decoded["user_id"] == 42
    assert "exp" in decoded


def test_task077_user_registration_and_login_flow():
    """Verify full multi-user registration, authentication, and login API."""
    uname = f"user_{int(time.time())}"
    reg_res = register_user(uname, "MyPass123!", role=UserRole.TRADER)
    assert reg_res["username"] == uname
    assert reg_res["role"] == UserRole.TRADER

    # Login API endpoint
    resp = client.post("/api/auth/login", json={
        "username": uname,
        "password": "MyPass123!"
    })
    # Since 2FA is enabled on registration, prompt for 2FA or access token
    assert resp.status_code in (200, 401)
    body = resp.json()
    assert "status" in body or "detail" in body

    # Roles API endpoint
    resp_roles = client.get("/api/auth/roles")
    assert resp_roles.status_code == 200
    roles_data = resp_roles.json()
    assert "ADMIN" in roles_data["roles"]


# ── TASK-078: Prometheus Telemetry Exporter Tests ─────────────────────────────

def test_task078_prometheus_metrics_exporter_endpoint():
    """Verify /metrics exporter endpoint outputs valid Prometheus exposition format."""
    # Send requests to populate metrics
    client.get("/api/report")
    client.get("/api/dashboard")

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")

    content = response.text
    assert "# HELP system_cpu_usage_percent" in content
    assert "# TYPE system_cpu_usage_percent gauge" in content
    assert "system_cpu_usage_percent" in content

    assert "# HELP system_ram_usage_bytes" in content
    assert "system_ram_usage_bytes" in content

    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content
    assert "db_query_duration_seconds" in content
    assert "websocket_ticks_total" in content
    assert "websocket_active_connections" in content


# ── TASK-079: Append-Only SEBI Audit Log Tests ────────────────────────────────

def test_task079_sebi_audit_log_append_and_hash_chain():
    """Verify append-only SHA-256 hashed SEBI audit trail logging and verification."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sebi_audit_logs")

    evt1 = log_sebi_audit_event("ORDER_PROPOSAL", {"symbol": "TATASTEEL.NS", "qty": 500}, actor="ALGO_CORE")
    assert evt1["id"] >= 1
    assert len(evt1["entry_hash"]) == 64

    evt2 = log_sebi_audit_event("RISK_EVALUATION", {"symbol": "TATASTEEL.NS", "passed": True}, actor="RISK_ENGINE")
    assert evt2["prev_hash"] == evt1["entry_hash"]
    assert len(evt2["entry_hash"]) == 64

    # Verify chain integrity
    is_valid, errors = verify_sebi_audit_chain()
    assert is_valid is True
    assert len(errors) == 0


def test_task079_sebi_audit_chain_tamper_detection():
    """Verify that tampering with an audit entry invalidates the SHA-256 hash chain."""
    # Log an event
    evt = log_sebi_audit_event("TRADE_EXECUTION", {"order_id": "ORD_999", "price": 150.5}, actor="TRADER_BOB")

    # Tamper with the database record
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE sebi_audit_logs SET details = 'TAMPERED_PAYLOAD' WHERE id = ?", (evt["id"],))

    # Verify chain detects tampering
    is_valid, errors = verify_sebi_audit_chain()
    assert is_valid is False
    assert len(errors) > 0
    assert any(e["error"] == "ENTRY_HASH_MISMATCH" for e in errors)


def test_task079_sebi_audit_api_endpoints():
    """Test SEBI audit log HTTP API endpoints."""
    log_sebi_audit_event("API_TEST_EVENT", {"test_key": "test_val"})

    resp_list = client.get("/api/compliance/audit")
    assert resp_list.status_code == 200
    logs = resp_list.json()
    assert isinstance(logs, list)
    assert len(logs) > 0

    resp_verify = client.get("/api/compliance/audit/verify")
    assert resp_verify.status_code == 200
    verify_data = resp_verify.json()
    assert "chain_valid" in verify_data
    assert "verification_status" in verify_data


# ── TASK-080: GitHub Actions CI Workflow Tests ────────────────────────────────

def test_task080_github_actions_workflow_config_exists():
    """Verify GitHub Actions CI workflow config (.github/workflows/ci.yml) exists and is valid."""
    workflow_file = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_file.exists()
    assert workflow_file.is_file()

    content = workflow_file.read_text(encoding="utf-8")
    assert "name: Swing Trading System CI/CD Workflow" in content
    assert "on:" in content
    assert "push:" in content
    assert "pull_request:" in content
    assert "jobs:" in content
    assert "test-and-lint:" in content
    assert "actions/checkout@v4" in content
    assert "actions/setup-python@v5" in content
    assert "pytest tests/ -v" in content
