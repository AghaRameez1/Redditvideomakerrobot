"""Admin page API: statistics, user management and roles, and the Google OAuth client.

Managers see the statistics and manage plain users. Only admins change roles above "user",
manage other managers or admins, and change the Google settings.
"""
import json
import re
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, abort, current_app, jsonify, request, url_for
from werkzeug.security import generate_password_hash

from . import cleanup, db, plans, site_settings
from .auth import EMAIL_PATTERN, MIN_PASSWORD, is_last_admin, remove_user
from .security import ROLES, api_role_required, current_user, has_role
from .storage import disk_usage

bp = Blueprint("admin", __name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _check_google(client_id: str, secret: str):
    """Ask Google whether this client ID + secret pair exists, without signing anyone in.

    Exchanging a made-up code fails either way, but a wrong ID or secret fails with
    invalid_client, while a real pair fails with invalid_grant. Returns an error message or None.
    """
    try:
        resp = requests.post(GOOGLE_TOKEN_URL, timeout=15, data={
            "code": "credential-check", "grant_type": "authorization_code",
            "client_id": client_id, "client_secret": secret,
            "redirect_uri": url_for("auth.google_callback", _external=True)})
    except requests.RequestException:
        return "Couldn't reach Google to check these. Try again in a moment."
    try:
        error = resp.json().get("error")
    except ValueError:
        error = None
    if error == "invalid_client":
        return "Google doesn't recognise this client ID and secret pair. Copy both again from Google Cloud."
    if error not in ("invalid_grant", "redirect_uri_mismatch"):
        current_app.logger.warning("Unexpected Google check reply %s: %s", resp.status_code, resp.text[:300])
    return None


# Per service. "platform": the connections that stop working with a new app,
# because each user's access is tied to the app that granted it.
SERVICES = {
    "google": {"name": "Google", "id_name": "client ID", "platform": "youtube", "check": _check_google,
               "id_format": re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$"),
               "id_example": "1234567890-abc123.apps.googleusercontent.com",
               "callbacks": ("auth.google_callback", "connections.youtube_callback")},
}


def _service(provider):
    if provider not in SERVICES:
        abort(404)
    return SERVICES[provider]


def _mask(value: str) -> str:
    return f"····{value[-4:]}" if value else ""


def _status(provider):
    svc, creds = SERVICES[provider], site_settings.credentials(provider)
    conn = db.get()
    row = conn.execute(
        "SELECT s.updated_at, u.email FROM site_settings s LEFT JOIN users u ON u.id = s.updated_by "
        "WHERE s.key = ?", (site_settings.PROVIDERS[provider][1][0],)).fetchone()
    saved = row if row and creds["source"] == "admin" else None
    return {
        "source": creds["source"],
        "client_id": creds["client_id"],
        "secret_hint": _mask(creds["client_secret"]),
        "updated_at": saved["updated_at"] if saved else None,
        "updated_by": saved["email"] if saved else None,
        "redirect_uris": [url_for(c, _external=True) for c in svc["callbacks"]],
        "connections": conn.execute("SELECT COUNT(*) FROM connections WHERE platform = ?",
                                    (svc["platform"],)).fetchone()[0],
        # Only Google is a way to sign in; accounts with no password would be locked out without it.
        "google_only_users": conn.execute("SELECT COUNT(*) FROM users WHERE password_hash IS NULL").fetchone()[0]
        if provider == "google" else 0,
    }


def _forget_connections(platform) -> int:
    conn = db.get()
    removed = conn.execute("DELETE FROM connections WHERE platform = ?", (platform,)).rowcount
    conn.commit()
    return removed


@bp.get("/api/admin/<provider>")
@api_role_required("admin")
def get_settings(provider):
    _service(provider)
    return jsonify(_status(provider))


@bp.put("/api/admin/<provider>")
@api_role_required("admin")
def save_settings(provider):
    svc = _service(provider)
    if site_settings.credentials(provider)["source"] == "env":
        return jsonify(error="These are set by environment variables on the server. Change them there."), 409
    data = request.get_json(force=True) or {}
    client_id = (data.get("client_id") or "").strip()
    secret = (data.get("client_secret") or "").strip()
    if not svc["id_format"].match(client_id):
        return jsonify(error=f"That isn't a {svc['name']} {svc['id_name']}. It looks like {svc['id_example']}."), 400
    if not secret:
        return jsonify(error="Paste the secret too."), 400
    error = svc["check"](client_id, secret)
    if error:
        return jsonify(error=error), 400

    removed = 0
    previous = site_settings.credentials(provider)["client_id"]
    if previous and previous != client_id:
        removed = _forget_connections(svc["platform"])
    site_settings.save(provider, client_id, secret, current_user()["id"])
    return jsonify({**_status(provider), "removed_connections": removed})


@bp.delete("/api/admin/<provider>")
@api_role_required("admin")
def clear_settings(provider):
    svc = _service(provider)
    if site_settings.credentials(provider)["source"] == "env":
        return jsonify(error="These are set by environment variables on the server. Remove them there."), 409
    removed = _forget_connections(svc["platform"])
    site_settings.save(provider, "", "", current_user()["id"])
    return jsonify({**_status(provider), "removed_connections": removed})


# ---------- statistics ----------

CHART_DAYS = 30
_RECENT = "julianday({}) >= julianday('now', '-{} days')"


def _per_day(conn, table):
    """{"2026-09-30": count, ...} for the last CHART_DAYS days (UTC), including empty days."""
    rows = dict(conn.execute(f"SELECT date(created_at), COUNT(*) FROM {table} "
                             f"WHERE {_RECENT.format('created_at', CHART_DAYS)} GROUP BY 1").fetchall())
    today = datetime.now(timezone.utc).date()  # SQLite's date() is UTC too
    return [{"day": d, "count": rows.get(d, 0)}
            for d in ((today - timedelta(days=n)).isoformat() for n in range(CHART_DAYS - 1, -1, -1))]


@bp.get("/api/admin/stats")
@api_role_required("manager")
def stats():
    conn = db.get()
    one = lambda sql: conn.execute(sql).fetchone()[0]
    users = conn.execute(f"""
        SELECT u.id, u.email, u.name, u.created_at, u.role, u.plan,
               u.password_hash IS NOT NULL AS has_password, u.google_sub IS NOT NULL AS google,
               (SELECT COUNT(*) FROM videos v WHERE v.user_id = u.id) AS videos,
               (SELECT COALESCE(SUM(duration), 0) FROM videos v WHERE v.user_id = u.id) AS seconds,
               (SELECT MAX(created_at) FROM videos v WHERE v.user_id = u.id) AS last_video,
               (SELECT COUNT(*) FROM shares s JOIN videos v ON v.id = s.video_id
                 WHERE v.user_id = u.id AND s.status = 'done') AS posts,
               (SELECT group_concat(provider) FROM api_keys k WHERE k.user_id = u.id) AS ai_keys,
               EXISTS (SELECT 1 FROM connections c WHERE c.user_id = u.id AND c.platform = 'youtube') AS youtube
        FROM users u ORDER BY u.id DESC""").fetchall()
    people = []
    for u in users:
        person = dict(u)
        person["ai_keys"] = sorted((u["ai_keys"] or "").split(",")) if u["ai_keys"] else []
        person["disk_bytes"] = disk_usage(u["id"])
        people.append(person)
    return jsonify({
        "totals": {
            "users": len(people),
            "new_7d": one(f"SELECT COUNT(*) FROM users WHERE {_RECENT.format('created_at', 7)}"),
            "new_30d": one(f"SELECT COUNT(*) FROM users WHERE {_RECENT.format('created_at', 30)}"),
            "google_users": sum(p["google"] for p in people),
            "password_users": sum(p["has_password"] for p in people),
            "with_ai_key": sum(bool(p["ai_keys"]) for p in people),
            "active_7d": one(f"SELECT COUNT(DISTINCT user_id) FROM videos WHERE {_RECENT.format('created_at', 7)}"),
            "videos": one("SELECT COUNT(*) FROM videos"),
            "videos_7d": one(f"SELECT COUNT(*) FROM videos WHERE {_RECENT.format('created_at', 7)}"),
            "seconds": one("SELECT COALESCE(SUM(duration), 0) FROM videos"),
            "youtube_connections": one("SELECT COUNT(*) FROM connections WHERE platform = 'youtube'"),
            "posts_done": one("SELECT COUNT(*) FROM shares WHERE status = 'done'"),
            "posts_failed": one("SELECT COUNT(*) FROM shares WHERE status = 'error'"),
            "disk_bytes": sum(p["disk_bytes"] for p in people),
            "plans": {k: sum(p["plan"] == k for p in people) for k in plans.ORDER},
            "pending_requests": one("SELECT COUNT(*) FROM plan_requests WHERE status = 'pending'"),
        },
        "signups_by_day": _per_day(conn, "users"),
        "videos_by_day": _per_day(conn, "videos"),
        "users": people,
    })


# ---------- users and roles ----------

def _assignable(actor) -> tuple:
    """Roles this person may hand out."""
    return ROLES if has_role(actor, "admin") else ("user",)


def _target(user_id):
    """The user to change, if the signed-in person may manage them; else a JSON error response."""
    actor = current_user()
    target = db.get().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target:
        return None, (jsonify(error="That user no longer exists."), 404)
    if not has_role(actor, "admin") and target["role"] != "user":
        return None, (jsonify(error="Only an admin can change managers and admins."), 403)
    return target, None


def _clean(data, creating: bool):
    """Validated fields from the request: ({column: value}, error message or None)."""
    fields = {}
    if creating or "email" in data:
        email = (data.get("email") or "").strip().lower()
        if not EMAIL_PATTERN.match(email):
            return fields, "Enter a valid email address."
        fields["email"] = email
    if creating or "name" in data:
        fields["name"] = (data.get("name") or "").strip()[:80]
    password = data.get("password") or ""
    if password:
        if len(password) < MIN_PASSWORD:
            return fields, f"Use a password of at least {MIN_PASSWORD} characters."
        fields["password_hash"] = generate_password_hash(password)
    elif creating and not site_settings.google_enabled():
        return fields, "Set a password. Without one they could only sign in with Google, which isn't set up."
    if creating or "plan" in data:
        plan = data.get("plan") or "free"
        if plan not in plans.ORDER:
            return fields, "Unknown plan."
        fields["plan"] = plan
    if creating or "role" in data:
        role = data.get("role") or "user"
        if role not in _assignable(current_user()):
            return fields, "You can't give that role."
        fields["role"] = role
    return fields, None


def _email_taken(email, except_id=None) -> bool:
    return bool(db.get().execute("SELECT 1 FROM users WHERE email = ? AND id IS NOT ?", (email, except_id)).fetchone())


@bp.post("/api/admin/users")
@api_role_required("manager")
def create_user():
    fields, error = _clean(request.get_json(force=True) or {}, creating=True)
    if error:
        return jsonify(error=error), 400
    if _email_taken(fields["email"]):
        return jsonify(error="An account with this email already exists."), 409
    conn = db.get()
    uid = conn.execute("INSERT INTO users (email, name, password_hash, role, plan, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (fields["email"], fields["name"], fields.get("password_hash"), fields["role"], fields["plan"],
                        db.now())).lastrowid
    conn.commit()
    return jsonify(id=uid), 201


