"""Plans for the home page, and each user's plan, usage and upgrade request."""
from flask import Blueprint, jsonify, request

from . import db, jobs, plans
from .security import api_login_required, current_user

bp = Blueprint("billing", __name__)


@bp.get("/api/plans")
def public_plans():
    """No sign-in: the home page's pricing section reads this."""
    return jsonify(plans=[{"key": k, **p} for k, p in plans.all_plans().items()], yearly_months=plans.YEARLY_MONTHS)


@bp.get("/api/billing")
@api_login_required
def billing():
    user = current_user()
    return jsonify(plan=plans.plan_of(user), usage=plans.usage(user, running=jobs.active(user["id"])),
                   plans=[{"key": k, **p} for k, p in plans.all_plans().items()],
                   request=plans.pending_request(user["id"]))


@bp.post("/api/billing/request")
@api_login_required
def request_upgrade():
    user = current_user()
    data = request.get_json(force=True) or {}
    plan, period = data.get("plan"), data.get("period") or "monthly"
    if plan not in plans.all_plans() or plan == "free" or period not in ("monthly", "yearly"):
        return jsonify(error="Pick a paid plan and monthly or yearly billing."), 400
    if plan == user["plan"]:
        return jsonify(error="You're already on that plan."), 400
    conn = db.get()
    conn.execute("UPDATE plan_requests SET status = 'cancelled', decided_at = ? WHERE user_id = ? "
                 "AND status = 'pending'", (db.now(), user["id"]))  # one open request at a time
    conn.execute("INSERT INTO plan_requests (user_id, plan, period, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                 (user["id"], plan, period, db.now()))
    conn.commit()
    return billing()


@bp.delete("/api/billing/request")
@api_login_required
def cancel_request():
    conn = db.get()
    conn.execute("UPDATE plan_requests SET status = 'cancelled', decided_at = ? WHERE user_id = ? AND status = 'pending'",
                 (db.now(), current_user()["id"]))
    conn.commit()
    return billing()
