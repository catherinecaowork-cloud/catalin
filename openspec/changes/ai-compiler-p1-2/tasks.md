## 1. 协议与变量运行时

- [x] 1.1 `Step.phase`、`Job.record_intent`、`Job.variables` 协议扩展
- [x] 1.2 实现 `variables.py`：unique/now/env 解析，拒绝嵌套与未知类型
- [x] 1.3 `RunExecutor` 执行前深拷贝解析 value/expected
- [x] 1.4 新增 `scripts/selftest_variables.py` 并通过

## 2. 录制上下文

- [x] 2.1 起始页就绪后采集同源 JSON 请求摘要（≤30 条，脱敏）
- [x] 2.2 结束页 URL、title、可见文本、语义步骤写入 `compiler_context`
- [x] 2.3 保持 `compile_events` 签名与 P1.1 行为不变

## 3. AI 编译层

- [x] 3.1 `settings.py` 读取 `ANTHROPIC_*` 与 `ATP_AI_VISION_ENABLED`
- [x] 3.2 实现 `ai/client.py`：Messages API、重试、token usage
- [x] 3.3 实现 `ai/schemas.py` + `ai/compiler.py`：契约校验与安全应用
- [x] 3.4 新增 `scripts/selftest_ai_compiler.py` 并通过

## 4. 编译—验证状态机

- [x] 4.1 新增 `RecordingCompilation` 模型与 API（compile/status/retry/fallback）
- [x] 4.2 实现 `compilation_worker.py`：最多 3 轮 compile→validate→retry/fallback
- [x] 4.3 非 test/dev 环境停在 manual_validation
- [x] 4.4 新增 `scripts/selftest_compilation_worker.py` 并通过

## 5. 控制台与保存门禁

- [x] 5.1 录制表单必填意图；录制结束自动提交编译并轮询状态
- [x] 5.2 确认页：phase、参数模板编辑、编译进度与 token 展示
- [x] 5.3 保存默认要求已验证；`allow_unverified` 显式存 draft
- [x] 5.4 运行模块支持 `variables` JSON 入参

## 6. 文档与端到端验收

- [x] 6.1 新增 `docs/p1.2-ai-compiler-plan.md` 与 README 更新
- [x] 6.2 OpenSpec change `ai-compiler-p1-2` 提案/规格/设计/任务
- [ ] 6.3 真实站点端到端：意图→录制→AI 编译验证通过→保存→二次回放（需配置网关与 Worker）
  - 2026-09-20：福瑞丝环境已接入，「新建款式」从杰克 MES 导入后回放通过；本条要求的本环境现录尚未做
