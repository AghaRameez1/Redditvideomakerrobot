"""Site-wide settings the admin changes in the browser: the Google OAuth client and auto-clean.

Environment variables win: if GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are set, the admin page only
shows them. Otherwise the values saved on the admin page are used, encrypted like AI keys. Values
are read from the database on each use, so a change applies without a restart, and in every
worker process.
"""
import threading

from authlib.integrations.flask_client import FlaskIntegration, FlaskOAuth2App
from flask import current_app

from . import db
from .security import decrypt, encrypt

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"

# provider -> (environment variables, site_settings keys) for its ID and secret
PROVIDERS = {
    "google": (("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"), ("google_client_id", "google_client_secret")),
}


def get_value(key: str) -> str:
    row = db.get().execute("SELECT value_enc FROM site_settings WHERE key = ?", (key,)).fetchone()
    return decrypt(row["value_enc"]) if row else ""


def set_value(key: str, value: str, user_id=None):
    """Store a setting, or remove it when value is empty."""
    conn = db.get()
    if value:
        conn.execute("INSERT OR REPLACE INTO site_settings (key, value_enc, updated_at, updated_by) "
                     "VALUES (?, ?, ?, ?)", (key, encrypt(value), db.now(), user_id))
    else:
        conn.execute("DELETE FROM site_settings WHERE key = ?", (key,))
    conn.commit()


def save(provider: str, client_id: str, secret: str, user_id: int):
    """Store (or, with empty values, remove) a provider's ID and secret."""
    for key, value in zip(PROVIDERS[provider][1], (client_id, secret)):
        set_value(key, value, user_id)


def credentials(provider: str) -> dict:
    """The app in use: {"client_id", "client_secret", "source"}.

    source is "env", "admin", or "" when it isn't set up.
    """
    (env_id, env_secret), (key_id, key_secret) = PROVIDERS[provider]
    c = current_app.config
    if c[env_id] and c[env_secret]:
        return {"client_id": c[env_id], "client_secret": c[env_secret], "source": "env"}
    cid, secret = get_value(key_id), get_value(key_secret)
    if cid and secret:
        return {"client_id": cid, "client_secret": secret, "source": "admin"}
    return {"client_id": "", "client_secret": "", "source": ""}


def google() -> dict:
    return credentials("google")


def enabled(provider: str) -> bool:
    return bool(credentials(provider)["source"])


def google_enabled() -> bool:
    return enabled("google")


# One OAuth client per purpose ("google" sign-in, "youtube" connect),
# rebuilt when the credentials change.
_clients, _lock = {}, threading.Lock()


def _client(purpose: str, creds: dict, **kwargs):
    key = (purpose, creds["client_id"], creds["client_secret"])
    with _lock:
        client = _clients.get(purpose)
        if not client or client[0] != key:
            app = FlaskOAuth2App(FlaskIntegration(purpose), purpose, client_id=creds["client_id"],
                                 client_secret=creds["client_secret"], **kwargs)
            client = _clients[purpose] = (key, app)
        return client[1]


def google_client(purpose: str, scope: str):
    return _client(purpose, google(), server_metadata_url=GOOGLE_METADATA, client_kwargs={"scope": scope})
