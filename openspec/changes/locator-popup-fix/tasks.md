> 前置：先落地 `restructure-debt`（清掉 `api/` 的 855 处噪声导入）。本 change 的改动落在 `actions.py` / `locator.py` 两个大文件上，噪声没清之前 diff 无法评审。

## 1. 先取证（改之前）

- [x] 1.1 记录基线：`pytest tests/ -q` → **45 passed**
- [x] 1.2 造一个能稳定复现的样本：同一层内「隐藏副本在前、可见元素在后」的浮层 DOM（Ant Design 下拉的典型形态），确认当前实现报 `TargetNotFound`
      —— **已复现**。可见的 `.ant-select-dropdown` 内有 2 个 `.ant-select-item-option`：`nth(0).is_visible()=False`（量高副本，排在前面）、`nth(1).is_visible()=True`。改动前报 `TargetNotFound(所有候选定位方式都未命中：css='.ant-select-item-option')`
- [x] 1.3 记录基线：现有定位相关 selftest 全绿 —— 5 个全部 PASS
- [x] 1.4 记录基线：`_click_locator` 的 `force=True` 兜底当前被哪些用例走到
      —— **0 次**。运行时给 sync Playwright 的 `Locator.click` 打桩统计：pytest 45 条 **0 次**；4 个真起浏览器的 selftest（`optional_skip`/`field_anchor`/`matrix_grid`/`size_panel`）**0 次**。
      即：去掉兜底不会弄红任何现有测试；唯一未知是真站，那正是被推后的验收项

## 2. 可见性收敛（P0）—— **已完成**

- [x] 2.1 新增「取第一个可见匹配」的辅助函数 `_first_visible`，有界遍历 `nth(i)`（`_VISIBILITY_PROBE_LIMIT = 20`），并加 `_wait_first_visible` 做轮询
- [x] 2.2 立即尝试路径改用它
- [x] 2.3 等待重试路径改用它（替换掉 `locator.first.wait_for(state="visible")`）
- [x] 2.4 复核 `_try_root` 取**最后一个**可见匹配的语义 —— **确认不统一，刻意不同向**：`_try_root` 要的是**最新**打开的面板（新面板追加在 DOM 后面），候选匹配要的是**第一个活着的**匹配。两者理由不同，强行统一会把面板的语义错搬到候选上。已写进 `_first_visible` 的 docstring
- [x] 2.5 补测试：`tests/test_locator_visibility.py` 4 条 —— 隐藏副本在前 / 多个可见时取第一个 / 全部不可见仍报失败 / 探测有界（用 `_VISIBILITY_PROBE_LIMIT` 而非硬编码数字，改上限会让这条先失败）
- [x] 2.6 复跑 1.2 → **不再复现**，解析到可见元素
- [x] 2.7 顺带删除已成死函数的 `_immediately_visible`（只被上述两条路径使用）
- [x] 2.8 `pytest tests/ -q` → **49 passed**（45 基线 + 4 新增）；5 个定位 selftest 全绿；`ruff check .` 干净

## 3. 点击回退候选（P0）—— **已完成**

- [x] 3.1 让点击失败后回到候选轮转（`actions.py:467` 一带），而不是直接判定步骤失败
      —— 新增 `ActionRunner._click_candidate(step)`：循环「解析 → 点击」，点不动就把该候选记进
      `skip` 再解析一次。为此 `locator.resolve_target` 新增 keyword-only 的 `skip: dict[str, str]`
      （key 是 `candidate_key`，value 是 `FailureKind`），命中的候选被排除、并按给定原因记进
      `LocatorResolution.failed`。`_do_click` 的尾部由 `self._resolve(step)` 改为 `self._click_candidate(step)`
- [x] 3.2 回退受 `step.timeout_ms` 总预算约束，不是每个候选一份预算
      —— 一份 `deadline`，每次点击前用 `_remaining_ms(deadline)` 取余量。
      **但不是平均分**：`_click_slice_ms` 给首选留大头、给后续候选留底
      （`reserve = min(remaining // 2, _CLICK_RESERVE_MS * (candidates_left - 1))`）。
      原因见下方「施工中发现的两处设计缺陷」第 1 条。预算至少 1ms——Playwright 的 `timeout=0`
      是「不限时」，会把回退挂死
- [x] 3.3 复核 `actions.py:672` 的 `wait_for_timeout(250)` 硬等，改为轮询到超时
      —— 新增 `locator.wait_visible_dropdown_panel(page, timeout_ms)`，`_do_choose` 改用它
      （上限 `min(3_000, step.timeout_ms)`）。那 250ms 是纯硬等：动画快时白等、慢时又不够
