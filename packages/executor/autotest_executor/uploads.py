"""回放用的固定上传文件。

页面里的文件选择框给不出真实路径，所以录制不记系统对话框，
回放一律把项目里这份图片喂给 input[type=file]。
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_UPLOAD = "fixtures/uploads/ScreenShot_2026-04-16_084203_890.png"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[3]


def resolve_upload_file(value: str | None) -> Path:
    root = repo_root()
    default = root / DEFAULT_UPLOAD
    raw = (value or "").strip()
    if not raw or "fakepath" in raw.lower():
        return default
    path = Path(raw)
    if path.is_file():
        return path
    relative = root / raw
    if relative.is_file():
        return relative
    named = root / "fixtures" / "uploads" / path.name
    if named.is_file():
        return named
    return default
