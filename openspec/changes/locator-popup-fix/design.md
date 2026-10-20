## Context

见 `proposal.md`。本 change 修的是缺陷，不是新能力；范围严格限定在「浮层内元素定位与操作」这一条链上。

证据（行号为改动前，均已逐处核对）：

| 位置 | 事实 |
| --- | --- |
| `browser/locator.py:330-334` | 立即尝试路径：`_build(root, candidate).first` → `_immediately_visible(locator)`，不满足就 `continue` |
| `browser/locator.py:351-362` | 等待重试路径：同样 `.first` → `wait_for(state="visible")` |
| `browser/locator.py:286-290` | `_immediately_visible` 只看 `locator.first.is_visible()` |
| `browser/locator.py:223-236` | `_try_root` **已经**是正确写法：遍历 `nth(i)` 找可见的那个。正确模式就在同一文件里 |
| `browser/actions.py:467` | `self._click_locator(resolution.locator, ...)` —— 解析出单个 locator，点一次 |
| `browser/actions.py:515-534` | `_click_locator` 失败后 `target.click(..., force=True)` |
| `browser/actions.py:672` | `page.wait_for_timeout(250)` 硬等 |
| `browser/locator.py:91-111` | `LocatorMemory.remember` → `learn_candidates`（103）→ `target.candidates = learned`（104） |
| `protocol/dsl.py:130-145` | `learn_candidates` 把 `failed` 里的候选**直接丢弃** |
| `control/domain/heal.py:19-42` | `collect_heal_task`：不自动写回，只生成待确认任务 |
| `adapters/oinone/selectors.py:19,32,331,336,378` + `locator_candidates.js:11,28` | 「浮层面板」7 份定义，覆盖面两两不同 |
| `adapters/oinone/selectors.py:47` + `locator_candidates.js:10` | 「下拉选项」2 份定义，`DROPDOWN_OPTION` 6 项 vs `STD_OPTION_SEL` 2 项 |

漂移的实例（同一个概念，两份定义不一致）：

- `DROPDOWN_PANEL`（`oinone/selectors.py:32-37`）**没有** `.ant-dropdown:visible`，而 `PANEL_VISIBLE_DEFAULT`（`:331-334`）有。
- 反过来，`DROPDOWN_PANEL` 有 `.ant-cascader-dropdown` / `.ant-cascader-menus`，而 `PANEL_VISIBLE_DEFAULT` 没有。两份的差集互不包含——谁也覆盖不了谁。
- JS 的 `PORTAL_SEL`（`locator_candidates.js:11-27`）给 `.ant-select-dropdown` 加了 `:not(.ant-select-dropdown-hidden)`，而 `STD_DROPDOWN_SEL`（`:28-32`）连 visible 过滤都没有。
- `DROPDOWN_OPTION` 含 `.el-select-dropdown__item:not(.is-disabled)`、`[role=option]`、`.ant-dropdown-menu-item`；`STD_OPTION_SEL` 只有 `.ant-select-item-option, .el-select-dropdown__item`——**没有 disabled 过滤**，会命中禁用项。

`locator_candidates.js:1-4` 的头注释自己写着「两处各写一份迟早会漂移」。实际是 7 处，不是 2 处。

## Goals / Non-Goals

**Goals:**

- 浮层内元素在重复执行下不再偶发定位失败或点击无效
- 失败时能区分「没找到」「找到但点不到」「点了没生效」
- 「浮层面板」与「下拉选项」各只有一份通用定义，录制与回放共用
- 环境原因造成的未命中不再产生漂移判定、不再删候选

**Non-Goals:**

- iframe 支持（另开 change）
- 不改候选稳定性排序（`dsl.py` 的 `CANDIDATE_STABILITY` 与 `_stability`）
- 不改流程状态机、不改修补任务的确认流程本身（只收窄「什么算漂移」）
- 不改 `LocatorMemory` 的 `good` / `bad` 机制本身，只改「什么算失效」的判定
- 不引入新的浏览器驱动或等待框架

## Decisions

