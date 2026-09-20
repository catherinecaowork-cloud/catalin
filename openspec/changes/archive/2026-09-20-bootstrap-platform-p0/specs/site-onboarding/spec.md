## Purpose

让使用者把任意一个 Web 站点接入平台：登记环境地址与所属项目，保存登录所需的凭证，并保证凭证在存储、日志与报告中都不以明文出现。这是所有测试能力的入口。

## ADDED Requirements

### Requirement: 站点登记

平台 SHALL 允许在一个项目下登记站点，至少记录 base URL、环境标识与所用站点适配器；同一项目可登记多个环境的同一站点。

#### Scenario: 新建站点

- **WHEN** 使用者在项目内提交 base URL、环境标识与适配器名称
- **THEN** 平台创建站点记录并返回其 id，后续任务可引用该 id

#### Scenario: 环境地址不等于产品版本

- **WHEN** 同一 base URL 在不同时间部署了不同版本的被测系统
- **THEN** 平台不因 base URL 相同而认为被测对象相同，版本信息由站点配置或运行时探测单独记录

### Requirement: 凭证加密存储

平台 SHALL 以加密形式保存站点凭证（账号密码、Cookie、Token、自定义 Header），并且 SHALL NOT 在任何接口响应中回显凭证明文。

#### Scenario: 保存后不可读回

- **WHEN** 使用者保存一份凭证后再查询该凭证
- **THEN** 平台只返回凭证类型、名称与更新时间，不返回明文值

#### Scenario: 数据库落盘为密文

- **WHEN** 直接读取凭证表的存储内容
- **THEN** 凭证值为密文，无法从库中直接得到原始账号密码或 Token

### Requirement: 日志与产物脱敏

平台与执行器 SHALL 在日志、事件、报告、HAR 等产物中对凭证值与鉴权头做脱敏。

#### Scenario: HAR 中的鉴权头被脱敏

- **WHEN** 一次运行录制了包含 `Authorization` 或 `Cookie` 头的 HAR
- **THEN** 回传到平台的 HAR 中这些头的值被替换为掩码，原值不可还原

### Requirement: 租户与项目隔离

平台 SHALL 按租户与项目隔离所有业务数据；跨项目访问 SHALL 被拒绝，而不依赖调用方自觉传参。

#### Scenario: 越权访问被拒绝

- **WHEN** 使用者用 A 项目的身份请求 B 项目的站点或凭证
- **THEN** 平台返回未授权错误，且不泄露该资源是否存在
