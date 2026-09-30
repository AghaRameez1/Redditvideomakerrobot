"""Filesystem locations, all relative to the project root."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
FONTS = ROOT / "fonts"
BACKGROUNDS = ROOT / "assets" / "backgrounds"
TEMP = ROOT / "assets" / "temp"
# Finished videos. Override with RESULTS_DIR, e.g. a separate disk on a server, or a scratch
# folder for tests so they never write into real users' folders.
RESULTS = Path(os.environ.get("RESULTS_DIR") or ROOT / "results")

# Output video size (vertical, for Shorts / Reels / TikTok).
WIDTH, HEIGHT = 1080, 1920
