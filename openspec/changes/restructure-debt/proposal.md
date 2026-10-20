## Why

「拆边界」那一步只拆了文件，没拆耦合。全仓现在有 **864 处未用导入**（`ruff check --select F401`，可复现），分布在 15 个文件，来源分两类：

- **855 处集中在 8 个 API router**——起因是当初用一次性脚本 `scripts/split_api_routes.py` 把 `api.py` 整段复制成 8 个模块时，把整块导入语句一并复制了 8 份。
- **其余 9 处散在 7 个文件**，是日常留下的：`ai/compiler.py`、`browser/actions.py`、`browser/locator.py`、`runner.py`、`scripts/selftest_ai_observer.py`、`scripts/selftest_compilation_worker.py`、`tests/test_observer_control.py`。

这不是风格问题：它让「这个模块到底依赖什么」变得不可读，真正的依赖变化也淹没在噪声里。

同一批复制还留下两处重复定义（`ruff --select F811`）：`api/runs.py:231` 重复定义 `ACTIVE_RUN_STATUS`，`api/workers.py:19` 重复定义 `flag_modified`。另外 `api/sites.py` 有一个函数挂了两个完全相同的路由装饰器（第 265 与 277 行），该路由因此被注册两次，FastAPI 启动时抛 `Duplicate Operation ID` 警告。

现在处理，是因为下一步要做浮层定位缺陷修复（`locator-popup-fix`），改动落在同一批文件上——先把噪声清掉，那份 diff 才看得清。

## What Changes

- 清掉全仓 864 处未用导入（用 `ruff --fix`，不手改）
- 修 2 处重复定义（F811）：`runs.py:231`、`workers.py:19`
- 修 `api/sites.py` 的重复路由装饰器，消除重复注册与启动警告
- 删除一次性脚本 `scripts/split_api_routes.py`（硬编码的 `api.py` 行号已失效，区间还互相重叠）
- `.gitee-ci.yml` 加 lint 门禁，让 F401 / F811 不能再回流

**零行为变化。** 这是本 change 的硬边界，见 `design.md` 的 Non-Goals。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

（无）

纯结构整理，不改变任何外部行为，因此 `.openspec.yaml` 标 `skip_specs: true`。规格描述行为；行为不变，规格就不该变。

## Impact

- **控制面**：`api/` 下 8 个 router（855 处）与 `ai/compiler.py`（1 处）
- **执行器**：`browser/locator.py`、`browser/actions.py`、`runner.py`（各 1 处）
- **脚本与测试**：`scripts/selftest_ai_observer.py`、`scripts/selftest_compilation_worker.py`、`tests/test_observer_control.py`
- **运行时**：启动时的 `Duplicate Operation ID` 警告消失；`sites` router 路由数 10 → 9；`app.openapi()["paths"]` 仍为 52 条
- **转发点**：`browser/locator.py` 里 `click_ant_sidebar_menu` 的转出导入**必须保留**——`browser/actions.py` 是从 `locator` 导入它的，`ruff --fix` 会误判为未用而删除，导致 `ImportError`。已加 `# noqa: F401` 并注明原因，详见 `design.md` 决策 5
- **CI**：`.gitee-ci.yml` 增加 ruff 门禁；`pyproject.toml` 增 `[tool.ruff]` 配置与 `dev` 依赖
- **删除**：`scripts/split_api_routes.py`；`.gitignore` 增 `.ruff_cache/`
- **未纳入**：不重构 router 的职责划分，不动那 8 个文件里近乎相同的惰性导入块
