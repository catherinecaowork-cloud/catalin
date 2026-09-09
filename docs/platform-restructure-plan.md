# 平台重构与方向定盘（2026-09）

这份文档定三件事：**现在的问题是什么、目标形态是什么、按什么顺序改**。
它不描述新功能。功能线（AI 观察者、对象库）见 `docs/p1.2-ai-observer-plan.md`。

结论先行：

- 目标形态是**内网团队版**，不是 SaaS。之前提案里的多副本、对象存储、租户隔离**正式不做**。
- 真正卡住我们的不是架构，是**工程基本功缺失**：没有测试网、平台内核混着被测系统特例、四个上帝文件。
- 按 **测试网 → 拆边界 → 拆前端** 三步走，每步零行为变化、可独立验收。

---

## 1. 现状诊断

### 1.1 版本控制（已解决）

2026-09-09 之前，这个项目**没有 Git**，没有任何提交历史。

这是所有结构问题的根因：不能回滚、不能 review、不能分支，于是每个新需求只能在原文件末尾继续追加。
现已 `git init` 并推送到 `https://gitee.com/tatoqoq/catalin.git`，首次提交 138 文件 / 22126 行。
`var/`、`.secret.key`、`*.db`、`.venv` 不入库。

**从此以后**：任何结构调整先开分支，改完能回滚。

### 1.2 规划体系空转

OpenSpec 写了，但施工从不照它走：

| change | 任务完成 | 实际状态 |
| --- | --- | --- |
| `bootstrap-platform-p0` | **0 / 78** | 站点、回放、录制、SSE 全都已上线 |
| `ai-compiler-p1-2` | 21 / 22 | 已上线 |
| `flow-suites` | 10 / 10 | 已上线 |
| `ai-observer-p1-2` | 1 / 22 | 刚立项 |

P0 一条没勾，代码却已经做到 P1.2。OpenSpec 变成了事后补的说明书，不是施工契约。

**处理**：`bootstrap-platform-p0` 已经名存实亡，其中一部分早已实现、一部分被本文档正式取消。
下一次动它时按实际情况重写或归档，不要再挂着 0/78 假装还在排期。

### 1.3 P0 承诺但从未建立的结构

| 承诺 | 现状 | 本文档的处置 |
| --- | --- | --- |
| `packages/adapters` | **不存在** | **必须建**，见第 4 节 |
| `apps/console`（Vue 3） | **不存在** | **不建**。原生 JS 够用，但要拆文件 |
| Postgres + Alembic | SQLite + `db.py` 里手写 `ALTER TABLE` | 推迟，见 6.3 |
| MinIO | 本地 `var/artifacts` | **取消** |
| `deploy/` Docker Compose | 不存在 | 推迟到内网部署时再做 |
| CI | 不存在 | 第一步就做最简版 |

`packages/adapters` 缺失的后果最直接：Oinone / Ant Design 的选择器
（`.ant-select-dropdown`、`.oio-modal`、`data-name`）只能写死在通用定位器里。
换一个被测系统就要改内核，多人协作时改特例会碰到公共回放逻辑。

### 1.4 上帝文件

| 文件 | 行数 | 装了什么 |
| --- | --- | --- |
| `static/index.html` | 2851 | CSS + 全部模板 + 全部前端逻辑 |
| `api.py` | 1998 | 路由 + 批次状态机 + job 构造 + 脱敏 + heal 汇总 |
| `actions.py` | 1237 | 所有动作原语 + 框架特例 |
| `locator_candidates.js` | 775 | 通用候选计算 + Ant/Oinone 特例 |

单人开发时只是难看。**在「团队多人用」的目标下，这条从难看升级成阻塞**：两个人改前端必然天天冲突。

### 1.5 没有测试网

15 个 `scripts/selftest_*.py`，手写断言 + `SystemExit`，靠人记得去跑。
没有 `tests/`、没有 pytest、没有 CI。

后果：**不敢重构**。这是第一步必须先补的原因。

---

## 2. 目标形态：内网团队版

**做**：内网单机部署，团队多人使用，被测系统在内网或 NAT 后。

**明确不做**（以下条目从此不再出现在排期里）：

- 公网多租户、账号体系、RBAC、计费
- 控制面多副本、水平扩展、`FOR UPDATE SKIP LOCKED` 任务队列
- 对象存储（MinIO / S3）
- 移动端、桌面端自动化
- 把控制台做成通用 IDE

