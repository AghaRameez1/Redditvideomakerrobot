"""Claude, via the official Anthropic SDK."""
import anthropic

from .prompt import SCHEMA, SYSTEM, ScriptError, saved_key_rejected

NAME, LABEL = "anthropic", "Claude (Anthropic)"
KEY_URL = "https://console.anthropic.com/settings/keys"

# Offered models, best first. Only these are listed, because request options differ per model.
MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"]
# Models that accept effort and server-side refusal fallback ("default" form).
_MODERN = {"claude-opus-5-5", "claude-sonnet-5-5"}


def _errors(exc):
    if isinstance(exc, anthropic.AuthenticationError):
        return ScriptError("Anthropic rejected this key. Check you copied all of it.")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return ScriptError("This Anthropic key doesn't have access to that model.")
    if isinstance(exc, anthropic.RateLimitError):
        return ScriptError("Anthropic says too many requests. Wait a moment and try again.")
    if isinstance(exc, anthropic.APIConnectionError):
        return ScriptError("Couldn't reach Anthropic. Check your internet connection.")
    if isinstance(exc, anthropic.APIStatusError):
        return ScriptError(f"Anthropic returned an error ({exc.status_code}). Try again shortly.")
    return ScriptError(f"Anthropic request failed: {exc}")


def list_models(api_key: str) -> list:
    """Validates the key too: listing models is free."""
    try:
        client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        available = {m.id for m in client.models.list(limit=100)}
    except anthropic.AnthropicError as exc:
        raise _errors(exc)
    return [m for m in MODELS if m in available] or MODELS[:1]


def default_model(models: list) -> str:
    return models[0]


def generate(api_key: str, model: str, prompt: str) -> str:
    """Called with a key that passed check_key when saved, so a rejection means it was revoked since."""
    extra = {}
    if model in _MODERN:
        extra = {"output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                 # If a safety classifier declines, retry on Anthropic's recommended fallback model.
                 "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    else:
        extra = {"output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}}
    try:
        response = anthropic.Anthropic(api_key=api_key).beta.messages.create(
            model=model, max_tokens=16000, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}], **extra)
    except anthropic.AnthropicError as exc:
        raise saved_key_rejected(_errors(exc), "Anthropic")
    if response.stop_reason == "refusal":
        raise ScriptError("Claude declined to write about this topic. Try rephrasing it.")
    if response.stop_reason == "max_tokens":
        raise ScriptError("The script came back cut off. Try a shorter length.")
    return next((b.text for b in response.content if b.type == "text"), "")
