## 1. 先取证（改之前）

- [x] 1.1 基线：`ruff check --select F401 --output-format=concise . | grep -c F401` → **864**（其中 8 个 router 占 855，其余 9 处散在 7 个文件）
- [x] 1.2 基线：`ruff check --select F811` → **2**（`api/runs.py:231`、`api/workers.py:19`）
- [x] 1.3 基线：`api/sites.py` 的 `sites` router 路由数 → **10**（含 1 条重复注册），启动时抛 `Duplicate Operation ID` **1 条**
- [x] 1.4 基线：`app.openapi()["paths"]` 条数 → **52**
- [x] 1.5 基线：`pytest tests/ -q` → **45 passed in 135.65s**
- [x] 1.6 基线：裸 `ruff check`（默认规则集 `E4,E7,E9,F`）→ 876 = 864 F401 + 10 E402 + 2 F811。10 条 E402 全在 `scripts/selftest_ai_observer.py:14-23`，是门禁不开全量的直接依据

## 2. 清理未用导入

- [x] 2.1 `ruff check --select F401 --fix apps/ packages/ scripts/ tests/` → `Found 864 errors (864 fixed, 0 remaining)`
- [x] 2.2 人工复核 diff：确认删掉的是真未用，没有副作用导入被误删
- [x] 2.3 复跑 1.1 → **0**
- [x] 2.4 **复核发现 1 处误删**：`browser/locator.py` 的 `from autotest_adapters.oinone.navigation import click_sidebar_menu as click_ant_sidebar_menu` 被当作「本模块未使用」删掉，但它是**转出点**——`browser/actions.py:41` 从 `locator` 导入它、`:457` 调用。已恢复并加 `# noqa: F401`（见 `design.md` 决策 5）
- [x] 2.5 复核方法留档：用 AST 扫全仓，对每个被删名字查「是否有别的文件从该模块导入它」→ 全仓命中 **1 处**（即 2.4），其余 863 处无跨模块引用。只 grep 名字会大量误报

## 3. 修重复定义与重复注册

- [x] 3.1 修 `api/runs.py:231` 的 `ACTIVE_RUN_STATUS` 重复定义。**先验证**：本地字面量与 `domain/runs.py:14` 完全相同（`{"queued", "leased", "running"}`），故删本地那份、保留导入，零行为变化。全仓只有 `runs.py:255` 真正使用该符号
- [x] 3.2 修 `api/workers.py:19` 的 `flag_modified` 重复定义（18/19 两行逐字相同）
- [x] 3.3 删 `api/sites.py:265` 那个悬空的路由装饰器（第 277 行那个保留）
- [x] 3.4 复跑 1.2 → **0**；复跑 1.3 → **9 条且无警告**；复跑 1.4 → **仍为 52**

## 4. 删除一次性脚本

- [x] 4.1 删 `scripts/split_api_routes.py`（`git rm`）
- [x] 4.2 确认全仓无代码引用：`grep -rn "split_api_routes"` 仅命中文档与本 change 自身

## 5. CI 门禁

- [x] 5.1 `.gitee-ci.yml` 增加 `lint` 作业：`pip install -e ".[dev]"` + `ruff check .`（保持该文件原有 CRLF 行尾）
- [x] 5.2 规则集写进 `pyproject.toml`：`[tool.ruff] target-version` + `[tool.ruff.lint] select = ["F401","F811"]`，本地裸跑 `ruff check` 与 CI 一致；`dev` 依赖加 `ruff>=0.15`
- [x] 5.3 确认顺序：同一次提交里先清理、后开门禁，门禁不会在旧代码上亮红灯
- [x] 5.4 `.gitignore` 增 `.ruff_cache/`（ruff 运行产物，不该入库）

## 6. 验收

- [x] 6.1 `pytest tests/ -q` → **45 passed in 119.31s**，与基线一致
- [ ] 6.2 一次真实回放仍通过（福瑞丝导入「新建款式」）—— **未做**，需真站环境与能跑 headed 的 Worker，见下方「未完成项」
- [x] 6.3 启动日志无 `Duplicate Operation ID` 警告 → **0 条**
- [x] 6.4 `ruff check .`（走 `pyproject.toml` 配置）→ **All checks passed!**
- [x] 6.5 15 个改动文件逐个实际 `import` 成功；`click_ant_sidebar_menu` 转出点解析到 `autotest_adapters.oinone.navigation`

## 未完成项

- [ ] 6.2 真实回放验收。这是本 change 唯一未勾选项，挂起原因是**环境**不是代码：需要一个能访问福瑞丝（`http://192.168.99.165:8000`）且能跑 headed 的 Worker。`pytest` 45 passed 与全模块导入成功已覆盖静态层面的回归，但「为副作用而存在的导入」这类问题只有真实回放能兜住——本 change 已经因为这类问题中过一次（2.4）。
