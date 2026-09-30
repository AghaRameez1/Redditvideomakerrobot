"""Connect / disconnect a user's YouTube channel (OAuth)."""
import requests
from flask import Blueprint, current_app, jsonify, redirect, url_for

from . import db, site_settings
from .publish import PublishError, youtube
from .security import api_login_required, current_user, decrypt, encrypt, page_login_required

bp = Blueprint("connections", __name__)

PLATFORMS = {
    "youtube": {"label": "YouTube", "setup": "the Google client on the admin page"},
}


def configured(platform: str) -> bool:
    return platform == "youtube" and site_settings.google_enabled()


def _youtube():
    return site_settings.google_client("youtube", " ".join(youtube.SCOPES))


def connection(user_id: int, platform: str):
    return db.get().execute("SELECT * FROM connections WHERE user_id = ? AND platform = ?",
                            (user_id, platform)).fetchone()


def _save(platform, account, token, expires_at=None):
    conn = db.get()
    conn.execute("INSERT OR REPLACE INTO connections (user_id, platform, account_id, account_name, token_enc, "
                 "expires_at, connected_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (current_user()["id"], platform, account["id"], account["name"], encrypt(token),
                  expires_at, db.now()))
    conn.commit()


def _back(platform, error=None):
    return redirect(f"/settings?{'error' if error else 'connected'}={platform}"
                    + (f"&msg={requests.utils.quote(error)}" if error else "") + "#connections")


@bp.get("/api/connections")
@api_login_required
def list_connections():
    out = []
    for key, info in PLATFORMS.items():
        row = connection(current_user()["id"], key)
        expired = bool(row and row["expires_at"] and row["expires_at"] < db.now())
        out.append({"platform": key, "label": info["label"], "available": configured(key),
                    "setup": info["setup"], "connected": bool(row), "expired": expired,
                    "account": row["account_name"] if row else "", "expires_at": row["expires_at"] if row else None})
    return jsonify(out)


# ---------- YouTube ----------

@bp.get("/connect/youtube")
@page_login_required
def youtube_start():
    if not configured("youtube"):
        return _back("youtube", "YouTube isn't set up on this server.")
    # offline + consent: Google only returns a refresh token (needed to upload later) this way.
    return _youtube().authorize_redirect(url_for("connections.youtube_callback", _external=True),
                                            access_type="offline", prompt="consent",
                                            include_granted_scopes="true")


@bp.get("/connect/youtube/callback")
@page_login_required
def youtube_callback():
    try:
        token = _youtube().authorize_access_token()
    except Exception:
        current_app.logger.exception("YouTube connect failed")
        return _back("youtube", "YouTube didn't finish connecting. Try again.")
    if youtube.SCOPES[0] not in (token.get("scope") or ""):
        return _back("youtube", "Allow the upload permission when Google asks, so videos can be posted.")
    if not token.get("refresh_token"):
        return _back("youtube", "Google didn't grant long-term access. Try connecting again.")
    try:
        channel = youtube.channel(token["access_token"])
    except PublishError as exc:
        current_app.logger.warning("YouTube connect: %s", exc)
        return _back("youtube", str(exc))
    _save("youtube", channel, token["refresh_token"])
    return _back("youtube")


# ---------- disconnect ----------

@bp.post("/api/connections/<platform>/disconnect")
@api_login_required
def disconnect(platform):
    row = connection(current_user()["id"], platform)
    if row and platform == "youtube":
        # Best effort: also cancel the access at Google, not just forget it here.
        try:
            requests.post(youtube.REVOKE_URI, params={"token": decrypt(row["token_enc"])}, timeout=10)
        except requests.RequestException:
            pass
    conn = db.get()
    conn.execute("DELETE FROM connections WHERE user_id = ? AND platform = ?", (current_user()["id"], platform))
    conn.commit()
    return list_connections()
