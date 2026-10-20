## Context

见 `proposal.md`。本 change 是纯结构整理，零行为变化，故 `.openspec.yaml` 标 `skip_specs: true`。

## Goals / Non-Goals

**Goals:**

- `ruff check --select F401,F811` 在全仓干净
- 启动时不再有 `Duplicate Operation ID` 警告
- 一次性脚本不再留在仓库里被人误跑
- lint 门禁进 CI，这类债不再回流

**Non-Goals:**

- 不重构 8 个 router 的职责划分（哪个端点该归哪个模块）
- 不动那 8 个文件里近乎相同的惰性导入块（函数内 import）
- 不改任何 API 契约、路由路径、响应模型
- 不引入 ruff 的其它规则集（只开 F401 / F811）
- 不做格式化（不跑 `ruff format`），避免把 diff 淹没

## Decisions

1. **用 `ruff --fix`，不手改**  
   864 处手工清理既慢又必然出错。`ruff` 已装（0.15.12）。  
   备选：自己写脚本删。否决——ruff 已经做了这件事，且对 `__all__`、条件导入、`TYPE_CHECKING` 块的处理更正确。

2. **只开 F401 / F811，不开全量规则**  
   门禁的目的是防这一类债回流，不是借机做一次全仓风格整改。清理完 F401/F811 后，裸 `ruff check`（默认规则集 `E4,E7,E9,F`）仍会报 **10 条 E402**，全部在 `scripts/selftest_ai_observer.py:14-23`——那个文件先 `sys.path.insert` 再导入，是 selftest 脚本的正当写法，不是债。若门禁开全量，这 10 条会把门禁一次性点亮，从此没人看。  
   备选：开 `E`/`F` 全集。否决——见上。规则集写进 `pyproject.toml` 的 `[tool.ruff.lint]`，让本地裸跑 `ruff check` 与 CI 结果一致，不靠各自记参数。

3. **`sites.py` 的重复装饰器必须人工处理**  
   `ruff` 不报这一处（重复装饰器不是名字重定义，F811 只抓到 2 处重复定义）。要手工删掉第 265 行那个悬空装饰器，保留第 277 行的。  
   删除后需验证三件事：该路径在路由表里只剩 1 条、启动警告消失、OpenAPI 路径数仍为 52。  
   注意 OpenAPI 输出本来就没有重复——它按 path 去重，所以「路径数不变」是预期结果，不是没修好。

4. **删 `split_api_routes.py`，不留档**  
   它硬编码了 `api.py` 的行号区间，而 `api.py` 已不存在；`SECTIONS` 里 `sites`(230-500) 与 `ai`(272-316) 区间还互相重叠。留着只会被误跑、再复制一遍耦合。git 历史里有。

5. **`browser/locator.py` 的转出导入必须保留，`ruff --fix` 会误删**  
   实测：`ruff --fix` 删掉了 `locator.py` 里 `from autotest_adapters.oinone.navigation import click_sidebar_menu as click_ant_sidebar_menu`，理由是「本模块内未使用」。但 `locator.py` 是这个符号的**转出点**——`browser/actions.py:41` 正是从 `autotest_executor.browser.locator` 导入它、并在 `:457` 调用。删掉后 `actions.py` 直接 `ImportError`。  
   这正是 `Risks` 里担心的「副作用导入被误删」，而且它**确实发生了**，所以复核不能只看 ruff 报干净。  
   处置：恢复该行并加 `# noqa: F401`，沿用仓库既有体例（`scripts/replace_form_credential.py:23` 的 `# noqa: E402 - …`）。不改成 `actions.py` 直接导入适配器——那属于「适配器边界归位」，是 `locator-popup-fix` 的施工项，不在本 change 的零行为变化边界内。  
   复核方法：用 AST 扫全仓，对每个被删名字查「是否有别的文件从该模块导入它」。全仓命中 **1 处**，即上述转出点；其余 863 处均无跨模块引用。只靠 grep 名字会得到大量误报（`APIRouter` 等通用名在别处也从 fastapi 导入），必须解析 import 来源模块。

## Risks / Trade-offs

- [ruff 误删有用的「未用」导入] → 有些导入是为副作用（注册、插件）。**这个风险已经发生**：`browser/locator.py` 的转出导入被删（见决策 5）。清理后必须跑 `pytest`（基线 45 passed）并做一次真实回放确认，不能只看 ruff 报干净。
- [清理把 diff 放大] → 864 处删除会让 diff 很大。这是本 change 唯一的「大」，且全是删除行。其中 `browser/locator.py` 与 `browser/actions.py` 各有 1 处，**正是 `locator-popup-fix` 要重写的两个文件**——所以本 change 必须先落地，否则那份 diff 里会混着两件事，评审时分不清哪行属于哪个目的。这一点已用 ruff 核实，不是推测。
- [门禁在旧代码上立刻红灯] → 先清理、再开门禁，在同一个 change 内按 `tasks.md` 固定顺序完成。

## Migration Plan

无数据迁移。回滚：`git revert` 整个 change；门禁随之回退，旧代码回到现状（启动警告重新出现，但功能不受影响）。

## 施工中发现（不在本 change 范围，仅记录）

清理过程中顺带查实一件事：**验证码 / SSO 的检测链路从设计上就没接上**。

- `UnsupportedLoginChallenge`（`auth.py:17`）全仓**没有任何 `raise` 点**
- `detect_login_challenge`（`auth.py:147`）**没有任何调用点**，而它是 `_CHALLENGE_HINTS`（`auth.py:30`）的唯一使用者
- 两处 `except UnsupportedLoginChallenge`（`recorder.py:238`、`runner.py:74`）因此是**永远不会触发的处理分支**

后果：遇到验证码不会被识别为「不支持」，而是继续跑到登录成功断言才失败，报错信息指向症状而非原因。

**这是既有状态，不是本 change 造成的**——改动前 `runner.py` 就是「导入但从不调用」`detect_login_challenge`，本次只是把这个空转的导入删掉了。接线上属于行为改动，不塞进零行为变化的 change，已记入 `README.md`「还没做」，待后续单独开 change。

## Open Questions

无。
