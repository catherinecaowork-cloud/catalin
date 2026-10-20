## Purpose

定义「已确认用例的自动回归闸门」的对外行为：跑哪些流程、什么时候算跑完、结果如何反映为流水线信号。它是「用例是否还能跑通」这件事在流水线里的唯一信号来源。

## ADDED Requirements

### Requirement: 回归集合只取 active 流程

闸门 SHALL 以状态为 `active` 的流程作为回归集合，SHALL NOT 把 `draft` / `reviewed` / `golden` 的流程纳入。

#### Scenario: 只跑 active

- **WHEN** 闸门启动，库中同时存在若干 `active` 与若干 `draft` / `reviewed` / `golden` 流程
- **THEN** 只有 `active` 的流程被执行

#### Scenario: 没有 active 流程

- **WHEN** 闸门启动时没有任何 `active` 流程
- **THEN** 闸门明确报告「没有可跑的流程」并以非零退出码结束，SHALL NOT 以零退出码静默通过

### Requirement: 等待终态再判定

闸门 SHALL 等到每条流程的运行到达终态之后再判定结果，SHALL NOT 在入队后即结束。

#### Scenario: 入队后等待

- **WHEN** 一条流程被入队
- **THEN** 闸门持续查询该运行直到它结束，然后判定通过与否

#### Scenario: 超过总时限

- **WHEN** 某条运行在闸门的总时限内仍未结束
- **THEN** 闸门判定为失败，并指出是哪条流程未在时限内结束

### Requirement: 失败反映为退出码

闸门 SHALL 在任一流程未通过时以非零退出码结束，SHALL NOT 在存在失败流程时仍以零退出码结束。

#### Scenario: 一条失败

- **WHEN** 回归集合中有一条流程运行失败
- **THEN** 闸门以非零退出码结束

#### Scenario: 全部通过

- **WHEN** 回归集合中所有流程都通过
- **THEN** 闸门以零退出码结束

### Requirement: 逐条结果可见

闸门 SHALL 输出每条流程的名称与其结果，SHALL NOT 只给出一个汇总结果。

#### Scenario: 结果清单

- **WHEN** 闸门结束
- **THEN** 输出中能看到每条流程的名称，以及它是通过还是失败

#### Scenario: 失败可定位到运行

- **WHEN** 某条流程失败
- **THEN** 输出中给出可用于查看该次运行的标识，使用者不必靠猜
