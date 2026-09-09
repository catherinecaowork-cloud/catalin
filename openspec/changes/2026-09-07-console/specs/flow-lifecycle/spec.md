## ADDED Requirements

### Requirement: 控制台显式确认与退回

平台 SHALL 在运行模块提供将 `draft` 标为 `reviewed`（用例）以及将已确认流程退回 `draft` 的显式操作；SHALL NOT 因为一次运行通过而自动改变流程状态。

#### Scenario: 确认为用例

- **WHEN** 使用者选中一条 `draft` 流程并确认「确认为用例」
- **THEN** 该流程状态变为 `reviewed`，界面展示为用例

#### Scenario: 退回草稿

- **WHEN** 使用者选中一条非 `draft` 流程并确认「退回草稿」
- **THEN** 该流程状态变为 `draft`，并清除已固化基线

#### Scenario: 跑成功不升级

- **WHEN** 一条 `draft` 流程回放全部通过
- **THEN** 它仍为 `draft`

### Requirement: 用例不可删除

状态不是 `draft` 的流程 SHALL 不能被删除；使用者须先退回草稿。

#### Scenario: 接口拒绝删除用例

- **WHEN** 对 `reviewed` / `golden` / `active` 流程发起删除
- **THEN** 平台返回冲突，流程仍在

#### Scenario: 草稿可删

- **WHEN** 对 `draft` 流程发起删除且通过名称确认
- **THEN** 该流程被删除
