"""日闸夹具：不依赖内网/浏览器，验证退出码语义。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "ci_daily_gate.py"


def _run_fixture(mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--fixture", mode],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_broken_active_flow_fails() -> None:
    result = _run_fixture("broken")
    assert result.returncode != 0
    assert "夹具-故意失败" in result.stdout
    assert "FAIL" in result.stdout


def test_fixture_ok_passes() -> None:
    result = _run_fixture("ok")
    assert result.returncode == 0
    assert "夹具-应通过" in result.stdout
    assert "夹具-草稿" not in result.stdout


def test_fixture_empty_active_fails() -> None:
    result = _run_fixture("empty")
    assert result.returncode != 0
    assert "没有可跑的流程" in result.stderr


def test_run_gate_unit_select_and_timeout() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from ci_daily_gate import FixtureGateClient, run_gate, select_active

    flows = [
        {"id": "1", "name": "a", "status": "active"},
        {"id": "2", "name": "b", "status": "draft"},
        {"id": "3", "name": "c", "status": "golden"},
    ]
    assert [f["id"] for f in select_active(flows)] == ["1"]

    code, results = run_gate(FixtureGateClient("broken"), poll_seconds=0.01, timeout_seconds=30)
    assert code == 1
    assert any(r.status == "failed" for r in results)
