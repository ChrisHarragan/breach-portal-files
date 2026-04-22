import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth_router import auth_router
from breaches_router import breaches_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Breach Signal Portal")

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
