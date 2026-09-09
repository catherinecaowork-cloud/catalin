## Why

运行模块此前只能单条点选，草稿与用例在界面上分不清，确认只能走接口；本机执行器工作区还把每次运行的 UUID 目录堆在 `var/worker-ui`。同一天还补上了控制台 AI 配置、定位漂移须人工确认才写回。需要把这些已落地行为收成可验收规格，并同步到主 specs。

## What Changes

- 运行侧栏：草稿可「确认为用例」，用例显示「退回草稿」；非草稿不可删除（控制台隐藏删除、接口 409）
- 勾选已确认用例一次按序跑，可存成套件（详见并行 change `flow-suites`）
- 控制面产物只留最近 5 次运行；`worker` / `worker-ui` / `worker-headless` 的运行目录跑完清空，身份文件保留
- 回放定位漂移汇总成一条修补任务，用户确认后才改对应步骤的 `candidates`
- 顶栏 AI 配置写入 `var/ai.json`，保存后以文件为准；GLM 等走 Chat Completions 而不是 Anthropic Messages

## Capabilities

### New Capabilities

- `artifact-retention`: 运行产物与执行器工作区保留策略
- `locator-heal`: 监督者汇总漂移、执行者确认后只改列出的定位
- `ai-gateway-config`: 控制台网关配置落盘、测通、按模型选择协议

### Modified Capabilities

- `flow-lifecycle`: 控制台显式确认 / 退回草稿；用例不可删除

## Impact

- **控制面**：流程状态 API、删除门禁、套件/批次（`flow-suites`）、heal 任务、AI 配置、产物清理
- **控制台**：运行模块按钮与勾选、AI 弹窗、修补确认弹窗
- **执行器**：跑完删除本机运行目录；启动时清残留
- **未纳入本 change 文档**：同会话连续回放、套件进 CI（见 `flow-suites`）
