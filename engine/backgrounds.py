"""Download background footage/music once, and pick a random stretch for each video."""
import random
import subprocess
from pathlib import Path

from .catalog import Background
from .tts import duration


def ensure_downloaded(bg: Background, on_progress=None) -> Path:
    """Download from YouTube on first use. on_progress gets a 0-1 fraction."""
    if bg.downloaded:
        return bg.path
    import yt_dlp

    bg.path.parent.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if on_progress and d.get("status") == "downloading" and d.get("total_bytes"):
            on_progress(d["downloaded_bytes"] / d["total_bytes"])

    opts = {
        "outtmpl": str(bg.path),
        "retries": 10,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        # Prefer H.264: Macs before M3 have no AV1 hardware decoding, and software AV1
        # decoding is roughly 3x slower than real time, which dominates render time.
        "format": ("bestvideo[height<=1080][ext=mp4][vcodec^=avc1]/bestvideo[height<=1080][ext=mp4]"
                   if bg.kind == "video" else "bestaudio/best"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([bg.url])
    return bg.path


def random_start(source: Path, needed: float) -> float:
    """A start time that leaves `needed` seconds, skipping intros where possible."""
    total = duration(source)
    if total <= needed:
        return 0.0
    earliest = min(180.0, (total - needed) / 2)
    return random.uniform(earliest, total - needed)


def preview_frame(bg: Background, out_jpg: Path) -> Path:
    """A still from the footage, cropped to 9:16 the same way the render crops it."""
    return still_frame(bg.path, out_jpg)


def still_frame(video: Path, out_jpg: Path) -> Path:
    """A 9:16 still from any footage file: 30 s in, or the middle of a shorter clip."""
    from .render import CROP_9_16
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    at = min(30.0, duration(video) / 2)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"{CROP_9_16},scale=540:-2", str(out_jpg)],
        check=True,
    )
    return out_jpg
