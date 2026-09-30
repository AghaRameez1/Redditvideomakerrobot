"""Accounts: email + password, Google sign-in, sign out, delete account."""
import re
import shutil

from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, site_settings
from .security import (api_login_required, clear_failures, current_user, has_role, login_user, logout_user,
                       record_failure, too_many_failures)
from .storage import user_dir

bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def _google():
    """Google sign-in client. Its ID and secret come from site_settings (admin page or env)."""
    return site_settings.google_client("google", "openid email profile")


def public_user(user):
    return {"email": user["email"], "name": user["name"] or "",
            "has_password": bool(user["password_hash"]), "google": bool(user["google_sub"]),
            "role": user["role"], "can_manage": has_role(user, "manager"), "plan": user["plan"]}


# ---------- email + password ----------

@bp.get("/api/auth/config")
def auth_config():
    return jsonify(google=site_settings.google_enabled())


@bp.get("/api/auth/me")
def me():
    user = current_user()
    return jsonify(user=public_user(user) if user else None)


@bp.post("/api/auth/register")
def register():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()[:80]
    if not EMAIL_PATTERN.match(email):
        return jsonify(error="Enter a valid email address."), 400
    if len(password) < MIN_PASSWORD:
        return jsonify(error=f"Use a password of at least {MIN_PASSWORD} characters."), 400
    conn = db.get()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify(error="An account with this email already exists. Sign in instead."), 409
    conn.execute("INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                 (email, name, generate_password_hash(password), db.now()))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    login_user(user)
    return jsonify(user=public_user(user))


@bp.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if too_many_failures(email):
        return jsonify(error="Too many failed attempts. Wait 15 minutes and try again."), 429
    user = db.get().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user and not user["password_hash"] and user["google_sub"]:
        return jsonify(error="This account uses Google sign-in. Use the Google button."), 400
    if not user or not check_password_hash(user["password_hash"], password):
        record_failure(email)
        return jsonify(error="Email or password is incorrect."), 401  # same message either way
    clear_failures(email)
    login_user(user)
    return jsonify(user=public_user(user))


@bp.post("/api/auth/logout")
def logout():
    logout_user()
    return jsonify(ok=True)


@bp.post("/api/auth/logout-everywhere")
@api_login_required
def logout_everywhere():
    conn = db.get()
    conn.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (current_user()["id"],))
    conn.commit()
    logout_user()
    return jsonify(ok=True)


@bp.post("/api/auth/delete-account")
@api_login_required
def delete_account():
    if is_last_admin(current_user()):
        return jsonify(error="You're the only admin. Make someone else an admin first, then delete your account."), 400
    remove_user(current_user()["id"])
    logout_user()
    return jsonify(ok=True)


def is_last_admin(user) -> bool:
    return user["role"] == "admin" and db.get().execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] <= 1


def remove_user(uid: int):
    """Delete an account and everything it owns: keys, connections, videos (ON DELETE CASCADE) and files."""
    conn = db.get()
    conn.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn.commit()
    shutil.rmtree(user_dir(uid), ignore_errors=True)


# ---------- Google ----------

@bp.get("/auth/google")
def google_start():
    if not site_settings.google_enabled():
        return redirect("/login?error=google_off")
    return _google().authorize_redirect(url_for("auth.google_callback", _external=True))


@bp.get("/auth/google/callback")
def google_callback():
    if not site_settings.google_enabled():
        return redirect("/login?error=google_off")
    try:
        info = _google().authorize_access_token().get("userinfo") or {}
    except Exception:  # user cancelled, state mismatch, network error
        current_app.logger.exception("Google sign-in failed")
        return redirect("/login?error=google_failed")
    sub, email = info.get("sub"), (info.get("email") or "").lower()
    if not sub or not email or not info.get("email_verified"):
        return redirect("/login?error=google_unverified")

    conn = db.get()
    user = conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
    if not user:
        existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            # Link Google to an email account. If that account's email was never verified,
            # someone else may have registered it: drop the password and sign out its sessions,
            # so only the verified Google owner keeps access.
            if not existing["email_verified"]:
                conn.execute("UPDATE users SET password_hash = NULL, session_version = session_version + 1 "
                             "WHERE id = ?", (existing["id"],))
            conn.execute("UPDATE users SET google_sub = ?, email_verified = 1, "
                         "name = COALESCE(NULLIF(name, ''), ?) WHERE id = ?",
                         (sub, info.get("name", ""), existing["id"]))
        else:
            conn.execute("INSERT INTO users (email, name, google_sub, email_verified, created_at) "
                         "VALUES (?, ?, ?, 1, ?)", (email, info.get("name", ""), sub, db.now()))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
    login_user(user)
    return redirect("/")
