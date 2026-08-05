"""
Agent installer distribution (spec §7.2) — serves the compiled
`Aaditech-Agent-Setup.exe` (built by agent-installer/build-agent-installer.ps1)
to endpoint staff for one-click fleet rollout.

Deliberately PUBLIC (no auth dependency):
- The installer carries no secrets — all server values are bal:Overridable and
  injected at INSTALL time, so exposing the file is safe.
- Fleet staff / GPO / Intune must be able to grab the package without a portal
  account.

Two endpoints:
  GET /api/agent-installer/info      -> JSON metadata (available, size, filename)
  GET /api/agent-installer/download  -> the actual .exe, as an attachment

The executable is expected under `settings.installer_dir` (an env-mounted path;
see infra/). If it hasn't been built yet, both endpoints report
"installer_not_available" rather than crashing.
"""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings

router = APIRouter(prefix="/agent-installer", tags=["agent-installer"])

INSTALLER_FILENAME = "Aaditech-Agent-Setup.exe"


def installer_path() -> str:
    """Absolute path to the compiled installer (may be missing)."""
    return os.path.join(settings.installer_dir, INSTALLER_FILENAME)


def _installed() -> bool:
    path = installer_path()
    return bool(path) and os.path.isfile(path)


@router.get("")
async def installer_info():
    """Metadata for the frontend download card (availability, size)."""
    if not _installed():
        return {"available": False, "filename": INSTALLER_FILENAME, "size_bytes": 0,
                "message": "Installer not published yet. Build it with "
                           "agent-installer/build-agent-installer.ps1 and mount the output."}

    size = os.path.getsize(installer_path())
    return {
        "available": True,
        "filename": INSTALLER_FILENAME,
        "size_bytes": size,
        "size_mb": round(size / (1024 * 1024), 2),
    }


@router.get("/download")
async def download_installer():
    """Stream the installer to the requester (browser click or GPO/Intune URL)."""
    if not _installed():
        return JSONResponse({"error": "installer_not_available"}, status_code=404)

    return FileResponse(
        installer_path(),
        media_type="application/octet-stream",
        filename=INSTALLER_FILENAME,
    )