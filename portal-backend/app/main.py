"""
Aaditech Portal — Backend Entrypoint

Single API gateway in front of Wazuh, Zabbix, GLPI, MeshCentral, and
Grafana. End users and the frontend only ever talk to this service;
this service is the only thing with credentials to the backend tools.

Run locally:      uvicorn app.main:app --reload --port 8000
API docs (auto):  http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app import agent_commands, cleanup_store, users
from app.config import settings
from app.routers import (
    alerts,
    auth_local,
    auth_sso,
    cleanup,
    dashboards,
    downloads,
    metrics,
    remote,
    setup,
    system,
    tickets,
)
from app.ilm import start_ilm_background_task

# Point the persistent stores at the configured SQLite file ("" => in-memory).
# Must run before any router handler touches them.
cleanup_store.init_db(settings.db_path)
agent_commands.init_db(settings.db_path)
users.init_db(settings.db_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Finding 2.8: the ILM scheduler (purge-expired on a timer) was documented
    # in the spec/docs but never actually ran. Start it as a background task on
    # the portal process. Disable via AADITECH_ILM_DISABLED=1 (tests/dev).
    ilm_task = start_ilm_background_task()
    yield
    if ilm_task is not None:
        ilm_task.cancel()


app = FastAPI(
    title="Aaditech IT Monitoring & Automation Platform — Portal API",
    description=(
        "Unified API gateway for security (Wazuh), infra monitoring (Zabbix), "
        "ticketing (GLPI), remote access (MeshCentral), and dashboards (Grafana)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://portal.aaditech.local"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_sso.router, prefix="")
app.include_router(auth_local.router, prefix="")
app.include_router(setup.router, prefix="")
app.include_router(alerts.router, prefix="")
app.include_router(metrics.router, prefix="")
app.include_router(tickets.router, prefix="")
app.include_router(cleanup.router, prefix="")
app.include_router(remote.router, prefix="")
app.include_router(dashboards.router, prefix="")
app.include_router(downloads.router, prefix="")
app.include_router(system.router, prefix="")


# ---------------------------------------------------------------------------
# Setup wizard page — served by the temporary bootstrap service (SETUP_MODE)
# ---------------------------------------------------------------------------


@app.get("/setup", include_in_schema=False)
async def setup_page():
    if not settings.setup_mode:
        return RedirectResponse(url="/login")
    return FileResponse(setup.SETUP_HTML, media_type="text/html")


@app.get("/", include_in_schema=False)
async def root():
    if settings.setup_mode:
        return RedirectResponse(url="/setup")
    return {"service": "aaditech-portal-backend", "status": "ok"}


@app.get("/health")
async def health():
    """Liveness probe — used by Docker healthcheck and deployment automation."""
    return {"status": "ok", "service": "aaditech-portal-backend"}
