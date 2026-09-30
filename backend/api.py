"""The studio's JSON API. Every route here needs a signed-in user and only touches their data."""
import json

from flask import Blueprint, abort, current_app, jsonify, request, send_file

from engine import ai, catalog
from engine.backgrounds import preview_frame
from engine.cards import DEFAULT_STYLE
from engine.paths import BACKGROUNDS, FONTS
from engine.tts import available_voices

from . import db, jobs, plans
from .security import api_login_required, current_user, decrypt, encrypt

bp = Blueprint("api", __name__)


def _uid():
    return current_user()["id"]


# ---------- studio ----------

@bp.get("/api/options")
@api_login_required
def options():
    return jsonify(
        voices=[{"key": k, "label": label} for k, label in available_voices()],
        backgrounds=[{"key": b.key, "credit": b.credit, "downloaded": b.downloaded}
                     for b in catalog.videos().values()],
        music=[{"key": m.key, "downloaded": m.downloaded} for m in catalog.music().values()],
        default_style=DEFAULT_STYLE,
        tones=list(ai.TONES),
        ai_providers=[p for p in ai.provider_info() if p["key"] in _saved_keys()],
    )


@bp.post("/api/jobs")
@api_login_required
def create_job():
    data = request.get_json(force=True)
    title, body = (data.get("title") or "").strip(), (data.get("body") or "").strip()
    if not title or not body:
        return jsonify(error="Add a title and some script text."), 400
    if len(title) > 200 or len(body) > 5000:
        return jsonify(error="That script is too long for a short video."), 400
    voice = data.get("voice")
    if voice not in {k for k, _ in available_voices()}:
        return jsonify(error="Unknown voice."), 400
    if data.get("background") not in catalog.videos():
        return jsonify(error="Unknown background."), 400
    music = data.get("music")
    if music != "none" and music not in catalog.music():
        return jsonify(error="Unknown music."), 400
    use = plans.usage(current_user(), running=jobs.active(_uid()))
    if use["left"] == 0:
        return jsonify(error=f"You've used all {use['limit']} videos on your plan this month. Upgrade in "
                             "Settings, or wait until the 1st.", upgrade=True), 403
    style = data.get("style") if isinstance(data.get("style"), dict) else {}
    job_id = jobs.start(current_app.config["DATABASE_PATH"], _uid(), title, body, voice,
                        data["background"], music, style,
                        watermark=plans.WATERMARK if use["watermark"] else "")
    return jsonify(id=job_id)


@bp.get("/api/jobs/<job_id>")
@api_login_required
def job_status(job_id):
    return jsonify(jobs.get(job_id, _uid()) or abort(404))


@bp.get("/api/preview/<key>")
@api_login_required
def preview(key):
    bg = catalog.videos().get(key)
    if not bg or not bg.downloaded:
        abort(404)
    still = BACKGROUNDS / "preview" / f"{key}.jpg"
    if not still.exists():
        preview_frame(bg, still)
    return send_file(still)


@bp.get("/fonts/<name>")
def font(name):
    if name not in {"Roboto-Medium.ttf", "Roboto-Bold.ttf"}:
        abort(404)
    return send_file(FONTS / name)


# ---------- AI script writer ----------

@bp.post("/api/script")
@api_login_required
def generate_script():
    data = request.get_json(force=True)
    provider = data.get("provider")
    row = _key_row(provider)
    if not row:
        return jsonify(error="Add an API key for this AI in Settings first."), 400
    try:
        seconds = max(15, min(90, int(data.get("seconds") or 40)))
        script = ai.write_script(data.get("topic") or "", data.get("tone") or "informative", seconds,
                                 provider=provider, model=row["model"], api_key=decrypt(row["key_enc"]))
    except ai.ScriptError as exc:
        return jsonify(error=str(exc)), 400
    except ValueError:
        return jsonify(error="Length must be a number of seconds."), 400
    return jsonify(title=script["title"], body="\n".join(script["sentences"]))


# ---------- settings: AI keys ----------

def _saved_keys():
    rows = db.get().execute("SELECT provider FROM api_keys WHERE user_id = ?", (_uid(),)).fetchall()
    return {r["provider"] for r in rows}


def _key_row(provider):
    return db.get().execute("SELECT * FROM api_keys WHERE user_id = ? AND provider = ?",
                            (_uid(), provider)).fetchone()


@bp.get("/api/settings/keys")
@api_login_required
def list_keys():
    out = []
    for p in ai.provider_info():
        row = _key_row(p["key"])
        out.append({**p, "saved": bool(row), "hint": row["hint"] if row else "",
                    "model": row["model"] if row else "", "models": json.loads(row["models"]) if row else []})
    return jsonify(out)


@bp.put("/api/settings/keys/<provider>")
@api_login_required
def save_key(provider):
    if provider not in ai.PROVIDERS:
        abort(404)
    api_key = ((request.get_json(force=True) or {}).get("api_key") or "").strip()
    if len(api_key) < 20 or len(api_key) > 400 or any(c.isspace() for c in api_key):
        return jsonify(error="That doesn't look like an API key."), 400
    try:
        found = ai.check_key(provider, api_key)  # checks the key and lists its models; costs nothing
    except ai.ScriptError as exc:
        return jsonify(error=str(exc)), 400
    conn = db.get()
    conn.execute("INSERT OR REPLACE INTO api_keys (user_id, provider, key_enc, hint, model, models, updated_at) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (_uid(), provider, encrypt(api_key), api_key[-4:], found["default"],
                  json.dumps(found["models"]), db.now()))
    conn.commit()
    return list_keys()


@bp.patch("/api/settings/keys/<provider>")
@api_login_required
def choose_model(provider):
    row = _key_row(provider) or abort(404)
    model = (request.get_json(force=True) or {}).get("model")
    if model not in json.loads(row["models"]):
        return jsonify(error="That model isn't available on this key."), 400
    conn = db.get()
    conn.execute("UPDATE api_keys SET model = ?, updated_at = ? WHERE user_id = ? AND provider = ?",
                 (model, db.now(), _uid(), provider))
    conn.commit()
    return list_keys()


@bp.delete("/api/settings/keys/<provider>")
@api_login_required
def delete_key(provider):
    conn = db.get()
    conn.execute("DELETE FROM api_keys WHERE user_id = ? AND provider = ?", (_uid(), provider))
    conn.commit()
    return list_keys()
