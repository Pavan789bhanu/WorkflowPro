"""Tests for authentication endpoints and supporting utilities.

Coverage added this run:
- POST /api/auth/register (success, duplicate email, auto-derived username)
- GET  /api/auth/me (valid token, invalid token)
- Password hashing round-trip (direct bcrypt, not via passlib)
- Logger masking of sensitive data
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

os.environ.setdefault("SECRET_KEY", "test_secret_key_for_ci_must_be_32_chars_long")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-ci-only")
os.environ.setdefault("ENVIRONMENT", "test")

from app.main import app
from app.core.database import Base, get_db
from app.core.security import get_password_hash, verify_password


# ---------------------------------------------------------------------------
# Shared test DB fixtures (isolated from the main integration test DB)
# ---------------------------------------------------------------------------

_AUTH_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="workflowpro_auth_test_"), "test_auth.db")
_AUTH_DB_URL = f"sqlite:///{_AUTH_TEST_DB}"
_engine = create_engine(_AUTH_DB_URL, connect_args={"check_same_thread": False})
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db):
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Password hashing (bcrypt round-trip, no passlib)
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        pw = "super-secret-123"
        assert get_password_hash(pw) != pw

    def test_verify_correct_password(self):
        pw = "correct-horse-battery"
        assert verify_password(pw, get_password_hash(pw)) is True

    def test_verify_wrong_password(self):
        assert verify_password("wrong", get_password_hash("right")) is False

    def test_hashes_are_unique(self):
        pw = "same-password"
        assert get_password_hash(pw) != get_password_hash(pw)  # bcrypt uses random salts

    def test_long_password_truncated_safely(self):
        """Passwords longer than 72 bytes must still verify correctly."""
        long_pw = "x" * 100
        hashed = get_password_hash(long_pw)
        assert verify_password(long_pw, hashed) is True


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

class TestRegisterEndpoint:
    def test_register_new_user(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "alice@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "alice@example.com"
        assert "hashed_password" not in data  # never expose hash

    def test_register_derives_username_from_email(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "bob.smith@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "bobsmith"

    def test_register_explicit_username(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "carol@example.com", "username": "carolX", "password": "SecurePass1!"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "carolX"

    def test_register_duplicate_email_rejected(self, client):
        payload = {"email": "dup@example.com", "password": "SecurePass1!"}
        client.post("/api/auth/register", json=payload)
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_duplicate_username_rejected(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "user1@example.com", "username": "sharedname", "password": "Pass1!"},
        )
        resp = client.post(
            "/api/auth/register",
            json={"email": "user2@example.com", "username": "sharedname", "password": "Pass2!"},
        )
        assert resp.status_code == 400
        assert "taken" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

class TestMeEndpoint:
    def _register_and_login(self, client, email="me@example.com", password="Pass1!"):
        client.post("/api/auth/register", json={"email": email, "password": password})
        resp = client.post("/api/auth/login", data={"username": email, "password": password})
        return resp.json()["access_token"]

    def test_me_returns_current_user(self, client):
        token = self._register_and_login(client)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "me@example.com"

    def test_me_without_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-valid-token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logger — sensitive-data masking
# ---------------------------------------------------------------------------

class TestLoggerMasking:
    """Verify that the log() utility redacts sensitive data before emission."""

    def test_email_is_masked(self, caplog):
        import logging
        from app.automation.utils.logger import log, _mask_sensitive

        assert _mask_sensitive("user@example.com connected") == "[EMAIL] connected"

    def test_api_key_is_masked(self):
        from app.automation.utils.logger import _mask_sensitive

        raw = "Using sk-abcdefghijklmnopqrstu for inference"
        assert "[API_KEY]" in _mask_sensitive(raw)
        assert "sk-" not in _mask_sensitive(raw)

    def test_password_field_is_masked(self):
        from app.automation.utils.logger import _mask_sensitive

        raw = 'Credentials: {"password": "hunter2", "user": "bob"}'
        masked = _mask_sensitive(raw)
        assert "hunter2" not in masked
        assert "[PASSWORD]" in masked

    def test_non_sensitive_text_unchanged(self):
        from app.automation.utils.logger import _mask_sensitive

        msg = "Workflow 42 completed in 5 steps"
        assert _mask_sensitive(msg) == msg

    def test_log_function_accepts_level_kwarg(self):
        """log() should not raise regardless of level string."""
        from app.automation.utils.logger import log

        for level in ("debug", "info", "warning", "error", "critical"):
            log(f"Test message at {level}", level=level)
