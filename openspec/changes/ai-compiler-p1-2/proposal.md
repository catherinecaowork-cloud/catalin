## Why

P1.1 已证明「开窗录制 → 确定性清洗 → 人工确认 → 回放」闭环成立，但步骤仍是机械 label、无断言推断、无参数化，第二次回放容易撞唯一性校验。P1.2 在**不替换** P1.1 底座的前提下，引入 Compiler 层：只在录制结束后调模型，把草稿升级为语义化、可参数化、带断言的流程，并**必须经自动回放自证**后才默认可保存。

## What Changes

- 录制任务必填「录制意图」，作为 AI 编译输入
- 执行器采集脱敏的 `compiler_context`（页面文本、有限请求摘要、语义步骤），供控制面编译
- 控制面新增 Anthropic Messages 兼容 Compiler：严格 JSON 契约，不得改写 action/target/顺序
- 编译产物自动触发无头回放验证，失败最多重编译 3 轮；仍失败或模型不可用时回退 P1.1 确定性步骤
- 步骤支持 `phase`（setup/main/verify）与变量模板 `{{unique}}` / `{{now}}` / `{{env}}`，回放前解析
- 控制台展示编译/验证进度；默认只允许保存已验证版本，人工改步骤后需显式以 draft 保存
- 非 test/dev 环境不自动执行写操作验证，停在「待人工验证」

## Capabilities

### New Capabilities

- `ai-compiler`: 录制后 AI 编译、契约校验、最多 3 轮回放验证、回退与持久化状态机
- `step-variables`: 步骤 value/expected 的参数化模板与单次运行解析规则
- `recording-intent`: 录制意图采集与随任务传递

### Modified Capabilities

- `browser-replay`: 回放前解析步骤中的变量模板；步骤可选 phase 元数据
- `flow-lifecycle`: 保存流程时默认要求编译验证通过；允许显式保存未验证 draft

## Impact

- **控制面**：`ai/` 模块、`compilation_worker`、`RecordingCompilation` 表、录制/编译 API、控制台确认 UI
- **执行器**：`variables.py`、录制 summary 扩展；日常已保存流程回放仍零模型调用
- **协议**：`Step.phase`、`Job.record_intent`、`Job.variables`
- **配置**：`ANTHROPIC_*` 环境变量（密钥不落库）；可选 `ATP_AI_VISION_ENABLED`
- **未纳入**：`{{pick:实体}}`、完整 HAR/L1 用例、对话入口（P1.4）、Reviewer（P1.6）