@bp.patch("/api/admin/users/<int:user_id>")
@api_role_required("manager")
def edit_user(user_id):
    target, error_response = _target(user_id)
    if error_response:
        return error_response
    fields, error = _clean(request.get_json(force=True) or {}, creating=False)
    if error:
        return jsonify(error=error), 400
    if "role" in fields and fields["role"] != target["role"]:
        if target["id"] == current_user()["id"]:
            return jsonify(error="You can't change your own role. Ask another admin."), 400
        if is_last_admin(target):
            return jsonify(error="This is the only admin. Make someone else an admin first."), 400
    if "email" in fields:
        if fields["email"] == target["email"]:
            del fields["email"]
        elif _email_taken(fields["email"], user_id):
            return jsonify(error="Another account already uses this email."), 409
        else:
            fields["email_verified"] = 0  # the new address hasn't been proven by Google yet
    if not fields:
        return jsonify(ok=True)
    sets = ", ".join(f"{k} = ?" for k in fields)
    if "password_hash" in fields:
        sets += ", session_version = session_version + 1"  # a new password signs them out everywhere
    conn = db.get()
    conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*fields.values(), user_id))
    conn.commit()
    return jsonify(ok=True)


@bp.delete("/api/admin/users/<int:user_id>")
@api_role_required("manager")
def delete_user(user_id):
    target, error_response = _target(user_id)
    if error_response:
        return error_response
    if target["id"] == current_user()["id"]:
        return jsonify(error="To delete your own account, use Settings."), 400
    if is_last_admin(target):
        return jsonify(error="This is the only admin. Make someone else an admin first."), 400
    remove_user(user_id)
    return jsonify(ok=True)


