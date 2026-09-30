"""AI script writing with the user's own key, for Claude, ChatGPT or Gemini.

Keys are always passed in explicitly: a hosted app must never fall back to the server's own
credentials and bill the wrong account.
"""
from . import anthropic_provider, gemini_provider, openai_provider
from .prompt import TONES, ScriptError, build_prompt, parse_reply

PROVIDERS = {p.NAME: p for p in (anthropic_provider, openai_provider, gemini_provider)}


def provider_info() -> list:
    return [{"key": p.NAME, "label": p.LABEL, "key_url": p.KEY_URL} for p in PROVIDERS.values()]


def check_key(provider: str, api_key: str) -> dict:
    """Validate a key and return the models it can use, plus a sensible default."""
    p = _provider(provider)
    models = p.list_models(api_key)
    if not models:
        raise ScriptError("This key works, but has access to no suitable text models.")
    return {"models": models, "default": p.default_model(models)}


def write_script(topic: str, tone: str, seconds: int, *, provider: str, model: str, api_key: str) -> dict:
    """Return {"title": str, "sentences": [str, ...]} for a video of about `seconds` long."""
    topic = topic.strip()
    if not topic:
        raise ScriptError("Describe what the video should be about.")
    if not api_key:
        raise ScriptError("Add an API key in Settings to use the AI writer.")
    text = _provider(provider).generate(api_key, model, build_prompt(topic, tone, seconds))
    return parse_reply(text)


def _provider(name):
    if name not in PROVIDERS:
        raise ScriptError(f"Unknown AI provider: {name}")
    return PROVIDERS[name]


__all__ = ["PROVIDERS", "TONES", "ScriptError", "check_key", "provider_info", "write_script"]
