# 进度记录

本文件记录**跨 change 的施工进度与交接状态**，不替代各 change 自己的 `tasks.md`。
排期理由以 `docs/platform-restructure-plan.md` 为准；本文件只记「做到哪了、卡在哪、下一步是什么」。

---

## 2026-10-29（开窗尺寸修复 + 站点放行预检 + 顶栏环境切换器）

### 一句话状态

三块改动：**① 开窗一律按「带录制面板」的尺寸起窗**（141 登录在全屏宽下渲染不同，之前录制死在登录）；**② 录制前加「站点放行预检」**（办公机跑自动化会间歇被拒连，等它自愈而不是直接死掉）；**③ 控制台顶栏常驻「当前环境」切换器**（切环境不再借道录制弹窗）。定位层指纹相关代码无改动。

### 环境问题排查线（占了大半天，结论值得记住）

1. **Mihomo 挡内网是红鲱鱼 + 真问题各一半**：用户浏览器打不开内网站点，最终在 Clash Verge Rev 的「全局扩展配置(Merge)」加了 `prepend-rules: IP-CIDR,192.168.0.0/16/10.0.0.0/8/172.16.0.0/12 → DIRECT` 后解决（UI 操作，非订阅文件）。已验证走 Mihomo 7897 访问 141 也 200。
2. **真正的拦路虎疑似 Sangfor aTrust 零信任**：办公机（10.118.23.x，跨网段）跑自动化会间歇 `ERR_CONNECTION_REFUSED`，约一分钟自愈；低频 curl 探测永远 200（8 分钟 161 次全 200）、40 并发静态请求也无拒连，但浏览器/自动化开页面的突发会触发。**同网段的 99.138 服务器跑同样任务开窗通过**——同 VLAN 直达、无管控设备在路径上。141 部署自身问题清单外的新环境坑。
3. 排查手段沉淀：`curl --noproxy "*"` 直连对照（区分代理 vs 网络）、录制截图看页面实际状态（260KB=正常登录页 / 23KB=Chrome 错误页 / 空白渐变=SPA 没渲染）、HAR 里的 `startedDateTime`（UTC）对齐本地时间线。

### 做了什么

1. **开窗尺寸**（`browser/session.py` + `browser/window_dock.py`）：起窗与 `apply_main_only_layout` 都改用 `compute_record_layout()` 的主窗口尺寸（工作区宽 − 面板宽 460），登录阶段就是最终尺寸，面板打开时窗口不再跳动。录制、回放共用此路径（回放开窗也不再全屏）。
2. **站点放行预检**（`recorder.py` 新增 `_wait_for_site_open`）：录制开跑前直连探测（`http.client`，不走代理），拒连则每 5 秒重试、最多 150 秒，恢复/超时都发 log 事件。只覆盖录制；回放未接。
3. **顶栏环境切换器**（`apps/control-plane/web`）：`MainToolbar` 挂 `RecordEnvPicker`（复用录制弹窗组件）+ 直接挂 `RecordEnvironmentsModal`（建站/凭证管理不再进录制弹窗）；`App.tsx` 传入 `sitesState`；`theme.css` 加顶栏紧凑样式 + 菜单 `left:0` 左对齐（默认 `right:0` 会伸出屏幕左缘）。状态仍是全局 `selectedSiteId`，explorer/执行/历史/录制同步行为不变。

### 验证

- `ruff check` 改动文件全过；`pytest tests/test_session_locator_injection.py` passed
- web：`tsc --noEmit` 干净，`npm run build` 成功，控制台已吐新资源
- 真站对照：99.138 上开窗录制**通过**（用户实测）；本机录制两次失败分别是拒连窗口（`640e4074`，截图即 Chrome 错误页）和 SPA 空白未渲染（`f66f9a57`，同窗口期），预检就是为这个加的
- 本机录制在新尺寸下的验证仍未完成（被拒连窗口挡住），下次录制通过才算闭环

### 踩到的坑

- **改 `autotest_executor` 必须重启 worker**（老坑再确认）：控制台自己的 `local-ui` worker 也要经 `workers/local/stop` + `local/start` 重启，只重启自己起的 runner 没用。
- 录制弹窗里的环境切换会改全局站点——这次把入口搬到顶栏后行为不变、心智变直（「当前环境」是工作区状态，录制只是消费者之一）。
- aTrust 限流从外部测不透规律（curl 全绿与浏览器被拒可以同时发生），不要试图在代码侧绕，方向只有两条：IT 加白 / worker 放 99 网段。

