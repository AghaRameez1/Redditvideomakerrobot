#!/usr/bin/env python
"""Make a video from the command line.

    python make_video.py my_script.txt
    python make_video.py my_script.txt --voice google:co.uk --background gta --music none --style style.json

The script file is plain text: the first non-empty line is the title, the rest is read aloud
one sentence per card. The finished video is saved in results/.
"""
import argparse
import json
import sys
from pathlib import Path

from engine import make_video
from engine.pipeline import DEFAULT_VOICE


def main():
    parser = argparse.ArgumentParser(description="Make a vertical video from a script file.")
    parser.add_argument("script", type=Path)
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="e.g. google:com, google:co.uk, google:com.au, google:co.in")
    parser.add_argument("--background", default="minecraft", help="key from engine/data/background_videos.json")
    parser.add_argument("--music", default="lofi", help="key from engine/data/background_audios.json, or none")
    parser.add_argument("--style", type=Path, help="JSON file of look settings (keys: engine/cards.py DEFAULT_STYLE)")
    args = parser.parse_args()

    lines = [ln.strip() for ln in args.script.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) < 2:
        sys.exit("The script needs a title line and at least one line of text.")
    style = json.loads(args.style.read_text(encoding="utf-8")) if args.style else None

    last = [None]

    def progress(percent, stage):
        if (percent, stage) != last[0]:
            print(f"\r{percent:3d}%  {stage:<50}", end="", flush=True)
            last[0] = (percent, stage)

    out = make_video(lines[0], "\n".join(lines[1:]), args.voice, args.background, args.music, style, progress)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
