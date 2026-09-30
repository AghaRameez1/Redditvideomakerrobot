"""The script-writing instructions and output shape, shared by every AI provider."""
import json

WORDS_PER_SECOND = 2.5  # roughly how fast the voices speak

TONES = {
    "informative": "clear and informative, like a good explainer",
    "story": "a short first-person story with a twist or lesson at the end",
    "funny": "light and funny, without forcing jokes",
    "dramatic": "suspenseful, building to a reveal",
}

SYSTEM = """You write scripts for short vertical videos (YouTube Shorts, Instagram Reels, TikTok).
The video shows each sentence as its own on-screen card while a text-to-speech voice reads it,
over background footage.

What makes these work:
- The first sentence is a hook: a surprising claim, a question, or tension. Viewers decide in two seconds.
- One idea per sentence, and short sentences (under 15 words) so each card is readable on a phone.
- Write for the ear: spell out numbers and units when they matter ("800 megabytes", not "800MB"),
  and avoid abbreviations a voice would read letter by letter.
- No emoji, hashtags, stage directions, or speaker labels. Only the words to be spoken.
- End with a short call to action or a memorable final line.
- Keep it original and accurate. Don't invent statistics or quotes presented as real.

The title appears on the first card and is read aloud, so keep it under 10 words.
Reply with JSON only: a "title" string and a "sentences" array of strings in reading order."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Video title, under 10 words"},
        "sentences": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The script, one sentence per item, in reading order",
        },
    },
    "required": ["title", "sentences"],
    "additionalProperties": False,
}


class ScriptError(Exception):
    """A problem worth showing to the user as-is."""


def build_prompt(topic: str, tone: str, seconds: int) -> str:
    words = round(seconds * WORDS_PER_SECOND)
    return (f"Topic: {topic}\n\nTone: {TONES.get(tone, TONES['informative'])}.\n"
            f"Length: about {words} words in total, for a video of roughly {seconds} seconds.")


def parse_reply(text: str) -> dict:
    """Validate a provider's JSON reply into {"title": str, "sentences": [str, ...]}."""
    try:
        data = json.loads(text)
        title = str(data["title"]).strip()
        sentences = [str(s).strip() for s in data["sentences"] if str(s).strip()]
    except (ValueError, KeyError, TypeError):
        raise ScriptError("The AI replied in an unexpected format. Try again.")
    if not title or not sentences:
        raise ScriptError("The AI returned an empty script. Try again.")
    return {"title": title, "sentences": sentences}


def saved_key_rejected(error: ScriptError, company: str) -> ScriptError:
    """Reword a 'key rejected' error for the studio, where the key was saved earlier."""
    if "rejected this key" in str(error):
        return ScriptError(f"{company} rejected your saved key. Update it in Settings.")
    return error
