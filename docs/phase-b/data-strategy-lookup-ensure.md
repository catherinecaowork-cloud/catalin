# 数据策略 lookup / ensure（环境 A vs B）

同一套流程、不同环境数据：用策略查已有或创建后再继续，而不是写死某一环境的单号。

## 策略语义

| kind | 行为 |
| --- | --- |
| `lookup` | 按 `query` 在页面 CSS / HTTP API / 内存 store 查值；查不到 → `failure=data_strategy`，`failure_kind=not_found` |
| `ensure` | 先 lookup；未命中则跑 `create_steps` 或 `create_flow_id`（含内置 `__store_upsert__`），再 lookup |

`query.source`：`page` | `api` | `store`。

## 同一流程 · 环境 A（已有数据）

环境 A 的订单列表里已有 `A-100`。步骤只 lookup，不创建：

```json
{
  "id": "fill_order",
  "action": "fill",
  "target": {"candidates": [{"kind": "label", "value": "单号"}]},
  "value_strategy": {
    "kind": "lookup",
    "query": {
      "source": "page",
      "html_path": "fixtures/data-strategy/env-a-orders.html",
      "selector": "tr.order-row[data-order-id=A-100]",
      "attr": "data-order-id"
    }
  }
}
```

解析结果：`value = "A-100"`。

## 同一流程 · 环境 B（缺数据 → ensure）

环境 B 的 HTML 没有 `B-200`。用 store + `__store_upsert__` 演示「查不到就建」（页面 create_steps 同理，由 Runner 执行内联步骤）：

```json
{
  "id": "fill_order",
  "action": "fill",
  "target": {"candidates": [{"kind": "label", "value": "单号"}]},
  "value_strategy": {
    "kind": "ensure",
    "create_flow_id": "__store_upsert__",
    "query": {
      "source": "store",
      "entity": "order",
      "match": {"code": "B-200"},
      "return_field": "code",
      "create": {"code": "B-200", "customer": "demo"}
    }
  }
}
```

1. store 里没有 `B-200` → lookup `not_found`
2. `__store_upsert__` 写入 `create`
3. 再次 lookup → `value = "B-200"`，主流程继续

环境差异落在 Environment 数据档 / 页面数据 / API，不落在步骤字面量。

## 本地验证（无内网）

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest tests/test_data_strategy.py -q
```

可选浏览器回归（page + Playwright）：

```bash
python3 -m pytest tests/test_data_strategy.py -q -m browser
```
