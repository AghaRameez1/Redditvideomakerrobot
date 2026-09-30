"""My Videos: list, play/download, delete, and share to YouTube (now or scheduled)."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, jsonify, request, send_file

from . import cleanup, db, shares, site_settings
from .connections import configured, connection
from .publish import youtube
from .security import api_login_required, current_user, decrypt
from .storage import disk_usage, owned_video, thumb_path, user_dir

bp = Blueprint("library", __name__)
NAMES = {"youtube": "YouTube"}
SCHEDULE_MIN, SCHEDULE_MAX = timedelta(minutes=15), timedelta(days=180)


def _uid():
    return current_user()["id"]


def _busy(video_id) -> bool:
    """True while an upload of this video is still running."""
    return bool(db.get().execute("SELECT 1 FROM shares WHERE video_id = ? AND status IN ('uploading', 'processing')",
                                 (video_id,)).fetchone())


def _publish_time(value):
    """A requested publish time as YouTube wants it (UTC, "2026-10-03T09:00:00Z"), or an error message."""
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None, "Pick a date and time to publish."
    if when.tzinfo is None:
        return None, "Pick a date and time to publish."
    now = datetime.now(timezone.utc)
    if when < now + SCHEDULE_MIN:
        return None, "Pick a time at least 15 minutes from now."
    if when > now + SCHEDULE_MAX:
        return None, "You can schedule up to 6 months ahead."
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), None


def _default_text(row):
    """Suggested description / caption: the script, the footage credit, and a Shorts tag."""
    credit = f"Background footage: {row['credit']}" if row["credit"] else ""
    return "\n\n".join(p for p in (row["script"].replace("\n", " "), credit) if p)


@bp.get("/api/library")
@api_login_required
def list_library():
    conn = db.get()
    rows = conn.execute("SELECT * FROM videos WHERE user_id = ? ORDER BY id DESC", (_uid(),)).fetchall()
    out = []
    for r in rows:
        history = conn.execute("SELECT id, platform, status, percent, url, error, created_at, scheduled_for FROM shares "
                               "WHERE video_id = ? ORDER BY id DESC", (r["id"],)).fetchall()
        has_file = not r["file_removed_at"] and (user_dir(_uid()) / r["filename"]).is_file()
        out.append({"id": r["id"], "title": r["title"], "duration": r["duration"], "created_at": r["created_at"],
                    "has_thumb": thumb_path(_uid(), r["id"]).exists(), "has_file": has_file,
                    "default_text": _default_text(r), "shares": [dict(h) for h in history]})
    return jsonify(out)


@bp.get("/api/library/stats")
@api_login_required
def library_stats():
    """The numbers at the top of My videos."""
    conn = db.get()
    row = conn.execute(
        "SELECT COUNT(*) AS videos, COALESCE(SUM(duration), 0) AS seconds, "
        "COUNT(CASE WHEN julianday(created_at) >= julianday('now', '-7 days') THEN 1 END) AS this_week "
        "FROM videos WHERE user_id = ?", (_uid(),)).fetchone()
    posted = conn.execute("SELECT COUNT(DISTINCT s.video_id) FROM shares s JOIN videos v ON v.id = s.video_id "
                          "WHERE v.user_id = ? AND s.status = 'done'", (_uid(),)).fetchone()[0]
    return jsonify({**dict(row), "posted": posted, "disk_bytes": disk_usage(_uid()),
                    "auto_clean_hours": cleanup.delay_hours()})


@bp.get("/api/library/<int:video_id>/file")
@api_login_required
def video_file(video_id):
    row, path = owned_video(_uid(), video_id)
    return send_file(path, as_attachment=request.args.get("download") == "1", download_name=row["filename"])


@bp.get("/api/library/<int:video_id>/thumb")
@api_login_required
def video_thumb(video_id):
    owned_video(_uid(), video_id, need_file=False)
    jpg = thumb_path(_uid(), video_id)
    if not jpg.exists():
        abort(404)
    return send_file(jpg)


@bp.post("/api/library/<int:video_id>/delete")
@api_login_required
def delete_video(video_id):
    """Delete everything: the file, the thumbnail, and the entry with its share history."""
    _row, path = owned_video(_uid(), video_id, need_file=False)
    if _busy(video_id):
        return jsonify(error="This video is still uploading. Wait for it to finish, then delete it."), 409
    path.unlink(missing_ok=True)
    thumb_path(_uid(), video_id).unlink(missing_ok=True)
    conn = db.get()
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))  # share history goes with it
    conn.commit()
    return jsonify(ok=True)


@bp.post("/api/library/<int:video_id>/remove-file")
@api_login_required
def remove_file(video_id):
    """Free the disk space but keep the entry, its thumbnail and its YouTube links."""
    row, path = owned_video(_uid(), video_id, need_file=False)
    if row["file_removed_at"]:
        return jsonify(ok=True)
    if _busy(video_id):
        return jsonify(error="This video is still uploading. Wait for it to finish first."), 409
    if not db.get().execute("SELECT 1 FROM shares WHERE video_id = ? AND status = 'done'", (video_id,)).fetchone():
        return jsonify(error="This video isn't posted anywhere yet, so no copy would be left. Delete it instead."), 400
    path.unlink(missing_ok=True)
    conn = db.get()
    conn.execute("UPDATE videos SET file_removed_at = ? WHERE id = ?", (db.now(), video_id))
    conn.commit()
    return jsonify(ok=True)


@bp.post("/api/library/<int:video_id>/share/<platform>")
@api_login_required
def share(video_id, platform):
    if platform != "youtube":
        abort(404)
    row, path = owned_video(_uid(), video_id, need_file=False)
    if row["file_removed_at"] or not path.is_file():
        return jsonify(error="The video file was removed from this computer, so it can't be posted again."), 400
    if not configured(platform):
        return jsonify(error=f"{NAMES[platform]} sharing isn't set up on this server."), 400
    conn_row = connection(_uid(), platform)
    if not conn_row:
        return jsonify(error=f"Connect your {NAMES[platform]} account in Settings first."), 400
    if conn_row["expires_at"] and conn_row["expires_at"] < db.now():
        return jsonify(error=f"Your {NAMES[platform]} connection has expired. Reconnect it in Settings."), 400

    data = request.get_json(force=True) or {}
    token = decrypt(conn_row["token_enc"])
    if not token:
        return jsonify(error=f"Reconnect {NAMES[platform]} in Settings."), 400
    title = (data.get("title") or row["title"]).strip()[:100]
    description = (data.get("description") or _default_text(row)).strip()[:5000]
    privacy = data.get("privacy") if data.get("privacy") in youtube.PRIVACY else "private"
    if not title:
        return jsonify(error="Add a title."), 400
    publish_at = None
    if data.get("publish_at"):
        publish_at, error = _publish_time(data["publish_at"])
        if error:
            return jsonify(error=error), 400
    creds = site_settings.google()
    job = shares.youtube_job(token, creds["client_id"], creds["client_secret"], path, title, description, privacy,
                             publish_at)
    return jsonify(share_id=shares.start(current_app.config["DATABASE_PATH"], video_id, platform, job,
                                         scheduled_for=publish_at))


@bp.get("/api/shares/<int:share_id>")
@api_login_required
def share_status(share_id):
    row = db.get().execute(
        "SELECT s.id, s.platform, s.status, s.percent, s.url, s.error, s.scheduled_for FROM shares s "
        "JOIN videos v ON v.id = s.video_id WHERE s.id = ? AND v.user_id = ?", (share_id, _uid())).fetchone()
    return jsonify(dict(row)) if row else (jsonify(error="Not found"), 404)
