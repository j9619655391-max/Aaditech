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