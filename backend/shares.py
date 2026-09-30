"""Background uploads to YouTube, with progress stored in the shares table."""
import sqlite3
import threading
import traceback

from . import db
from .publish import PublishError, youtube

_uploads = threading.Semaphore(2)  # a couple at a time; uploads are network-bound, not CPU-bound


def start(db_path, video_id, platform, run) -> int:
    """run(on_progress) -> url. Returns the share id to poll."""
    with sqlite3.connect(db_path) as conn:
        share_id = conn.execute("INSERT INTO shares (video_id, platform, status, created_at) "
                                "VALUES (?, ?, 'uploading', ?)", (video_id, platform, db.now())).lastrowid
    threading.Thread(target=_run, args=(db_path, share_id, run), daemon=True).start()
    return share_id


def _run(db_path, share_id, run):
    def update(**fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        with sqlite3.connect(db_path) as conn:
            conn.execute(f"UPDATE shares SET {cols} WHERE id = ?", (*fields.values(), share_id))

    last = [-1]

    def on_progress(pct):
        if pct != last[0]:  # skip redundant writes
            last[0] = pct
            update(percent=pct, status="processing" if pct >= 60 else "uploading")

    with _uploads:
        try:
            url = run(on_progress)
            update(status="done", percent=100, url=url)
        except PublishError as exc:
            update(status="error", error=str(exc))
        except Exception as exc:  # unexpected: keep the details in the server log
            traceback.print_exc()
            update(status="error", error=f"Upload failed unexpectedly: {exc}")


def youtube_job(refresh_token, client_id, client_secret, path, title, description, privacy):
    return lambda on_progress: youtube.upload(refresh_token, client_id, client_secret, path,
                                              title, description, privacy, on_progress)
