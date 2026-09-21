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
| `bootstrap-platform-p0` | 已归档 | 2026-09-20 归档；未把 P0 delta 同步进主 specs |
| `ai-compiler-p1-2` | 21 / 22 | 已上线；真站现录验收 **下一期** |
| `flow-suites` | 10 / 10 | 已上线 |
| `ai-observer-p1-2` | 21 / 22 | 已上线；真站现录验收 **下一期** |
| `ui-katalon-shell` | 外壳已改完 | 基准截图与目视对照是**持续**事项，不是一次验收 |

2026-09-20：真实环境「福瑞丝」已接入，从杰克 MES 导入「新建款式」无头回放通过。
这证明跨环境导入 + 表单登录 + 回放成立。现录验收、L1、CI、对象库都放到下一期。

P0 一条没勾，代码却已经做到 P1.2。OpenSpec 曾变成事后说明书。`bootstrap-platform-p0` 已归档。

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
能力差距、下一期需求 ID（K-OR / K-SPY / K-L1 等）见 `docs/katalon-gap-and-requirements.md`（需求来源）。

**取**：

- 对象库是中心：控件登记一次，多条用例引用
- 录制为对象库服务，不是为「这一次点击」服务
- 自愈修的是**对象**，引用它的用例一起好
- 无代码优先，需要时能导出脚本

**不取**：

- TestOps / TestCloud 那套云端多租户与并行执行（与第 2 节冲突）
- Selenium + Groovy 技术栈，我们继续用 Playwright
- Eclipse RCP 产品平台：桌面安装包、插件 / JAR、Perspective、XPath 第一定位
- 生产流量挖掘（TrueTest）

外观已经按 Katalon/Eclipse **信息架构**做了（左树、工具栏、底栏）——这是有意取的。不取的是把它做成可编程的通用 IDE。

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
    index.html            ← 过渡期保留；React 上线后改为 build 产物入口
  web/                    ← 第三步：Vite + React 控制台（见第 5 节第三步）

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

### 第一步：测试网（已完成）

- [x] 1.1 新增 `tests/`，`pytest tests/` 收编全部 `scripts/selftest_*.py`
- [x] 1.2 `pyproject.toml` 增加 `[project.optional-dependencies] dev` 与 pytest 配置
- [x] 1.3 浏览器自测缺 Chromium 时自动 skip；`scripts/run_tests.ps1` 与 `.gitee-ci.yml`
- [ ] 1.4 逐文件把断言从 scripts 迁到 `tests/test_*.py`（可选，不阻塞）

### 第二步：拆边界（已完成）

- [x] `api/` 按域拆 router，`router.py` 只做装配（原 `api.py` 已删除）
- [x] 批次状态机、job 构造、脱敏下沉到 `domain/`
- [x] 建 `packages/adapters/oinone`，Python 侧 Ant/Oinone 选择器已搬出；JS 注入文件仍含框架特例（后续可继续拆）

**验收**：`pytest` 全绿；`api.py` 已移除；Python 内核通过 adapter 引用框架特例。

### 第三步：React 控制台（已完成）

原方案是拆 `static/js/` 原生模块；**改为 Vite + React SPA**，与定盘「不引入复杂 SaaS 前端」不冲突——仍是内网单机、同一 FastAPI 进程托管静态资源。

**目录**（建议）：

```
apps/control-plane/web/          # Vite + React + TypeScript
  src/
    api/                         # fetch 封装、SSE 订阅
    components/                  # 顶栏、侧栏、日志、模态框
    pages/                       # 运行 / 录制 / 历史 / AI 配置
  vite.config.ts
  package.json
# build 输出 -> autotest_control/static/dist/
# main.py 的 GET / 改指向 dist/index.html（过渡期可与旧 index 并存）
```

**迁移顺序**（按使用频率，每步可独立验收）：

1. **壳层**：站点切换、Worker 条、Tab、底栏日志（替代顶栏 + `tabstrip`）
2. **运行**：流程列表、套件、勾选运行、SSE 直播、批次进度
3. **录制**：开窗录制、编译、保存为 Flow
4. **历史**：运行列表、删除、Heal 任务
5. **AI 配置**、站点接入（踩点）等模态框

**原则**：

- **只调现有 `/api/v1`**，第二步已拆好 router，前端不再碰领域逻辑
- ~~旧 `index.html` 在对应模块 React 化并验收前**不删**~~ 已删除（2026-09-09），仅保留 `static/dist/`
- 样式可先搬 CSS 变量/布局，再逐步组件化；不追求与设计系统对齐 Katalon

**验收**：

- `npm run build` 产物由 FastAPI 正常托管，`GET /` 打开 React 控制台
- 上表 5 个模块功能与现网一致（手工 checklist，同原第三步）
- `pytest tests/` 仍全绿（后端零行为变化）

### 之后

**下一期**：真站现录验收，以及 L1 接口引擎、CI 闸门、对象库。本期不做。
Katalon 基准截图与目视对照按 UI 变更持续更新，不作为本期收口。
三步重构已完成，不再往已删除的上帝文件追加。

---

## 6. 决策记录

### 6.1 控制台用 React，不建 Vue 3

P0 提案说 P1 上 Vue 3。**仍不做 Vue**。第三步改为 **Vite + React**（`apps/control-plane/web/`）：

- 与「内网团队版、FastAPI 单进程托管静态文件」兼容：`npm run build` → `static/dist/`
- 比继续维护 2851 行单文件 `index.html` 更适合多人改 UI
- 构建链只在前端目录，部署仍是「一个 Python 进程 + 本地 var/」，不引入 Node 运行时

若 React 脚手架尚未落地，**禁止**再往 `static/index.html` 末尾堆新功能；新 UI 只进 `web/`。

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
