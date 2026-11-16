"""裸克隆未构建 SPA 时，控制台入口应明确提示而非空白 500。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from autotest_control import main as control_main


def test_console_returns_503_when_dist_missing(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "dist" / "index.html"
    monkeypatch.setattr(control_main, "_CONSOLE_INDEX", missing)
    client = TestClient(control_main.create_app())
    response = client.get("/")
    assert response.status_code == 503
    assert "npm run build" in response.json()["detail"]
