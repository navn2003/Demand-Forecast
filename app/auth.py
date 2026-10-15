"""Login for the dashboard: one fixed user, signed session cookie.

No extra packages: the cookie is "<username>|<expiry>|<signature>", signed with
HMAC-SHA256 using SESSION_SECRET, so it cannot be forged or edited in the browser.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from .config import AUTH

COOKIE_NAME = "df_session"

# Paths reachable without logging in
PUBLIC_PATHS = {"/login", "/favicon.ico"}
PUBLIC_PREFIXES = ("/static/",)


def _sign(payload: str) -> str:
    return hmac.new(AUTH.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def check_credentials(username: str, password: str) -> bool:
    # compare_digest takes the same time whether or not the text matches (no timing hints)
    user_ok = hmac.compare_digest(username.encode(), AUTH.username.encode())
    pass_ok = hmac.compare_digest(password.encode(), AUTH.password.encode())
    return user_ok and pass_ok


def make_session(username: str) -> str:
    expires = int(time.time()) + AUTH.session_hours * 3600
    payload = f"{username}|{expires}"
    return f"{payload}|{_sign(payload)}"


def read_session(token: str | None) -> str | None:
    """Return the username if the cookie is genuine and not expired, else None."""
    if not token or token.count("|") != 2:
        return None
    username, expires, sig = token.split("|")
    if not hmac.compare_digest(sig, _sign(f"{username}|{expires}")):
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    return username


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def safe_next(target: str | None) -> str:
    """Only allow redirects back into this site (blocks //evil.com and https://...)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/"
