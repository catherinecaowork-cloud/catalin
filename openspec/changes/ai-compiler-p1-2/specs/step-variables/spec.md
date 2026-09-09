## Purpose

让录制时的硬编码值在回放时可参数化，避免唯一性字段第二次运行失败，同时保持定位 target 不被模板污染。

## ADDED Requirements

### Requirement: 支持的变量模板

步骤的 value 与 expected SHALL 支持以下模板：`{{unique:key}}`、`{{now:format}}`、`{{env:key}}`；SHALL NOT 支持嵌套模板或未知类型（含 `{{pick:...}}`）。

#### Scenario: unique 生成带前缀的唯一值

- **WHEN** 某次运行解析包含 `{{unique:style_code}}` 的步骤
- **THEN** 该次运行内所有同名 key 展开为相同值，且值以 `AT_` 前缀开头

#### Scenario: now 按格式展开

- **WHEN** 步骤包含 `{{now:%Y%m%d}}`
- **THEN** 回放时使用当前日期按给定格式展开

#### Scenario: env 从运行参数读取

- **WHEN** 步骤包含 `{{env:region}}` 且本次运行提供了 `region` 变量
- **THEN** 回放时使用提供的字符串值

#### Scenario: 缺失 env 被拒绝

- **WHEN** 步骤包含 `{{env:missing}}` 但本次运行未提供该变量
- **THEN** 运行在该步骤前失败并给出可理解错误

### Requirement: target 不参与变量解析

变量解析 SHALL 仅作用于 value 与 expected；定位 target 中的字符串 SHALL 保持原样。

#### Scenario: target 不被展开

- **WHEN** target 候选值中包含类似模板的文本
- **THEN** 回放定位仍使用原始字符串，不进行变量替换

### Requirement: 解析不改变原流程定义

执行器 SHALL 在运行前深拷贝步骤并解析变量，SHALL NOT 修改存储在流程定义中的原始模板字符串。

#### Scenario: 原流程保留模板

- **WHEN** 同一条流程被多次运行
- **THEN** 每次运行重新解析模板，且流程库中仍保存未展开的模板