### 工作区状态

本轮新增改动（均未提交）：`session.py`、`window_dock.py`、`recorder.py`、`web/src/components/layout/MainToolbar.tsx`、`web/src/App.tsx`、`web/src/theme.css`、`static/dist/*`（构建产物）。此前 10-27 指纹批次（13 文件 + 3 新测试）仍在工作区，两批改动混在一起，提交前按主题拆。

### 下一步

1. 用录制器真录一条 PO 卡片流程验证指纹（10-27 遗留，仍是最优先）
2. 本机完整跑通一次新尺寸录制，确认预检 + 窗口修复闭环
3. 找 IT 确认 aTrust 对 10.118→99 网段的临时拒连策略；worker 迁 99 网段（用户已定暂缓部署，拓扑方案已给：控制面+worker 都放服务器）
4. 录制器真录验证「站点放行预检」的事件流日志是否清晰

---

## 2026-10-27（定位层换成语义指纹：不再按站点/控件加特例）

### 一句话状态

定位从「固定 8 种候选 + 站点特例」改成**语义指纹 + 相似度打分**：元素用
角色/标签/占位符/文本/所在行格/所属分区等语义特征描述，候选全失效时在实时 DOM 里
按相似度找回来，双阈值（≥0.62 且领先第二名 ≥0.12）不满足就失败，绝不猜。
**141 真站端到端验证：候选故意全写废的 4 个 PO 卡片控件全部靠指纹命中并通过；旧流程 36/36 全绿。**

### 为什么改

上一轮的做法是「碰到认不出的控件就加一种候选 kind / 加一段站点特例」，等于每见一个没见过的
元素改一次代码——那不是测试平台该有的形态。用户要求的是 Katalon 式的通用录制回放：
**没见过的页面、改过版的控件也要能跑，而不是每个站点配一套补丁。**

### 做了什么

1. **协议**（`dsl.py`）：新增 `Fingerprint` 模型与 `Target.fingerprint`（旧流程没有该字段，
   行为完全不变）；`CandidateKind` 增加 `fingerprint`，仅用于展示命中来源。
2. **页面侧**（`locator_candidates.js`）：`fingerprintOf(el)` 产出语义描述，
   `fpScoreOf` 按特征权重算相似度，`__atpFindByFingerprint` 扫描可见元素、排序、
   打临时 `data-atp-hit` 标记；vxe 一类「表头与表体是两张 table」的表格按列头文本对齐列名。
3. **解析**（`locator.py`）：`resolve_by_fingerprint` 做轮询+双阈值+命中后 token 核对（防元素重绘点错）；
   `resolve_target` 改为**指纹优先**，有指纹时跳过无名 `role` 候选（`role=textbox` 会命中页面第一个输入框，
   静默错填），候选失败后再用指纹兜一次。
4. **回放注入**（`session.py`）：`locator_candidates.js` 改成上下文级 `add_init_script`。
   之前只有录制/踩点注入，回放页面里没有 `__atpFindByFingerprint`，指纹退路等于没接。
5. **落库**（`compiler.py` / `domain/recordings.py`）：录制结果一路保留 `fingerprint`，保存校验不丢字段。

### 验证

- `pytest tests/` → **71 passed，252.6s**，含新增 `test_fingerprint_resolve.py`（列换序+类名重生成、同款控件旁置、
  指纹相同的两个元素必须拒绝、指纹优先于无名 role、晚渲染元素的兜底自愈）、`test_recorded_fingerprint.py`（录制→编译→保存）、
  `test_session_locator_injection.py`（导航后页面必须有指纹函数）
- 141 真站回归（同一份「新建款式」，单进程串行）：`73bb8a1c` **passed，36/36，282.9s，零漂移**
- 141 真站端到端自愈（新流程 `b7c9d4e1`，卡片 4 个控件的候选全写成已删除的选择器）：
  `6c78c8d8` **passed 16/16**——PO单号 1.00、数量格 155/80A 1.00（次高 0.71）、
  160/84A 1.00（次高 0.71，与上一格区分开）、国家/地区 0.75（次高 0.58）、新增按钮 1.00
- 全程未点保存，没有往 141 写数据

### 踩到的坑

- **fingerprint 优先命中时不报 drift**：这是有意的——指纹是这些步骤的首选，不是「兜底撞上」。
  真正需要看见的「候选全废 → 指纹找回」由兜底路径给出，措辞为「定位自愈：…」。