内网可信意味着：`X-Tenant-Id` 请求头继续够用；`_lease_lock` 用进程内锁是**正确选择**，不是欠债；
产物落本地盘 + 保留最近 5 次运行也够用。

---

## 3. 对标 Katalon：取什么，不取什么

产品方向对标 Katalon Studio 的**分层**，不是它的功能清单。

**取**：

- 对象库是中心：控件登记一次，多条用例引用
- 录制为对象库服务，不是为「这一次点击」服务
- 自愈修的是**对象**，引用它的用例一起好
- 无代码优先，需要时能导出脚本

**不取**：

- TestOps / TestCloud 那套云端多租户与并行执行（与第 2 节冲突）
- Selenium + Groovy 技术栈，我们继续用 Playwright
- Eclipse 式 IDE、XPath 崇拜
- 生产流量挖掘（TrueTest）

**我们比它强、必须保留的差异**：环境即站点（跨环境靠导入而非拍平）、日常回归零模型调用、
选值「合法即可」而非复刻某次选项、Worker 单向长轮询适配内网。

---

## 4. 目标结构

```
apps/control-plane/autotest_control/
  api/                    ← 按域拆分，api.py 只 include_router
    sites.py    flows.py    runs.py    recordings.py    workers.py
  domain/                 ← 领域逻辑，从 api.py 下沉
    batch.py    job_builder.py    redact.py
  static/
    index.html            ← 只留结构
    js/                   ← 按模块拆
      site.js  record.js  run.js  history.js  log.js

packages/executor/autotest_executor/
  browser/                ← 只留通用能力
    actions/              ← click.py  fill.py  choose.py  assert_.py
    locator.py
packages/adapters/
  oinone/                 ← Ant Design / Oinone 特例从内核搬出
    selectors.py  selectors.js

tests/                    ← selftest 收编，pytest 可跑
```

原则：**内核不认识任何被测系统**。特例进 `adapters`，通过站点的 `adapter` 字段选用（该字段已存在）。

---

## 5. 排期

三步，顺序不可换。每步**零行为变化**，靠上一步的产物保证安全。

### 第一步：测试网（前提）

- 15 个 `selftest_*.py` 收进 `tests/`，改成 pytest 断言
- 一条命令跑完全部：`pytest`
- 加最简 CI（Gitee 流水线或本地钩子）

**验收**：`pytest` 全绿；改任意一行内核代码后，跑一次就知道有没有踩坏。

### 第二步：拆边界

- `api.py` 按域拆成 `api/` 下多个 router，`api.py` 只做装配
- 批次状态机、job 构造、脱敏从路由层下沉到 `domain/`
- 建 `packages/adapters/oinone`，把 Ant/Oinone 选择器搬出内核

**验收**：`pytest` 仍全绿；`api.py` 降到 200 行以内；内核代码里搜不到 `ant-` / `oio-`。

### 第三步：拆前端

- `index.html` 的 JS 按模块拆到 `static/js/`
- CSS 独立
- UI 行为不变

**验收**：控制台功能逐项手工过一遍；`index.html` 降到 500 行以内。

### 之后

对象库 / AI 观察者（`ai-observer-p1-2`）在干净模块上继续。
**禁止**在三步完成前，继续往那四个上帝文件末尾追加新功能。

---

## 6. 决策记录

### 6.1 不建 Vue 3 控制台

P0 提案说 P1 上 Vue 3。**取消**。原生 JS 已经能跑，引入构建链会增加部署复杂度，
而内网团队版不需要复杂前端。拆文件即可解决多人协作问题。

### 6.2 不做对象存储

产物落本地盘，`ATP_ARTIFACT_KEEP_RUNS` 控制保留量。内网单机不需要 MinIO。

### 6.3 Postgres 推迟，但要留后路

SQLite 在多人同时使用时会撞写锁，且 `db.py` 里手写 `ALTER TABLE` 迁移不可持续。
**触发条件**：出现第一次并发写冲突，或需要第三个人同时用，就切 Postgres + Alembic。
在此之前不动，避免为假想负载付出复杂度。

### 6.4 `_lease_lock` 保留进程内锁

单副本部署下这是正确实现。代码里那句「多副本时换 Postgres」的注释保留作为提示，但不列入排期。

### 6.5 selftest 全部保留

它们覆盖了定位学习、编译、套件、链式、跨环境绑定等核心逻辑，是重构唯一的安全网。
收编时只改断言写法，**不删测试用例**。