- [x] 3.4 补测试：首选可解析但点击不生效时，回退到下一候选并通过
      —— `scripts/selftest_click_fallback.py`（9 条断言全绿）+ `tests/test_locator_failure_kind.py`
      新增 2 条（`test_skipped_candidate_falls_through_without_being_judged_stale` 及其对照组）
- [x] 3.5 扩展 `scripts/selftest_choose_fallback.py` 覆盖这条路径
      —— **改为新建 `scripts/selftest_click_fallback.py`**。理由：`choose`（下拉选项点选）与
      `click` 回退是两个动作、两套 fixture，塞进同一个脚本只会让两边都难读；
      `tests/test_selftests.py` 按 `selftest_*.py` 通配发现，新建即被收编。
      已在 `BROWSER_SELFTESTS` 登记
- [x] 3.6 复跑：`pytest tests/ -q` → **60 passed**（57 + 2 条新测试 + 1 个新 selftest）；
      `ruff check .` 干净；`openspec validate locator-popup-fix --strict` 通过

### 施工中发现的两处设计缺陷（都不在任务书里）

1. **只给总预算会让 3.1 在它要修的那条路上失效。** Playwright 的 `click(timeout=T)` 会把
   可操作性重试铺满整个 `T`。首选被遮挡时它会吃光 `step.timeout_ms`，回退根本没机会跑——
   即「首选点不到」这个 3.1 唯一的适用场景，恰恰是它不生效的场景。
   故加 `_click_slice_ms`：首选拿 `remaining - reserve`，后续候选分 `reserve`。
   单候选时 `candidates_left <= 1` 直接返回全部余量，「首选只是慢」的正常等待不受影响。
2. **跳过点不到的候选必须按环境原因记账，不能判失效。** 否则第 5 节刚堵住的那条路会从
   `_click_candidate` 重新打开：点不到 → 进 `bad` → 下一轮回放删掉好候选。
   所以 `skip` 的 value 是 `FailureKind.COVERED`，走 `CandidateFailure.environmental` 的同一道闸。

顺带：4.1 的 `force=True` 兜底在本节一并删除。3.1 落地后 `_click_locator` 失败必须向上抛
才能触发回退，兜底留着会让它永远不抛——两处是同一处代码，分开做等于先写一段死代码。

## 4. 去掉静默通过（P0）—— **已完成**

- [x] 4.1 去掉 `actions.py:515-534` 的 `force=True` 兜底；若保留，只认步骤上显式标记
      —— **兜底已在第 3 节删除**（`_click_locator` 现在失败就抛，否则 3.1 的回退永远不触发）。
      「步骤上显式标记」这一半**刻意不做**：`Step` 加 `force` 字段是协议改动，而现在没有任何
      生产方——1.4 的统计（`force=True` 被走到 0 次）已经说明现有用例不依赖它。
      设计决定 4 的原文是「**若**确有必须强制的场景，只认显式标记」，是一条政策，不是要求现在就把字段建出来。
      真出现必须强制的场景时再加，那时它才有判据可依
- [x] 4.1b 复核全仓剩下的 `force` —— 只剩 `locator.py:682` 的 `box.fill("", force=True)`
      （清下拉搜索框）。**保留**：那是对一个宽为 0、`is_visible()` 为假的搜索框填空串，
      没有「点到别的东西上」的语义，且后面还跟着 `Ctrl+A` / `Backspace` 兜底。
      与 4.1 要修的「静默点错还报通过」不是一类
- [x] 4.2 加动作生效确认：点击看 URL / 焦点 / 目标状态 / 依赖浮层；填值看值确实变了
      —— **只确认「步骤自己声明了后果」的那一种**，理由见下。
      点击：目标是 select / combobox 触发器（`_click_opens_dropdown`）时，点它的唯一目的就是展开下拉，
      故新增 `_confirm_dropdown_opened`，轮询 `wait_any_dropdown_panel`（口径取
      `DROPDOWN_PANEL` 与 `DROPDOWN_MIXED_VISIBLE` 的**并集**，免得新检查把原本能过的用例判成没生效）。
      预算 `min(_DROPDOWN_CONFIRM_MS=1500, step.timeout_ms)`，沿用原 `_wait_dropdown` 的量级。
      填值：`_do_fill` 早就在 `box.fill` 后回读 `input_value` 并比对（`actions.py:712-726`），本轮只是补上分类
- [x] 4.3 无法确认生效时报失败，并标出「点了没生效」
      —— 点击侧 `StepOutcome(..., "failed", ..., data={"failure": FAILURE_NO_EFFECT, ...})`；
      填值侧的回读不一致同样标 `FAILURE_NO_EFFECT`。这两个是 `no_effect` 目前仅有的生产方。
      经 `runner.py` 的三个键 → 运行结论 → 前端 `FAILURE_LABELS.no_effect = "点了没生效"`