- **回放注入**：只在录制/踩点注入会让自愈在回放时静默失效（`no fn` 时现在会明说缺脚本，
  而不是含糊地报「不够像」）。
- 抓「带回」之前要先把**打开款式弹窗**那一步描述成步骤；原来用裸坐标点，回放时没人替它点。

### 工作区状态

`dsl.py`、`__init__.py`、`locator.py`、`locator_candidates.js`、`session.py`、`actions.py`、
`compiler.py`、`domain/recordings.py`、`openspec/specs/locator-heal/spec.md`、本文件已改，**未提交**；
`var/_capture_po_flow.py`、`var/_run_po_flow.py` 是本次的现场脚本（未纳入版本库）。

### 下一步

1. 用录制器真录一条 PO 卡片流程（不是手写候选），确认录出来的指纹在回放里同样命中
2. 指纹阈值（0.62 / 0.12）目前只在 PO 卡片和单测里校准过，需要更多页面样本
3. 指纹命中在步骤表 Object 列已能看到（`fingerprint='…（相似度 x，次高 y）'`），
   但混在其它定位方式里不显眼；要扫读「哪些步骤是靠指纹自愈的」还得单独标一列/一个标记

---

## 2026-10-27（面板值 / tab 兜底 + `pick_panel_choice` 总预算）

### 一句话状态

面板里**录到的值不存在时改选一项**，不再直接跳过（tag 和 tab 都适用，跳过已选/已激活的）；
`pick_panel_choice` 的 `timeout_ms` 从「每次尝试的预算」改成「整次选择的总预算」。
**141 真站复跑整条通过：35 passed / 0 failed / 1 skipped，454.9s**
（修复前 28/1/7、1089.4s）。本地自测与 pytest 全绿。

### 做了什么

1. **面板分支兜底**（`actions.py` 的 `_do_click`）：`pick_panel_choice` 找不到录到的项后，
   先调 `pick_any_panel_choice` 在同类面板里选第一项，选到即 `passed`，说明写「没有「X」，已改选「Y」」。
   口径与既定「下拉随便选一个就行，能选中就可以」一致，也符合「像人肉冒烟测试」的用法。
   跳过会让必填字段空着，保存时才失败，报错还指向上一步（s31 就是这个形态）。
2. **tab 也兜底**：录到的 tab 不存在时换一个**未激活**的 tab；`_click_first_match` 新增
   `skip_active`，避免把「再点一次已激活 tab」这个空操作报成通过。
3. **`empty_choice=True` 的语义收紧**：现在只有在兜底也选不到可用项后才会走到它，
   注释已写明——原来面板里明明有别的颜色，也按「面板是空的」跳过。
4. **`pick_panel_choice` 总预算**（`locator.py`）：函数入口算 `deadline`，tab 循环、
   `_click_visible_named`、`wait_for_timeout` 全部用剩余预算；预算用完就收手。
   `_click_visible_named` 新增 `deadline` 参数，逐个元素遍历时也检查。
   **不再是每切一个 tab 给满一份 `timeout_ms`**，这是 141 单步 305s/361s/243s 的根因。
5. **兜底不能重复点已选项**（真站第一次复跑后补的）：多选面板里再点一次已选项会**取消选择**。
   新增 `_is_selected_panel_tag()`——选中态挂在外层 `.el-tag`（`--info` 变 `--primary`），
   而 `_PANEL_TAG` 定位到的是里面的 `.el-tag__content`，要往上找最近一层。
   兜底跳过已选项，全选中时确认字段有值、不再点；精确命中已选项时也不点。

### 验证

- `ruff check .` → All checks passed
- `scripts/selftest_optional_skip.py` → 16 条断言全过：色板缺项改选「黄色」；
  第二次兜底改选「青色」而不是重复点已选的「黄色」；已选项再点不取消；
  tab 缺项改选「裤装」；已激活 tab 不被重复点击
- `scripts/selftest_size_panel.py` → 新增「10 个 400ms 慢 tab + timeout_ms=800」场景：
  **旧实现 12.7s 判失败，新实现 0.9s 通过**（已验证这条测试确实抓得住回归）
- `scripts/selftest_click_effect.py` / `selftest_click_fallback.py` → 全过
- `pytest tests/` → 61 passed

### 141 真站验证

