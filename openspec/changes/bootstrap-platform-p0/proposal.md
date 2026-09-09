## Why

现有测试资产（`mes-test-platform`）只能测一个 MES 系统：登录走 Pamirs 专用 mutation、页面靠 Oinone 锚点、主数据是写死的业务配置。想让别的系统也能用「接口 + UI 自动化」，必须把执行内核和业务语义拆开。

同时已有一条被实测否掉的路：全量 AI 巡检约 90 秒 / 页、约 78k token / 页，139 个菜单页跑一轮约 4 小时、千万 token，不可持续。所以平台必须以确定性回放为回归主力，AI 只在需要判断时介入。

P0 的目的不是做完整平台，而是先证明闭环成立：**接入任意站点 → 登录 → 接口回归 + UI 回放 → 看得见 → CI 可阻断发布**。

## What Changes

- 新建独立仓库 `autotest-platform`（控制面 + 执行器 + 适配器 + 协议包），MES 现仓库不改动
- 控制面提供租户 / 项目 / 站点 / 凭证管理，凭证加密存储、日志与报告脱敏
- 执行器以 Worker 形态运行，**长轮询领任务**，平台不反向连接，内网与 NAT 后的机器均可接入
- L1 接口引擎：导入 HAR 或手工请求成集，跑批并断言；**HTTP 200 但响应体含非空 `errors` 判为失败**
- 可插拔登录器：Cookie / Token / 表单三种，登录结果由 L1 与 L2 共享
- L2 浏览器回放：Playwright 真浏览器执行统一动作原语，逐步截图，**开窗 / 无头由用户选且执行行为一致**
- 通用页面探针：劫持 `console.error` / `error` / `unhandledrejection` / `fetch`，抓「页面视觉正常但底层请求失败」
- 运行可观测：Worker 上报结构化事件，控制面 SSE 直播，失败留截图 / 录像 / HAR / trace
- flow 生命周期状态机 `draft → reviewed → golden → active`，**只有 `active` 能进 CI 门禁**
- CI 契约：`runner run --ci` 失败以非零退出码阻断发布，产物回传平台
- **BREAKING**（相对现有资产）：不再使用 browser-use 与其 CDP 驱动栈；Playwright 统一锁 1.49.1；MES 专用登录 / 版本 / 主数据逻辑不进内核，下沉为 `adapters/oinone`

## Capabilities

### New Capabilities

- `site-onboarding`: 租户 / 项目 / 站点建模，环境地址与适配器配置，凭证加密存储与脱敏
- `auth-provider`: 可插拔登录器（Cookie / Token / 表单），登录态在 L1 与 L2 之间共享
- `worker-orchestration`: Worker 注册与心跳、长轮询领任务、job 协议、产物上传
- `api-test-engine`: L1 请求集重放与断言，HAR 导入，业务错误体判定
- `browser-replay`: L2 真浏览器回放，统一动作原语，选择器候选打分，开窗 / 无头等价
- `page-probe`: 通用页面探针注入与 `pageHealth` 读取
- `run-observability`: 结构化运行事件、SSE 直播、失败证据留存
- `flow-lifecycle`: flow 状态机与黄金跑基线，意图确认落到数据
- `ci-gate`: CI 触发契约与退出码语义

### Modified Capabilities

（无。本仓库为新建，`openspec/specs/` 目前为空。）

## Impact

- **新增代码**：`apps/control-plane`、`apps/console`、`packages/executor`、`packages/adapters`、`packages/protocol`、`deploy/`
- **数据**：新建 Postgres 库（租户 / 项目 / 站点 / 凭证 / 请求集 / flow / 基线 / job / run / event / worker），MinIO 存截图录像 HAR trace
- **依赖**：Python 3.11、FastAPI、SQLAlchemy + Alembic、httpx、**Playwright 1.49.1**、MinIO SDK；P0 不含任何 LLM SDK 与深度学习依赖
- **部署**：内网单机 Docker Compose（控制面 + Postgres + MinIO）；Worker 双分发（Windows pip 开窗 / 容器无头）
- **外部依赖**：2 个真实非 MES 被测站点（建议一个有 `data-testid`、一个完全没有）及其可登录账号
- **不受影响**：`mes-test-platform` 仓库保持原样，继续独立运行
- **未纳入**：Router / Explorer / Compiler / Reviewer 等 AI 角色、多租户配额、SSO、Worker 集群（P1 / P2）