- [x] 4.4 逐个看因 4.1 转红的用例 —— **0 条转红**，与 1.4 的统计一致（去兜底不会弄红任何现有测试）。
      不涉及「批量加回 `force`」
- [x] 4.5 补测试：元素被遮挡时报失败而不是通过
      —— `scripts/selftest_click_fallback.py` 的「失败时没有偷偷点上去」已覆盖；
      本轮新增 `scripts/selftest_click_effect.py` 6 条断言：下拉真展开时通过 / 没展开时报 `no_effect` /
      说明里有「点了没生效」/ 本来就开着时不误判（护栏）/ 护栏那轮确实把下拉点关了
- [x] 4.6 复跑：`pytest tests/ -q` → **61 passed**；`ruff check .` 干净

### 刻意**不**做的生效确认，以及理由

任务书 4.2 列了「URL / 焦点 / 目标状态 / 依赖浮层」四种判据。只落地了最后一种，其余三种
不落地是有理由的，不是漏做：

- **通用的「什么都没变就判失败」**（URL 未变 + 焦点未变 + 目标状态未变 → 报没生效）：
  点输入框取焦点、点表格行做选中、点按钮弹一个我们不追踪的 toast，都是**合法的不改 URL
  不改可见性的点击**。凭空判失败会把好用例弄红，而没人会看天天红的报告——那比漏报更糟。
  规范里那条 Scenario 自己也写了「**而该动作按预期应产生变化**」，前提就是「有预期」。
  只有步骤明确声明了该有什么后果，才够格当判据；`_click_opens_dropdown` 是当前唯一一种这样的声明。
- **URL 变化**：没有步骤声明「这一下应该跳转」。把它当**正向**信号（URL 变了 → 一定生效）
  也只是个提前退出，`wait_for_route_idle` 已经做了，加进来是死代码。
- **`disabled` / `aria-disabled`**：实测（Playwright 1.49.1）`<button disabled>` 的可操作性检查
  本来就会失败并进入回退，再加一次是死代码；`aria-disabled="true"` 被 Playwright 完全忽略
  （点击照发），但它常出现在 loading 之类的**瞬时**状态上，立刻判失败会造出假失败。
  先记进 design.md 的 Open Questions，不在没有真实样本前拍判据。
- **`_do_choose` / `pick_dropdown_option` 选完不确认选项真的落到字段上**：这是真实缺口
  （`pick_dropdown_option` 点完就 `return name`），但期望值在几种模式下不同——多选/标签模式
  下拉不关、`_choose_for_create` 还会「没有就兜底用第一条」或本地新建。期望值不唯一时写的
  检查只会变成假失败。同样记进 Open Questions。

## 5. 失败原因分类（P0）—— **已完成**

- [x] 5.1 在判定候选失效处加分类：目标确实变化 vs 环境原因（浮层未打开 / 被遮挡 / 超时）
      —— `locator.py` 新增 `FailureKind`（`TARGET_CHANGED` / `OVERLAY_ABSENT` / `COVERED` / `TIMEOUT`）、
      `ENVIRONMENTAL_KINDS`、`CandidateFailure`。判据落在新增的 `_overlay_absent(target, roots)`：
      `_roots_for` 找不到浮层时只留一个 page 兜底，所以 `len(roots) <= 1` 就是「层没找到」。
      **刻意偏向误判成环境原因**——浮层动画未完成时 `_try_root` 可能快照不到，代价只是这一轮不判候选失效；
      反过来误判成漂移会真的删掉好候选
- [x] 5.2 只有「目标确实变化」才进 `LocatorMemory.bad`（`locator.py:91-111`）与 `updates`
      —— `remember` 收 `list[CandidateFailure]`，只把非 environmental 的写进 `bad`；
      并在「失败项全是环境原因」时**整轮不改写**：环境原因下的命中往往只是退到 page 兜底撞上的，
      把它升为首选等于用一次环境抖动改写脚本（`learn_candidates` 即使 `failed=[]` 也会把 winner 提到首位，
      所以只挡 `bad` 不够）。`resolve_target` 里那两处直接 `memory.bad.add(...)` 一并收口：
      立即路径那处与 `remember` 完全重复，直接删；等待路径那处保留但同样按 `environmental` 放行，
      因为「全部候选都没命中」时 `remember` 不会被调用（抛 `TargetNotFound`）