同一份用例（flow `3a054f6f-…`），**单进程**（公司限制请求数）：

| 运行 | 结论 | 通过 / 失败 / 跳过 | 时长 |
| --- | --- | --- | --- |
| 基线 `4f003a24`（10-19 前） | failed | 16 / 1 / 19 | 741.8s |
| `f24d8868`（10-19 修复后） | failed | 28 / 1 / 7 | 1089.4s |
| `1c50470a`（本轮第一次） | failed | 35 / 1 / 0 | 405.9s |
| `a6c62de1`（第二次，worker 未重启） | failed | 35 / 1 / 0 | 434.2s |
| `886999f3`（重启 worker 后） | **passed** | **35 / 0 / 1** | 454.9s |

- s12「SAD BLUE」不在 141 主数据 → 改选「1」，passed。
- s15–s18：155→155/80A、160→160/84A、165→165/88A、170→170/92A，各 9–12s
  （原来三步合计 910s）。
- s31 保存 passed（上两个版本都是这里 failed：先是「颜色 必填」，后来是「尺码 必填」）。
- s10 品牌「Gucci」本轮 skipped：s9 把下拉打开了但里面没有选项，141 上已知的
  「面板时有时无」抖动；品牌非必填，不影响保存。上一轮它兜底到「杰克」并 passed。
- s2 本轮 passed：`cusAuthRbacRolePermissionProxyQuery` 的 toast 没触发，
  **本次没有加任何临时屏蔽**。该部署问题仍在，下次仍可能撞上。

### 踩到的坑

**worker 是常驻进程，改了 `autotest_executor` 必须重启 worker。** 第二次复跑（`a6c62de1`）
35/1/0 就是拿旧代码跑的：s16–s18 仍重复点「155/80A」，白跑 434s。
重启后同一份代码才真正生效。

### 工作区状态

`actions.py`、`locator.py`、`scripts/selftest_optional_skip.py`、`scripts/selftest_size_panel.py`、
本文件已改，**未提交**。`ruff` 干净，pytest 全绿，141 真站整条通过。

### 下一步

1. `choose` 兜底一步要 60–90s（s8 66s、s10 90s）：`pick_first_dropdown_option` 的搜索/滚动
   循环值得按总预算收一下
2. `pick_panel_choice` 切 tab 前的「这个名字有没有可能出现在别的 tab」预判（本次只加了总预算）
3. 回 `locator-popup-fix` 第 6/7 节（选择器单一来源 / iframe 明确报不支持）

---

## 2026-10-19（141 真站：修复「新建款式」的 Escape 关弹窗）

### 一句话状态

`actions.py` 三处改动完成并验证：**关下拉不再关弹窗**、**嵌套弹窗关闭加固**、**下拉触发器判据收紧**。141 真站复跑通过率 16/36 → 28/36，13 步由 skipped 变 passed。剩余 1 处失败（s31 保存）已定位为**必填项「颜色」的数据不在 141 主数据里**，与本次修复无关。

### 做了什么

落点 `packages/executor/autotest_executor/browser/actions.py`：

1. **`_dismiss_dropdown()`（`:903`）** —— 先看有没有开着的下拉面板，没有就直接返回（不再无脑按 Escape）；面板开着且弹窗也在时，不按 Escape，改点触发器收起（新增 `_toggle_panel_closed()`，`:926`）；只有页面级下拉才保留 Escape。141 这个 Oinone 构建把 Escape 绑成「关弹窗」，跳过一个非必填字段就把整个「新增」表单关掉，后面 20 步全落在列表页上。
2. **`_dismiss_extra_dialog(dialogs_before)`（`:1155`）** —— 把「取消/关闭」的查找限定在最上层可见弹窗内，点不到再按 Escape，且只在嵌套层确实还在时才按。
3. **`_skip_optional()`（`:882`）** —— 加诊断网：关之前记弹窗数，关之后再看，原来是开着的、现在没了就**就地判红**（`overlay_absent`），而不是 skipped 后让失败推迟 20 步、还报成「浮层不存在」指错方向。
4. **`_click_opens_dropdown()`（`:1418`）** —— 删掉 `cand.kind == "field"` 分支。`field` 是定位器种类（`CANDIDATE_STABILITY` 排第 1），不是「这是下拉」的声明；留着它，任何带 field 候选的目标都要「点完出现下拉面板」才算过，输入框/数字框/文本域全被判成没生效。**这条是第 1 条能生效的前提**：`_do_click` 的 `no_effect` 失败路径（`:571-583`）绕过 `_should_skip_optional`，非必填也照样判红。

