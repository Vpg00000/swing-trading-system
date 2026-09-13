"""
Unit tests for Phase 5 Task B: JWT & TOTP 2FA Multi-User Access Control.

Verifies:
1. Password hashing & verification (`hash_password`, `verify_password`).
2. JWT token encoding, expiration, decoding, and tamper protection (`create_jwt_token`, `decode_jwt_token`).
3. TOTP 2FA generation and code verification (`generate_totp_secret`, `verify_totp_code`, `verify_2fa`).
4. AuthManager class multi-user access control methods.
5. FastAPI web server authentication endpoints (`POST /api/auth/login`, `POST /api/auth/verify-2fa`, `GET /api/auth/me`).
"""

import time
import pytest
from fastapi.testclient import TestClient

from engine.security import (
    AuthManager,
    hash_password,
    verify_password,
    create_jwt_token,
    decode_jwt_token,
    generate_totp_secret,
    verify_totp_code,
    verify_2fa,
    authenticate_user,
    register_user,
    get_user_by_username,
    UserRole,
    ROLE_PERMISSIONS
)
from web_server import app


@pytest.fixture
def test_client():
    return TestClient(app)


def test_password_hashing_and_verification():
    """Verify PBKDF2 password hashing and verification logic."""
    password = "TestPassword123!"
    
    # Module-level hash and verify with tuple unpacking
    p_hash, salt_hex = hash_password(password)
    assert len(p_hash) == 64
    assert len(salt_hex) == 32
    assert verify_password(password, p_hash, salt_hex) is True
    assert verify_password("WrongPassword!", p_hash, salt_hex) is False

    # Single-string salt:hash format verification
    formatted = f"{salt_hex}:{p_hash}"
    assert verify_password(password, formatted) is True
    assert verify_password("WrongPassword!", formatted) is False

    # AuthManager class methods
    am_hash = AuthManager.hash_password(password)
    assert ":" in am_hash
    assert AuthManager.verify_password(password, am_hash) is True
    assert AuthManager.verify_password("WrongPassword!", am_hash) is False


def test_jwt_token_lifecycle():
    """Verify JWT token encoding, decoding, and expiration validation."""
    payload = {
        "sub": "trader_user",
        "user_id": 42,
        "role": UserRole.TRADER,
        "permissions": list(ROLE_PERMISSIONS[UserRole.TRADER])
    }

    # Standard 60-minute token creation & decoding
    token = create_jwt_token(payload, expires_minutes=60)
    assert isinstance(token, str)
    assert len(token) > 20

    decoded = decode_jwt_token(token)
    assert decoded["sub"] == "trader_user"
    assert decoded["user_id"] == 42
    assert decoded["role"] == UserRole.TRADER

    # AuthManager JWT wrapper
    am_token = AuthManager.create_jwt_token(payload, expires_minutes=30)
    am_decoded = AuthManager.decode_jwt_token(am_token)
    assert am_decoded["sub"] == "trader_user"

    # Expired token test (expires_minutes=-1)
    expired_token = create_jwt_token(payload, expires_minutes=-1)
    with pytest.raises(ValueError, match="expired"):
        decode_jwt_token(expired_token)

    # Invalid token format test
    with pytest.raises(ValueError):
        decode_jwt_token("invalid.jwt.token.string")


