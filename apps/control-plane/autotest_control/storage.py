"""本地产物清理：截图、录像只留最近若干次运行。"""

from __future__ import annotations

import shutil
from pathlib import Path

from autotest_control.settings import settings


def prune_run_dirs(root: Path, keep: int) -> None:
    """按修改时间保留最新 keep 个运行目录。keep<=0 表示不自动删。"""
    if keep <= 0 or not root.is_dir():
        return
    dirs = [path for path in root.iterdir() if path.is_dir()]
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for path in dirs[keep:]:
        shutil.rmtree(path, ignore_errors=True)


def wipe_run_dirs(root: Path) -> None:
    """执行器工作区只留身份文件，运行目录全部删掉。"""
    if not root.is_dir():
        return
    for path in root.iterdir():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def prune_retained_runs() -> None:
    keep = int(getattr(settings, "artifact_keep_runs", 5))
    prune_run_dirs(settings.artifacts_dir, keep)
    for name in ("worker", "worker-ui", "worker-headless"):
        wipe_run_dirs(settings.var_dir / name)
