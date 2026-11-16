"""运行时数据策略解析。

失败一律归为 data_strategy，不得冒充 locator / TargetNotFound。

lookup：page（CSS / 本地 HTML）· api（HTTP JSON）· store（内存实体表）
ensure：lookup 未命中 → 跑 create_steps / create_flow_id → 再 lookup
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urljoin

import httpx

from autotest_executor.variables import VariableResolutionError, VariableResolver
from autotest_protocol import DataStrategy, Step
from autotest_protocol.data_strategy import STORE_UPSERT_FLOW_ID


class DataStrategyError(Exception):
    """数据策略失败（缺 key、查无数据、创建后仍无等）。"""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        strategy: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind  # missing_env | missing_step | not_found | not_implemented | invalid
        self.strategy = strategy
        self.detail = detail or {}

    def as_failure_data(self) -> dict[str, Any]:
        return {
            "failure": "data_strategy",
            "failure_kind": self.kind,
            "strategy": self.strategy,
            "environmental": True,
            **self.detail,
        }


class PageLike(Protocol):
    """Playwright Page 的最小表面，便于测试注入。"""

    def locator(self, selector: str) -> Any: ...


CreateFlowHandler = Callable[[DataStrategy, "DataStrategyResolver"], None]
CreateStepsHandler = Callable[[list[dict[str, Any]], "DataStrategyResolver"], None]


class _ElementCollector(HTMLParser):
    """极简 HTML 收集器：支持 tag / .class / #id / [attr] / [attr=value] 子集。"""

    def __init__(self, wanted_tag: str | None, class_name: str | None, elem_id: str | None,
                 attr_filters: list[tuple[str, str | None]]) -> None:
        super().__init__()
        self.wanted_tag = (wanted_tag or "").lower() or None
        self.class_name = class_name
        self.elem_id = elem_id
        self.attr_filters = attr_filters
        self.matches: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v if v is not None else "") for k, v in attrs}
        node = {"tag": tag.lower(), "attrs": attr_map, "text": ""}
        self._stack.append(node)
        if self._matches(node):
            self.matches.append(node)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1]["tag"] == tag.lower():
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"] += data

    def _matches(self, node: dict[str, Any]) -> bool:
        if self.wanted_tag and node["tag"] != self.wanted_tag:
            return False
        attrs: dict[str, str] = node["attrs"]
        if self.elem_id is not None and attrs.get("id") != self.elem_id:
            return False
        if self.class_name is not None:
            classes = attrs.get("class", "").split()
            if self.class_name not in classes:
                return False
        for key, expected in self.attr_filters:
            if key not in attrs:
                return False
            if expected is not None and attrs.get(key) != expected:
                return False
        return True


_SELECTOR_ATTR = re.compile(r"\[([^\]]+)\]")
_SELECTOR_ID = re.compile(r"#([A-Za-z_][\w-]*)")
_SELECTOR_CLASS = re.compile(r"\.([A-Za-z_][\w-]*)")
_SELECTOR_TAG = re.compile(r"^([A-Za-z][\w-]*)")


def _parse_simple_selector(selector: str) -> tuple[str | None, str | None, str | None, list[tuple[str, str | None]]]:
    raw = selector.strip()
    attr_filters: list[tuple[str, str | None]] = []
    for match in _SELECTOR_ATTR.finditer(raw):
        body = match.group(1).strip()
        if "=" in body:
            key, _, value = body.partition("=")
            value = value.strip().strip("\"'")
            attr_filters.append((key.strip(), value))
        else:
            attr_filters.append((body, None))
    without_attr = _SELECTOR_ATTR.sub("", raw)
    elem_id = None
    id_match = _SELECTOR_ID.search(without_attr)
    if id_match:
        elem_id = id_match.group(1)
        without_attr = _SELECTOR_ID.sub("", without_attr, count=1)
    class_name = None
    class_match = _SELECTOR_CLASS.search(without_attr)
    if class_match:
        class_name = class_match.group(1)
        without_attr = _SELECTOR_CLASS.sub("", without_attr, count=1)
    tag = None
    tag_match = _SELECTOR_TAG.match(without_attr.strip())
    if tag_match:
        tag = tag_match.group(1).lower()
    return tag, class_name, elem_id, attr_filters


