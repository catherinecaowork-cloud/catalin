"""阶段 B：DataStrategy 协议与运行时（literal/env/from_step + lookup/ensure，无内网）。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from playwright.sync_api import sync_playwright

from autotest_executor.data_strategy import DataStrategyError, DataStrategyResolver
from autotest_protocol import STORE_UPSERT_FLOW_ID, DataStrategy, Step
from tests.conftest import require_browser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "data-strategy"
ENV_A = FIXTURES / "env-a-orders.html"
ENV_B = FIXTURES / "env-b-orders.html"


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


def test_lookup_page_html_fixture_env_a_hits() -> None:
    """环境 A：本地 HTML 已有订单，lookup 直接命中。"""
    resolver = DataStrategyResolver({})
    value = resolver.resolve_strategy(
        DataStrategy(
            kind="lookup",
            query={
                "source": "page",
                "html_path": str(ENV_A),
                "selector": "tr.order-row[data-order-id=A-100]",
                "attr": "data-order-id",
            },
        )
    )
    assert value == "A-100"


def test_lookup_page_html_fixture_miss_is_data_strategy() -> None:
    """环境 B：目标单号不在页面 → failure=data_strategy / not_found。"""
    resolver = DataStrategyResolver({})
    with pytest.raises(DataStrategyError) as caught:
        resolver.resolve_strategy(
            DataStrategy(
                kind="lookup",
                query={
                    "source": "page",
                    "html_path": str(ENV_B),
                    "selector": "tr.order-row[data-order-id=B-200]",
                    "attr": "data-order-id",
                },
            )
        )
    err = caught.value
    assert err.kind == "not_found"
    assert err.strategy == "lookup"
    data = err.as_failure_data()
    assert data["failure"] == "data_strategy"
    assert data["failure_kind"] == "not_found"
    assert data["environmental"] is True


def test_ensure_store_creates_when_missing_then_continues() -> None:
    """环境 B 叙事：store 缺 B-200 → ensure 创建 → 再 lookup 成功。"""
    store: dict = {"order": [{"code": "B-001", "customer": "carol"}]}
    resolver = DataStrategyResolver(store=store)
    value = resolver.resolve_strategy(
        DataStrategy(
            kind="ensure",
            create_flow_id=STORE_UPSERT_FLOW_ID,
            query={
                "source": "store",
                "entity": "order",
                "match": {"code": "B-200"},
                "return_field": "code",
                "create": {"code": "B-200", "customer": "demo"},
            },
        )
    )
    assert value == "B-200"
    assert any(row.get("code") == "B-200" for row in store["order"])


def test_ensure_create_steps_handler_runs_on_miss() -> None:
    store: dict = {"sku": []}
    calls: list[str] = []

    def _create(steps: list[dict], resolver: DataStrategyResolver) -> None:
        calls.append(steps[0]["id"])
        resolver.store.setdefault("sku", []).append({"code": "SKU-NEW", "name": "新建"})

    resolver = DataStrategyResolver(store=store, create_steps_handler=_create)
    value = resolver.resolve_strategy(
        DataStrategy(
            kind="ensure",
            create_steps=[{"id": "create_sku", "action": "screenshot"}],
            query={
                "source": "store",
                "entity": "sku",
                "match": {"code": "SKU-NEW"},
                "return_field": "code",
            },
        )
    )
    assert value == "SKU-NEW"
    assert calls == ["create_sku"]


def test_lookup_api_local_hook() -> None:
    """本地 httpx mock transport，无外网。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/orders"
        return httpx.Response(
            200,
            json={"items": [{"code": "A-100", "status": "open"}, {"code": "A-101", "status": "closed"}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://test.local")
    resolver = DataStrategyResolver(base_url="http://test.local", http_client=client)
    value = resolver.resolve_strategy(
        DataStrategy(
            kind="lookup",
            query={
                "source": "api",
                "url": "/api/orders",
                "json_path": "items",
                "match": {"code": "A-100"},
                "return_field": "code",
            },
        )
    )
    assert value == "A-100"
    client.close()


def test_lookup_api_miss_is_data_strategy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://test.local"
    )
    resolver = DataStrategyResolver(base_url="http://test.local", http_client=client)
    with pytest.raises(DataStrategyError) as caught:
        resolver.resolve_strategy(
            DataStrategy(
                kind="lookup",
                query={
                    "source": "api",
                    "url": "/api/orders",
                    "json_path": "items",
                    "match": {"code": "MISSING"},
                    "return_field": "code",
                },
            )
        )
    assert caught.value.as_failure_data()["failure"] == "data_strategy"
    assert caught.value.kind == "not_found"
    client.close()


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


@pytest.mark.browser
def test_lookup_page_playwright_against_fixture() -> None:
    """绑定真实 page 时，selector 查本地 fixture DOM。"""
    require_browser()
    html = ENV_A.read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html)
            resolver = DataStrategyResolver(page=page)
            value = resolver.resolve_strategy(
                DataStrategy(
                    kind="lookup",
                    query={
                        "source": "page",
                        "selector": "tr.order-row[data-order-id='A-100']",
                        "attr": "data-order-id",
                    },
                )
            )
            assert value == "A-100"
        finally:
            browser.close()