# ---------- auto-clean ----------

def _cleanup_status():
    hours = cleanup.delay_hours()
    return {"hours": "" if hours is None else str(hours), "options": cleanup.DELAYS,
            "last_run": cleanup.last_run(current_app._get_current_object())}


@bp.get("/api/admin/cleanup")
@api_role_required("admin")
def get_cleanup():
    return jsonify(_cleanup_status())


@bp.put("/api/admin/cleanup")
@api_role_required("admin")
def save_cleanup():
    hours = str((request.get_json(force=True) or {}).get("hours") or "")
    if hours and hours not in cleanup.DELAYS:
        return jsonify(error="Pick one of the options."), 400
    site_settings.set_value(cleanup.SETTING, hours, current_user()["id"])
    return jsonify(_cleanup_status())


@bp.post("/api/admin/cleanup/run")
@api_role_required("admin")
def run_cleanup():
    result = cleanup.run_now(current_app._get_current_object())
    if not result["ran"]:
        return jsonify(error="Auto-clean is off. Pick when to remove files first."), 400
    return jsonify({**_cleanup_status(), "removed": result["removed"]})


# ---------- plans, prices and upgrade requests ----------

@bp.get("/api/admin/plans")
@api_role_required("admin")
def get_plans():
    return jsonify(plans=plans.all_plans(), yearly_months=plans.YEARLY_MONTHS)