测试：`scripts/selftest_optional_skip.py` 新增第二个场景（弹窗 + Escape 关窗 + 点触发器切换面板），断言「跳过非必填后弹窗必须还在」。已用「临时把旧 Escape 路径放回去」验证过这条测试确实抓得住回归。

### 验证

- `ruff check .` → All checks passed
- `scripts/selftest_optional_skip.py` → 5 条断言全过
- `pytest tests/` → 见下「工作区状态」处的复跑记录
- 141 真站单进程复跑 → 见「141 真站对照」

### 141 真站对照

同一份用例（flow `3a054f6f-ecf0-4b39-9765-5b501de4d2ae`），**单进程**（公司限制请求数）：

| | 基线 `4f003a24` | 修复后 `f24d8868` |
| --- | --- | --- |
| 结论 | failed | failed |
| 通过 / 失败 / 跳过 | 16 / 1 / 19 | **28 / 1 / 7** |
| 时长 | 741.8s | 1089.4s |

**关键证据**：s10（当初触发 Escape 的那一步）跳过后，「新增」弹窗仍在（运行录像抽帧 + `36_s31.png` 确认）。s11/s13/s14/s16/s19/s21/s22/s24/s25/s26/s27/s29/s30 共 **13 步**由 skipped「找到但点不到 / 目标所在浮层没有出现」变为 passed。

时长上涨是因为原来被跳过的步骤现在真的执行了；并且 s15/s17/s18 三步合计吃掉 **910s**（见下「新发现」），其余全部步骤合计仅 179s。

### 剩余失败：s31 保存

`页面报错：颜色 必填`。与基线的 `overlay_absent` **不是同一个失败**：基线是平台把弹窗关了；现在是弹窗在、保存按钮点到了、**应用自己拒绝**。

根因：s11 打开颜色下拉 → s12 点「SAD BLUE」→ 141 的颜色主数据里没有 SAD BLUE → 跳过 → 颜色是必填 → 保存被拒。s31 截图里款名、尺码=160、成本 99,00、图片、描述都已填好，只差颜色。

#### 改法（未实施，待定）

- **数据侧**：把用例的颜色值对齐 141 主数据。
- **平台侧**（与既定口径「下拉随便选一个就行，能选中就可以」一致）：`_do_click` 的**面板选择分支**（`:498`）找不到就直接跳过，没有兜底；而同函数的**选项分支**（`:527`）有 `pick_first_dropdown_option` 兜底。两条分支不对称。改法：面板分支在跳过前先试一次「选第一条可用项」。
- 顺带一个小洞：`:512` 传 `empty_choice=True` 是**无条件**的。面板里明明有一堆别的颜色，却按「面板是空的」处理（判据在 `should_skip_optional_miss`，`:296-304`）。

### 新发现（未修，独立问题）

**`pick_panel_choice` 的 tab 遍历没有总预算。** 落点 `packages/executor/autotest_executor/browser/locator.py:1098`，当前 tab 找不到就挨个切 tab 全量重扫（`:1134-1152`）。`timeout_ms` 是**每次调用**的预算、不是总预算，tab 循环把它乘了好几倍；141 每切一个 tab 还要发一次请求拉该 tab 的尺码表。实测 s15/s17/s18（数据里不存在的尺码）分别耗时 **305s / 361s / 243s**。改法：给函数一个总 deadline（`time.monotonic() + timeout_ms`）并在 tab 循环里检查；切 tab 前先判断这个名字有没有可能出现在别的 tab。

### 环境坑（重要）

1. **141 部署自身的报错 toast**：每次跑到 s2 抛 `Unknown field 'cusAuthRbacRolePermissionProxyQuery'`，`runner.py:_attach_page_toasts` 会判成「页面报错」→ s2 failed。用户已定**不在本次范围**。本次两次对照运行都带着同一份**临时屏蔽**（只过滤这一条）跑，屏蔽在跑完后**已删除**（`git diff runner.py` 为空）。**该部署不修，下次真站跑仍会死在 s2。**
2. **s8「品类=T恤」这轮是 skipped，基线里是 passed**：s7 结束时截图显示下拉开着、10 个选项都在，s8 却报「也没有可兜底的选项」。s8 走的 `_do_choose` / `_choose_for_create` 本次未改，且基线里 s10/s12/s14 也报过同样的「找不到」，判定为 141 上「面板时有时无」的环境抖动，不是回归。
3. 跑 pytest 必须用 `.venv/Scripts/python.exe`（老坑，见上一轮）；`ruff` 不在 venv 里，用 PATH 上的。

