## MODIFIED Requirements

### Requirement: 步骤确认是显式动作

从 `draft` 进入 `reviewed` SHALL 要求使用者查看完整步骤清单并显式确认；平台 SHALL NOT 因为流程执行成功而自动推进该状态。通过 AI 编译自动回放验证的步骤，在**未被人工修改**的前提下，SHALL 允许默认保存为 `draft`；若使用者修改了步骤或选择保存未验证版本，SHALL 要求显式确认。

#### Scenario: 执行成功不等于已确认

- **WHEN** 一条 `draft` 流程被执行且全部步骤通过
- **THEN** 它仍处于 `draft`，直到使用者确认步骤符合业务意图

#### Scenario: 已验证且未改动的编译结果可默认保存

- **WHEN** AI 编译验证通过且使用者未修改编译产物即保存
- **THEN** 平台允许保存为 `draft` 流程

#### Scenario: 未验证版本需显式确认

- **WHEN** 使用者修改了编译步骤或编译未通过自动验证仍要保存
- **THEN** 平台要求显式允许保存未验证版本，且流程仍以 `draft` 状态入库
