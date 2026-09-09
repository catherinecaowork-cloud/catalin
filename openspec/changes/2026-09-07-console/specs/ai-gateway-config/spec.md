## Purpose

让控制台可以配置模型网关并落盘，按模型选择正确的调用协议，避免只靠进程环境变量、填错路径或用错接口。

## ADDED Requirements

### Requirement: 控制台保存网关配置

平台 SHALL 提供 AI 配置的读取与保存；Token SHALL NOT 以明文回读，仅可提供末几位提示；保存后的配置 SHALL 以控制台文件为准，不被空的环境变量覆盖。

#### Scenario: 保存后可测通

- **WHEN** 使用者填写网关地址、Token、模型并保存，再请求测通
- **THEN** 平台使用刚保存的配置发起一次请求，并返回成功或失败原因

#### Scenario: Token 不回明文

- **WHEN** 读取已保存的 AI 配置
- **THEN** 响应不含完整 Token，可含是否已配置与末四位提示

### Requirement: 按模型选择调用协议

平台 SHALL 根据模型名选择网关协议：GLM / DeepSeek / Kimi 等走 OpenAI Chat Completions，Claude 走 Anthropic Messages；网关根地址 SHALL 去掉误填的 `/v1/chat/completions`、`/v1/messages` 或多余的 `/v1`。

#### Scenario: glm 走 Chat Completions

- **WHEN** 模型为 `glm-5.1` 且网关填为站点根地址
- **THEN** 平台请求 `{root}/v1/chat/completions`，而不是 `{root}/v1/messages`