@bp.put("/api/admin/plans")
@api_role_required("admin")
def save_plans():
    error = plans.save_plans(request.get_json(force=True) or {}, current_user()["id"])
    if error:
        return jsonify(error=error), 400
    return get_plans()


@bp.get("/api/admin/plan-requests")
@api_role_required("manager")
def plan_requests():
    rows = db.get().execute(
        "SELECT r.id, r.plan, r.period, r.created_at, u.id AS user_id, u.email, u.name, u.plan AS current_plan "
        "FROM plan_requests r JOIN users u ON u.id = r.user_id WHERE r.status = 'pending' ORDER BY r.id").fetchall()
    return jsonify([dict(r) for r in rows])


@bp.post("/api/admin/plan-requests/<int:request_id>/<decision>")
@api_role_required("manager")
def decide_request(request_id, decision):
    if decision not in ("approve", "dismiss"):
        abort(404)
    row = db.get().execute("SELECT * FROM plan_requests WHERE id = ? AND status = 'pending'", (request_id,)).fetchone()
    if not row:
        return jsonify(error="That request was already handled."), 404
    _user, error_response = _target(row["user_id"])
    if error_response:
        return error_response
    conn = db.get()
    if decision == "approve":
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", (row["plan"], row["user_id"]))
    conn.execute("UPDATE plan_requests SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
                 ("approved" if decision == "approve" else "dismissed", db.now(), current_user()["id"], request_id))
    conn.commit()
    return plan_requests()


