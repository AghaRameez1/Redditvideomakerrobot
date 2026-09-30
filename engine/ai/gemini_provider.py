"""Gemini, via Google's official google-genai SDK."""
import re

from google import genai
from google.genai import errors, types

from .prompt import SCHEMA, SYSTEM, ScriptError, saved_key_rejected

NAME, LABEL = "gemini", "Gemini (Google)"
KEY_URL = "https://aistudio.google.com/apikey"

_SKIP = re.compile(r"embedding|image|tts|live|audio|aqa|vision|learnlm|gemma")
# Gemini's structured output supports a subset of JSON Schema; this keyword isn't needed here.
_SCHEMA = {k: v for k, v in SCHEMA.items() if k != "additionalProperties"}


def _errors(exc):
    code = getattr(exc, "code", None)
    if code in (400, 401, 403) and "API key" in str(exc):
        return ScriptError("Google rejected this key. Check you copied all of it.")
    if code == 403:
        return ScriptError("This Google key doesn't have access to that model.")
    if code == 404:
        return ScriptError("That Gemini model isn't available on this key. Pick another in Settings.")
    if code == 429:
        return ScriptError("Google says too many requests, or the free quota is used up.")
    if code:
        return ScriptError(f"Google returned an error ({code}). Try again shortly.")
    return ScriptError(f"Couldn't reach Google: {exc}")


def _version(name: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", name.split("-")[1])) if "-" in name else ()


def list_models(api_key: str) -> list:
    """Validates the key too. Newest first, 'pro' before 'flash' within a version."""
    try:
        # Keep the client in a variable: the pager fetches lazily, and a temporary client is
        # closed before it runs ("Cannot send a request, as the client has been closed").
        client = genai.Client(api_key=api_key)
        models = list(client.models.list())
    except (errors.APIError, OSError) as exc:
        raise _errors(exc)
    names = [m.name.removeprefix("models/") for m in models
             if "generateContent" in (m.supported_actions or [])]
    names = [n for n in names if n.startswith("gemini-") and not _SKIP.search(n)]
    return sorted(names, key=lambda n: (_version(n), "pro" in n, "preview" not in n), reverse=True)


def default_model(models: list) -> str:
    return models[0]


def generate(api_key: str, model: str, prompt: str) -> str:
    """Called with a key that passed check_key when saved, so a rejection means it was revoked since."""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_json_schema=_SCHEMA,
                # No tools are used; switching this off also silences an SDK warning.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
    except (errors.APIError, OSError) as exc:
        raise saved_key_rejected(_errors(exc), "Google")
    if not response.text:
        raise ScriptError("Gemini returned no script, possibly blocked by its safety filters. Try rephrasing.")
    return response.text
