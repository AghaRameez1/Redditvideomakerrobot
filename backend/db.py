"""SQLite storage: accounts, keys, videos, connections, site settings. One connection per request."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name            TEXT,
    password_hash   TEXT,                 -- NULL for Google-only accounts
    google_sub      TEXT UNIQUE,          -- Google's stable user id
    email_verified  INTEGER NOT NULL DEFAULT 0,
    session_version INTEGER NOT NULL DEFAULT 1,  -- bump to sign out every device
    role            TEXT NOT NULL DEFAULT 'user',  -- user | manager | admin (see security.ROLES)
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider   TEXT NOT NULL,
    key_enc    BLOB NOT NULL,             -- encrypted; never returned to the browser
    hint       TEXT NOT NULL,             -- last 4 characters, for display
    model      TEXT NOT NULL,
    models     TEXT NOT NULL,             -- JSON list the key can use
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, provider)
);
CREATE TABLE IF NOT EXISTS videos (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,            -- inside results/user-N/
    title       TEXT NOT NULL,
    script      TEXT NOT NULL,
    credit      TEXT NOT NULL,            -- footage creator, added to share descriptions
    duration    REAL NOT NULL,
    created_at  TEXT NOT NULL,
    file_removed_at TEXT,                 -- set when the user removed the file but kept the post links
    UNIQUE (user_id, filename)
);
CREATE TABLE IF NOT EXISTS connections (  -- linked YouTube channels
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform      TEXT NOT NULL,
    account_id    TEXT NOT NULL,          -- YouTube channel id
    account_name  TEXT NOT NULL,
    token_enc     BLOB NOT NULL,          -- encrypted refresh token
    expires_at    TEXT,                   -- when the token stops working, if it does
    connected_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, platform)
);
CREATE TABLE IF NOT EXISTS shares (
    id          INTEGER PRIMARY KEY,
    video_id    INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    platform    TEXT NOT NULL,
    status      TEXT NOT NULL,            -- uploading | processing | done | error
    percent     INTEGER NOT NULL DEFAULT 0,
    url         TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS site_settings (  -- set on the admin page
    key         TEXT PRIMARY KEY,
    value_enc   BLOB NOT NULL,            -- encrypted
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init(app):
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(app.config["DATABASE_PATH"]) as conn:
        conn.executescript(SCHEMA)
        # Columns added after the first release, for existing databases.
        for table, column, spec in (("users", "role", "TEXT NOT NULL DEFAULT 'user'"),
                                    ("videos", "file_removed_at", "TEXT")):
            if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
        # The earlier yes/no admin flag became the role column.
        if "is_admin" in {r[1] for r in conn.execute("PRAGMA table_info(users)")}:
            conn.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")
            conn.execute("ALTER TABLE users DROP COLUMN is_admin")
        # Instagram sharing was removed: forget its app keys and any account links.
        conn.execute("DELETE FROM site_settings WHERE key IN ('meta_app_id', 'meta_app_secret', "
                     "'instagram_app_id', 'instagram_app_secret')")
        conn.execute("DELETE FROM connections WHERE platform = 'instagram'")
        # Uploads run in this process, so any still marked as running were cut off by a restart.
        conn.execute("UPDATE shares SET status = 'error', error = 'The app restarted during the upload. Try again.' "
                     "WHERE status IN ('uploading', 'processing')")
    app.teardown_appcontext(close)
