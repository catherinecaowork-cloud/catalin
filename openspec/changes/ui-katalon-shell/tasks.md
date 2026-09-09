# UI Katalon 复古 IDE 改造 — 分步任务

> OpenSpec change: `ui-katalon-shell`  
> 原则：**每步零行为变化**，只改视觉与布局；每步结束可 `npm run build` + 手工点一遍五模块。

---

## Phase 0 — 准备（0.5 天）

- [ ] 0.1 在 `apps/control-plane/web` 截当前五模块基准截图（站点/录制/运行/历史/日志），存 `docs/ui-baseline/`
- [x] 0.2 确认 dev 命令：`npm run dev` / build 路径
- [x] 0.3 安装图标依赖：`npm i lucide-react`（仅 web 包）

**验收**：基准图齐全；build 通过。

---

## Phase 1 — 设计令牌与全局浅色主题（1 天）

**目标**：整页从深色 VS Code 变为 Katalon 浅灰 IDE，组件结构不动。

- [x] 1.1 在 `theme.css` 替换 `:root` tokens（见 `design.md` Visual Tokens）
- [x] 1.2 调整 `body`：`color-scheme: light`；背景 `--bg-workbench`
- [x] 1.3 逐类更新外壳：`.titlebar` `.activity` `.sidebar` `.editor` `.bottomlog` `.tabstrip` `.etab`
- [x] 1.4 更新表单控件：`.btn` `.input` `.select` `.modal` pass/fail 色对比度
- [x] 1.5 Tab 样式：激活 Tab 白底 + 底边框消失；非激活灰底 `#E8E8E8`
- [x] 1.6 `explorer-item.selected` 改为浅蓝选中 `#D6EAF8`（非深色 `#243044`）

**涉及文件**：`theme.css`（主），必要时微调 `components/ui/*.tsx` 内联 style

**验收**：
- 五模块均可打开，无白字白底/黑字黑底
- Tab、侧栏、日志区边界清晰（1px `#C8C8C8`）
- pass/fail/warn 在浅色底可读

---

## Phase 2 — ActivityBar 图标化 + TitleBar 收紧（0.5 天）

**目标**：左侧模块切换像 VS Code/Katalon 图标栏。

- [x] 2.1 新建 `components/layout/moduleIcons.tsx`：`site→Globe`, `record→CircleDot`, `run→Play`, `history→Clock`, `log→Terminal`
- [x] 2.2 改 `ActivityBar.tsx`：36px 宽、只显示图标，`title` 作 tooltip
- [x] 2.3 激活态：左侧 2px 色条（模块色）+ 浅灰背景
- [x] 2.4 `TitleBar` 高度 32px；`WorkerBar` 按钮改为 compact 图标按钮
- [x] 2.5 `SiteChip` 样式对齐 Katalon 项目选择器（白底、FolderOpen + ChevronDown）

**涉及文件**：`ActivityBar.tsx`, `TitleBar.tsx`, `WorkerBar.tsx`, `SiteChip.tsx`, `theme.css`

**验收**：模块切换正常；图标可识别；Worker 开始/停止仍可用

---

## Phase 3 — Explorer 侧栏树形化（1.5 天）

**目标**：左栏像 Katalon Tests Explorer。

- [x] 3.1 新建 `components/patterns/ExplorerTree.tsx`：
  - 节点类型：`folder` | `flow` | `suite` | `run` | `draft`
  - props: `nodes`, `filter`, `onFilterChange`
- [x] 3.2 侧栏头：`Tests Explorer` + 模块副标题；树内搜索框
- [x] 3.3 改 `RunSidebar` / `HistorySidebar` + `AppSidebar` explorer 模式
- [x] 3.4 树节点 lucide 图标；缩进 14px/层；折叠 chevron
- [x] 3.5 运行：`测试用例` / `套件` 文件夹；历史：`运行记录` 文件夹

**涉及文件**：`ExplorerTree.tsx`, 各 `*Sidebar.tsx`, `theme.css`（`.tree-node` 等）

**验收**：
- 搜索过滤生效
- 点击节点行为与改前一致（打开 Tab / 选中 run）
- 折叠/展开不影响选中态

---

## Phase 4 — 模块工具栏图标化（1 天）

**目标**：录制/运行区头像 Katalon Record Web / Run 工具条。

- [x] 4.1 新建 `components/patterns/ModuleToolbar.tsx`（Group / Sep / Button / Badge / Label）
- [x] 4.2 改 `RunToolbar.tsx`：Play 标题 + Activity 状态徽章
- [x] 4.3 改 `RecordEditorBody` / `RecordDraftWorkspace`：脚本切换、重新编写、保存
- [x] 4.4 工具栏高 28px；组间竖线分隔
- [x] 4.5 `EditorLayout.tsx` toolbar slot 支持 ReactNode

**涉及文件**：`ModuleToolbar.tsx`, `RunToolbar.tsx`, `Record*.tsx`, `EditorLayout.tsx`

**验收**：所有原按钮功能保留；disabled 态清晰

---

## Phase 5 — 底栏多 Tab 面板（1.5 天）

**目标**：底部像 Katalon Console / Problems。

- [x] 5.1 新建 `components/layout/BottomPanel.tsx` 替代 `BottomLog.tsx`：
  - Tabs: `输出` | `步骤` | `告警`
- [x] 5.2 **输出 Tab**：现有 log 行，等宽字体 11px
- [x] 5.3 **步骤 Tab**：`StepTable` + `BottomPanelContext` 订阅 run stream
- [x] 5.4 **告警 Tab**：复用 `AlertPane` 展示 probe.alert
- [x] 5.5 面板头：Tab + 清空/收起；高度 180px
- [x] 5.6 `AppEditor` 接入；`RunWorkspace` 发布 steps/alerts

**涉及文件**：`BottomPanel.tsx`, `App.tsx`, `StepRow.tsx`（或新 `StepTable.tsx`）, `theme.css`

**验收**：
- 回放时步骤 Tab 实时更新、耗时列可见
- 切换 Tab 不丢日志
- 折叠/展开与改前一致

---

## Phase 6 — 细节打磨与文档（0.5 天）

- [x] 6.1 空态页：`StartPage` Quick Links（站点/录制/运行/历史）
- [x] 6.2 运行截图区 `shot-pane` / `img.shot` 浅灰边框
- [x] 6.3 Modal 标题与正文浅色对齐
- [ ] 6.4 与 Phase 0 基准截图对比，修遗漏（需本地目视）
- [x] 6.5 更新 `docs/ui-katalon-redesign-plan.md`；build 通过

**验收**：团队目视认可「Katalon 复古 IDE 风」；`npm run build` 成功

---

## 实施顺序（给 AI / 开发者）

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
   ↑         ↑
  截图      最先合，风险最低
```

**建议第一步**：从 **Phase 1** 开始（你确认计划后我说「开始 Phase 1」即动手改 `theme.css`）。

---

## 不在本 change 内

- 对象库 / Spy Web
- 暗色主题切换
- 后端 API 变更
- Playwright 录制逻辑变更
