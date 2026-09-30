"""ChatGPT models, via the official OpenAI SDK (Responses API)."""
import re

import openai

from .prompt import SCHEMA, SYSTEM, ScriptError, saved_key_rejected

NAME, LABEL = "openai", "ChatGPT (OpenAI)"
KEY_URL = "https://platform.openai.com/api-keys"

# The models endpoint also lists audio, image, embedding and realtime models; keep text-chat ones.
_CHAT = re.compile(r"^(gpt-\d|o\d)")
_SKIP = re.compile(r"audio|realtime|tts|transcribe|image|embedding|search|instruct|moderation|codex")


def _errors(exc):
    if isinstance(exc, openai.AuthenticationError):
        return ScriptError("OpenAI rejected this key. Check you copied all of it.")
    if isinstance(exc, openai.PermissionDeniedError):
        return ScriptError("This OpenAI key doesn't have access to that model.")
    if isinstance(exc, openai.NotFoundError):
        return ScriptError("That OpenAI model isn't available on this key. Pick another in Settings.")
    if isinstance(exc, openai.RateLimitError):
        return ScriptError("OpenAI says too many requests, or the account is out of credit.")
    if isinstance(exc, openai.APIConnectionError):
        return ScriptError("Couldn't reach OpenAI. Check your internet connection.")
    if isinstance(exc, openai.APIStatusError):
        return ScriptError(f"OpenAI returned an error ({exc.status_code}). Try again shortly.")
    return ScriptError(f"OpenAI request failed: {exc}")


def list_models(api_key: str) -> list:
    """Validates the key too. Newest first."""
    try:
        client = openai.OpenAI(api_key=api_key, max_retries=0)
        models = list(client.models.list())
    except openai.OpenAIError as exc:
        raise _errors(exc)
    chat = [m for m in models if _CHAT.match(m.id) and not _SKIP.search(m.id)]
    return [m.id for m in sorted(chat, key=lambda m: m.created, reverse=True)]


def default_model(models: list) -> str:
    """Newest full-size model; mini/nano variants only if nothing else is available."""
    full = [m for m in models if not re.search(r"mini|nano", m)]
    return (full or models)[0]


def generate(api_key: str, model: str, prompt: str) -> str:
    """Called with a key that passed check_key when saved, so a rejection means it was revoked since."""
    try:
        response = openai.OpenAI(api_key=api_key).responses.create(
            model=model,
            instructions=SYSTEM,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "video_script", "strict": True, "schema": SCHEMA}},
        )
    except openai.OpenAIError as exc:
        raise saved_key_rejected(_errors(exc), "OpenAI")
    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "refusal":
                    raise ScriptError("ChatGPT declined to write about this topic. Try rephrasing it.")
    return response.output_text
