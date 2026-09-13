"""
Unit tests for Phase 5 Task C: Automated SQLite Nightly Backup Engine.

Verifies:
1. Backup creation (compress=True, encrypt=False/True).
2. Backup listing with detailed metadata.
3. Backup restoration with integrity check.
4. Retention rotation (max_keep policy).
5. Helper trigger_nightly_backup().
6. Admin API endpoints POST /api/admin/backup & GET /api/admin/backups.
"""

import gzip
import sqlite3
import tempfile
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from data.database_backup import (
    DatabaseBackupManager,
    trigger_nightly_backup,
)
from web_server import app

client = TestClient(app)


def test_backup_creation():
    """Verify backup creation with compression and encryption options."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_db = tmp_path / "test_source.db"
        backup_dir = tmp_path / "backups"

        # Create source DB with test table and data
        with sqlite3.connect(source_db) as conn:
            conn.execute("CREATE TABLE orders (id INT PRIMARY KEY, symbol TEXT, price REAL)")
            conn.execute("INSERT INTO orders VALUES (1, 'TATASTEEL.NS', 150.5)")

        mgr = DatabaseBackupManager(db_path=source_db, backup_dir=backup_dir)

        # 1. Default compressed backup (compress=True, encrypt=False)
        compressed_backup = mgr.create_backup(compress=True, encrypt=False)
        assert compressed_backup.exists()
        assert compressed_backup.name.endswith(".db.gz")
        assert compressed_backup.stat().st_size > 0

        # Verify compressed data format
        raw_bytes = compressed_backup.read_bytes()
        assert raw_bytes.startswith(b"\x1f\x8b")  # gzip magic number
        decompressed_data = gzip.decompress(raw_bytes)
        assert b"TATASTEEL.NS" in decompressed_data

        # 2. Encrypted backup (compress=False, encrypt=True)
        encrypted_backup = mgr.create_backup(compress=False, encrypt=True)
        assert encrypted_backup.exists()
        assert encrypted_backup.name.endswith(".db.enc")
        assert encrypted_backup.stat().st_size > 0

        # 3. Compressed & Encrypted backup (compress=True, encrypt=True)
        comp_enc_backup = mgr.create_backup(compress=True, encrypt=True)
        assert comp_enc_backup.exists()
        assert comp_enc_backup.name.endswith(".db.gz.enc")


def test_list_backups():
    """Verify listing backup files returns complete metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_db = tmp_path / "test_source.db"
        backup_dir = tmp_path / "backups"

        with sqlite3.connect(source_db) as conn:
            conn.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO users VALUES (1, 'Trader1')")

        mgr = DatabaseBackupManager(db_path=source_db, backup_dir=backup_dir)
        b1 = mgr.create_backup(compress=True, encrypt=False)
        time.sleep(0.01)
        b2 = mgr.create_backup(compress=True, encrypt=True)

        backups = mgr.list_backups()
        assert len(backups) == 2

        filenames = [b["filename"] for b in backups]
        assert b1.name in filenames
        assert b2.name in filenames

        for b in backups:
            assert "filepath" in b
            assert "size_bytes" in b
            assert "modified_at" in b
            assert "is_compressed" in b
            assert "is_encrypted" in b


def test_restore_backup():
    """Verify backup restoration restores SQLite data integrity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_db = tmp_path / "source.db"
        backup_dir = tmp_path / "backups"
        restored_db = tmp_path / "restored.db"

        with sqlite3.connect(source_db) as conn:
            conn.execute("CREATE TABLE trades (id INT PRIMARY KEY, symbol TEXT, qty INT)")
            conn.execute("INSERT INTO trades VALUES (101, 'INFY.NS', 50)")
            conn.execute("INSERT INTO trades VALUES (102, 'TCS.NS', 30)")

        mgr = DatabaseBackupManager(db_path=source_db, backup_dir=backup_dir)

        # Test restoring from compressed backup
        comp_backup = mgr.create_backup(compress=True, encrypt=False)
        res_path = mgr.restore_backup(comp_backup.name, target_db_path=restored_db)
        assert res_path.exists()

        with sqlite3.connect(res_path) as conn:
            rows = conn.execute("SELECT symbol, qty FROM trades ORDER BY id").fetchall()
            assert len(rows) == 2
            assert rows[0] == ("INFY.NS", 50)
            assert rows[1] == ("TCS.NS", 30)

        # Test restoring from encrypted & compressed backup
        restored_db2 = tmp_path / "restored2.db"
        enc_backup = mgr.create_backup(compress=True, encrypt=True)
        res_path2 = mgr.restore_backup(enc_backup.name, target_db_path=restored_db2)
        assert res_path2.exists()

        with sqlite3.connect(res_path2) as conn:
            rows = conn.execute("SELECT symbol, qty FROM trades ORDER BY id").fetchall()
            assert len(rows) == 2
            assert rows[0] == ("INFY.NS", 50)


def test_rotate_backups():
    """Verify backup rotation limits total stored backup files to max_keep."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create 35 dummy backup files
        for i in range(35):
            f = backup_dir / f"backup_20260901_{i:06d}.db.gz"
            f.write_bytes(b"dummy backup data")
            time.sleep(0.001)

        mgr = DatabaseBackupManager(backup_dir=backup_dir)
        deleted = mgr.rotate_backups(max_keep=30)

        assert len(deleted) == 5
        remaining = mgr.list_backups()
        assert len(remaining) == 30


def test_trigger_nightly_backup():
    """Verify trigger_nightly_backup helper function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_db = tmp_path / "system.db"
        backup_dir = tmp_path / "backups"

        with sqlite3.connect(source_db) as conn:
            conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO config VALUES ('version', '1.0.0')")

        res = trigger_nightly_backup(
            db_path=source_db,
            backup_dir=backup_dir,
            max_keep=5,
            compress=True,
            encrypt=False
        )

        assert res["status"] == "SUCCESS"
        assert "backup_file" in res
        assert res["backup_file"].endswith(".db.gz")
        assert res["file_size_bytes"] > 0
        assert "timestamp" in res


def test_admin_backup_api_endpoints():
    """Verify POST /api/admin/backup and GET /api/admin/backups FastAPI endpoints."""
    # Test POST /api/admin/backup
    res_post = client.post("/api/admin/backup", json={"compress": True, "encrypt": False, "max_keep": 30})
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["status"] == "SUCCESS"
    assert "backup_file" in post_data
    assert "file_size_bytes" in post_data

    # Test GET /api/admin/backups
    res_get = client.get("/api/admin/backups")
    assert res_get.status_code == 200
    get_data = res_get.json()
    assert get_data["status"] == "success"
    assert "backups" in get_data
    assert get_data["count"] >= 1
