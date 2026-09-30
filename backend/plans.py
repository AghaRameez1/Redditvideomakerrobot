"""Plans, monthly video limits and upgrade requests.

There's no payment provider yet: users ask to upgrade from Settings, and an admin or manager
approves the request on the admin page, which switches their plan. Prices and limits have
defaults below and can be changed on the admin page. Managers and admins aren't limited.
"""
import json
from datetime import datetime, timezone

from . import db, site_settings
from .security import has_role

WATERMARK = "Made with Script Studio"
YEARLY_MONTHS = 10  # a year costs 10 months: 2 months free
DEFAULTS = {
    "free": {"name": "Free", "monthly": 0, "videos": 3, "watermark": True},
    "creator": {"name": "Creator", "monthly": 9, "videos": 60, "watermark": False},
    "pro": {"name": "Pro", "monthly": 24, "videos": 300, "watermark": False},
}
ORDER = tuple(DEFAULTS)
SETTING = "plans"


def all_plans() -> dict:
    """{key: {"name", "monthly", "yearly", "videos", "watermark"}} with the admin's changes applied."""
    try:
        saved = json.loads(site_settings.get_value(SETTING) or "{}")
    except ValueError:
        saved = {}
    out = {}
    for key in ORDER:
        plan = {**DEFAULTS[key], **{k: v for k, v in saved.get(key, {}).items() if k in DEFAULTS[key]}}
        plan["yearly"] = plan["monthly"] * YEARLY_MONTHS
        out[key] = plan
    return out


def save_plans(changes: dict, user_id: int) -> str:
    """Validate and store prices / limits. Returns an error message, or "" when saved."""
    clean = {}
    for key in ORDER:
        given = changes.get(key) or {}
        try:
            monthly = round(float(given.get("monthly", DEFAULTS[key]["monthly"])), 2)
            videos = int(given.get("videos", DEFAULTS[key]["videos"]))
        except (TypeError, ValueError):
            return "Prices and video limits must be numbers."
        if monthly < 0 or not 1 <= videos <= 100000:
            return "Use a price of 0 or more and a limit between 1 and 100,000 videos."
        name = str(given.get("name") or DEFAULTS[key]["name"]).strip()[:30]
        clean[key] = {"name": name, "monthly": monthly, "videos": videos,
                      "watermark": bool(given.get("watermark", DEFAULTS[key]["watermark"]))}
    if clean["free"]["monthly"] != 0:
        return "The Free plan has to stay at $0."
    site_settings.set_value(SETTING, json.dumps(clean), user_id)
    return ""


def month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def next_month_start() -> str:
    now = datetime.now(timezone.utc)
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc).isoformat(timespec="seconds")


def used_this_month(user_id: int) -> int:
    """Videos rendered since the 1st (UTC). Deleting a video doesn't give the slot back."""
    return db.get().execute("SELECT COUNT(*) FROM renders WHERE user_id = ? AND julianday(created_at) >= "
                            "julianday(?)", (user_id, month_start())).fetchone()[0]


def plan_of(user) -> dict:
    plans = all_plans()
    return {"key": user["plan"] if user["plan"] in plans else "free",
            **plans.get(user["plan"], plans["free"])}


def usage(user, running: int = 0) -> dict:
    """{"used", "limit" (None = unlimited), "left", "resets_at", "watermark", "staff"}."""
    staff = has_role(user, "manager")
    plan = plan_of(user)
    used = used_this_month(user["id"]) + running
    limit = None if staff else plan["videos"]
    return {"used": used, "limit": limit, "left": None if limit is None else max(0, limit - used),
            "resets_at": next_month_start(), "watermark": plan["watermark"] and not staff, "staff": staff}


def pending_request(user_id: int):
    row = db.get().execute("SELECT id, plan, period, created_at FROM plan_requests WHERE user_id = ? "
                           "AND status = 'pending' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    return dict(row) if row else None
