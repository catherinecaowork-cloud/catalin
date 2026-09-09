"""录制观察快照：脱敏、去重、校验。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autotest_protocol import (
    LayerRef,
    ObservationSnapshot,
    ObservedField,
    is_transient_component_identity,
)

_MAX_SNAPSHOTS = 60
_REDACTED = "[REDACTED]"
_PASSWORD_WIDGET = "password"


def _redact_text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "")
    return text[:max_len]


def sanitize_observed_field(raw: dict[str, Any]) -> ObservedField | None:
    label = _redact_text(raw.get("label"), max_len=80).strip()
    if not label or is_transient_component_identity(label):
        return None
    widget_kind = raw.get("widget_kind") or "unknown"
    locator = raw.get("locator")
    cleaned_locator = None
    if isinstance(locator, dict) and locator.get("kind") and locator.get("value") is not None:
        cleaned_locator = {
            "kind": locator["kind"],
            "value": _redact_text(locator["value"], max_len=120),
        }
        if locator.get("name"):
            cleaned_locator["name"] = _redact_text(locator["name"], max_len=80)
    options: list[str] = []
    for item in raw.get("sample_options") or []:
        text = _redact_text(item, max_len=80).strip()
        if not text:
            continue
        if widget_kind == _PASSWORD_WIDGET:
            continue
        options.append(text)
        if len(options) >= 20:
            break
    return ObservedField(
        label=label,
        widget_kind=widget_kind,
        required=bool(raw.get("required")),
        locator=cleaned_locator,
        operation=raw.get("operation"),
        value_strategy=raw.get("value_strategy"),
        sample_options=options,
    )


def sanitize_observation_payload(raw: dict[str, Any]) -> ObservationSnapshot | None:
    fields: list[ObservedField] = []
    for item in raw.get("fields") or []:
        if not isinstance(item, dict):
            continue
        field = sanitize_observed_field(item)
        if field is None:
            continue
        if field.widget_kind == _PASSWORD_WIDGET:
            field = field.model_copy(update={"sample_options": []})
        fields.append(field)
        if len(fields) >= 80:
            break
    if not fields:
        return None
    layer_raw = raw.get("layer") if isinstance(raw.get("layer"), dict) else {}
    return ObservationSnapshot(
        trigger=raw.get("trigger") or "form_visible",
        url=_redact_text(raw.get("url"), max_len=2048),
        title=_redact_text(raw.get("title"), max_len=120) or None,
        layer=LayerRef(
            kind=layer_raw.get("kind") or "page",
            name=_redact_text(layer_raw.get("name"), max_len=80) or None,
            path=_redact_text(layer_raw.get("path"), max_len=256) or None,
        ),
        fields=fields,
        open_panel_kind=_redact_text(raw.get("open_panel_kind"), max_len=64) or None,
        seq=raw.get("seq"),
        captured_at=datetime.now(timezone.utc),
    )


def snapshot_dedupe_key(snapshot: ObservationSnapshot) -> str:
    layer = snapshot.layer
    labels = sorted(field.label for field in snapshot.fields)
    return "|".join(
        [
            snapshot.trigger,
            snapshot.url,
            layer.kind,
            layer.name or "",
            ",".join(labels[:40]),
        ]
    )
