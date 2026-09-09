## Purpose

用状态机管理一条 UI 流程从草稿到进入回归的全过程，让「这条用例是不是我想要的」成为一次显式的人工确认，而不是从绿勾里猜。

## ADDED Requirements

### Requirement: 流程状态机

每条流程 SHALL 具有状态：`draft`、`reviewed`、`golden`、`active`；状态 SHALL 只能按 `draft → reviewed → golden → active` 推进，并 SHALL 允许因被测系统变更回退到 `draft`。

#### Scenario: 状态按序推进

- **WHEN** 一条新建流程尚未经过人工确认
- **THEN** 它处于 `draft`，且不能直接被设为 `active`

#### Scenario: 变更后回退

- **WHEN** 被测页面发生变更导致既有流程不再适用
- **THEN** 该流程可回退到 `draft` 并重新走确认与固化流程

### Requirement: 步骤确认是显式动作

从 `draft` 进入 `reviewed` SHALL 要求使用者查看完整步骤清单并显式确认；平台 SHALL NOT 因为流程执行成功而自动推进该状态。

#### Scenario: 执行成功不等于已确认

- **WHEN** 一条 `draft` 流程被执行且全部步骤通过
- **THEN** 它仍处于 `draft`，直到使用者确认步骤符合业务意图

### Requirement: 黄金跑固化基线

从 `reviewed` 进入 `golden` SHALL 要求一次成功运行，并将该次运行的截图与关键数据快照固化为基线；后续回放 SHALL 以该基线作为对比依据。

#### Scenario: 基线来自被认可的运行

- **WHEN** 一条 `reviewed` 流程完成一次成功运行并被采纳为黄金跑
- **THEN** 该次运行的截图与数据快照成为基线，流程进入 `golden`

#### Scenario: 无基线不得进入回归

- **WHEN** 一条流程尚未固化基线
- **THEN** 它不能被设为 `active`

### Requirement: 只有 active 流程进入门禁

CI 回归 SHALL 只执行 `active` 状态的流程；非 `active` 流程 SHALL 可手动执行但 SHALL NOT 影响门禁结论。

#### Scenario: 门禁只认已批准资产

- **WHEN** 项目中同时存在 `draft`、`golden` 与 `active` 流程且触发 CI 回归
- **THEN** 只有 `active` 流程被执行，门禁结论只由它们决定

### Requirement: 失败结论需人工终审

运行失败 SHALL 产生一条待审记录，其结论分类（真缺陷 / 环境抖动 / 用例过期 / 产品改版）SHALL 由使用者最终确认后才生效。

#### Scenario: 待审记录不自动关闭

- **WHEN** 一次运行失败并生成待审记录
- **THEN** 该记录保持待审状态直到使用者打标，平台不自行判定为非问题
