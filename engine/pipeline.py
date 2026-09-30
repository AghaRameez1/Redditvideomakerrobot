"""make_video(): script text in, finished .mp4 out."""
import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image

from . import catalog
from .backgrounds import ensure_downloaded, random_start
from .cards import render_card, render_watermark, render_word_frame, resolve_style
from .paths import HEIGHT, RESULTS, TEMP, WIDTH
from .render import render
from .script import displayable, safe_filename, speakable, split_sentences
from .tts import GAP_SECONDS, synthesize

DEFAULT_VOICE = "google:com"


def make_video(title: str, body: str, voice: str = DEFAULT_VOICE, background: str = "minecraft",
               music: str = "lofi", style: dict = None, on_progress=None, out_dir: Path = RESULTS,
               watermark: str = "", background_path: Path = None) -> Path:
    """Build a vertical video and return its path in out_dir (default: results/).

    background_path: the user's own footage file, used instead of the `background` catalog entry.
    watermark: optional small label drawn in a corner (used for free-plan videos).

    on_progress(percent, stage) is called as work moves along (percent is 0-100).
    """
    report = on_progress or (lambda percent, stage: None)
    title = " ".join(title.split())
    sentences = split_sentences(body)
    if not title or not sentences:
        raise ValueError("Add a title and some script text.")
    style = resolve_style(style)
    videos, tracks = catalog.videos(), catalog.music()
    if background_path is None and background not in videos:
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

        # 2. Captions. The title is always a bold card. The script is either one card per
        #    sentence, or ("words" mode) a few words at a time with the spoken word highlighted.
        report(30, "Drawing captions")
        words_mode = style["captions"] == "words"
        cards, captions = [], None
        for i, (text, start, end) in enumerate(timeline[:1] if words_mode else timeline):
            png = work / f"card{i:03}.png"
            render_card(displayable(text), style, WIDTH, png, bold=True if i == 0 else None)
            cards.append((png, start, end))
        if words_mode:
            captions = _word_captions(timeline, style, work)

        mark = None
        if watermark:
            mark = work / "watermark.png"
            render_watermark(watermark, mark)

        # 3. Backgrounds (downloaded from YouTube on first use, then cached), or the user's footage.
        if background_path is not None:
            bg_path = Path(background_path)
        else:
            bg = videos[background]
            if not bg.downloaded:
                report(33, "Downloading background video (first time only)")
            ensure_downloaded(bg, lambda f: report(33 + round(12 * f), "Downloading background video (first time only)"))
            bg_path = bg.path
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
        render(bg_path, random_start(bg_path, total), cards, voice_track,
               track.path if track else None, random_start(track.path, total) if track else 0.0,
               style, total, out, on_progress=lambda f: report(50 + round(49 * f), "Rendering"),
               watermark=mark, captions=captions)
        report(100, "Done")
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _word_timings(text: str, start: float, end: float) -> list:
    """[(word, start, end)] spread over the sentence's audio.

    The voices don't report word timings, so each word gets a share of the spoken time in
    proportion to its length: close enough to follow along.
    """
    words = displayable(text).split()
    if not words:
        return []
    spoken = max(0.2, end - start - GAP_SECONDS)
    weights = [len(w.strip(".,!?;:\"'()")) + 2 for w in words]
    scale = spoken / sum(weights)
    out, clock = [], start
    for word, weight in zip(words, weights):
        out.append((word, clock, clock + weight * scale))
        clock += weight * scale
    return out


def _chunks(timed: list, size: int) -> list:
    """Groups of up to `size` words, ending early after punctuation so phrases stay together."""
    groups, group = [], []
    for item in timed:
        group.append(item)
        if len(group) == size or item[0][-1] in ".,!?;:":
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    return groups


def _word_captions(timeline: list, style: dict, work: Path) -> Path:
    """Write one full-frame PNG per spoken word and an ffconcat list that plays them in time.

    Nothing shows during the title (it has its own card) or in the pause after a sentence.
    """
    blank = work / "blank.png"
    Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)).save(blank)
    entries = [(blank, timeline[0][2])]  # the title's time
    n = 0
    for text, start, end in timeline[1:]:
        timed = _word_timings(text, start, end)
        for group in _chunks(timed, style["words_at_once"]):
            words = [w for w, _, _ in group]
            for k, (_, w_start, w_end) in enumerate(group):
                png = work / f"word{n:04}.png"
                render_word_frame(words, k, style, (WIDTH, HEIGHT), png)
                entries.append((png, w_end - w_start))
                n += 1
        if timed:
            entries.append((blank, end - timed[-1][2]))  # the short pause after the sentence
    listing = work / "captions.ffconcat"
    lines = ["ffconcat version 1.0"]
    for png, seconds in entries:
        lines += [f"file '{png.name}'", f"duration {max(seconds, 0.001):.3f}"]
    lines.append(f"file '{entries[-1][0].name}'")  # concat needs the last file twice to honour its duration
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing


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
