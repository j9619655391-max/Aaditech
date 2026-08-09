"""
Tests for the public agent-installer distribution endpoints (§7.2).
Covers both states:
  - installer not mounted  -> 404 on download, available=False in info
  - installer present      -> 200 file download, correct size in info
Run with: pytest tests/test_downloads.py
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_info_reports_unavailable_when_not_published(monkeypatch):
    # Point installer_dir at an empty temp dir so "available" is false.
    monkeypatch.setattr("app.routers.downloads.settings.installer_dir", "/nonexistent")
    resp = client.get("/agent-installer")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["filename"] == "Aaditech-Agent-Setup.exe"


def test_download_returns_404_when_not_published(monkeypatch):
    monkeypatch.setattr("app.routers.downloads.settings.installer_dir", "/nonexistent")
    resp = client.get("/agent-installer/download")
    assert resp.status_code == 404
    assert resp.json()["error"] == "installer_not_available"


def test_info_and_download_with_real_file(tmp_path, monkeypatch):
    fake = tmp_path / "Aaditech-Agent-Setup.exe"
    fake.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB so size_mb rounds to > 0
    monkeypatch.setattr("app.routers.downloads.settings.installer_dir", str(tmp_path))

    info = client.get("/agent-installer")
    assert info.status_code == 200
    body = info.json()
    assert body["available"] is True
    assert body["size_bytes"] == os.path.getsize(fake)
    assert body["size_mb"] > 0

    dl = client.get("/agent-installer/download")
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].startswith('attachment; filename="Aaditech-Agent-Setup.exe"')
    assert dl.content == b"x" * (2 * 1024 * 1024)


def test_download_is_public_no_auth_required(tmp_path, monkeypatch):
    # No Authorization header → must still return the file (fleet staff
    # without portal accounts can grab it). 200, not 403.
    fake = tmp_path / "Aaditech-Agent-Setup.exe"
    fake.write_bytes(b"x")
    monkeypatch.setattr("app.routers.downloads.settings.installer_dir", str(tmp_path))

    resp = client.get("/agent-installer/download")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /agent-installer/build — GitHub Actions build & pull (admin only)
# ---------------------------------------------------------------------------

def _auth_headers(roles):
    from app.auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token('test-user', roles)}"}


def test_build_requires_authentication(monkeypatch):
    resp = client.post("/agent-installer/build")
    assert resp.status_code in (401, 403)


def test_build_requires_approver_role(monkeypatch):
    resp = client.post("/agent-installer/build", headers=_auth_headers(["viewer"]))
    assert resp.status_code == 403


def test_build_reports_not_configured(monkeypatch):
    monkeypatch.setattr("app.routers.downloads.settings.github_build_pat", "")
    resp = client.post("/agent-installer/build", headers=_auth_headers(["cleanup_approver"]))
    assert resp.status_code == 400
    assert resp.json()["error"] == "github_build_not_configured"


def test_build_full_flow_mocked(tmp_path, monkeypatch):
    """Config present -> workflow dispatched -> run completes -> artifact is
    extracted into installer_dir."""
    import httpx
    from app.routers import downloads

    installers = tmp_path / "installers"
    installers.mkdir()
    monkeypatch.setattr("app.routers.downloads.settings.github_build_pat", "github_pat_x")
    monkeypatch.setattr("app.routers.downloads.settings.github_repo", "acme/repo")
    monkeypatch.setattr("app.routers.downloads.settings.installer_dir", str(installers))

    exe_bytes = b"MZ fake exe"
    artifact_zip = __import__("io").BytesIO()
    with __import__("zipfile").ZipFile(artifact_zip, "w") as zf:
        zf.writestr("Aaditech-Agent-Setup.exe", exe_bytes)
    artifact_zip.seek(0)

    class _Resp:
        def __init__(self, status_code=200, content=b"", json=None):
            self.status_code = status_code
            self.content = content
            self._json = json or {}

        def json(self):
            return self._json

    calls = {"runs_listed": 0}

    async def fake_post(url, **kwargs):
        assert url.endswith("/dispatches")
        return _Resp(204)

    async def fake_get(url, params=None, **kwargs):
        if "/artifacts/" in url:
            return _Resp(200, content=artifact_zip.getvalue())
        if url.endswith("/artifacts"):
            return _Resp(json={"artifacts": [{"id": 7, "name": "Aaditech-Agent-Setup.exe"}]})
        if "/runs/55" in url:  # run status polling
            return _Resp(json={"status": "completed", "conclusion": "success"})
        if url.endswith("/runs"):
            # First call = "before" snapshot (old run), then the new run appears.
            calls["runs_listed"] += 1
            run_id = 54 if calls["runs_listed"] == 1 else 55
            return _Resp(json={"workflow_runs": [{"id": run_id}]})
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(downloads.httpx.AsyncClient, "post", staticmethod(fake_post))
    monkeypatch.setattr(downloads.httpx.AsyncClient, "get", staticmethod(fake_get))

    resp = client.post("/agent-installer/build", headers=_auth_headers(["cleanup_approver"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["built"] is True
    assert body["run_id"] == 55
    assert (installers / "Aaditech-Agent-Setup.exe").read_bytes() == exe_bytes