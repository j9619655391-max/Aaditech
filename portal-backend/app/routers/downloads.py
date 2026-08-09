"""
Agent installer distribution (spec §7.2) — serves the compiled
`Aaditech-Agent-Setup.exe` (built by agent-installer/build-agent-installer.ps1,
or pulled from GitHub Actions via the build endpoint below) to endpoint staff
for one-click fleet rollout.

Deliberately PUBLIC (no auth dependency):
- The installer carries no secrets — all server values are bal:Overridable and
  injected at INSTALL time, so exposing the file is safe.
- Fleet staff / GPO / Intune must be able to grab the package without a portal
  account.

Endpoints:
  GET  /api/agent-installer/info      -> JSON metadata (available, size, filename)
  GET  /api/agent-installer/download  -> the actual .exe, as an attachment
  POST /api/agent-installer/build     -> (CLEANUP_APPROVER) trigger a GitHub
        Actions build of the .exe and pull it into installer_dir. Requires
        GITHUB_BUILD_PAT + GITHUB_REPO configured in infra/.env.

The executable is expected under `settings.installer_dir` (an env-mounted path;
see infra/). If it hasn't been built yet, both GET endpoints report
"installer_not_available" rather than crashing.
"""
from __future__ import annotations

import io
import os
import zipfile

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.roles import require_cleanup_approver

router = APIRouter(prefix="/agent-installer", tags=["agent-installer"])

INSTALLER_FILENAME = "Aaditech-Agent-Setup.exe"
WORKFLOW = "build-agent-installer.yml"

GITHUB_API = "https://api.github.com"


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


def _gh_headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {settings.github_build_pat}",
    }


def _gh_configured() -> bool:
    return bool(settings.github_build_pat and settings.github_repo and settings.installer_dir)


async def _trigger_workflow(ref: str = "main") -> None:
    url = f"{GITHUB_API}/repos/{settings.github_repo}/actions/workflows/{WORKFLOW}/dispatches"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            headers=_gh_headers(),
            json={"ref": ref, "inputs": {"wazuh_version": "4.14.5", "zabbix_version": "7.4.3"}},
        )
    if resp.status_code == 204:
        return
    if resp.status_code in (401, 403):
        raise RuntimeError(f"GitHub rejected the PAT ({resp.status_code}) — check GITHUB_BUILD_PAT permissions (actions: read+write)")
    if resp.status_code == 404:
        raise RuntimeError(f"Workflow '{WORKFLOW}' not found in {settings.github_repo}")
    raise RuntimeError(f"GitHub workflow dispatch failed: HTTP {resp.status_code}")


async def _await_run(run_id: int, timeout: int = 600) -> None:
    """Poll a workflow run until it reaches a terminal status."""
    url = f"{GITHUB_API}/repos/{settings.github_repo}/actions/runs/{run_id}"
    import asyncio

    async with httpx.AsyncClient(timeout=15) as client:
        elapsed = 0
        while elapsed < timeout:
            resp = await client.get(url, headers=_gh_headers())
            if resp.status_code != 200:
                raise RuntimeError(f"GitHub run status failed: HTTP {resp.status_code}")
            run = resp.json()
            status = run.get("status")
            conclusion = run.get("conclusion")
            if status == "completed":
                if conclusion != "success":
                    raise RuntimeError(f"GitHub Actions build failed ({conclusion}) — see run {run.get('html_url')}")
                return
            await asyncio.sleep(10)
            elapsed += 10
        raise RuntimeError("Timed out waiting for the GitHub Actions build")


async def _download_artifact(run_id: int) -> None:
    """Download the workflow artifact zip and extract Aaditech-Agent-Setup.exe
    into installer_dir."""
    url = f"{GITHUB_API}/repos/{settings.github_repo}/actions/runs/{run_id}/artifacts"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_gh_headers())
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub artifact list failed: HTTP {resp.status_code}")
        artifacts = resp.json().get("artifacts", [])
    if not artifacts:
        raise RuntimeError("Build finished but no artifact named 'Aaditech-Agent-Setup.exe' was uploaded")

    # Prefer the newest artifact.
    artifact = artifacts[0]
    dl = f"{GITHUB_API}/repos/{settings.github_repo}/actions/artifacts/{artifact['id']}/zip"
    async with httpx.AsyncClient(timeout=120) as client:
        zip_resp = await client.get(dl, headers=_gh_headers())
        if zip_resp.status_code != 200:
            raise RuntimeError(f"GitHub artifact download failed: HTTP {zip_resp.status_code}")

    os.makedirs(settings.installer_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        for member in zf.namelist():
            if os.path.basename(member) == INSTALLER_FILENAME:
                with zf.open(member) as src, open(installer_path(), "wb") as dst:
                    dst.write(src.read())
                break
        else:
            raise RuntimeError(f"Artifact zip did not contain {INSTALLER_FILENAME}")


@router.post("/build")
async def build_installer(user: dict = Depends(require_cleanup_approver)):
    """Trigger a GitHub Actions build of Aaditech-Agent-Setup.exe and pull it
    into the installer directory. Requires GITHUB_BUILD_PAT configured by the
    setup wizard (or infra/.env)."""
    if not _gh_configured():
        return JSONResponse(
            {"error": "github_build_not_configured",
             "message": "Set GITHUB_BUILD_PAT + GITHUB_REPO in infra/.env (wizard field) to enable builds."},
            status_code=400,
        )

    # Snapshot the newest run id BEFORE dispatching, so we can wait for the
    # NEW run that our dispatch creates (workflow_dispatch returns no id).
    runs_url = f"{GITHUB_API}/repos/{settings.github_repo}/actions/workflows/{WORKFLOW}/runs"

    async def _latest_run_id() -> int | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(runs_url, params={"per_page": 1}, headers=_gh_headers())
                runs = resp.json().get("workflow_runs", [])
            return runs[0]["id"] if runs else None
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return None

    before = await _latest_run_id()
    try:
        await _trigger_workflow()
    except RuntimeError as exc:
        return JSONResponse({"error": "trigger_failed", "message": str(exc)}, status_code=502)

    # Wait for the dispatched run to show up (can take a few seconds).
    run_id = None
    for _ in range(15):
        latest = await _latest_run_id()
        if latest is not None and latest != before:
            run_id = latest
            break
        import asyncio

        await asyncio.sleep(2)

    if run_id is None:
        return JSONResponse(
            {"error": "run_lookup_failed",
             "message": "Workflow dispatched, but the new run did not appear. Check the Actions tab."},
            status_code=502,
        )

    try:
        await _await_run(run_id)
        await _download_artifact(run_id)
    except RuntimeError as exc:
        return JSONResponse({"error": "build_failed", "message": str(exc)}, status_code=502)

    return {
        "built": True,
        "run_id": run_id,
        "filename": INSTALLER_FILENAME,
        "size_bytes": os.path.getsize(installer_path()),
        "message": f"Agent installer built and pulled from GitHub Actions (run {run_id}).",
    }