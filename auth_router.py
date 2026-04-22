"""
Auth router — magic link login via Supabase, server-side sessions.

Routes:
  GET  /auth/login       — show email form
  POST /auth/login       — send magic link
  GET  /auth/callback    — landing page after magic link click (JS reads hash)
  POST /auth/session     — verify token, write session, return redirect URL
  GET  /auth/logout      — clear session, redirect to login
"""

import logging
import os

import requests as http
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger(__name__)

auth_router = APIRouter()

_base      = os.path.dirname(__file__)
templates  = Jinja2Templates(directory=os.path.join(_base, "templates"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
PORTAL_URL   = os.environ.get("PORTAL_URL", "").rstrip("/")

ALLOWED_PLANS = {"growth", "professional"}


def _supa_headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
    }


def _get_supabase_user(access_token: str) -> dict | None:
    """Return Supabase auth user dict for the given access token, or None."""
    r = http.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )
    if r.ok:
        return r.json()
    log.warning("get_user failed %s: %s", r.status_code, r.text[:200])
    return None


def _get_plan(user_id: str) -> str | None:
    """
    Query public.subscriptions for the user's active plan.
    Returns plan string or None if no active subscription found.
    """
    r = http.get(
        f"{SUPABASE_URL}/rest/v1/subscriptions",
        headers=_supa_headers(),
        params={
            "user_id": f"eq.{user_id}",
            "status":  "eq.active",
            "select":  "plan",
            "limit":   "1",
        },
        timeout=10,
    )
    if not r.ok:
        log.warning("get_plan failed %s: %s", r.status_code, r.text[:200])
        return None
    rows = r.json()
    if isinstance(rows, list) and rows:
        return rows[0].get("plan")
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/portal/breaches")
    return templates.TemplateResponse("login.html", {"request": request, "sent": False})


@auth_router.post("/auth/login", response_class=HTMLResponse)
async def send_magic_link(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    redirect_to = f"{PORTAL_URL}/auth/callback"

    r = http.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers=_supa_headers(),
        json={
            "type":  "magiclink",
            "email": email,
            "options": {"redirect_to": redirect_to},
        },
        timeout=10,
    )
    if not r.ok:
        log.warning("Magic link failed for %s: %s %s", email, r.status_code, r.text[:300])
        return templates.TemplateResponse("login.html", {
            "request": request,
            "sent":    False,
            "error":   "Could not send login link. Please try again.",
        })

    log.info("Magic link sent to %s", email)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "sent":    True,
        "email":   email,
    })


@auth_router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """Renders callback.html — JS reads the hash fragment and POSTs the token."""
    return templates.TemplateResponse("callback.html", {"request": request})


@auth_router.post("/auth/session")
async def create_session(request: Request):
    """
    Receive access_token from callback JS, verify it with Supabase,
    look up subscription plan, store in session.
    """
    body = await request.json()
    access_token = (body.get("access_token") or "").strip()

    if not access_token:
        return JSONResponse({"error": "missing access_token"}, status_code=400)

    user = _get_supabase_user(access_token)
    if not user:
        return JSONResponse({"error": "invalid token"}, status_code=401)

    user_id = user.get("id", "")
    email   = user.get("email", "")
    plan    = _get_plan(user_id) or "starter"

    request.session["user"] = {
        "id":    user_id,
        "email": email,
        "plan":  plan,
    }
    log.info("Session created: %s  plan=%s", email, plan)
    return JSONResponse({"redirect": "/portal/breaches"})


@auth_router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)
