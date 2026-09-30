"""Text to speech.

Voices are identified as "google:<tld>": gTTS, free, needs internet. The tld picks the accent
(com, co.uk, com.au, co.in).

Every voice ends up as a 44.1 kHz WAV, so clips can be joined without re-timing.
"""
import subprocess
from pathlib import Path

GOOGLE_ACCENTS = [("com", "US"), ("co.uk", "UK"), ("com.au", "Australia"), ("co.in", "India")]

GAP_SECONDS = 0.25  # short pause after each sentence


def available_voices() -> list:
    return [(f"google:{tld}", f"Google {label}") for tld, label in GOOGLE_ACCENTS]


def synthesize(text: str, voice: str, out_wav: Path) -> float:
    """Speak `text` into out_wav and return its duration in seconds."""
    provider, _, option = voice.partition(":")
    raw = out_wav.with_suffix(".raw")
    if provider == "google":
        from gtts import gTTS

        gTTS(text=text, lang="en", tld=option or "com").save(str(raw))
    else:
        raise ValueError(f"Unknown voice: {voice}")

    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-ar", "44100", "-ac", "2",
         "-af", f"apad=pad_dur={GAP_SECONDS}", str(out_wav)],
        check=True,
    )
    raw.unlink(missing_ok=True)
    return duration(out_wav)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())
