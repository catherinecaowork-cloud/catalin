## ADDED Requirements

### Requirement: 观察者脚本允许改写操作骨架

当本轮产物来自 AI 观察者编写时，平台 SHALL 允许步骤的 action、target 与取值策略不同于样例轨迹；SHALL 仍拒绝 DSL 原语之外的动作。当观察者未启用或已回退到仅润色路径时，平台 SHALL 继续只允许按步骤 id 修改 label、phase、mutating、value 并追加断言。

#### Scenario: 观察者可将点击选项改为选择组件步骤

- **WHEN** 样例轨迹是多次点击下拉选项，观察者输出为一条带任选策略的选择步骤
- **THEN** 平台接受该编写结果并进入 DSL 校验与验证回放

#### Scenario: 仅润色路径仍禁止改 target

- **WHEN** 本轮走仅润色编译且模型试图修改某步的 action 或 target
- **THEN** 该轮编译失败，不写入已验证步骤
