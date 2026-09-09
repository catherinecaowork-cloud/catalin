"""P1.2 观察者协议 schema 自测。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autotest_protocol import (
    LayerRef,
    LocatorSummary,
    ObservedField,
    ObservationSnapshot,
    PageWidgetEntry,
    PageWidgetModel,
    RecordingSummary,
    infer_value_strategy,
    is_transient_component_identity,
    merge_snapshot_into_model,
    new_observe_snapshot_event,
    observation_snapshot_from_event_data,
)


def test_dropdown_field_infers_choose_any() -> None:
    strategy = infer_value_strategy(label="品牌", widget_kind="searchable_dropdown")
    assert strategy == "choose_any"


def test_code_field_infers_parameterized() -> None:
    strategy = infer_value_strategy(label="款式编码", widget_kind="text")
    assert strategy == "parameterized"


def test_size_option_text_is_not_component_identity() -> None:
    assert is_transient_component_identity("155") is True
    with pytest.raises(ValidationError):
        PageWidgetEntry(
            id="size-155",
            layer=LayerRef(kind="modal", name="新增款式"),
            display_name="155",
            widget_kind="tab",
            operation="choose",
            value_strategy="choose_any",
        )


def test_snapshot_merges_size_selector_not_sample_value() -> None:
    snapshot = ObservationSnapshot(
        trigger="form_visible",
        url="https://example.test/style/new",
        layer=LayerRef(kind="modal", name="新增款式"),
        fields=[
            ObservedField(
                label="尺码",
                widget_kind="tab",
                required=True,
                sample_options=["155", "160", "165"],
                locator=LocatorSummary(kind="label", value="尺码"),
            ),
            ObservedField(
                label="155",
                widget_kind="tab",
                sample_options=[],
            ),
        ],
    )
    model = merge_snapshot_into_model(PageWidgetModel(), snapshot, site_id="site-1")
    names = {entry.display_name for entry in model.entries}
    assert "尺码" in names
    assert "155" not in names
    size = next(entry for entry in model.entries if entry.display_name == "尺码")
    assert size.value_strategy == "choose_any"
    assert size.choose_mode == "other"


def test_recording_summary_splits_sample_and_observer_steps() -> None:
    legacy = RecordingSummary.model_validate(
        {
            "steps": [{"id": "s1", "action": "click", "label": "保存"}],
            "notes": ["ok"],
        }
    )
    assert len(legacy.sample_steps) == 1
    assert legacy.observer_steps == []
    payload = legacy.to_summary_dict()
    assert payload["sample_steps"][0]["id"] == "s1"
    assert payload["steps"][0]["id"] == "s1"


def test_observe_snapshot_event_roundtrip() -> None:
    event = new_observe_snapshot_event(
        trigger="layer_open",
        url="https://example.test/",
        layer={"kind": "modal", "name": "新增款式"},
        fields=[
            {
                "label": "品牌",
                "widget_kind": "searchable_dropdown",
                "required": True,
                "sample_options": ["Gucci", "Prada"],
            }
        ],
    )
    assert event.type == "observe.snapshot"
    parsed = observation_snapshot_from_event_data(event.data)
    assert parsed.layer.name == "新增款式"
    assert parsed.fields[0].label == "品牌"