### 工作区状态

`actions.py`、`scripts/selftest_optional_skip.py` 已改，**未提交**。`runner.py` 的临时屏蔽已还原，工作区与暂存区一致。`ruff check .` 干净。

### 下一步

1. 定「面板分支兜底」要不要做（做了 s31 大概率能过）。
2. 治 `pick_panel_choice` 的总预算。
3. 141 部署修 `cusAuthRbacRolePermissionProxyQuery`，否则真站验收永远卡在 s2。

---

## 2026-10-12（第二轮：执行收尾）

### 一句话状态

`restructure-debt` 已完成（余真站验收）；`locator-popup-fix` 代码完成 5/7 节，余第 6、7 节；`ci-daily-gate` 仍是纯提案。**本轮未写任何代码，工作区未提交。**

### 本轮做了什么

只有调查与验证，**零代码改动**：

1. **确认测试基线**：`.venv/Scripts/python.exe -m pytest tests/ -q` → **61 passed in 294.25s**，与文档记录一致。
2. **摸清第 6 节的实际范围**，比计划里写的更大（详见下）。
3. **确认第 7 节是全空的**：全仓源码（`packages/` `apps/control-plane/autotest_control` `scripts/` `tests/`）**没有任何 iframe 处理代码**，要从零加。
4. **发现一处必须先解除的耦合**（见下「第 6 节的两个约束」第 2 条）。

### 环境坑（重要，别再踩）

跑 pytest **必须**显式用 `.venv/Scripts/python.exe`。

PATH 上的 `python` 解析到 `C:\Users\EDY\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`，**里面没装 playwright**。用它跑 pytest 会在**收集阶段**就失败（`ModuleNotFoundError: No module named 'playwright'`，来自 `tests/test_locator_failure_kind.py` 顶层的 playwright 导入），看起来像代码坏了，其实只是解释器错了。

全量测试约 5 分钟，改单模块时只跑相关测试文件。

### 各 change 状态

| change | 状态 | 说明 |
| --- | --- | --- |
| `restructure-debt` | 25/27 | 代码全完成，`ruff check .` 干净。仅 6.2 真站回放验收挂起（需福瑞丝环境 + 能跑 headed 的 Worker） |
| `locator-popup-fix` | 32/47 | 第 2–5 节代码完成（可见性收敛 / 点击回退 / 去静默通过 / 失败分类）。余第 6、7 节与验收 |
| `ci-daily-gate` | 0/18 | **只有 proposal / design / spec / tasks 四份文档，一行代码没写**。闸门脚本不存在 |
| `ai-compiler-p1-2` | 21/22 | 代码完成；余真站现录验收（挂起原因已写进其 `tasks.md`） |
| `ai-observer-p1-2` | 21/22 | 同上 |

### 第 6 节（选择器单一来源）的实际范围

计划里写的是「改两处常量」，实际涉及约 **15 个文件**：

- `packages/adapters/autotest_adapters/oinone/selectors.py` —— 40+ 个顶层名字要分类：通用件迁出 / 厂商特例留下
- 两个 JS 文件各有一份：`browser/locator_candidates.js`（`PORTAL_SEL` / `STD_OPTION_SEL` / `STD_DROPDOWN_SEL` / `ACTION_HOST_SEL` / `OVERLAY_SEL` / `COMBO_HOST_SEL`）、`browser/observer_snapshot.js`（`OVERLAY_SEL` / `PORTAL_SEL` / `OPTION_SEL`）
- 加载这两个 JS 的地方共 6 处：`recorder.py:39`、`onboarding.py:16`、`scripts/inspect_page.py:19`、`scripts/selftest_field_anchor.py:26`、`scripts/selftest_matrix_grid.py:19`、`scripts/selftest_size_panel.py:17`、`tests/test_observer_collect.py:13`

**分层是安全的**：`packages/adapters` 不引用 `packages/executor`（已验证），所以通用件迁进执行器不会造成循环导入。

**但 `SIDEBAR_MENU_ITEM` / `SIDEBAR_SUBMENU_TITLE` 必须留在 `oinone/`**：它们被同目录的 `navigation.py` 使用，而 `navigation.py` 是厂商特例，本来就该在适配器里。