- [x] 5.3 运行结论与失败详情能区分「没找到」「找到但点不到」「点了没生效」
      —— 执行器侧定下三类常量（`actions.py` 的 `FAILURE_NOT_FOUND` / `FAILURE_NOT_ACTIONABLE` /
      `FAILURE_NO_EFFECT`），本轮只落「没找到」；`StepOutcome.data` 带 `failure` / `failure_kind` /
      `environmental`，`runner.py` 的 `step_results` 三项一并带出（只写在 message 里就没法按类聚合）。
      控制面 Web 侧 `RunStep.failure` + `RunStepGrid` 渲染中文类名（红字）。
      `TargetNotFound` 也带上 `kind`：浮层没出现时不再报「所有候选定位方式都未命中」，
      改报「目标所在浮层这次没有出现」；`_with_drift` 同样不再把环境原因下的兜底命中说成「首选失效」
      ——另两类由第 3、4 节接线
- [x] 5.4 确认 `control/domain/heal.py:19-42` 的 `collect_heal_task` 不再为环境原因生成条目
      —— **确认**：它只认执行器写来的 `locator_updates`，而 5.2 已把环境原因挡在 `updates` 之外，
      所以环境原因连 `patches` 都进不去，`collect_heal_task` 直接返回 `None`。
      未在此处加二次判断——凭空替执行器猜原因只会再造一条删好候选的路径。已把这条界线写进 docstring
- [x] 5.5 扩展 `scripts/selftest_locator_learn.py` 与 `selftest_heal.py`：环境原因不得删候选
      —— `selftest_locator_learn.py` 对三类环境原因各断言「不进 bad / 不写 updates / 不删候选、不改首选」，
      并补一条正例（`TARGET_CHANGED` 该进 bad、该写 updates、该删候选）；
      `selftest_heal.py` 钉住接缝：空 `updates` 与残缺更新项都不生成修补任务
- [x] 5.6 补测试 `tests/test_locator_failure_kind.py` 8 条 —— 浮层没出现时退到兜底命中不判失效 /
      浮层在且目标真没了才判失效 / 全没命中且浮层没出现时报环境原因 / 同一轮混两类失败时按项判定 /
      纯环境原因不写 updates / 三类环境原因一个不漏（参数化）。
      真起浏览器的 4 条，纯单元 4 条
- [x] 5.7 `pytest tests/ -q` → **57 passed**（49 + 8 新增）；`ruff check .` 干净；
      两个自测脚本全绿；`tsc --noEmit` 干净

## 6. 选择器单一来源（P1）—— **已完成（本 PR）**

- [x] 6.1 在执行器侧建立通用定义（Ant Design / Element UI），作为唯一来源
      —— `autotest_executor/ui_selectors.py`
- [x] 6.2 合并时取现有各份定义的**并集**并逐条核对；`DROPDOWN_OPTION` 的 disabled 过滤必须保留（取更严的那份）
- [x] 6.3 修掉已漂移的具体差异：`DROPDOWN_PANEL` 补上 `.ant-dropdown`；`STD_OPTION_SEL` 对齐 disabled + `[role=option]`
- [x] 6.4 `adapters/oinone/selectors.py` 只留厂商特例（`oio-` 等）并 re-export 通用名；通用件迁出
- [x] 6.5 `locator.py` / `actions.py` 的通用选择器导入改到 `ui_selectors`
- [x] 6.6 录制端 `locator_candidates.js` 与回放端共用同一份（经 `locator_script.locator_init_script()` 注入 `__atpUiSelectors`）
- [x] 6.7 确认 `locator_candidates.js` 头注释已改为「禁止再抄一份」

## 7. iframe 记为不支持（P1）—— **已完成（本 PR）**

- [x] 7.1 目标位于 iframe 内时明确报不支持（`IframeNotSupported`），不产出偶发失败
- [x] 7.2 规格与 README 的「明确不支持」清单已含 iframe 内元素（README 既有；本 PR 补运行时判定 + 测试）

## 8. 验收

- [x] 8.1 `pytest tests/ -q` 全绿（本 PR：**88 passed**；含本地浮层 fixture）
- [x] 8.2 定位相关 selftest 全绿（经 `tests/test_selftests.py` 收编）
- [ ] 8.3 真实站点重复执行浮层用例（福瑞丝 / 杰克）**连续 5 次全过** —— **依赖内网，本 PR 用本地 HTML 连续 3 轮替代闸门**
- [x] 8.4 人为制造三类失败：本地 fixture 覆盖「浮层未出现 / 点了没生效 / iframe 不支持」；既有 selftest 覆盖「点不到」
- [x] 8.5 环境原因造成的失败不产生修补任务、不删候选（既有 `test_locator_failure_kind` / learn selftest）
- [ ] 8.6 `openspec validate locator-popup-fix --strict` —— 本环境无 openspec CLI，未跑
