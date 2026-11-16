"""阶段 B：DataStrategy 协议与运行时解析（无浏览器 / 无内网）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autotest_executor.data_strategy import DataStrategyError, DataStrategyResolver
from autotest_protocol import DataStrategy, Step


def test_literal_and_env_strategy() -> None:
    resolver = DataStrategyResolver({"username": "alice-a", "order_no": "A-100"})
    assert resolver.resolve_strategy(DataStrategy(kind="literal", value="fixed")) == "fixed"
    assert resolver.resolve_strategy(DataStrategy(kind="env", key="username")) == "alice-a"


def test_env_missing_is_data_strategy_not_locator() -> None:
    resolver = DataStrategyResolver({})
    with pytest.raises(DataStrategyError) as caught:
        resolver.resolve_strategy(DataStrategy(kind="env", key="missing"))
    err = caught.value
    assert err.kind == "missing_env"
    data = err.as_failure_data()
    assert data["failure"] == "data_strategy"
    assert data["failure_kind"] == "missing_env"
    assert data["environmental"] is True


def test_from_step_reads_prior_output() -> None:
    resolver = DataStrategyResolver({})
    resolver.record_step_output("read_order", {"exports": {"order_no": "B-200"}, "text": "ok"})
    assert (
        resolver.resolve_strategy(
            DataStrategy(kind="from_step", step_id="read_order", field="order_no")
        )
        == "B-200"
    )
    assert (
        resolver.resolve_strategy(DataStrategy(kind="from_step", step_id="read_order"))
        == "ok"
    )


def test_from_step_missing_reports_data_strategy() -> None:
    resolver = DataStrategyResolver({})
    with pytest.raises(DataStrategyError) as caught:
        resolver.resolve_strategy(
            DataStrategy(kind="from_step", step_id="ghost", field="x")
        )
    assert caught.value.as_failure_data()["failure"] == "data_strategy"
    assert caught.value.kind == "missing_step"


def test_lookup_and_ensure_stubs() -> None:
    resolver = DataStrategyResolver({})
    with pytest.raises(DataStrategyError) as lookup:
        resolver.resolve_strategy(
            DataStrategy(kind="lookup", query={"entity": "sku", "code": "X"})
        )
    assert lookup.value.kind == "not_implemented"
    assert lookup.value.strategy == "lookup"

    with pytest.raises(DataStrategyError) as ensure:
        resolver.resolve_strategy(
            DataStrategy(
                kind="ensure",
                query={"entity": "sku", "code": "X"},
                create_flow_id="flow-create-sku",
            )
        )
    assert ensure.value.kind == "not_implemented"
    assert ensure.value.strategy == "ensure"
    assert ensure.value.detail.get("create_flow_id") == "flow-create-sku"


def test_step_value_strategy_preferred_over_raw_value() -> None:
    step = Step(
        id="fill",
        action="fill",
        target={"candidates": [{"kind": "label", "value": "用户名"}]},
        value="should-not-win",
        value_strategy=DataStrategy(kind="env", key="username"),
    )
    resolved = DataStrategyResolver({"username": "bob"}).resolve_step_fields(step)
    assert resolved.value == "bob"


def test_template_env_still_works_without_strategy() -> None:
    step = Step(
        id="fill",
        action="fill",
        target={"candidates": [{"kind": "label", "value": "单号"}]},
        value="ORD-{{env:suffix}}",
    )
    resolved = DataStrategyResolver({"suffix": "77"}).resolve_step_fields(step)
    assert resolved.value == "ORD-77"


def test_protocol_rejects_incomplete_strategies() -> None:
    with pytest.raises(ValidationError):
        DataStrategy(kind="env")
    with pytest.raises(ValidationError):
        DataStrategy(kind="from_step")
    with pytest.raises(ValidationError):
        DataStrategy(kind="lookup")
    with pytest.raises(ValidationError):
        DataStrategy(kind="ensure", query={"a": 1})


def test_goto_accepts_value_strategy_only() -> None:
    step = Step(
        id="go",
        action="goto",
        value_strategy=DataStrategy(kind="env", key="home_path"),
    )
    assert step.value is None
    assert step.value_strategy is not None
