# flow-lifecycle Specification

## Purpose

用状态机管理一条 UI 流程从草稿到进入回归的全过程，让「这条用例是不是我想要的」成为一次显式的人工确认，而不是从绿勾里猜。

## Requirements

### Requirement: 流程状态机

每条流程 SHALL 具有状态：`draft`、`reviewed`、`golden`、`active`；状态 SHALL 只能按 `draft → reviewed → golden → active` 推进，并 SHALL 允许因被测系统变更回退到 `draft`。

#### Scenario: 状态按序推进

- **WHEN** 一条新建流程尚未经过人工确认
- **THEN** 它处于 `draft`，且不能直接被设为 `active`

#### Scenario: 变更后回退

- **WHEN** 被测页面发生变更导致既有流程不再适用
- **THEN** 该流程可回退到 `draft` 并重新走确认与固化流程

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
