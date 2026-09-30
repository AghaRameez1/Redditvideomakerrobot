"""Users' own background footage: upload, list, preview still, delete.

Uploading your own footage (with the rights to it) avoids relying on other creators' gameplay.
Files live in results/user-N/.footage/ and count towards the user's disk use.
"""
import json
import subprocess
import uuid

from flask import Blueprint, jsonify, request, send_file

from engine.backgrounds import still_frame

from . import db
from .security import api_login_required, current_user
from .storage import footage_dir, owned_footage

bp = Blueprint("footage", __name__)

EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_FILE = 500 * 1024 * 1024
MAX_TOTAL = 3 * 1024 * 1024 * 1024
MAX_FILES = 20
MIN_SECONDS, MAX_SECONDS = 3, 60 * 60


def _uid():
    return current_user()["id"]


def _still(user_id, footage_id):
    return footage_dir(user_id) / f"{int(footage_id)}.jpg"


def _probe(path):
    """(duration, width, height) of the first video stream, or None if it isn't a usable video."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height:format=duration", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=60, check=True).stdout
        info = json.loads(out)
        stream = info["streams"][0]
        return float(info["format"]["duration"]), int(stream["width"]), int(stream["height"])
    except (subprocess.SubprocessError, KeyError, IndexError, ValueError, TypeError):
        return None


def _list(user_id):
    rows = db.get().execute("SELECT id, name, duration, width, height, size, created_at FROM footage "
                            "WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


@bp.get("/api/footage")
@api_login_required
def list_footage():
    items = _list(_uid())
    return jsonify(items=items, used=sum(i["size"] for i in items), max_total=MAX_TOTAL,
                   max_file=MAX_FILE, max_files=MAX_FILES)


@bp.post("/api/footage")
@api_login_required
def upload():
    uid = _uid()
    if request.form.get("rights") != "yes":
        return jsonify(error="Confirm you own this footage or have permission to use it."), 400
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="Choose a video file."), 400
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in EXTENSIONS:
        return jsonify(error="Use an MP4, MOV, WebM or MKV video."), 400
    existing = _list(uid)
    if len(existing) >= MAX_FILES:
        return jsonify(error=f"You can keep up to {MAX_FILES} clips. Delete one to add another."), 400

    folder = footage_dir(uid)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}{ext}"
    file.save(stored)
    size = stored.stat().st_size
    if size > MAX_FILE:
        stored.unlink(missing_ok=True)
        return jsonify(error=f"That file is over {MAX_FILE // 1024 // 1024} MB. Trim or compress it first."), 400
    if sum(i["size"] for i in existing) + size > MAX_TOTAL:
        stored.unlink(missing_ok=True)
        return jsonify(error="That would go over your 3 GB footage space. Delete a clip first."), 400
    probe = _probe(stored)
    if not probe:
        stored.unlink(missing_ok=True)
        return jsonify(error="That file doesn't look like a video we can read."), 400
    seconds, width, height = probe
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        stored.unlink(missing_ok=True)
        return jsonify(error="Use a clip between 3 seconds and 1 hour long."), 400

    name = file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:120]
    conn = db.get()
    footage_id = conn.execute("INSERT INTO footage (user_id, name, filename, duration, width, height, size, created_at) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                              (uid, name, stored.name, round(seconds, 1), width, height, size, db.now())).lastrowid
    conn.commit()
    try:
        still_frame(stored, _still(uid, footage_id))
    except subprocess.SubprocessError:
        pass  # the preview is optional
    return list_footage()


@bp.get("/api/footage/<int:footage_id>/still")
@api_login_required
def still(footage_id):
    owned_footage(_uid(), footage_id)
    jpg = _still(_uid(), footage_id)
    if not jpg.exists():
        return jsonify(error="No preview"), 404
    return send_file(jpg)


@bp.delete("/api/footage/<int:footage_id>")
@api_login_required
def delete(footage_id):
    _row, path = owned_footage(_uid(), footage_id)
    path.unlink(missing_ok=True)
    _still(_uid(), footage_id).unlink(missing_ok=True)
    conn = db.get()
    conn.execute("DELETE FROM footage WHERE id = ?", (footage_id,))
    conn.commit()
    return list_footage()
