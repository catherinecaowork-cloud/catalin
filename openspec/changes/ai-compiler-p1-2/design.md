## Context

见 [proposal.md](proposal.md)。P1.1 的 `compile_events()` 仍是不可替代的确定性预处理；P1.2 在其输出之上加 Compiler，而不是把 raw events 直接交给模型。

继承 P1.1 三条红线：控制面不碰浏览器；执行器不连库；已保存流程的日常回放零模型调用。

## Goals / Non-Goals

**Goals:**

- 模型只改 label / phase / mutating / value，并追加断言；action、target、顺序不变
- 编译产物过 DSL 校验后自动无头回放；通过才算「已验证」
- 模型不可用或 3 轮失败时，回退 P1.1 步骤，不阻断手工保存 draft
- 唯一性字段参数化为 `{{unique:key}}`，同次运行内一致

**Non-Goals:**

- `{{pick:品类}}` 与夹具库（P1.6）
- 完整 HAR 抓取与 L1 接口用例生成
- 对话入口与 Router（P1.4）
- 多模态视觉复核（P1.5）；截图送模型默认关闭

## Decisions

### D1：Compiler 跑在控制面，验证回放仍派 Worker

**为什么**：遵守「控制面不装浏览器」。编译与编排是 I/O + 模型调用；浏览器只在 Worker。

**备选**：Worker 内调模型——会把密钥与编排逻辑散到多机，且难做持久化状态机。

### D2：Anthropic Messages 兼容网关 + httpx

**为什么**：公司网关已按此形态部署；不引额外 LLM SDK，MockTransport 可单测。

**配置**：`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`；缺配置时识别为 `ai_configuration_missing` 并回退。

### D3：严格 JSON 契约 + 白名单应用

模型输出 `step_edits + assertions + notes`；应用前校验：不得改 action/target；模板仅 `unique/now/env`；断言 target 只能引用已有步骤 id。

### D4：持久化状态机 `recording_compilation`

状态：`queued → compiling → validating → passed | manual_validation | fallback | error`。

后台线程扫描 DB，控制面重启后可继续。验证 run 不建 Flow，job 自包含步骤。

### D5：变量在 RunExecutor 执行前深拷贝解析

只解析 `value` / `expected`，不展开 `target`；`env` 只读 Job.variables，不读进程环境。

### D6：录制上下文有界且脱敏

同源 JSON 请求 ≤30 条；递归脱敏 password/token/cookie；不保存无限 raw events。

## Risks / Trade-offs

| 风险 | 缓解 |
| --- | --- |
| 模型改坏步骤 | 契约禁止改 target；验证回放 gate；3 轮后回退 |
| 自动验证写脏数据 | 仅 test/dev 环境自动验证；其他环境 manual_validation |
| 模型成本 | 仅录制后编译；记录 token usage；日常回归零调用 |
| 网关不可用 | 回退 P1.1 + 可手工保存 draft |
| 人工改步骤后未再验证 | 保存门禁 + UI 提示 |

## Migration Plan

1. 部署含 P1.2 的控制面（配置 `ANTHROPIC_*` 可选）
2. 重启控制面与 Worker（常驻进程须重启）
3. `create_all` 创建 `recording_compilation` 表；SQLite 开发库可直接重建
4. 已有 P1.1 流程不受影响；新录制走 AI 编译链路

## Open Questions

- 网关是否稳定支持图片输入：由 `ATP_AI_VISION_ENABLED` 开关，默认关，待实测后再开
