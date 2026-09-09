# UI Katalon 复古 IDE 改造

> OpenSpec change: [`ui-katalon-shell`](../openspec/changes/ui-katalon-shell/)  
> 基准截图说明: [`ui-baseline/README.md`](ui-baseline/README.md)

## 目标

将 control-plane React 控制台从深色 VS Code 风，改为 **Katalon Studio 式浅色复古 IDE**：高密度、左树 Explorer、图标工具栏、底栏多 Tab。

## 阶段完成情况

| Phase | 内容 | 状态 |
|-------|------|------|
| 0 | 准备（lucide-react、基准截图目录） | 完成 |
| 1 | 全局浅色 theme tokens | 完成 |
| 2 | ActivityBar 图标化 + TitleBar 收紧 | 完成 |
| 3 | Explorer 侧栏树形化 + 搜索 | 完成 |
| 4 | ModuleToolbar 模块工具栏 | 完成 |
| 5 | BottomPanel 输出/步骤/告警 | 完成 |
| 6 | StartPage Quick Links、截图/Modal 打磨 | 完成 |

## 主要文件

- `apps/control-plane/web/src/theme.css` — 设计令牌与组件皮肤
- `apps/control-plane/web/src/components/layout/` — StartPage、BottomPanel、Sidebar
- `apps/control-plane/web/src/components/patterns/` — ExplorerTree、ModuleToolbar
- `apps/control-plane/web/src/context/BottomPanelContext.tsx` — 运行步骤/告警馈送

## 本地预览

```powershell
cd apps/control-plane/web
npm run dev
```

或重启控制面后刷新静态资源（`npm run build` 输出到 `autotest_control/static/dist/`）。

## 验收清单

- [ ] 五模块均可打开，浅色主题无对比度问题
- [ ] 运行回放时底栏「步骤」Tab 实时更新
- [ ] 侧栏 Tests Explorer 可搜索、折叠
- [ ] 无 Tab 时 StartPage Quick Links 可跳转模块
