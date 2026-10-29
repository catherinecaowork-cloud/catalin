"""指纹必须能一路存进流程：录制 → 编译 → 保存校验。

任何一环把未知字段丢掉，回放时就永远只剩失效的候选，自愈等于没做。
"""

from __future__ import annotations

from autotest_control.domain.recordings import prepare_recorded_step
from autotest_executor.compiler import _clean_candidates
from autotest_protocol import Step

FINGERPRINT = {
    "tag": "input",
    "role": "textbox",
    "label": "国家/地区",
    "attrs": {"name": "country"},
    "grid_row": "1",
    "grid_col": "155/80A",
    "index": 0,
}

RAW = {
    "id": "s1",
    "action": "fill",
    "value": "10",
    "target": {
        "candidates": [{"kind": "css", "value": ".x"}],
        "fingerprint": FINGERPRINT,
    },
}


def test_compiler_keeps_fingerprint() -> None:
    cleaned = _clean_candidates(dict(RAW["target"]))
    assert cleaned is not None
    assert cleaned["fingerprint"] == FINGERPRINT


def test_save_sanitizer_keeps_fingerprint() -> None:
    prepared = prepare_recorded_step(dict(RAW))
    assert prepared["target"]["fingerprint"] == FINGERPRINT
    step = Step.model_validate(prepared)
    assert step.target is not None
    assert step.target.fingerprint is not None
    assert step.target.fingerprint.label == "国家/地区"
    assert step.target.fingerprint.grid_col == "155/80A"


def test_old_flow_without_fingerprint_still_valid() -> None:
    raw = {"id": "s1", "action": "click", "target": {"candidates": [{"kind": "text", "value": "保存"}]}}
    step = Step.model_validate(prepare_recorded_step(dict(raw)))
    assert step.target is not None
    assert step.target.fingerprint is None
