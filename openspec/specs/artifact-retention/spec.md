# artifact-retention Specification

## Purpose

限制本地运行产物占用磁盘：控制面保留最近若干次运行的截图，执行器工作区不堆积每次运行的 UUID 目录。

## Requirements

### Requirement: 控制面只保留最近若干次运行产物

平台 SHALL 按配置保留最近 N 次运行的产物目录（默认 N=5）；N=0 时 SHALL NOT 自动删除控制面产物。

#### Scenario: 超出保留份数则删除更早的

- **WHEN** `var/artifacts` 下运行目录数量超过保留份数
- **THEN** 平台删除最旧的超出部分，保留最新的 N 个

### Requirement: 执行器工作区不保留运行目录

`var/worker`、`var/worker-ui`、`var/worker-headless` 下的运行 UUID 目录 SHALL 在任务结束后删除；Worker 身份文件 SHALL 保留。

#### Scenario: 跑完清空本机运行目录

- **WHEN** 一次回放或录制在执行器上结束
- **THEN** 该次运行在工作区下的目录被删除，`worker-identity.json` 仍在

#### Scenario: 控制面也会清执行器工作区残留

- **WHEN** 控制面执行产物清理
- **THEN** 上述三个工作区中的运行目录被清空，身份文件不受影响
