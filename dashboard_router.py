"""
Dashboard router — mounts at /portal/dashboard
Add to your main app with:  app.include_router(dashboard_router)
"""

import os
import logging
from datetime import datetime, timezone

import requests as http
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger(__name__)

dashboard_router = APIRouter()

# Adjust path if your templates folder is elsewhere
_base = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(_base, "templates"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

PLAN_LABELS = {
    "starter":      "Starter",
    "growth":       "Growth",
    "professional": "Professional",
    "enterprise":   "Enterprise",
}


def _get_subscription(user_id: str) -> dict | None:
    """Fetch the user's active subscription from Supabase via REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        resp = http.get(
            f"{SUPABASE_URL}/rest/v1/subscriptions",
            headers={
                "apikey":        SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={
                "user_id": f"eq.{user_id}",
                "order":   "created_at.desc",
                "limit":   "1",
                "select":  "plan,status,current_period_end",
            },
            timeout=5,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("Could not fetch subscription for %s: %s", user_id, exc)
        return None


def _format_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%-d %b %Y")          # e.g. "3 May 2026"
    except Exception:
        return None


@dashboard_router.get("/portal/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session_id: str | None = None):
    # ── Auth check ────────────────────────────────────────────────────────
    # Reads user_id and email from the existing session (set by your auth routes)
    user_id = request.session.get("user_id")
    email   = request.session.get("email")

    if not user_id:
        return RedirectResponse(
            url=f"/auth/login?next=http://{request.headers.get('host', '')}/portal/dashboard",
            status_code=302,
        )

    # ── Subscription data ─────────────────────────────────────────────────
    sub = _get_subscription(user_id)

    plan_key    = (sub or {}).get("plan", "starter")
    status      = (sub or {}).get("status", "active")
    period_end  = _format_date((sub or {}).get("current_period_end"))
    plan_display = PLAN_LABELS.get(plan_key, plan_key.title())

    # ── Render ────────────────────────────────────────────────────────────
    return templates.TemplateResponse("dashboard.html", {
        "request":       request,
        "email":         email or "",
        "plan_display":  plan_display,
        "status":        status,
        "period_end":    period_end,
        "billing_period": None,          # extend later if needed
        "new_subscriber": bool(session_id),   # True when arriving from Stripe
    })
