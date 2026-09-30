"""App settings and secrets.

Production (APP_ENV=production) reads every secret from environment variables and refuses to
start without them. Local development generates them once into instance/ (not in git).

  SECRET_KEY            signs login sessions
  ENCRYPTION_KEY        encrypts users' AI keys (a Fernet key; see README)
  GOOGLE_CLIENT_ID      optional, enables "Sign in with Google" and "Connect YouTube". Usually set
  GOOGLE_CLIENT_SECRET  on the admin page instead; these variables override it when set.
  DATABASE_PATH         optional, defaults to instance/app.db
  RESULTS_DIR           optional, where finished videos go (defaults to results/)
  TRUST_PROXY=1         set when running behind an HTTPS reverse proxy
"""
import os
import secrets

from cryptography.fernet import Fernet

from engine.paths import ROOT

INSTANCE = ROOT / "instance"
PRODUCTION = os.environ.get("APP_ENV") == "production"


def _secret(name, make):
    value = os.environ.get(name)
    if value:
        return value
    if PRODUCTION:
        raise RuntimeError(f"{name} must be set in production.")
    INSTANCE.mkdir(mode=0o700, exist_ok=True)
    path = INSTANCE / name.lower()
    if not path.exists():
        path.write_text(make())
        path.chmod(0o600)
    return path.read_text().strip()


def load() -> dict:
    return {
        "SECRET_KEY": _secret("SECRET_KEY", lambda: secrets.token_urlsafe(48)),
        "ENCRYPTION_KEY": _secret("ENCRYPTION_KEY", lambda: Fernet.generate_key().decode()),
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", str(INSTANCE / "app.db")),
        "TRUST_PROXY": os.environ.get("TRUST_PROXY") == "1",
        "PRODUCTION": PRODUCTION,
        # Session cookie: not readable by JavaScript, not sent on cross-site requests.
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": PRODUCTION,
        "PERMANENT_SESSION_LIFETIME": 60 * 60 * 24 * 30,
        "MAX_CONTENT_LENGTH": 1024 * 1024,  # requests are small JSON; refuse anything large
    }
