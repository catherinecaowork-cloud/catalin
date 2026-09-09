from __future__ import annotations

from typing import Any

from autotest_control.deps import SENSITIVE_HEADER


def redact(value: Any) -> Any:
    """事件与产物脱敏：凭证值不进日志、不进报告。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and SENSITIVE_HEADER.match(key):
                out[key] = "***"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
