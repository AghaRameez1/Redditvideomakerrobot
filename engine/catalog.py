"""Background videos and music: what exists, and what's already downloaded.

The lists live in engine/data/*.json. Each entry is [youtube_url, filename, credit, ...].
Downloads are cached in assets/backgrounds/{video,audio}/<credit>-<filename>.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import BACKGROUNDS, DATA


@dataclass(frozen=True)
class Background:
    key: str
    kind: str  # "video" or "audio"
    url: str
    filename: str
    credit: str

    @property
    def path(self) -> Path:
        return BACKGROUNDS / self.kind / f"{self.credit}-{self.filename}"

    @property
    def downloaded(self) -> bool:
        return self.path.is_file()


def _load(kind: str) -> dict:
    raw = json.loads((DATA / f"background_{kind}s.json").read_text(encoding="utf-8"))
    return {
        key: Background(key, kind, entry[0], entry[1], entry[2])
        for key, entry in raw.items()
        if key != "__comment"
    }


def videos() -> dict:
    return _load("video")


def music() -> dict:
    return _load("audio")
