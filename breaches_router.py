"""
Breach search router — public, no auth required.
Mounts at /portal/breaches via:  app.include_router(breaches_router)
"""

import csv
import io
import logging
import os
from datetime import date, timedelta

import requests as http
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

log = logging.getLogger(__name__)

breaches_router = APIRouter()

_base = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(_base, "templates"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

PAGE_SIZE = 50

INDUSTRIES = [
    "Education", "Energy", "Financial", "Financial Services", "Government",
    "Healthcare", "Insurance", "Legal", "Manufacturing", "Media",
    "Non-profit", "Retail", "Technology", "Telecommunications", "Transportation",
]

COUNTRIES = [
    "Australia", "Brazil", "Canada", "China", "France", "Germany", "India",
    "International/Global", "Israel", "Japan", "Russia", "Singapore",
    "South Korea", "Spain", "Sweden", "United Kingdom", "United States",
]

SELECT_COLS = (
    "id,company_name,date_reported,records_affected,records_affected_range,"
    "industry_primary,headquarters_country,severity_score,"
    "data_types_exposed,primary_incident_type,breach_id"
)

EXPORT_COLS = [
    "company_name", "date_reported", "records_affected", "records_affected_range",
    "industry_primary", "headquarters_country", "severity_score",
    "data_types_exposed", "primary_incident_type",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _supa_headers(count: bool = False) -> dict:
    h = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    if count:
        h["Prefer"] = "count=exact"
    return h


def _build_params(q: str, industry: str, country: str,
                  date_from: str, date_to: str, severity_min: int,
                  limit: int, offset: int, select: str) -> dict:
    params = {
        "select": select,
        "order":  "date_reported.desc.nullslast",
        "limit":  str(limit),
        "offset": str(offset),
    }
    if q:
        params["company_name"] = f"ilike.*{q}*"
    if industry:
        params["industry_primary"] = f"eq.{industry}"
    if country:
        params["headquarters_country"] = f"eq.{country}"
    if date_from:
        params["date_reported"] = f"gte.{date_from}"
    if date_to:
        if date_from:
            params["and"] = f"(date_reported.gte.{date_from},date_reported.lte.{date_to})"
            del params["date_reported"]
        else:
            params["date_reported"] = f"lte.{date_to}"
    if severity_min and severity_min > 1:
        params["severity_score"] = f"gte.{severity_min}"
    return params


def _query_breaches(params: dict, count: bool = False):
    r = http.get(
        f"{SUPABASE_URL}/rest/v1/breaches",
        headers=_supa_headers(count=count),
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    total = None
    if count:
        cr = r.headers.get("content-range", "")
        if "/" in cr:
            total = int(cr.split("/")[1])
    return r.json(), total


# ---------------------------------------------------------------------------
# Search route
# ---------------------------------------------------------------------------

ALLOWED_PLANS = {"growth", "professional"}


@breaches_router.get("/portal/breaches", response_class=HTMLResponse)
async def breach_search(
    request:      Request,
    q:            str = "",
    industry:     str = "",
    country:      str = "",
    date_from:    str = "",
    date_to:      str = "",
    severity_min: int = 1,
    page:         int = 1,
):
    # ── Auth gate ──────────────────────────────────────────────────────────
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    if user.get("plan", "").lower() not in ALLOWED_PLANS:
        return templates.TemplateResponse("upgrade.html", {
            "request": request,
            "user":    user,
        })
    # ───────────────────────────────────────────────────────────────────────

    page   = max(1, page)
    offset = (page - 1) * PAGE_SIZE

    rows, total = [], 0
    error = None

    try:
        params = _build_params(
            q, industry, country, date_from, date_to, severity_min,
            limit=PAGE_SIZE, offset=offset, select=SELECT_COLS,
        )
        rows, total = _query_breaches(params, count=True)
        total = total or 0
    except Exception as exc:
        log.error("Breach search failed: %s", exc)
        error = "Search unavailable — please try again."

    total_pages = max(1, -(-total // PAGE_SIZE))

    return templates.TemplateResponse("breaches.html", {
        "request":      request,
        "rows":         rows,
        "total":        total,
        "page":         page,
        "total_pages":  total_pages,
        "page_size":    PAGE_SIZE,
        "error":        error,
        "q":            q,
        "industry":     industry,
        "country":      country,
        "date_from":    date_from,
        "date_to":      date_to,
        "severity_min": severity_min,
        "industries":   INDUSTRIES,
        "countries":    COUNTRIES,
        "user":         user,
    })


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@breaches_router.get("/portal/breaches/export")
async def breach_export(
    request:      Request,
    q:            str = "",
    industry:     str = "",
    country:      str = "",
    date_from:    str = "",
    date_to:      str = "",
    severity_min: int = 1,
):
    params = _build_params(
        q, industry, country, date_from, date_to, severity_min,
        limit=5000, offset=0,
        select=",".join(EXPORT_COLS),
    )

    try:
        rows, _ = _query_breaches(params, count=False)
    except Exception as exc:
        log.error("Export failed: %s", exc)
        return HTMLResponse("Export failed. Please try again.", status_code=500)

    def _stream():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=EXPORT_COLS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        yield buf.getvalue()

    filename = f"breach-signal-export-{date.today()}.csv"
    return StreamingResponse(
        _stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Breach detail route
# ---------------------------------------------------------------------------

DETAIL_COLS = (
    "id,company_name,date_reported,severity_score,primary_incident_type,"
    "incident_summary,records_affected,industry_primary,headquarters_country,"
    "data_types_exposed,source_url"
)


@breaches_router.get("/breaches/{breach_slug}", response_class=HTMLResponse)
async def breach_detail(request: Request, breach_slug: str):
    breach_id = breach_slug.split("-")[0]
    log.info("detail: slug=%r  extracted_id=%r", breach_slug, breach_id)

    resp = http.get(
        f"{SUPABASE_URL}/rest/v1/breaches",
        headers=_supa_headers(),
        params={"id": f"eq.{breach_id}", "select": DETAIL_COLS},
        timeout=10,
    )
    log.info("detail: supabase status=%s body=%r", resp.status_code, resp.text[:300])
    rows = resp.json() if resp.ok else []
    if not isinstance(rows, list) or not rows:
        log.warning("detail: no rows found for id=%r", breach_id)
        return HTMLResponse("<h1>404 – Breach not found</h1>", status_code=404)

    breach = rows[0]
    raw_types = breach.get("data_types_exposed") or ""
    breach["data_types_list"] = [
        t.strip()
        for t in raw_types.replace("|", ",").split(",")
        if t.strip()
    ]
    breach["source_urls_list"] = [
        u.strip()
        for u in (breach.get("source_url") or "").split("\n")
        if u.strip()
    ]

    since = (date.today() - timedelta(days=90)).isoformat()
    rel_resp = http.get(
        f"{SUPABASE_URL}/rest/v1/breaches",
        headers=_supa_headers(),
        params={
            "company_name": f"eq.{breach['company_name']}",
            "date_reported": f"gte.{since}",
            "id": f"neq.{breach_id}",
            "select": "id,company_name,date_reported,severity_score,primary_incident_type",
            "limit": "5",
        },
        timeout=10,
    )
    related = rel_resp.json() if rel_resp.ok else []

    summary = breach.get("incident_summary") or ""
    meta_desc = summary[:150].rstrip() + ("…" if len(summary) > 150 else "")
    page_title = (
        f"{breach['company_name']} Data Breach"
        f" – {breach.get('date_reported', '')} | Breach Signal"
    )

    return templates.TemplateResponse("breach_detail.html", {
        "request":    request,
        "breach":     breach,
        "related":    related,
        "page_title": page_title,
        "meta_desc":  meta_desc,
        "canonical":  str(request.url),
    })
