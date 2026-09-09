## Purpose

让执行器能部署在内网、值班电脑或 CI 机器上并从平台领取任务，同时保证平台不需要主动连接这些机器。这决定了平台能否覆盖进不了公网的被测系统。

## ADDED Requirements

### Requirement: Worker 注册与心跳

平台 SHALL 支持 Worker 注册并返回其访问令牌；Worker SHALL 周期性上报心跳与能力标签（是否可开窗、可达网段、操作系统）。

#### Scenario: 注册后可见

- **WHEN** 一台机器上的 Worker 首次注册
- **THEN** 平台记录该 Worker 并在执行器列表中展示其标签与最近心跳时间

#### Scenario: 心跳超时标记离线

- **WHEN** 某 Worker 超过约定时间未上报心跳
- **THEN** 平台将其标记为离线，且不再向其分派新任务

### Requirement: 任务由 Worker 主动领取

任务分派 SHALL 通过 Worker 发起的长轮询完成；平台 SHALL NOT 依赖对 Worker 的入站连接。

#### Scenario: 内网 Worker 无入站端口也能工作

- **WHEN** Worker 位于 NAT 或防火墙之后、不暴露任何入站端口
- **THEN** 它仍能领到任务、上报事件并完成运行

#### Scenario: 同一任务不被重复领取

- **WHEN** 多个 Worker 同时向平台领取任务
- **THEN** 每个任务最多被一个 Worker 领取，不出现同一任务并发执行

#### Scenario: 按标签匹配

- **WHEN** 任务要求开窗执行
- **THEN** 平台只将其分派给声明了可开窗能力的 Worker

### Requirement: 任务描述自包含

平台下发的任务 SHALL 包含执行所需的全部信息（站点、登录方式引用、执行目标、可见性与产物选项）；Worker SHALL NOT 直接访问平台数据库。

#### Scenario: 仅凭任务描述即可执行

- **WHEN** Worker 领到一个任务
- **THEN** 它无需查询数据库即可完成执行，凭证通过受控接口按引用换取

### Requirement: 产物上传与断点重试

Worker SHALL 将截图、录像、HAR、trace 上传到平台指定位置；网络中断后 SHALL 支持重试而不丢失已完成步骤的结果。

#### Scenario: 上传中断后恢复

- **WHEN** 产物上传过程中网络短暂中断
- **THEN** Worker 重试上传，最终产物在平台侧完整可见
