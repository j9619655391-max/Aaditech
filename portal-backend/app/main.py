"""
Aaditech Portal — Backend Entrypoint

Single API gateway in front of Wazuh, Zabbix, GLPI, MeshCentral, and
Grafana. End users and the frontend only ever talk to this service;
this service is the only thing with credentials to the backend tools.

Run locally:      uvicorn app.main:app --reload --port 8000
API docs (auto):  http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import agent_commands, cleanup_store
from app.config import settings
from app.routers import alerts, auth_sso, cleanup, dashboards, downloads, metrics, remote, tickets

# Point the persistent stores at the configured SQLite file ("" => in-memory).
# Must run before any router handler touches them.
cleanup_store.init_db(settings.db_path)
agent_commands.init_db(settings.db_path)

app = FastAPI(
    title="Aaditech IT Monitoring & Automation Platform — Portal API",
    description=(
        "Unified API gateway for security (Wazuh), infra monitoring (Zabbix), "
        "ticketing (GLPI), remote access (MeshCentral), and dashboards (Grafana)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://portal.aaditech.local"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_sso.router, prefix="")
app.include_router(alerts.router, prefix="")
app.include_router(metrics.router, prefix="")
app.include_router(tickets.router, prefix="")
app.include_router(cleanup.router, prefix="")
app.include_router(remote.router, prefix="")
app.include_router(dashboards.router, prefix="")
app.include_router(downloads.router, prefix="")


@app.get("/health")
async def health():
    """Liveness probe — used by Docker healthcheck and deployment automation."""
    return {"status": "ok", "service": "aaditech-portal-backend"}