`oinone/__init__.py` 的包级 `__all__` 导出（`LIVE_MODAL` / `LIVE_DROPDOWN` / `DROPDOWN_PANEL` / `DROPDOWN_OPTION` / `click_sidebar_menu`）**全仓无外部使用者**（已验证），迁出后需同步处理。

### 第 6 节的两个约束（动工前必须知道）

1. **Playwright 的 `:visible` 不能在原生 DOM JS 里用。** Python 侧选择器可以用 `:visible`（仓库在用），但注入到页面的 JS（`locator_candidates.js`、`observer_snapshot.js`）用的是原生 `querySelector`，**不认** `:visible`，只能靠类名过滤（如 `:not(.ant-select-dropdown-hidden)`）加 `isShown()` 判定。所以「JS 与 Python 共用同一份选择器」不能是字面量的同一份——JS 侧要么接收注入的常量并换算，要么保留一份带可见性判定的变体。设计决定 6 写的是「JS 侧通过注入时传入」，落地时要解决这个换算，不能直接照搬 Python 的 `:visible` 串。

2. **`wait_any_dropdown_panel` 必须与第 6 节一起改。** `browser/locator.py` 里这个函数的 docstring 明确写着：取并集是为了**不把原本能过的用例判成「点了没生效」**，并写明「收窄口径是『选择器单一来源』那一节的事，不在这里顺手做」。所以第 6 节收窄 `DROPDOWN_PANEL` / `DROPDOWN_MIXED_VISIBLE` 时，这个函数**必须一并处理**，否则第 4 节刚加的动作生效确认会开始造假失败。它的调用点是 `actions.py:601`（`_confirm_dropdown_opened`）。

### 第 7 节（iframe 记为不支持）

全空的，要从零加。`TargetScope`（`packages/protocol/autotest_protocol/dsl.py:93`）只有 `page` / `modal` / `drawer` / `dropdown` 四种 kind，没有 frame 维度。要做的是**明确报不支持**（不产出偶发失败），不是支持 iframe。

### 下一步（依赖顺序）

1. `locator-popup-fix` 第 6 节（**先解除上面第 2 条的那个耦合**）
2. `locator-popup-fix` 第 7 节
3. `ci-daily-gate` 闸门脚本 + CI 接线
4. 真站验收（`restructure-debt` 6.2、`locator-popup-fix` 8.3/8.4）—— **需要真环境，本机做不到**，见下

### 做不到的部分（不要假装完成）

以下验收都需要真控制面 + 真 Worker + 能访问福瑞丝（`http://192.168.99.165:8000`）的环境，**本机不具备**：

- `restructure-debt` 6.2 真实回放
- `locator-popup-fix` 8.3 真站重复执行浮层用例连续 5 次全过
- `locator-popup-fix` 8.4 人为制造三类失败核对报告
- `ci-daily-gate` 4.1–4.5 端到端验收

静态层面（`ruff`、`pytest`、模块导入）能覆盖，但「为副作用而存在的导入」「真站元素是否稳定」这类问题只有真实回放能兜住。

### 工作区状态

**全部未提交，也没有 stage。** `git status --short` 共 42 项（35 修改 + 7 未跟踪）。上次提交 `6616b24`（2026-09-21）。

`restructure-debt` 与 `locator-popup-fix` 的改动**混在同一个工作区里**，建议提交前按 change 拆开。

---

## 2026-10-12（第一轮：文档与 OpenSpec 记录）

产出：改写 `openspec/config.yaml` 定盘口径；新建三个 change（`locator-popup-fix` / `restructure-debt` / `ci-daily-gate`）；修订 `docs/platform-restructure-plan.md`（§5 保留意见、§5 之后的依赖顺序、§6.6 多租户暂缓非取消）、`docs/katalon-gap-and-requirements.md`（§3 施工顺序）、`docs/p1-record-heal-chat.md`（P1.3 / P1.5 降级为按需）；同步 `README.md`「还没做」「方向与排期」；修订两个 `ai-*-p1-2/tasks.md` 的备注口径。

`docs/ui-baseline/` 与 `ui-katalon-shell` 的 0.1 / 6.4 **刻意不动** —— 那两条标的是「持续」，是常驻职责不是未完成项。

原计划见（会话外）：`C:\Users\EDY\.claude\plans\snuggly-gathering-lightning.md`
