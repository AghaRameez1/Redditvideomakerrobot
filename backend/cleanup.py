"""Auto-clean: remove video files from this computer once they're posted to YouTube.

The entry, its thumbnail and its YouTube link stay in My videos (like "Remove file, keep link").
The admin picks the delay on the admin page; it's off until then. While the app runs
(python app.py) a background thread checks every CHECK_EVERY seconds. On a server, run
`flask --app app cleanup` from cron instead.
"""
import json
import sqlite3
import threading
import time

from . import db, site_settings
from .storage import user_dir

CHECK_EVERY = 15 * 60
# hours after posting -> label. "" (not stored) means off.
DELAYS = {"0": "As soon as it's posted", "24": "1 day after posting", "168": "7 days after posting",
          "720": "30 days after posting"}
SETTING, LAST_RUN = "cleanup_after_hours", "cleanup_last_run"


def delay_hours():
    """The chosen delay in hours, or None when auto-clean is off. Needs an app context."""
    value = site_settings.get_value(SETTING)
    return int(value) if value in DELAYS else None


def run(db_path: str, hours: int) -> int:
    """Remove the files of videos posted at least `hours` ago. Returns how many were removed."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT v.id, v.user_id, v.filename FROM videos v WHERE v.file_removed_at IS NULL "
            "AND EXISTS (SELECT 1 FROM shares s WHERE s.video_id = v.id AND s.status = 'done' "
            "            AND julianday(s.created_at) <= julianday('now', ?)) "
            "AND NOT EXISTS (SELECT 1 FROM shares s WHERE s.video_id = v.id "
            "                AND s.status IN ('uploading', 'processing'))",  # never pull a file mid-upload
            (f"-{int(hours)} hours",)).fetchall()
        for r in rows:
            folder = user_dir(r["user_id"]).resolve()
            path = (folder / r["filename"]).resolve()
            if path.parent == folder:  # stay inside the user's folder
                path.unlink(missing_ok=True)
            conn.execute("UPDATE videos SET file_removed_at = ? WHERE id = ?", (db.now(), r["id"]))
    return len(rows)


def run_now(app) -> dict:
    """One pass with the saved delay. Records when it ran. Returns {"ran", "removed"}."""
    with app.app_context():
        hours = delay_hours()
        if hours is None:
            return {"ran": False, "removed": 0}
        removed = run(app.config["DATABASE_PATH"], hours)
        site_settings.set_value(LAST_RUN, json.dumps({"at": db.now(), "removed": removed}))
        return {"ran": True, "removed": removed}


def last_run(app) -> dict:
    with app.app_context():
        try:
            return json.loads(site_settings.get_value(LAST_RUN) or "null")
        except ValueError:
            return None


def start_scheduler(app):
    """Check in the background for as long as the app runs."""
    def loop():
        while True:
            try:
                result = run_now(app)
                if result["removed"]:
                    app.logger.info("Auto-clean removed %s posted video file(s)", result["removed"])
            except Exception:  # keep checking; a bad pass shouldn't stop future ones
                app.logger.exception("Auto-clean failed")
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, name="auto-clean", daemon=True).start()