1. **复用 `_try_root` 已有的写法，而不是新造**  
   `locator.py:223-236` 的 `_try_root` 就是「遍历匹配、返回可见的那个」。新增一个同构的辅助函数用于候选匹配，两条解析路径（立即 / 等待）都改用它。  
   备选：用 `locator.filter(visible=True)`。**不可用**——它需要 Playwright ≥1.51，本仓库锁 1.49.1（`pyproject.toml:16`）。  
   备选：在候选 CSS 后面拼 `:visible`。否决——`candidate.value` 可能是 role/text 等非 CSS 候选，拼字符串会破坏语义候选；而且 Playwright 的 `:visible` 与 `is_visible()` 语义不完全一致，混用会引入新的不一致。

2. **可见性探测必须有界**  
   遍历 `nth(i)` 要设上限（隐藏副本通常是个位数）。无上限会在病态 DOM 上把一次解析拖成秒级。上限值在实现时按现有 `_candidate_timeout` 的量级定，并留注释说明为什么有界。

3. **点击回退：改的是控制流，不是候选生成**（已实施）  
   候选轮转逻辑已经在 `_resolve` / `resolve_target` 里；缺的是**点击失败后回到轮转**。  
   备选：在 `_resolve` 里预先验证候选可点击。否决——可点击性只有在点击那一刻才成立（动画、遮挡都在变），预检会得到过期结论。

   落点：`ActionRunner._click_candidate(step)` 循环「解析 → 点击」，点不动就把该候选记进 `skip` 再解析一次。
   为让 `skip` 生效，`resolve_target` 新增 keyword-only 的 `skip: dict[str, str]`
   （key 是 `candidate_key`，value 是 `FailureKind`）——命中的候选被排除，并按**给定原因**记进
   `LocatorResolution.failed`。`skip` 的原因由调用方给、不由 `resolve_target` 猜：调用方知道得比它多。

   三条一起定下来的规则：

   - **`skip` 的原因是 `FailureKind.COVERED`，不是 `TARGET_CHANGED`。** 点不到多半是遮挡或动画，
     不是候选失效；判成失效会在下一轮把好候选从脚本里删掉——正是第 5 节刚堵住的那条路，
     从 `_click_candidate` 重新打开。所以 `skip` 走 `CandidateFailure.environmental` 的同一道闸。
   - **预算是总共一份，但不是平均分。** Playwright 的 `click(timeout=T)` 会把可操作性重试铺满整个 `T`，
     首选被遮挡时会吃光 `step.timeout_ms`，回退根本没机会跑——「首选点不到」这个唯一的适用场景，
     恰恰是它不生效的场景。故 `_click_slice_ms` 给首选 `remaining - reserve`、
     给后续候选 `reserve = min(remaining // 2, _CLICK_RESERVE_MS * (candidates_left - 1))`。
     单候选时 `candidates_left <= 1` 直接返回全部余量，「首选只是慢」的正常等待不受影响。
     切片至少 1ms：Playwright 的 `timeout=0` 是「不限时」，会把回退挂死。
   - **`_click_locator` 失败必须向上抛。** 否则回退永远不触发。故 `force=True` 兜底在**本节**
     一并删除（原属 4.1）——留着等于先写一段死代码，两处是同一处代码。

   失败归类：候选耗尽时抛 `ClickNotActionable`（「找到但点不到」），与 `TargetNotFound`（「没找到」）
   分开。它的 message 只取 Playwright 报错的**首行**——那段 call log 有几十行，
   会经 `step_results` 进运行结论灌到 UI 里。

4. **去掉 `force=True`，但保留逃生口**（已实施）  
   默认不强制点击。若确有必须强制的场景，只认步骤上**显式**的标记，而不是失败后自动降级。  
   风险：现有用例可能依赖这个兜底才能通过。所以这一步要单独验收——去掉后若有用例转红，说明它此前一直是「静默点错还算过」，应当单独看，而不是把 `force` 加回来。

   实际落地：兜底**在第 3 节就删了**，因为 3.1 的点击回退要求 `_click_locator` 失败必须向上抛——
   留着兜底它永远不抛，回退是死代码。两处是同一处代码，分开做等于先写一段死代码。
   实测 0 条用例转红，与 1.4 的统计（`force=True` 被走到 0 次）一致。

   「步骤上显式标记」这一半**刻意不做**：`Step` 加 `force` 字段是协议改动，而现在没有任何生产方。
   本决定是一条**政策**（若将来要强制，必须是显式的，不能是失败后自动降级），
   不是要求现在就把字段建出来。真出现必须强制的场景时再加，那时它才有判据可依。

   例外：`locator.py:682` 的 `box.fill("", force=True)`（清下拉搜索框）保留。那是对一个宽为 0、
   `is_visible()` 为假的搜索框填空串，没有「点到别的东西上」的语义，后面还跟着 `Ctrl+A`/`Backspace` 兜底。