def _json_path(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


class DataStrategyResolver:
    """持有一次 run 的 env 变量、前序产出，以及 lookup/ensure 钩子。"""

    def __init__(
        self,
        variables: Mapping[str, str] | None = None,
        *,
        page: PageLike | None = None,
        base_url: str | None = None,
        store: dict[str, list[dict[str, Any]]] | None = None,
        create_flows: Mapping[str, CreateFlowHandler] | None = None,
        create_steps_handler: CreateStepsHandler | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._variables = dict(variables or {})
        self._step_outputs: dict[str, dict[str, Any]] = {}
        self._templates = VariableResolver(self._variables)
        self.page = page
        self.base_url = (base_url or "").rstrip("/")
        self.store: dict[str, list[dict[str, Any]]] = store if store is not None else {}
        self._create_flows = dict(create_flows or {})
        self._create_steps_handler = create_steps_handler
        self._http = http_client
        self._owns_http = False

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None

    @property
    def variables(self) -> dict[str, str]:
        return dict(self._variables)

    def bind_page(self, page: PageLike | None) -> None:
        self.page = page

    def set_create_steps_handler(self, handler: CreateStepsHandler | None) -> None:
        self._create_steps_handler = handler

    def register_create_flow(self, flow_id: str, handler: CreateFlowHandler) -> None:
        self._create_flows[flow_id] = handler

    def record_step_output(self, step_id: str, data: Mapping[str, Any] | None) -> None:
        payload = dict(data or {})
        self._step_outputs[step_id] = payload
        exports = payload.get("exports")
        if isinstance(exports, dict):
            for key, value in exports.items():
                if value is None:
                    continue
                self._variables[str(key)] = str(value)
                self._templates = VariableResolver(self._variables)

    def resolve_strategy(self, strategy: DataStrategy) -> str:
        kind = strategy.kind
        if kind == "literal":
            return strategy.value if strategy.value is not None else ""
        if kind == "env":
            key = (strategy.key or "").strip()
            if key not in self._variables:
                raise DataStrategyError(
                    f"环境数据档缺少键：{key}",
                    kind="missing_env",
                    strategy="env",
                    detail={"key": key},
                )
            return self._variables[key]
        if kind == "from_step":
            return self._resolve_from_step(strategy)
        if kind == "lookup":
            return self._lookup(strategy.query, strategy_name="lookup")
        if kind == "ensure":
            return self._ensure(strategy)
        raise DataStrategyError(
            f"未知数据策略：{kind}",
            kind="invalid",
            strategy=str(kind),
        )

    def resolve_step_fields(self, step: Step) -> Step:
        """深拷贝并解析 value / expected（策略优先，其次 {{}} 模板）。"""
        copied = step.model_copy(deep=True)
        try:
            if copied.value_strategy is not None:
                copied.value = self.resolve_strategy(copied.value_strategy)
            else:
                copied.value = self._templates.resolve(copied.value)
            if copied.expected_strategy is not None:
                copied.expected = self.resolve_strategy(copied.expected_strategy)
            else:
                copied.expected = self._templates.resolve(copied.expected)
        except VariableResolutionError as exc:
            raise DataStrategyError(
                str(exc),
                kind="missing_env" if "缺少环境变量" in str(exc) else "invalid",
                strategy="template",
            ) from exc
        return copied

    # ------------------------------------------------------------ lookup / ensure

    def _ensure(self, strategy: DataStrategy) -> str:
        try:
            return self._lookup(strategy.query, strategy_name="ensure")
        except DataStrategyError as exc:
            if exc.kind != "not_found":
                raise
        self._run_create(strategy)
        try:
            return self._lookup(strategy.query, strategy_name="ensure")
        except DataStrategyError as exc:
            if exc.kind == "not_found":
                raise DataStrategyError(
                    "ensure 已执行创建，但仍查不到目标数据",
                    kind="not_found",
                    strategy="ensure",
                    detail={
                        "query": dict(strategy.query or {}),
                        "create_flow_id": strategy.create_flow_id,
                        "after_create": True,
                    },
                ) from exc
            raise

    def _run_create(self, strategy: DataStrategy) -> None:
        if strategy.create_steps:
            if self._create_steps_handler is None:
                raise DataStrategyError(
                    "ensure 提供了 create_steps，但未绑定创建步骤执行器",
                    kind="invalid",
                    strategy="ensure",
                    detail={"create_steps": len(strategy.create_steps)},
                )
            self._create_steps_handler(list(strategy.create_steps), self)
            return

        flow_id = (strategy.create_flow_id or "").strip()
        if flow_id == STORE_UPSERT_FLOW_ID:
            self._store_upsert(strategy.query)
            return
        handler = self._create_flows.get(flow_id)
        if handler is None:
            raise DataStrategyError(
                f"ensure 找不到创建子流程：{flow_id}",
                kind="not_implemented",
                strategy="ensure",
                detail={"create_flow_id": flow_id, "query": dict(strategy.query or {})},
            )
        handler(strategy, self)

    def _store_upsert(self, query: Mapping[str, Any]) -> None:
        entity = str(query.get("entity") or "").strip()
        if not entity:
            raise DataStrategyError(
                "store upsert 需要 query.entity",
                kind="invalid",
                strategy="ensure",
                detail={"query": dict(query)},
            )
        payload = query.get("create")
        if not isinstance(payload, dict):
            match = query.get("match")
            if isinstance(match, dict):
                payload = dict(match)
            else:
                raise DataStrategyError(
                    "store upsert 需要 query.create 或 query.match 对象",
                    kind="invalid",
                    strategy="ensure",
                    detail={"entity": entity},
                )
        rows = self.store.setdefault(entity, [])
        match = query.get("match") if isinstance(query.get("match"), dict) else payload
        for index, row in enumerate(rows):
            if all(str(row.get(k)) == str(v) for k, v in match.items()):
                merged = dict(row)
                merged.update({str(k): v for k, v in payload.items()})
                rows[index] = merged
                return
        rows.append({str(k): v for k, v in payload.items()})

    def _lookup(self, query: Mapping[str, Any], *, strategy_name: str) -> str:
        source = str(query.get("source") or "store").strip().lower()
        if source == "store":
            return self._lookup_store(query, strategy_name=strategy_name)
        if source == "api":
            return self._lookup_api(query, strategy_name=strategy_name)
        if source == "page":
            return self._lookup_page(query, strategy_name=strategy_name)
        raise DataStrategyError(
            f"未知 lookup source：{source}（支持 page / api / store）",
            kind="invalid",
            strategy=strategy_name,
            detail={"query": dict(query)},
        )

    def _lookup_store(self, query: Mapping[str, Any], *, strategy_name: str) -> str:
        entity = str(query.get("entity") or "").strip()
        if not entity:
            raise DataStrategyError(
                "store lookup 需要 query.entity",
                kind="invalid",
                strategy=strategy_name,
                detail={"query": dict(query)},
            )
        rows = list(self.store.get(entity) or [])
        match = query.get("match") if isinstance(query.get("match"), dict) else {}
        matched = [
            row
            for row in rows
            if all(str(row.get(k)) == str(v) for k, v in match.items())
        ]
        if not matched:
            raise DataStrategyError(
                f"store 未找到 {entity} 匹配 {match}",
                kind="not_found",
                strategy=strategy_name,
                detail={"entity": entity, "match": dict(match), "source": "store"},
            )
        row = matched[0]
        field = str(query.get("return_field") or "").strip()
        if field:
            if field not in row or row[field] is None:
                raise DataStrategyError(
                    f"store 命中行缺少字段：{field}",
                    kind="not_found",
                    strategy=strategy_name,
                    detail={"entity": entity, "field": field, "source": "store"},
                )
            return str(row[field])
        for candidate in ("id", "code", "name", "value", "text"):
            if candidate in row and row[candidate] is not None:
                return str(row[candidate])
        raise DataStrategyError(
            f"store 命中行没有可返回字段：{entity}",
            kind="not_found",
            strategy=strategy_name,
            detail={"entity": entity, "row": dict(row), "source": "store"},
        )

    def _http_client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=10.0)
            self._owns_http = True
        return self._http

    def _lookup_api(self, query: Mapping[str, Any], *, strategy_name: str) -> str:
        url = str(query.get("url") or "").strip()
        if not url:
            raise DataStrategyError(
                "api lookup 需要 query.url",
                kind="invalid",
                strategy=strategy_name,
                detail={"query": dict(query)},
            )
        if not url.startswith("http://") and not url.startswith("https://"):
            if not self.base_url:
                raise DataStrategyError(
                    "相对 url 需要 base_url",
                    kind="invalid",
                    strategy=strategy_name,
                    detail={"url": url},
                )
            url = urljoin(self.base_url + "/", url.lstrip("/"))
        try:
            response = self._http_client().get(url)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise DataStrategyError(
                f"api lookup 请求失败：{exc}",
                kind="not_found",
                strategy=strategy_name,
                detail={"url": url, "source": "api"},
            ) from exc

        path = str(query.get("json_path") or "").strip()
        try:
            target = _json_path(payload, path) if path else payload
        except Exception as exc:  # noqa: BLE001
            raise DataStrategyError(
                f"api lookup json_path 未命中：{path}",
                kind="not_found",
                strategy=strategy_name,
                detail={"url": url, "json_path": path, "source": "api"},
            ) from exc

        match = query.get("match") if isinstance(query.get("match"), dict) else None
        if match is not None:
            if isinstance(target, list):
                found = [
                    item
                    for item in target
                    if isinstance(item, dict)
                    and all(str(item.get(k)) == str(v) for k, v in match.items())
                ]
                if not found:
                    raise DataStrategyError(
                        f"api lookup 列表中无匹配：{match}",
                        kind="not_found",
                        strategy=strategy_name,
                        detail={"url": url, "match": dict(match), "source": "api"},
                    )
                target = found[0]
            elif isinstance(target, dict):
                if not all(str(target.get(k)) == str(v) for k, v in match.items()):
                    raise DataStrategyError(
                        f"api lookup 对象不匹配：{match}",
                        kind="not_found",
                        strategy=strategy_name,
                        detail={"url": url, "match": dict(match), "source": "api"},
                    )
            else:
                raise DataStrategyError(
                    "api lookup 带 match 时 json_path 需指向对象或列表",
                    kind="invalid",
                    strategy=strategy_name,
                    detail={"url": url, "source": "api"},
                )

        field = str(query.get("return_field") or "").strip()
        if field:
            if not isinstance(target, dict) or field not in target or target[field] is None:
                raise DataStrategyError(
                    f"api lookup 缺少返回字段：{field}",
                    kind="not_found",
                    strategy=strategy_name,
                    detail={"url": url, "field": field, "source": "api"},
                )
            return str(target[field])
        if isinstance(target, (dict, list)):
            return json.dumps(target, ensure_ascii=False)
        return str(target)

    def _lookup_page(self, query: Mapping[str, Any], *, strategy_name: str) -> str:
        selector = str(query.get("selector") or "").strip()
        if not selector:
            raise DataStrategyError(
                "page lookup 需要 query.selector",
                kind="invalid",
                strategy=strategy_name,
                detail={"query": dict(query)},
            )
        text_contains = query.get("text_contains")
        text_filter = str(text_contains) if text_contains is not None else None
        attr = str(query.get("attr") or "").strip() or None

        html = query.get("html")
        html_path = query.get("html_path")
        if isinstance(html, str) or html_path:
            content = html if isinstance(html, str) else Path(str(html_path)).read_text(encoding="utf-8")
            return self._lookup_html_content(
                content,
                selector=selector,
                attr=attr,
                text_contains=text_filter,
                strategy_name=strategy_name,
            )

        if self.page is None:
            raise DataStrategyError(
                "page lookup 需要绑定 Playwright page，或在 query 中提供 html / html_path",
                kind="invalid",
                strategy=strategy_name,
                detail={"selector": selector, "source": "page"},
            )
        return self._lookup_playwright(
            selector=selector,
            attr=attr,
            text_contains=text_filter,
            strategy_name=strategy_name,
        )

    def _lookup_playwright(
        self,
        *,
        selector: str,
        attr: str | None,
        text_contains: str | None,
        strategy_name: str,
    ) -> str:
        assert self.page is not None
        loc = self.page.locator(selector)
        try:
            count = loc.count()
        except Exception as exc:  # noqa: BLE001
            raise DataStrategyError(
                f"page lookup 选择器无效：{selector}",
                kind="invalid",
                strategy=strategy_name,
                detail={"selector": selector, "source": "page", "error": str(exc)},
            ) from exc
        if count == 0:
            raise DataStrategyError(
                f"页面未找到选择器：{selector}",
                kind="not_found",
                strategy=strategy_name,
                detail={"selector": selector, "source": "page"},
            )
        for index in range(count):
            item = loc.nth(index)
            try:
                text = (item.inner_text() or "").strip()
            except Exception:
                text = ""
            if text_contains is not None and text_contains not in text:
                continue
            if attr:
                value = item.get_attribute(attr)
                if value is None:
                    continue
                return str(value)
            if text:
                return text
            value_attr = item.get_attribute("value")
            if value_attr is not None:
                return str(value_attr)
        raise DataStrategyError(
            f"页面选择器命中但无可用值：{selector}",
            kind="not_found",
            strategy=strategy_name,
            detail={
                "selector": selector,
                "attr": attr,
                "text_contains": text_contains,
                "source": "page",
            },
        )

    def _lookup_html_content(
        self,
        html: str,
        *,
        selector: str,
        attr: str | None,
        text_contains: str | None,
        strategy_name: str,
    ) -> str:
        tag, class_name, elem_id, attr_filters = _parse_simple_selector(selector)
        collector = _ElementCollector(tag, class_name, elem_id, attr_filters)
        collector.feed(html)
        for node in collector.matches:
            text = (node.get("text") or "").strip()
            if text_contains is not None and text_contains not in text:
                continue
            attrs: dict[str, str] = node["attrs"]
            if attr:
                if attr not in attrs:
                    continue
                return str(attrs[attr])
            if text:
                return text
            if "value" in attrs:
                return str(attrs["value"])
            if "data-id" in attrs:
                return str(attrs["data-id"])
        raise DataStrategyError(
            f"HTML fixture 未找到：{selector}",
            kind="not_found",
            strategy=strategy_name,
            detail={
                "selector": selector,
                "attr": attr,
                "text_contains": text_contains,
                "source": "page",
            },
        )

    def _resolve_from_step(self, strategy: DataStrategy) -> str:
        step_id = (strategy.step_id or "").strip()
        if step_id not in self._step_outputs:
            raise DataStrategyError(
                f"前序步骤尚无产出：{step_id}",
                kind="missing_step",
                strategy="from_step",
                detail={"step_id": step_id, "field": strategy.field},
            )
        output = self._step_outputs[step_id]
        field = (strategy.field or "").strip()
        if not field:
            for candidate in ("text", "value", "result"):
                if candidate in output and output[candidate] is not None:
                    return str(output[candidate])
            exports = output.get("exports")
            if isinstance(exports, dict) and exports:
                first = next(iter(exports.values()))
                return str(first)
            raise DataStrategyError(
                f"步骤 {step_id} 没有可用的默认产出字段",
                kind="missing_step",
                strategy="from_step",
                detail={"step_id": step_id},
            )
        if field in output and output[field] is not None:
            return str(output[field])
        exports = output.get("exports")
        if isinstance(exports, dict) and field in exports and exports[field] is not None:
            return str(exports[field])
        raise DataStrategyError(
            f"步骤 {step_id} 产出中没有字段：{field}",
            kind="missing_step",
            strategy="from_step",
            detail={"step_id": step_id, "field": field},
        )
