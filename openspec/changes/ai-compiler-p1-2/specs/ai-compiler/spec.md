## Purpose

在 P1.1 确定性录制草稿之上，用模型生成语义化步骤与断言，并通过自动回放验证编译产物；失败时安全回退，不阻断人工保存。

## ADDED Requirements

### Requirement: 录制结束后触发 AI 编译

平台 SHALL 在录制任务成功结束后，允许发起 AI 编译；编译输入 SHALL 包含确定性步骤、录制意图、脱敏后的编译上下文，以及可选的结束截图（仅当视觉能力开启）。

#### Scenario: 录制成功后可发起编译

- **WHEN** 一次录制任务以成功结束且包含至少一步操作
- **THEN** 使用者或控制台可以发起 AI 编译并收到编译任务标识

#### Scenario: 无步骤时不允许编译

- **WHEN** 录制结果除打开页面外没有任何操作步骤
- **THEN** 平台拒绝发起 AI 编译并给出可理解的原因

### Requirement: 模型输出不得改变操作骨架

AI 编译 SHALL 只允许按步骤 id 修改 label、phase、mutating、value，并追加断言步骤；SHALL NOT 修改既有步骤的 action、target 或顺序。

#### Scenario: 越权修改被拒绝

- **WHEN** 模型输出试图修改某步的 action 或 target
- **THEN** 该轮编译失败，错误信息可被重试逻辑或使用者看到，且不写入已验证步骤

#### Scenario: 合法语义增强被接受

- **WHEN** 模型仅修改 label、phase、mutating、value 或追加断言
- **THEN** 平台接受输出并进入 DSL 校验与后续验证

### Requirement: 编译即回放验证

每次 AI 编译成功后，平台 SHALL 自动创建一次无头回放验证运行；验证 SHALL 使用编译后的步骤与录制相同的站点凭证上下文（不持久化为正式 Flow）。

#### Scenario: 验证通过标记为已验证

- **WHEN** 验证运行全部步骤通过
- **THEN** 编译状态变为已通过，步骤可被默认保存

#### Scenario: 验证失败触发重编译

- **WHEN** 验证运行失败且当前轮次小于上限
- **THEN** 平台将失败摘要作为反馈再次调用模型重编译

#### Scenario: 达到重试上限后回退

- **WHEN** 验证失败且已达到最大重试轮次
- **THEN** 平台回退到 P1.1 确定性步骤，并标记为需人工处理

### Requirement: 模型不可用时可降级

当模型网关未配置或调用失败时，平台 SHALL NOT 阻断 P1.1 流程；SHALL 回退确定性步骤并允许使用者手工编辑后保存为 draft。

#### Scenario: 缺配置时回退

- **WHEN** 发起编译但模型网关缺少必需配置
- **THEN** 编译进入回退或错误可见状态，确定性步骤仍可用于确认与保存

### Requirement: 非测试环境限制自动写操作验证

当站点环境标识不是 test/dev/development 时，平台 SHALL NOT 自动派发会写入被测数据的验证运行；SHALL 停在待人工验证状态。

#### Scenario: 生产类环境不自动验证

- **WHEN** 站点环境为 staging 或 production 且 AI 编译成功
- **THEN** 编译状态为待人工验证，不自动创建写操作验证 run
