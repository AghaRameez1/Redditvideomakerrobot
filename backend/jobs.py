"""Background render jobs. One render runs at a time; later ones wait their turn.

Each job remembers its owner, so users can only see their own. A finished video is recorded in
the videos table (with a thumbnail) and appears in My Videos.
"""
import sqlite3
import subprocess
import threading
import time
import traceback
import uuid

from engine import catalog, make_video
from engine.tts import duration

from . import db
from .storage import thumb_path, user_dir

_jobs = {}
_render_lock = threading.Lock()
KEEP_FINISHED = 60 * 60  # seconds a finished job stays listed, so a reloaded page can still show it


def start(db_path, user_id, title, body, voice, background, music, style, watermark="", background_path=None) -> str:
    _forget_old()
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"owner": user_id, "status": "queued", "percent": 0, "title": " ".join(title.split())[:120],
                     "stage": "Waiting for the previous render", "video_id": None, "error": None,
                     "started_at": time.time(), "finished_at": None}
    args = (job_id, db_path, user_id, title, body, voice, background, music, style, watermark, background_path)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return job_id


def active(user_id) -> int:
    """Renders of this user's that are queued or running, so limits count them too."""
    return sum(1 for j in _jobs.values() if j["owner"] == user_id and j["status"] in ("queued", "running"))


def for_user(user_id) -> list:
    """This user's renders that are queued or running, oldest first, for pages that reload mid-render."""
    mine = [(job_id, j) for job_id, j in _jobs.items()
            if j["owner"] == user_id and j["status"] in ("queued", "running")]
    return [{"id": job_id, **_public(j)} for job_id, j in sorted(mine, key=lambda item: item[1]["started_at"])]


def _public(job):
    return {k: v for k, v in job.items() if k not in ("owner", "started_at", "finished_at")}


def _forget_old():
    cutoff = time.time() - KEEP_FINISHED
    for job_id in [k for k, j in _jobs.items() if j["finished_at"] and j["finished_at"] < cutoff]:
        _jobs.pop(job_id, None)


def get(job_id, user_id):
    job = _jobs.get(job_id)
    if not job or job["owner"] != user_id:
        return None
    return _public(job)


def _run(job_id, db_path, user_id, title, body, voice, background, music, style, watermark, background_path):
    job = _jobs[job_id]

    def progress(percent, stage):
        job.update(percent=max(job["percent"], min(percent, 98)), stage=stage)

    with _render_lock:
        job.update(status="running", stage="Starting")
        try:
            out = make_video(title, body, voice, background, music, style,
                             on_progress=progress, out_dir=user_dir(user_id), watermark=watermark,
                             background_path=background_path)
            job["stage"] = "Saving to My Videos"
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute(
                    "INSERT INTO videos (user_id, filename, title, script, credit, duration, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, out.name, " ".join(title.split()), body.strip(),
                     "" if background_path else catalog.videos()[background].credit,  # own footage: no credit
                     round(duration(out), 1), db.now()))
                video_id = cur.lastrowid
                conn.execute("INSERT INTO renders (user_id, created_at) VALUES (?, ?)", (user_id, db.now()))
            _make_thumb(out, thumb_path(user_id, video_id))
            job.update(status="done", percent=100, stage="Done", video_id=video_id, finished_at=time.time())
        except Exception as exc:  # report any failure to the page instead of hanging
            traceback.print_exc()
            job.update(status="error", stage="Failed", error=str(exc), finished_at=time.time())


def _make_thumb(video, jpg):
    """A still from 1 second in, where the title card is showing."""
    jpg.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=360:-2", "-q:v", "4", str(jpg)], check=False)