# ---------- payment settings (stored now, used once online checkout is built) ----------

PAYMENT_PROVIDERS = {"": "Not chosen", "lemonsqueezy": "Lemon Squeezy", "paddle": "Paddle", "other": "Other"}
CHECKOUTS = ("creator_monthly", "creator_yearly", "pro_monthly", "pro_yearly")
PAYMENT_SECRETS = {"api_key": "payments_api_key", "webhook_secret": "payments_webhook_secret"}
PAYMENTS = "payments"


def _payment_config() -> dict:
    try:
        saved = json.loads(site_settings.get_value(PAYMENTS) or "{}")
    except ValueError:
        saved = {}
    return {"provider": saved.get("provider", ""), "mode": saved.get("mode", "test"),
            "store_id": saved.get("store_id", ""), "checkout": {k: saved.get("checkout", {}).get(k, "") for k in CHECKOUTS}}


def _payments_status():
    config = _payment_config()
    row = db.get().execute("SELECT s.updated_at, u.email FROM site_settings s LEFT JOIN users u ON u.id = s.updated_by "
                           "WHERE s.key = ?", (PAYMENTS,)).fetchone()
    provider = config["provider"] or "provider"
    return {**config, "providers": PAYMENT_PROVIDERS,
            **{f"{name}_hint": _mask(site_settings.get_value(key)) for name, key in PAYMENT_SECRETS.items()},
            # Where the provider will send "paid / renewed / cancelled" notices, once that's built.
            "webhook_url": f"{request.host_url}api/billing/webhook/{provider}",
            "public_site": request.scheme == "https",
            "updated_at": row["updated_at"] if row else None, "updated_by": row["email"] if row else None}


@bp.get("/api/admin/payments")
@api_role_required("admin")
def get_payments():
    return jsonify(_payments_status())


@bp.put("/api/admin/payments")
@api_role_required("admin")
def save_payments():
    data = request.get_json(force=True) or {}
    config = _payment_config()
    if "provider" in data:
        if data["provider"] not in PAYMENT_PROVIDERS:
            return jsonify(error="Pick one of the listed payment services."), 400
        config["provider"] = data["provider"]
    if "mode" in data:
        if data["mode"] not in ("test", "live"):
            return jsonify(error="Mode must be test or live."), 400
        config["mode"] = data["mode"]
    if "store_id" in data:
        config["store_id"] = str(data["store_id"] or "").strip()[:100]
    for key, url in (data.get("checkout") or {}).items():
        if key not in CHECKOUTS:
            continue
        url = str(url or "").strip()
        if url and not re.match(r"^https://[^\s/]+\.[^\s/]+/\S*$", url):
            return jsonify(error="Checkout links must be full https:// addresses from your payment service."), 400
        config["checkout"][key] = url[:500]
    for name, key in PAYMENT_SECRETS.items():
        value = str(data.get(name) or "").strip()
        if value:  # blank means "keep what's saved"
            site_settings.set_value(key, value[:500], current_user()["id"])
        if data.get(f"clear_{name}"):
            site_settings.set_value(key, "")
    site_settings.set_value(PAYMENTS, json.dumps(config), current_user()["id"])
    return jsonify(_payments_status())


@bp.delete("/api/admin/payments")
@api_role_required("admin")
def clear_payments():
    for key in (PAYMENTS, *PAYMENT_SECRETS.values()):
        site_settings.set_value(key, "")
    return jsonify(_payments_status())
