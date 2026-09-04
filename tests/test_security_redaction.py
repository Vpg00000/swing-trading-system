"""
Security & Redaction Engine Test Suite (TASK-037).

Verifies:
1. Secret redaction on dictionaries, strings, nested structures, and exceptions.
2. Fernet symmetric encryption and decryption of secrets with derived 32-byte keys.
3. Credential masking for logging and UI.
4. Immutable SQLite Audit Logger automatic secret redaction.
5. Dhan API safe credential handling and redacted authentication status responses.
6. Error response sanitization.
7. Python logging filter secret redaction.
"""

import sqlite3
import logging
import pytest
from pathlib import Path

from engine.security import (
    redact_secrets,
    mask_credential,
    encrypt_api_secret,
    decrypt_api_secret,
    log_audit_event,
    sanitize_error_response,
    validate_cors_origin,
    SecretRedactionFilter,
    DB_PATH
)
from data.dhan_auth import (
    get_dhan_credentials,
    get_redacted_auth_status,
    renew_dhan_access_token
)


def test_redact_secrets_dict():
    """Verify dictionary secret keys are replaced with [REDACTED]."""
    raw_payload = {
        "user_id": 101,
        "api_key": "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",
        "secret_key": "my_super_secret_key_123",
        "nested": {
            "access_token": "dhan_token_valid_24h",
            "password": "SuperPassword123!",
            "public_metric": 95.5
        }
    }
    redacted = redact_secrets(raw_payload)
    assert redacted["user_id"] == 101
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["secret_key"] == "[REDACTED]"
    assert redacted["nested"]["access_token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["public_metric"] == 95.5


def test_redact_secrets_string_patterns():
    """Verify raw strings containing API keys or Bearer tokens are redacted."""
    openrouter_str = "Connecting with key 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 to model"
    redacted_or = redact_secrets(openrouter_str)
    assert "sk-or-v1" not in redacted_or
    assert "[REDACTED_OPENROUTER_KEY]" in redacted_or or "[REDACTED" in redacted_or

    bearer_str = "Authorization: Bearer my_secret_jwt_token_12345"
    redacted_bearer = redact_secrets(bearer_str)
    assert "my_secret_jwt_token_12345" not in redacted_bearer
    assert "[REDACTED" in redacted_bearer


def test_mask_credential():
    """Verify credential masking format."""
    assert mask_credential("10001234") == "1000****"
    assert mask_credential("sk-1234567890", show_prefix_len=3) == "sk-**********"
    assert mask_credential("") == ""
    assert mask_credential("123") == "***"


def test_fernet_encrypt_decrypt():
    """Verify Fernet encryption and decryption works with arbitrary master keys."""
    plain = "dhan_live_secret_998877"
    enc = encrypt_api_secret(plain, master_key="MY_TEST_MASTER_KEY")
    assert enc.startswith("ENC_")
    assert plain not in enc
    dec = decrypt_api_secret(enc, master_key="MY_TEST_MASTER_KEY")
    assert dec == plain


def test_audit_log_event_redaction():
    """Verify audit log event redacts secrets before writing to SQLite DB."""
    sensitive_details = {
        "action": "CONFIG_CHANGE",
        "secret_key": "SUPER_SECRET_VALUE",
        "atr_multiplier": 2.5
    }
    log_audit_event("TEST_REDACTION_ACTION", sensitive_details, user_ip="127.0.0.1")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT details FROM audit_logs WHERE action = 'TEST_REDACTION_ACTION' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        assert row is not None
        details_text = row[0]
        assert "SUPER_SECRET_VALUE" not in details_text
        assert "[REDACTED]" in details_text
        assert "2.5" in details_text


def test_dhan_auth_credentials_and_redaction():
    """Verify Dhan auth safe credential handling and redacted auth status."""
    auth_status = get_redacted_auth_status()
    assert "status" in auth_status
    assert "is_configured" in auth_status
    assert "client_id" in auth_status
    assert "secret_key" not in auth_status
    assert "access_token" not in auth_status

    renewal = renew_dhan_access_token(client_id="10009988", secret_key="demo_secret_key_123")
    assert renewal["status"] == "SUCCESS"
    assert renewal["client_id"] == "1000****"
    assert renewal["access_token"] == "dhan_token_valid_24h"
    assert renewal["access_token_redacted"] == "dhan" + "*" * 16



def test_sanitize_error_response():
    """Verify exception stack traces and secrets are sanitized in error responses."""
    err = ValueError("Failed connecting with secret_key=TOP_SECRET_123 at file /Users/dev/project/engine/main.py:45")
    sanitized = sanitize_error_response(err)
    assert sanitized["status"] == "ERROR"
    assert sanitized["error_code"] == "INTERNAL_SERVER_ERROR"
    assert "TOP_SECRET_123" not in sanitized["details"]
    assert "/Users/dev/project/engine/main.py" not in sanitized["details"]


def test_cors_validation():
    """Verify CORS origin validation."""
    assert validate_cors_origin("http://localhost:8000") is True
    assert validate_cors_origin("http://malicious-site.com") is False


def test_logging_filter_redaction():
    """Verify logging filter redacts secret messages."""
    logger = logging.getLogger("test_security_logger")
    handler = logging.StreamHandler()
    logger.addFilter(SecretRedactionFilter())
    record = logger.makeRecord(
        name="test", level=logging.INFO, fn="test.py", lno=10,
        msg="Logging API Key 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",
        args=(), exc_info=None
    )
    filter_result = SecretRedactionFilter().filter(record)
    assert filter_result is True
    assert "sk-or-v1" not in record.msg