5. **动作生效确认：只在步骤声明了后果时才判失败**（已实施）  
   原表述是「点击看 URL / 焦点 / 目标状态 / 依赖浮层；填值看值确实变了」。落地时收窄成
   **只确认步骤自己声明了后果的那一种**，因为通用的「什么都没变就判失败」会造假失败：

   点输入框取焦点、点表格行做选中、点按钮弹一个我们不追踪的 toast，都是**合法的不改 URL
   不改可见性的点击**。凭空判失败会把好用例弄红，而没人会看天天红的报告——那比漏报更糟。
   规范里那条 Scenario 自己也写了前提：「**而该动作按预期应产生变化**」。

   当前唯一够格的声明是 `_click_opens_dropdown(step)`：目标是 select / combobox 触发器，
   点它的唯一目的就是展开下拉。故 `_confirm_dropdown_opened` 轮询到下拉出现为止，
   超时则报 `FAILURE_NO_EFFECT`「点了没生效：点击下拉触发器后没有出现下拉面板」。
   填值侧的「值确实变了」`_do_fill` 早就有了（回读 `input_value` 比对），本轮只补分类。

   两条实现细节：

   - **口径取并集。** `wait_any_dropdown_panel` 同时认 `DROPDOWN_PANEL`（正规口径，多出 cascader）
     与 `DROPDOWN_MIXED_VISIBLE`（`_wait_dropdown` 原来的口径，多出 `.el-popper`/`.ant-dropdown`），
     两份各有对方没有的选择器。取窄会把原本能过的用例判成没生效——把新检查变成新故障。
     收窄口径是第 6 节的事。
   - **「本来就开着」是护栏。** 点击前若已有可见下拉，点触发器只会把它收起（Ant 的开关行为），
     「点完没有下拉」说明不了没生效。这道护栏也顺带挡住 `_ensure_panel_open` 刚点开面板、
     紧接着又被 `_click_candidate` 点关的乱局。

   判据要容忍合理延迟，用轮询到预算（`min(_DROPDOWN_CONFIRM_MS=1500, step.timeout_ms)`，
   沿用原 `_wait_dropdown` 的量级），不用固定 `wait_for_timeout`。

6. **选择器单一来源放执行器，不放协议**  
   收敛到执行器（`browser/` 下的一个通用模块），`adapters/oinone` 只保留 `oio-` 前缀等厂商特例。  
   备选：放 `packages/protocol`。否决——protocol 是步骤 DSL / 任务 / 事件模型，选择器是执行细节，放进协议会让协议依赖 DOM 知识。  
   录制端（`locator_candidates.js`）与回放端共用同一份：JS 侧通过注入时传入，避免在 JS 里再抄一份常量。

7. **漂移判定收窄的落点**（已实施）  
   在「判定候选失效」的地方加失败原因分类：只有确认目标本身变化才算 `stale`；浮层未打开 / 被遮挡 / 超时归为环境原因，不进 `memory.bad`，也不进 `updates`。  
   这样 `learn_candidates`（`dsl.py:130`）的输入天然干净，不必改它的签名。  
   备选：改 `learn_candidates` 加参数区分。否决——它是 `protocol` 的公开函数，改签名要动调用方与 selftest；在源头分类更小。

   落点：`locator.py` 新增 `FailureKind` / `ENVIRONMENTAL_KINDS` / `CandidateFailure`，
   `remember` 改收 `list[CandidateFailure]`，只把非 environmental 的写进 `bad`。
   `resolve_target` 里原先那两处直接 `memory.bad.add(...)` 一并收口——立即路径那处与 `remember` 完全重复，直接删；
   等待路径那处保留但同样按 `environmental` 放行，因为「全部候选都没命中」时 `remember` 不会被调用（抛 `TargetNotFound`）。

   判据：新增 `_overlay_absent(target, roots)`。`_roots_for` 找不到浮层时只留一个 page 兜底，
   所以 `len(roots) <= 1` 就是「层没找到」。**刻意偏向误判成环境原因**——浮层动画未完成时
   `_try_root` 可能快照不到，代价只是这一轮不判候选失效；反过来误判成漂移会真的删掉好候选。

   施工中发现的一条**必须一起改**的规则：`learn_candidates` 即使 `failed=[]` 也会把 winner 提到首位，
   所以「只挡 `bad`」不够——纯环境原因的那一轮必须**整轮不改写** `target.candidates`，也不写 `updates`。
   环境原因下的命中往往只是退到 page 兜底撞上的，把它升为首选等于用一次环境抖动改写脚本，比不修更糟。

   连带修正：`TargetNotFound` 带 `kind`，浮层没出现时报「目标所在浮层这次没有出现」而非
   「所有候选定位方式都未命中」；`_with_drift` 不再把环境原因下的兜底命中说成「首选失效」——
   报成漂移会让人去改本来没问题的候选。两处都是**报告口径**的修正，不改变判定本身。

