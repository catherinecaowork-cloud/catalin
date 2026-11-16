# 回放失败 → AI 提案补丁（MVP）

AI 是编译器/修复器，不是逐步远程点击器。日常回放仍走确定性定位与数据策略；**只有失败后**才收集紧凑上下文并提案。

## 做什么

1. 从失败步骤收集：截图路径（若有）、候选/tried、步骤与 `object_id`、环境数据档键名、失败分类（`locator` / `data_strategy` / `uncertain`）。
2. 调用现有 Anthropic 兼容网关；**无 API Key 或显式 fixture** 时用确定性夹具提案。
3. 提案种类：`target_candidates`（改步骤候选）、`object_rebind`（改对象库）、`data_strategy`（literal→env/lookup/ensure）。
4. 默认 **dry-run**：只落库提案，不写回。人工 `apply` 后才改 flow draft / 对象库，审计字段区分 `proposed` vs `applied`。
5. `uncertain` 或低置信度：强制 `requires_human_confirm`，不静默改生产脚本。

## 如何启用

1. 控制台顶栏「AI」配置网关（`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`），或沿用已有 AI 编译配置。
2. 控制面写接口需 API Token（`ATP_API_TOKEN`）。
3. 回放失败后调用：

```bash
curl -sS -X POST "$ATP_URL/api/v1/runs/$RUN_ID/failure-heal/propose" \
  -H "X-API-Token: $ATP_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "fixture_mode": null}'
```

- `fixture_mode: null`（默认）：有网关配置走真实模型，否则自动 fixture。
- `fixture_mode: true`：强制夹具，本地/CI 不调 LLM。
- `fixture_mode: false`：强制真实模型（缺配置则 400）。

## 如何 dry-run

提案接口默认 `dry_run: true`：创建 `failure_heal_task`，`status=proposed`，**不修改**流程步骤与对象库。

确认后再写回：

```bash
curl -sS -X POST "$ATP_URL/api/v1/failure-heal-tasks/$TASK_ID/apply" \
  -H "X-API-Token: $ATP_API_TOKEN"
```

拒绝：

```bash
curl -sS -X POST "$ATP_URL/api/v1/failure-heal-tasks/$TASK_ID/reject" \
  -H "X-API-Token: $ATP_API_TOKEN"
```

`applied_log` 每条包含 `proposed`、`applied`、`status`（`applied` / `skipped`），便于审计。

## 本地测试（无真实 LLM）

```bash
pytest tests/test_failure_heal.py -q
```

## 边界

- 不自动在每次 `complete` 时调模型；需显式 propose。
- 不把环境密钥/整页 DOM 塞进提示词；只传候选摘要与数据档键名。
- 与现有「定位漂移 HealTask」（成功回退候选后的监督者任务）并存：本 MVP 面向**步骤失败**。
