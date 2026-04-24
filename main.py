import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth_router import auth_router
from breaches_router import breaches_router
from sitemap import build_sitemap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Breach Signal Portal")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
PORTAL_URL   = os.environ.get("PORTAL_URL", "https://web-production-54737.up.railway.app")

# SessionMiddleware must be added before CORSMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "change-me-in-production"),
    session_cookie="bs_session",
    max_age=60 * 60 * 24 * 7,  # 7 days
    https_only=True,
    same_site="lax",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
app.include_router(breaches_router)


@app.get("/")
async def root():
    return RedirectResponse("/portal/breaches")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    try:
        with open("static/robots.txt") as f:
            return f.read()
    except FileNotFoundError:
        return "User-agent: *\nAllow: /\n"


@app.get("/sitemap.xml")
async def sitemap_xml():
    path = "static/sitemap.xml"
    if os.path.exists(path):
        return FileResponse(path, media_type="application/xml")
    return PlainTextResponse("Sitemap not yet generated. Hit /generate-sitemap first.", status_code=404)


@app.get("/generate-sitemap")
async def regenerate_sitemap():
    count = build_sitemap(SUPABASE_URL, SUPABASE_KEY, PORTAL_URL, "static/sitemap.xml")
    return {"status": "ok", "urls": count, "path": "/sitemap.xml"}
