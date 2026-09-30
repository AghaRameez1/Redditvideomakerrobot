"""Sessions, access control, request-origin checks, key encryption and login throttling."""
import threading
import time
from functools import wraps
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from flask import abort, current_app, g, jsonify, redirect, request, session

from . import db

# ---------- who is signed in ----------

def current_user():
    """The signed-in user row, or None. A bumped session_version ends old sessions."""
    if "user" not in g:
        g.user = None
        uid, version = session.get("uid"), session.get("ver")
        if uid:
            row = db.get().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
            if row and row["session_version"] == version:
                g.user = row
            else:
                session.clear()
    return g.user


def login_user(user):
    session.clear()  # new session id on sign-in, so an old cookie can't be reused
    session.permanent = True
    session["uid"], session["ver"] = user["id"], user["session_version"]
    g.pop("user", None)


def logout_user():
    session.clear()
    g.pop("user", None)


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify(error="Please sign in."), 401
        return view(*args, **kwargs)
    return wrapper


def page_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapper


# ---------- roles ----------
# user: makes videos. manager: also sees the admin dashboard and manages plain users.
# admin: everything, including roles and site settings.
ROLES = ("user", "manager", "admin")
RANK = {role: i for i, role in enumerate(ROLES)}


def has_role(user, role: str) -> bool:
    return bool(user) and RANK.get(user["role"], 0) >= RANK[role]


def api_role_required(role: str):
    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return jsonify(error="Please sign in."), 401
            if not has_role(user, role):
                return jsonify(error="You don't have access to that."), 403
            return view(*args, **kwargs)
        return wrapper
    return decorate


def page_role_required(role: str):
    """Signed-out visitors go to sign-in; people without the role get a plain 404."""
    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect("/login")
            if not has_role(user, role):
                abort(404)
            return view(*args, **kwargs)
        return wrapper
    return decorate


# ---------- cross-site request protection ----------

UPLOAD_PATHS = {"/api/footage"}
JSON_LIMIT = 1024 * 1024  # everything except uploads is small JSON


def check_same_origin():
    """Reject state-changing requests that come from another site (CSRF).

    Combined with SameSite=Lax cookies and JSON-only API bodies, this blocks forged requests.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source or urlparse(source).netloc != request.host:
        abort(403)
    if request.path in UPLOAD_PATHS:  # the one place that takes a file (multipart form)
        return
    if request.content_length and request.content_length > JSON_LIMIT:
        abort(413)
    if request.content_length is None and request.headers.get("Transfer-Encoding"):
        abort(411)  # no declared size: could bypass the 1 MB limit
    if request.path.startswith("/api/") and request.content_length and not request.is_json:
        abort(415)


# ---------- AI key encryption ----------

def _fernet():
    return Fernet(current_app.config["ENCRYPTION_KEY"].encode())


def encrypt(secret: str) -> bytes:
    return _fernet().encrypt(secret.encode())


def decrypt(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken:  # e.g. the encryption key was changed
        return ""


# ---------- login throttling ----------

_attempts, _lock = {}, threading.Lock()
MAX_FAILURES, WINDOW = 5, 15 * 60


def too_many_failures(email: str) -> bool:
    key = (request.remote_addr, email.lower())
    with _lock:
        recent = [t for t in _attempts.get(key, []) if time.time() - t < WINDOW]
        _attempts[key] = recent
        return len(recent) >= MAX_FAILURES


def record_failure(email: str):
    with _lock:
        _attempts.setdefault((request.remote_addr, email.lower()), []).append(time.time())


def clear_failures(email: str):
    with _lock:
        _attempts.pop((request.remote_addr, email.lower()), None)
