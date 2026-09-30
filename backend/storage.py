"""Where each user's files live, and safe lookups inside them."""
from pathlib import Path

from flask import abort

from engine.paths import RESULTS

from . import db


def user_dir(user_id: int) -> Path:
    return RESULTS / f"user-{int(user_id)}"


def thumb_path(user_id: int, video_id: int) -> Path:
    return user_dir(user_id) / ".thumbs" / f"{int(video_id)}.jpg"


def owned_video(user_id: int, video_id: int, need_file: bool = True):
    """(row, file path) for a video this user owns, or 404. need_file=False allows a removed file."""
    row = db.get().execute("SELECT * FROM videos WHERE id = ? AND user_id = ?", (video_id, user_id)).fetchone()
    if not row:
        abort(404)
    folder = user_dir(user_id).resolve()
    path = (folder / row["filename"]).resolve()
    if path.parent != folder or (need_file and not path.is_file()):  # never serve anything outside the user's folder
        abort(404)
    return row, path


def disk_usage(user_id: int) -> int:
    """Bytes this user's videos and thumbnails take up on disk."""
    folder = user_dir(user_id)
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else 0


def footage_dir(user_id: int) -> Path:
    return user_dir(user_id) / ".footage"


def owned_footage(user_id: int, footage_id: int):
    """(row, file path) for footage this user uploaded, or 404."""
    row = db.get().execute("SELECT * FROM footage WHERE id = ? AND user_id = ?", (footage_id, user_id)).fetchone()
    if not row:
        abort(404)
    folder = footage_dir(user_id).resolve()
    path = (folder / row["filename"]).resolve()
    if path.parent != folder or not path.is_file():
        abort(404)
    return row, path