def test_totp_2fa_generation_and_verification():
    """Verify TOTP secret generation and code verification."""
    secret = generate_totp_secret()
    assert isinstance(secret, str)
    assert len(secret) >= 16

    # Generate current TOTP code
    try:
        import pyotp
        totp = pyotp.TOTP(secret)
        current_code = totp.now()
    except ImportError:
        # Generate RFC6238 code
        import struct, hmac, hashlib, base64
        missing_padding = len(secret) % 8
        secret_padded = secret + "=" * (8 - missing_padding) if missing_padding else secret
        key = base64.b32decode(secret_padded, casefold=True)
        t = int(time.time()) // 30
        msg = struct.pack(">Q", t)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code_num = ((struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000)
        current_code = f"{code_num:06d}"

    assert verify_totp_code(secret, current_code) is True
    assert verify_totp_code(secret, "000000") is False
    assert AuthManager.verify_totp_code(secret, current_code) is True


def test_auth_manager_user_lifecycle():
    """Verify user registration, lookup, authentication, and 2FA verification."""
    uname = f"test_user_{int(time.time())}"
    pwd = "SecurePassword123!"

    reg = AuthManager.register_user(uname, pwd, role=UserRole.TRADER)
    assert reg["username"] == uname
    assert reg["role"] == UserRole.TRADER
    totp_secret = reg["totp_secret"]

    # Lookup user
    user_info = AuthManager.get_user_by_username(uname)
    assert user_info is not None
    assert user_info["username"] == uname

    # Authenticate user
    auth = AuthManager.authenticate_user(uname, pwd)
    assert auth is not None
    assert auth["username"] == uname
    assert auth["role"] == UserRole.TRADER

    auth_failed = AuthManager.authenticate_user(uname, "BadPassword!")
    assert auth_failed is None

    # Verify 2FA
    try:
        import pyotp
        totp_code = pyotp.TOTP(totp_secret).now()
    except ImportError:
        import struct, hmac, hashlib, base64
        missing_padding = len(totp_secret) % 8
        secret_padded = totp_secret + "=" * (8 - missing_padding) if missing_padding else totp_secret
        key = base64.b32decode(secret_padded, casefold=True)
        t = int(time.time()) // 30
        msg = struct.pack(">Q", t)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code_num = ((struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000)
        totp_code = f"{code_num:06d}"

    assert AuthManager.verify_2fa(uname, totp_code) is True
    assert AuthManager.verify_2fa(uname, "999999") is False


def test_web_server_auth_endpoints(test_client):
    """Verify Web Server POST /api/auth/login, POST /api/auth/verify-2fa, GET /api/auth/me endpoints."""
    uname = f"web_user_{int(time.time())}"
    pwd = "WebUserPass123!"

    reg = register_user(uname, pwd, role=UserRole.ADMIN)
    totp_secret = reg["totp_secret"]

    # 1. Login with correct password but missing 2FA code -> 2FA_REQUIRED
    res_login_req = test_client.post("/api/auth/login", json={"username": uname, "password": pwd})
    assert res_login_req.status_code == 200
    data_login_req = res_login_req.json()
    assert data_login_req["status"] == "2FA_REQUIRED"
    assert data_login_req["requires_2fa"] is True

    # 2. Login with invalid password -> 401
    res_bad_pwd = test_client.post("/api/auth/login", json={"username": uname, "password": "WrongPassword"})
    assert res_bad_pwd.status_code == 401

    # Generate valid TOTP code
    try:
        import pyotp
        valid_code = pyotp.TOTP(totp_secret).now()
    except ImportError:
        import struct, hmac, hashlib, base64
        missing_padding = len(totp_secret) % 8
        secret_padded = totp_secret + "=" * (8 - missing_padding) if missing_padding else totp_secret
        key = base64.b32decode(secret_padded, casefold=True)
        t = int(time.time()) // 30
        msg = struct.pack(">Q", t)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code_num = ((struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000)
        valid_code = f"{code_num:06d}"

    # 3. Login with password and valid 2FA code -> SUCCESS with Bearer token
    res_login_ok = test_client.post("/api/auth/login", json={
        "username": uname,
        "password": pwd,
        "code": valid_code
    })
    assert res_login_ok.status_code == 200
    data_login_ok = res_login_ok.json()
    assert data_login_ok["status"] == "SUCCESS"
    token = data_login_ok["access_token"]
    assert token is not None

    # 4. Verify 2FA endpoint
    res_verify_2fa = test_client.post("/api/auth/verify-2fa", json={
        "username": uname,
        "code": valid_code
    })
    assert res_verify_2fa.status_code == 200
    data_verify = res_verify_2fa.json()
    assert data_verify["status"] == "SUCCESS"
    assert "access_token" in data_verify

    # 5. GET /api/auth/me with Bearer token in header
    res_me = test_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    data_me = res_me.json()
    assert data_me["status"] == "SUCCESS"
    assert data_me["user"]["username"] == uname
    assert data_me["user"]["role"] == UserRole.ADMIN

    # 6. GET /api/auth/me without token -> 401
    res_me_no_token = test_client.get("/api/auth/me")
    assert res_me_no_token.status_code == 401

    # 7. GET /api/auth/me with invalid token -> 401
    res_me_bad_token = test_client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token_str"})
    assert res_me_bad_token.status_code == 401
