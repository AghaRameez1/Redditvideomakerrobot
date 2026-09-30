"""make_video(): script text in, finished .mp4 out."""
import shutil
import subprocess
import uuid
from pathlib import Path

from . import catalog
from .backgrounds import ensure_downloaded, random_start
from .cards import render_card, resolve_style
from .paths import RESULTS, TEMP, WIDTH
from .render import render
from .script import displayable, safe_filename, speakable, split_sentences
from .tts import synthesize

DEFAULT_VOICE = "google:com"


def make_video(title: str, body: str, voice: str = DEFAULT_VOICE, background: str = "minecraft",
               music: str = "lofi", style: dict = None, on_progress=None, out_dir: Path = RESULTS) -> Path:
    """Build a vertical video and return its path in out_dir (default: results/).

    on_progress(percent, stage) is called as work moves along (percent is 0-100).
    """
    report = on_progress or (lambda percent, stage: None)
    title = " ".join(title.split())
    sentences = split_sentences(body)
    if not title or not sentences:
        raise ValueError("Add a title and some script text.")
    style = resolve_style(style)
    videos, tracks = catalog.videos(), catalog.music()
    if background not in videos:
        raise ValueError(f"Unknown background: {background}")
    if music != "none" and music not in tracks:
        raise ValueError(f"Unknown music: {music}")

    work = TEMP / uuid.uuid4().hex[:10]
    work.mkdir(parents=True)
    try:
        # 1. Voiceover: the title, then each sentence. Timings drive when each card shows.
        pieces = [title] + sentences
        timeline, clock = [], 0.0
        for i, text in enumerate(pieces):
            report(5 + round(25 * i / len(pieces)), "Recording voiceover")
            length = synthesize(speakable(text) or text, voice, work / f"voice{i:03}.wav")
            timeline.append((text, clock, clock + length))
            clock += length
        total = clock
        voice_track = _join_audio(sorted(work.glob("voice*.wav")), work / "voice.wav")

        # 2. One card per piece; the title card is bold.
        report(30, "Drawing text cards")
        cards = []
        for i, (text, start, end) in enumerate(timeline):
            png = work / f"card{i:03}.png"
            render_card(displayable(text), style, WIDTH, png, bold=True if i == 0 else None)
            cards.append((png, start, end))

        # 3. Backgrounds (downloaded from YouTube on first use, then cached).
        bg = videos[background]
        if not bg.downloaded:
            report(33, "Downloading background video (first time only)")
        ensure_downloaded(bg, lambda f: report(33 + round(12 * f), "Downloading background video (first time only)"))
        track = None
        if music != "none":
            track = tracks[music]
            if not track.downloaded:
                report(45, "Downloading music (first time only)")
            ensure_downloaded(track, lambda f: report(45 + round(4 * f), "Downloading music (first time only)"))

        # 4. Render.
        report(50, "Rendering")
        out = _unused_path(out_dir / f"{safe_filename(title)}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        render(bg.path, random_start(bg.path, total), cards, voice_track,
               track.path if track else None, random_start(track.path, total) if track else 0.0,
               style, total, out, on_progress=lambda f: report(50 + round(49 * f), "Rendering"))
        report(100, "Done")
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _join_audio(parts: list, out: Path) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing.name,
                    "-c", "copy", out.name], cwd=out.parent, check=True)
    return out


def _unused_path(path: Path) -> Path:
    """Never overwrite an earlier video: add (2), (3), ... to repeated titles."""
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate
