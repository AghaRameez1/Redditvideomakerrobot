"""Background render jobs. One render runs at a time; later ones wait their turn.

Each job remembers its owner, so users can only see their own. A finished video is recorded in
the videos table (with a thumbnail) and appears in My Videos.
"""
import sqlite3
import subprocess
import threading
import traceback
import uuid

from engine import catalog, make_video
from engine.tts import duration

from . import db
from .storage import thumb_path, user_dir

_jobs = {}
_render_lock = threading.Lock()


def start(db_path, user_id, title, body, voice, background, music, style) -> str:
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"owner": user_id, "status": "queued", "percent": 0,
                     "stage": "Waiting for the previous render", "video_id": None, "error": None}
    args = (job_id, db_path, user_id, title, body, voice, background, music, style)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return job_id


def get(job_id, user_id):
    job = _jobs.get(job_id)
    if not job or job["owner"] != user_id:
        return None
    return {k: v for k, v in job.items() if k != "owner"}


def _run(job_id, db_path, user_id, title, body, voice, background, music, style):
    job = _jobs[job_id]

    def progress(percent, stage):
        job.update(percent=max(job["percent"], min(percent, 98)), stage=stage)

    with _render_lock:
        job.update(status="running", stage="Starting")
        try:
            out = make_video(title, body, voice, background, music, style,
                             on_progress=progress, out_dir=user_dir(user_id))
            job["stage"] = "Saving to My Videos"
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute(
                    "INSERT INTO videos (user_id, filename, title, script, credit, duration, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, out.name, " ".join(title.split()), body.strip(),
                     catalog.videos()[background].credit, round(duration(out), 1), db.now()))
                video_id = cur.lastrowid
            _make_thumb(out, thumb_path(user_id, video_id))
            job.update(status="done", percent=100, stage="Done", video_id=video_id)
        except Exception as exc:  # report any failure to the page instead of hanging
            traceback.print_exc()
            job.update(status="error", stage="Failed", error=str(exc))


def _make_thumb(video, jpg):
    """A still from 1 second in, where the title card is showing."""
    jpg.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=360:-2", "-q:v", "4", str(jpg)], check=False)