## Risks / Trade-offs

- [去掉 `force=True` 后有用例转红] → 这正是要暴露的：那些用例此前是静默点错。逐个看，不批量加回 `force`。
- [可见性收敛让解析变慢] → 有界遍历 + 只在多匹配时才逐个检查；单匹配是快路径。
- [候选回退把「真失败」拖长] → 回退受 `step.timeout_ms` 总预算约束，不是每个候选一份预算。这也是要修的（`actions.py:672` 的 250ms 硬等一并复核）。
- [选择器合并可能改变现有命中范围] → 合并时取各份定义的**并集**并逐条核对，不用其中任一份的现状；`DROPDOWN_OPTION` 的 disabled 过滤必须保留（并集时以更严的那份为准）。
- [改动落在 `actions.py` / `locator.py` 这两个大文件上] → 先把 `restructure-debt` 落地，清掉噪声再动，否则 diff 无法评审。

## Migration Plan

无数据迁移。已录流程的 `target.candidates` 结构不变，因此不需要迁移脚本；修补任务的既有数据继续可用。

回滚：`git revert` 整个 change。若已产生被误删候选的修补任务，从运行历史里取回原始候选列表。

## Open Questions

- ~~可见性遍历的上限取多少？~~ **已定**：`_VISIBILITY_PROBE_LIMIT = 20`，轮询间隔 `_VISIBILITY_POLL_MS = 100`，均写进注释。
- 动作生效确认的判据，是否要按站点可配置？（倾向先给一套默认判据，不做配置）
- ~~「被遮挡」的判据落在哪一节？~~ **已定**：第 3 节。`_click_candidate` 把点不动的候选以
  `FailureKind.COVERED` 记进 `skip`，这是它的唯一生产方。
- `FailureKind.TIMEOUT` 仍**没有生产方**。它已在 `ENVIRONMENTAL_KINDS` 里备好，
  但谁该在什么条件下产它（`_wait_first_visible` 等超时算不算候选失效？）留到第 4 节
  接「动作生效确认」时一起定——那一节才会真正出现「等到了但没生效」这种既非找不到、
  也非点不动的第三态。在那之前，不为了让枚举「看起来完整」而硬塞一个生产方。
- `_click_slice_ms` 的 `_CLICK_RESERVE_MS = 1_000` 是拍的。它对「元素正常、只是页面慢」
  远远够用，只有真点不动时才会用满；真站验收（8.3）时若发现回退给后续候选的底不够，调这一个常量即可。
- **`disabled` / `aria-disabled` 要不要当生效确认的判据？** 实测（Playwright 1.49.1）：
  `<button disabled>` 的可操作性检查本来就会失败并进入回退，再加一次是死代码；
  `aria-disabled="true"` 被 Playwright 完全忽略（点击照发、动作照跑），但它常出现在
  loading 之类的**瞬时**状态上，立刻判失败会造出假失败。倾向：等真站上拿到样本再定，
  若定，也要给一个「等它变回 enabled」的窗口而不是立即判死。
- **`_do_choose` / `pick_dropdown_option` 选完不确认选项真的落到字段上**（真实缺口）。
  `pick_dropdown_option` 点完就 `return name`，`_choose_existing` 直接报通过。但期望值在几种
  模式下不同：多选/标签模式下拉不关、`_choose_for_create` 还会「没有就兜底用第一条」或本地新建。
  期望值不唯一时写的检查只会变成假失败，所以先不做。要做的话，得先让「期望值」从 `_choose_existing`
  的入参（`value`）而不是 `step.value` 来——这一条已经具备，缺的是各模式下「怎么读回」的统一口径。
