"""收编 scripts/selftest_*.py：一条 pytest 命令跑完全部自测。

逻辑仍在 scripts 里；本文件负责调度、浏览器依赖跳过、失败时打出完整输出。
后续拆边界时可逐文件把断言迁到 tests/test_*.py。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import require_browser

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "scripts").glob("selftest_*.py"))

# 需要真 Chromium 的自测
BROWSER_SELFTESTS = frozenset(
    {
        "selftest_probe.py",
        "selftest_optional_skip.py",
        "selftest_choose_fallback.py",
    }
)


def _run_script(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.mark.parametrize(
    "script",
    SCRIPTS,
    ids=lambda path: path.stem.removeprefix("selftest_"),
)
def test_selftest_script(script: Path) -> None:
    if script.name in BROWSER_SELFTESTS:
        require_browser()
    result = _run_script(script)
    if result.returncode != 0:
        detail = "\n".join(
            part for part in (result.stdout.strip(), result.stderr.strip()) if part
        )
        pytest.fail(f"{script.name} 失败 (exit {result.returncode})\n{detail}")
