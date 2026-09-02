"""Session-based authentication and bot protection for Furiganalyse."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Optional
from fastapi import Request

SESSION_COOKIE_NAME = "furiganalyse_session"
SESSION_MAX_AGE = 30 * 86400  # 30 days in seconds

# File path to persist secret key across restarts if not set in environment
SECRET_KEY_PATH = Path("/tmp/furiganalysed/.secret_key")


def _get_secret_key() -> bytes:
    """Retrieve or generate a persistent secret key for signing session tokens."""
    env_key = os.environ.get("FURIGANALYSE_SECRET_KEY")
    if env_key:
        return env_key.encode("utf-8")

    try:
        if SECRET_KEY_PATH.is_file():
            key_data = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
            if key_data:
                return key_data.encode("utf-8")
    except Exception:
        pass

    # Generate new random key and attempt to persist
    new_key = secrets.token_hex(32)
    try:
        SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SECRET_KEY_PATH.write_text(new_key, encoding="utf-8")
    except Exception:
        pass
    return new_key.encode("utf-8")


def is_auth_enabled() -> bool:
    """Check if site authentication is enabled."""
    val = os.environ.get("FURIGANALYSE_AUTH_ENABLED", "true").strip().lower()
    return val not in {"false", "0", "no", "off"}


def get_configured_credentials() -> tuple[str, str]:
    """Return the configured username and password."""
    username = os.environ.get("FURIGANALYSE_USERNAME", "admin").strip()
    password = os.environ.get("FURIGANALYSE_PASSWORD", "furigana2026").strip()
    return username, password


def authenticate(username: str, password: str) -> bool:
    """Validate submitted credentials against configured environment values."""
    if not is_auth_enabled():
        return True

    expected_user, expected_pass = get_configured_credentials()
    # Constant-time comparison to protect against timing attacks
    user_match = hmac.compare_digest(username.strip(), expected_user)
    pass_match = hmac.compare_digest(password.strip(), expected_pass)
    return user_match and pass_match


def create_session_token(username: str) -> str:
    """Generate a signed, timestamped session token."""
    secret = _get_secret_key()
    timestamp = str(int(time.time()))
    payload = f"{username}:{timestamp}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw_token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")


def verify_session_token(token: Optional[str]) -> Optional[str]:
    """Validate a session token and return the authenticated username if valid."""
    if not token or not isinstance(token, str):
        return None

    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = raw.split(":")
        if len(parts) != 3:
            return None
        username, timestamp_str, signature = parts
        timestamp = int(timestamp_str)
    except Exception:
        return None

    # Check expiration (30 days)
    if time.time() - timestamp > SESSION_MAX_AGE or timestamp > time.time() + 300:
        return None

    # Verify cryptographic signature
    secret = _get_secret_key()
    payload = f"{username}:{timestamp_str}"
    expected_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return None

    return username


def get_current_user(request: Request) -> Optional[str]:
    """Retrieve the currently authenticated username from the request session cookie."""
    if not is_auth_enabled():
        return "anonymous"

    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    return verify_session_token(cookie_val)
