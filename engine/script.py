"""Turn a pasted script into the pieces a video is made of."""
import re
import unicodedata

_URL = re.compile(r"https?://\S+|www\.\S+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(body: str) -> list:
    """One sentence per on-screen card. Line breaks also start a new card."""
    parts = []
    for line in body.splitlines():
        parts += [s.strip() for s in _SENTENCE_END.split(line) if s.strip()]
    return parts


def speakable(text: str) -> str:
    """Text for the voice: drop URLs and characters TTS engines read out literally."""
    text = _URL.sub(" ", text)
    text = re.sub(r"[#*_~`|<>{}\[\]\\^]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def displayable(text: str) -> str:
    """Text for the cards: Roboto has no emoji, so drop them rather than draw empty boxes."""
    # "So" (other symbol) covers emoji and pictographs; the rest are joiners/variation selectors.
    text = "".join(ch for ch in text if unicodedata.category(ch) != "So"
                   and ord(ch) <= 0xFFFF and not 0xFE00 <= ord(ch) <= 0xFE0F and ch != "‍")
    return re.sub(r"\s+", " ", text).strip()


def safe_filename(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|%]', "", title)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "video"
