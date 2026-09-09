## Context

现有控制台骨架（`App.tsx` → `Workbench` → `ActivityBar` + `Sidebar` + `AppEditor` + `BottomLog`）已具备 IDE 三区布局。本次只换 **皮肤 + 信息密度 + 部分组件形态**，不碰 Context / hooks 业务逻辑。

参考：Katalon Studio 9 — 浅灰 `#F0F0F0` / `#E1E1E1`、白工作区、16px 彩色 flat 图标、左树 Explorer、顶栏分组工具条、底栏 Problems/Console Tab。

## Goals / Non-Goals

**Goals:**

- 一眼识别为「测试 IDE」，不是通用 SaaS 后台
- 功能入口更密：录制/运行/Worker 控制在顶栏或模块工具栏一次可见
- 左栏树形浏览站点 → 套件 → 流程 / 录制草稿 / 历史 run
- 底栏可切换：平台日志、当前 run 步骤表、探针告警
- 分 6 个阶段交付，每阶段可独立验收、可回滚

**Non-Goals:**

- 不做主题切换（暗/亮）；第一版固定 Katalon 浅色
- 不新增 Object Repository、Spy Web 等业务功能
- 不重写 Context 层；不迁移到 Ant Design / MUI
- 不做移动端适配

## Visual Tokens（design tokens）

```css
/* 背景层级 */
--bg-workbench:   #F0F0F0;   /* 外壳、ActivityBar */
--bg-panel:       #E8E8E8;   /* 侧栏、工具栏 */
--bg-editor:      #FFFFFF;   /* 编辑区、Tab 内容 */
--bg-input:       #FFFFFF;

/* 边框 */
--border:         #C8C8C8;
--border-light:   #D4D4D4;

/* 文字 */
--text:           #222222;
--text-muted:     #6E6E6E;
--text-section:   #444444;   /* QUICK LINKS 式小标题 */

/* 状态色（测试语义，略饱和） */
--pass:           #2E7D32;
--fail:           #C62828;
--warn:           #E65100;
--accent:         #1565C0;

/* 模块色（ActivityBar / Tab 左边条） */
--c-site:         #1565C0;
--c-record:       #E65100;
--c-run:          #2E7D32;
--c-history:      #6A1B9A;
--c-log:          #546E7A;

/* 尺寸 */
--font-size:      12px;
--font-size-sm:   11px;
--toolbar-h:      28px;
--titlebar-h:     32px;
--activity-w:     36px;
--sidebar-w:      260px;
--bottom-h:       180px;
--icon-size:      16px;
--radius:         2px;       /* 几乎直角，Katalon 风 */
```

字体：`Segoe UI`, `Microsoft YaHei`, system-ui；行高 1.35。

## Layout 对照

```
┌─────────────────────────────────────────────────────────────┐
│ TitleBar: [ATP] [站点▼] [Tab Tab Tab ...]    Worker 开始 停止│  ← 32px
├─────────────────────────────────────────────────────────────┤
│ MainToolbar: [▶运行][■停止] | [录制] | [AI] ...              │  ← 28px 可选合并到模块
├──┬──────────────────────────────────────────────────────────┤
│A │ Explorer          │  Editor Tab Content                  │
│c │ [🔍 filter]       │  ┌─ toolbar ─────────────────────┐   │
│t │ ▼ 站点            │  │ 模块操作按钮组                  │   │
│  │   ▼ 套件          │  └───────────────────────────────┘   │
│B │     流程 A        │  [步骤列表 / 截图 / 表单 ...]         │
│a │     流程 B        │                                      │
│r │   ▼ 录制草稿      │                                      │
│  │   run #123        │                                      │
├──┴──────────────────┴──────────────────────────────────────┤
│ [输出] [步骤] [告警]                              [清空][×]  │
│ ─────────────────────────────────────────────────────────── │
│ 表格 / 日志行 ...                                            │
└─────────────────────────────────────────────────────────────┘
```

## Component 映射

| 现有 | 改造后 |
|------|--------|
| `theme.css` `:root` 暗色 | 新 tokens + 组件类名保留，只改值 |
| `ActivityBar` 文字按钮 | 36px 图标栏 + tooltip |
| `Sidebar` + `ExplorerItem` 平铺列表 | `ExplorerTree`：可折叠节点 + 搜索 |
| `TitleBar` | 保持；Tab 改矩形白底激活态 |
| `editor-toolbar` 纯文字 | `ModuleToolbar`：图标 + 分隔符 |
| `BottomLog` 单面板 | `BottomPanel`：Tab + 步骤表格视图 |
| `StepRow` 卡片式 | 表格行：状态点 / 描述 / 动作 / 耗时 |

## Decisions

1. **CSS 变量驱动，不引 Tailwind** — 与现有 `theme.css` 单文件习惯一致，diff 可控。
2. **图标用 lucide-react** — 16px stroke，MIT，Tree-shaking；若 bundle 敏感则 Phase 6 再换内联 SVG。
3. **Explorer 树先「视觉树」，数据仍扁平** — Phase 3 用 CSS 缩进 + 折叠 state，不强制改 API；套件/流程层级用现有 `Suite`/`Flow` 数据组装。
4. **底栏步骤 Tab 只在 run 模块或有 active run 时启用** — 避免空 Tab。
5. **每 Phase 独立 PR/commit** — 便于 review；Phase 1 仅 tokens 也可先合。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 大改 CSS 导致遗漏组件样式 | Phase 1 加 `--legacy-compat` 过渡；逐模块截图对比 |
| 树形 Explorer 与多 Tab 打开逻辑冲突 | 树节点 click = 现有 `openTab`；不改变 Tab 状态机 |
| 浅色下截图预览边框不清 | 截图区加 `#D4D4D4` 1px 框 |
| lucide 增 bundle | 只 import 用到的图标 |

## Migration Plan

无数据迁移。部署后 `npm run build` 刷新静态资源即可。开发时 `npm run dev` 逐 Phase 验收。

## Open Questions

- 顶栏 MainToolbar 是全局一条，还是各模块 `editor-toolbar` 各自一条？**建议**：Worker/AI 留 TitleBar 右；录制/运行动作进模块 toolbar（更接近 Katalon）。
- 是否需要「开始页」空态（Quick Links）？**建议**：Phase 5 做简单欢迎页，非必须。
