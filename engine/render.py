"""Put background, cards and audio together with a single ffmpeg run."""
import subprocess
from pathlib import Path

from .paths import HEIGHT, WIDTH
from .tts import duration

MUSIC_VOLUME = 0.15


def render(background: Path, bg_start: float, cards: list, voice: Path, music, music_start: float,
           style: dict, total: float, out: Path, on_progress=None) -> Path:
    """cards: [(png_path, start_s, end_s)]. music: Path or None. on_progress gets a 0-1 fraction."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-nostats", "-progress", "pipe:1"]
    if duration(background) < total:
        cmd += ["-stream_loop", "-1"]  # short footage: loop it
    cmd += ["-ss", f"{bg_start:.2f}", "-t", f"{total:.2f}", "-i", str(background)]
    for png, _, _ in cards:
        cmd += ["-i", str(png)]
    cmd += ["-i", str(voice)]
    if music:
        cmd += ["-ss", f"{music_start:.2f}", "-t", f"{total:.2f}", "-i", str(music)]

    # Drop to 30 fps first so every later filter handles half the frames of 60 fps footage.
    # Crop the landscape footage to 9:16, then scale to full size so cards overlay 1:1.
    # Blur runs at half size (4x fewer pixels, same look) before scaling up.
    bg = f"[0:v]fps=30,crop=ih*{WIDTH}/{HEIGHT}:ih"
    if style["blur"]:
        bg += f",scale={WIDTH // 2}:{HEIGHT // 2},gblur=sigma={style['blur'] / 2}"
    bg += f",scale={WIDTH}:{HEIGHT},setsar=1"
    if style["dim"]:
        keep = round(1 - style["dim"] / 100, 3)
        bg += f",colorchannelmixer=rr={keep}:gg={keep}:bb={keep}"
    filters = [bg + "[v0]"]

    # Card centre sits at `position` percent down the frame, kept fully on screen.
    y = f"max(0\\,min(main_h-overlay_h\\,main_h*{style['position'] / 100}-overlay_h/2))"
    for i, (_, start, end) in enumerate(cards, start=1):
        filters.append(f"[v{i - 1}][{i}:v]overlay=x=(main_w-overlay_w)/2:y={y}"
                       f":enable=between(t\\,{start:.3f}\\,{end:.3f})[v{i}]")

    voice_in = len(cards) + 1
    if music:
        filters.append(f"[{voice_in + 1}:a]volume={MUSIC_VOLUME}[m];"
                       f"[{voice_in}:a][m]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        filters.append(f"[{voice_in}:a]anull[a]")

    cmd += ["-filter_complex", ";".join(filters), "-map", f"[v{len(cards)}]", "-map", "[a]",
            "-t", f"{total:.2f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:  # ffmpeg -progress output: key=value lines
        if line.startswith("out_time_us=") and on_progress:
            value = line.split("=", 1)[1].strip()
            if value.isdigit():
                on_progress(min(1.0, int(value) / 1e6 / total))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.read().strip()[-800:]}")
    return out
