"""Unit tests for Furiganalyse session authentication and route protection."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from furiganalyse import auth
from furiganalyse.app import app


@pytest.fixture(autouse=True)
def configure_test_auth(monkeypatch):
    """Ensure consistent authentication settings during test execution."""
    monkeypatch.setenv("FURIGANALYSE_AUTH_ENABLED", "true")
    monkeypatch.setenv("FURIGANALYSE_USERNAME", "testadmin")
    monkeypatch.setenv("FURIGANALYSE_PASSWORD", "testpass123")
    monkeypatch.setenv("FURIGANALYSE_SECRET_KEY", "test-secret-key-1234567890")


def test_auth_token_generation_and_verification():
    token = auth.create_session_token("testadmin")
    assert token is not None
    assert isinstance(token, str)

    username = auth.verify_session_token(token)
    assert username == "testadmin"


def test_auth_token_tamper_rejection():
    token = auth.create_session_token("testadmin")
    # Tamper with token
    tampered = token[:-4] + "abcd"
    assert auth.verify_session_token(tampered) is None
    assert auth.verify_session_token("invalid:token") is None
    assert auth.verify_session_token("") is None


def test_authenticate_credentials():
    assert auth.authenticate("testadmin", "testpass123") is True
    assert auth.authenticate("testadmin", "wrongpass") is False
    assert auth.authenticate("wronguser", "testpass123") is False
    assert auth.authenticate("", "") is False


def test_unauthenticated_request_redirects_to_login():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/")
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


def test_unauthenticated_api_request_returns_401():
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/api/recent_conversions")
    assert resp.status_code == 401
    assert "error" in resp.json()


def test_public_assets_accessible_without_auth():
    client = TestClient(app, follow_redirects=False)
    # Login page is public
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Sign in" in resp.text


def test_login_flow_and_authenticated_access():
    client = TestClient(app, follow_redirects=False)

    # Attempt login with valid credentials
    login_resp = client.post(
        "/login",
        data={"username": "testadmin", "password": "testpass123", "remember_me": "true"},
    )
    assert login_resp.status_code == 303
    assert auth.SESSION_COOKIE_NAME in login_resp.cookies

    # Access protected root with session cookie
    root_resp = client.get("/", cookies=login_resp.cookies)
    assert root_resp.status_code == 200
    assert "Furiganalyse" in root_resp.text
    assert "Sign Out" in root_resp.text


def test_login_failure():
    client = TestClient(app, follow_redirects=False)
    login_resp = client.post(
        "/login",
        data={"username": "testadmin", "password": "wrong_password"},
    )
    assert login_resp.status_code == 401
    assert "Invalid username or password" in login_resp.text
    assert auth.SESSION_COOKIE_NAME not in login_resp.cookies


def test_logout_clears_session():
    client = TestClient(app, follow_redirects=False)
    token = auth.create_session_token("testadmin")
    cookies = {auth.SESSION_COOKIE_NAME: token}

    # Verify authenticated
    resp = client.get("/", cookies=cookies)
    assert resp.status_code == 200

    # Logout
    logout_resp = client.get("/logout", cookies=cookies)
    assert logout_resp.status_code == 303
    assert "/login" in logout_resp.headers["location"]
