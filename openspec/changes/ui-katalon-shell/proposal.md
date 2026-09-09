## Why

控制面 React 前端已完成模块化拆分（ActivityBar / Sidebar / Editor / BottomLog），但视觉仍是深色 VS Code 风，与测试工程师熟悉的 **Katalon / Eclipse 式桌面 IDE** 差异大。团队希望界面更像「专业测试工具」：浅色、高密度、树形资源管理、图标工具栏、底部多 Tab 输出——降低学习成本，同时不改变现有业务行为。

## What Changes

- 引入 **Katalon 复古 IDE 视觉体系**：浅灰底、1px 边框分区、矩形 Tab、小字号高密度
- 重构 **外壳布局**：顶栏密集工具条 + 左 Explorer 树 + 中 Tab 工作区 + 底面板 Tab
- **ActivityBar** 从文字条改为图标竖栏（站点 / 录制 / 运行 / 历史 / 日志）
- **侧栏** 统一为 Tests Explorer 风格：搜索框 + 树形节点 + 类型图标
- **底栏** 从单一日志改为 Tab 面板（输出 / 步骤 / 告警），步骤视图表格化
- **模块内工具栏**（录制、运行）改为图标按钮组 + 分隔线，对齐 Katalon Record / Run 区
- 保留全部现有功能与 API 调用；**零后端变更**

## Capabilities

### New Capabilities

（无 — 纯 UI 换肤与布局，不涉及新业务行为）

### Modified Capabilities

（无）

本 change 在 `.openspec.yaml` 标记 `skip_specs: true`：外观与信息架构调整，验收以视觉对照与现有 E2E/手工回归为准。

## Impact

- **前端**：`apps/control-plane/web/src/theme.css`、layout 组件、各模块 Sidebar/Toolbar
- **依赖**：可选引入轻量图标库（如 lucide-react 或内联 SVG），不引 UI 框架
- **不影响**：FastAPI API、Worker 协议、录制/回放逻辑
- **风险**：浅色主题下 pass/fail 色需重新校准对比度；改 layout 时勿破坏 Tab/Context 状态
