# 通用接口 / UI 自动化测试平台

给任意能登录的网站做接口与 UI 自动化回归。不绑定被测系统：站点、登录方式、
流程都是配置出来的。

当前进度是 **P1.2 已落地，真站回放已过**：控制台建环境 → 表单登录 → 跨环境导入
流程 → 真浏览器回放，已在真实站点「福瑞丝」跑通「新建款式」。
L1、CI、对象库和真站「现录」验收都放到下一期。见文末。

## 它是什么，不是什么

- 不是录制回放工具。回放的是结构化步骤，不是坐标和录像。
- 不是全 AI 自动化。日常回归零模型调用；AI 只在首跑探索、变更编译、失败复核时介入。
- 不是爬虫。一切以已授权的登录态为前提。

## 三个进程

| 组件 | 职责 | 红线 |
| --- | --- | --- |
| `apps/control-plane` | API、派任务、事件直播、产物存储 | 不碰浏览器，不访问被测站点 |
| `packages/executor` | 真正点页面、发请求的 Worker | 不连数据库；job 自包含 |
| `packages/protocol` | 两端共享的步骤 DSL / job / 事件模型 | 只有一份定义 |

平台从不反向连接 Worker——Worker 单向长轮询领任务。被测系统多在内网、
值班机常在 NAT 后，只要能出网就能干活。

## 跑起来

需要 Python 3.11+，以及 Node.js 18+（只为构建控制台 SPA）。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
```

控制台是 Vite + React，构建产物不进仓库。裸克隆后先构建一次，否则打开
`http://127.0.0.1:8910` 会得到 503「控制台前端未构建」：

```powershell
cd apps\control-plane\web
npm i
npm run build
cd ..\..\..
```

三个终端（或者前两个后台跑）：

```powershell
# 1) 控制面
python -m uvicorn autotest_control.main:app --host 127.0.0.1 --port 8910

# 2) 执行器（首次自动注册，身份缓存在 var/worker/）
# 注册码默认读 var/worker.register_code（控制面首次启动生成）
runner worker --server http://127.0.0.1:8910 --name my-pc

# 3) 造一个不需要登录的示例站点和两条流程（脚本会自动带上 API Token）
python scripts\seed_demo.py
```

然后打开 <http://127.0.0.1:8910> ，选流程点「开始执行」。
本机控制台会经 `/api/v1/auth/bootstrap` 拿到 API Token；写接口无 Token 会被拒。

### 准入密钥（生产必设）

控制面**写接口**需要共享 API Token；Worker **注册**需要预共享注册码。
未设环境变量时，首次启动会写入 `var/`（已 gitignore）：

| 用途 | 环境变量 | 默认落盘 |
| --- | --- | --- |
| 写 API | `ATP_API_TOKEN` | `var/api.token` |
| Worker 注册 | `ATP_WORKER_REGISTER_CODE` | `var/worker.register_code` |

```powershell
# 生产建议显式设置，不要依赖落盘文件
$env:ATP_API_TOKEN = "换成足够长的随机串"
$env:ATP_WORKER_REGISTER_CODE = "换成另一串随机码"

# 请求示例
# Authorization: Bearer <ATP_API_TOKEN>
# 或头：X-API-Token: <ATP_API_TOKEN>

runner worker --server http://控制面:8910 --name ci-box --register-code $env:ATP_WORKER_REGISTER_CODE
```

凭证明文接口 `/credentials/{id}/material` 仅允许当前已领任务（leased/running）引用的凭证。

### 日闸（业务回归，与单元测试分开）

```powershell
# 有控制面 + 在线 Worker 时：跑光 active 流程，失败非零退出
python scripts\ci_daily_gate.py --server http://127.0.0.1:8910

# 无内网 / CI 夹具：验证「故意失败的 active 流 → 非零」
python scripts\ci_daily_gate.py --fixture broken
```

GitHub Actions / Gitee 流水线里 `ci-daily-gate` 作业与 `pytest` 分离；夹具不依赖被测内网。

勾上「开窗执行」就能看见浏览器真的弹出来点页面。开窗和无头**跑的是同一份步骤、
同一套断言**，只切 `headless`——否则 CI 的结论就不可信了。

不想开浏览器看的话，命令行也能看全过程：

```powershell
python scripts\run_flow.py "应通过"     # 加 --headed 则开窗
python scripts\show_run.py              # 省略 run_id 则看最近一次
```

## 接入一个真实站点

在控制台左上角「接入站点」填登录页地址，点「识别登录表单」。

平台会派一个**踩点任务**给执行器（控制面不装浏览器，打开页面这活只能执行器干），
执行器打开页面、等单页应用渲染完、认出账号框 / 密码框 / 提交按钮，把候选定位和
截图交回来。你核对无误后填账号密码保存，凭证加密落库，同时生成一条
「登录 → 首页体检」的冒烟流程。

命令行也能做同样的事，留给脚本化场景（识别逻辑与控制台共用一份）：

```powershell
python scripts\onboard_site.py http://你的站点/login
```

想先看看页面结构，或者自动识别不准时手工配：

```powershell
python scripts\inspect_page.py http://你的站点/login --shot login.png
```

它列出所有可交互元素及其候选定位方式，按稳定性排序，直接能抄进流程配置。

## 录制一条流程（P1.1 + P1.2 AI 编译）

控制面不装浏览器，录制也是派给执行器的任务，而且**必须开窗**。

1. 执行器常驻：`runner worker --server http://127.0.0.1:8910 --name my-pc`
2. 打开控制台，在「录制流程」选站点 / 凭证，**填写录制意图**（如「新增一条款式」），点「开始录制」
3. 浏览器弹出后（会先自动登录），按你平时的操作点一遍
4. 点页面右上角「结束录制」，或控制台上的同名按钮
5. 控制台自动进入 **AI 编译**：语义 label、断言推断、唯一性字段参数化；最多 3 轮自动回放验证
6. 核对编译结果（可改文案、phase、参数模板、断言），保存为流程
7. 勾上「开窗执行」立刻回放一遍——录出来却跑不通，就不算录上了

未配置模型网关时，会回退 P1.1 确定性步骤，仍可手工编辑后保存为 `draft`。
日常已保存流程的回放**不会**再调模型。

### 模型网关（可选）

控制面启动前设置（不要写进仓库）：

```powershell
$env:ANTHROPIC_BASE_URL = "http://你的网关:18080"
$env:ANTHROPIC_AUTH_TOKEN = "你的 token"
$env:ANTHROPIC_MODEL = "ark-code-latest"
# 可选：把录制结束截图送给模型
# $env:ATP_AI_VISION_ENABLED = "true"
```

### 参数化

步骤 `value` / `expected` 支持：

- `{{unique:style_code}}` — 每次运行生成 `AT_` 前缀唯一值
- `{{now:%Y%m%d}}` — 当前时间

拖拽 / canvas / 文件上传录不上，确认页会提示。细节见 `docs/p1.2-ai-compiler-plan.md`。

自测：

```powershell
pip install -e ".[dev]"
pytest tests/
# 或
.\scripts\run_tests.ps1
```

浏览器相关自测（探针、下拉任选、非必填跳过）需要本机已装 Chromium：

```powershell
playwright install chromium
```

单独脚本仍可直接跑（与 pytest 等价）：

```powershell
python scripts\selftest_compiler.py
python scripts\selftest_variables.py
python scripts\selftest_ai_compiler.py
python scripts\selftest_compilation_worker.py
```

### 单页应用的坑

`networkidle` 对单页应用不可靠：请求早停了，框架还没渲染。实测某 Vue + Apollo
应用在 networkidle 之后 **2 秒**才出现登录表单——在那之前找元素必然扑空，
而且是间歇性的，比稳定失败更难查。

所以 `goto` 之后会自动等到页面出现可交互元素才继续。静态页面立刻返回，不会拖慢。

同理，登录成功不能靠 `load` 事件判断：单页应用登录后往往不触发整页导航，
`load` 会立刻返回，于是**密码错误也会被当成登录成功**，后面的步骤全是错的。
这里用「密码框消失」作为成功信号。

## 报错 `Executable doesn't exist at ...headless_shell.exe`

浏览器和 Playwright 的版本是绑死的：1.49.1 只认 `chromium-1148` 这个构建，
装了别的版本不算数。在**装了本项目的那个虚拟环境里**执行：

```powershell
.\.venv\Scripts\Activate.ps1
playwright install chromium
```

如果环境变量 `PLAYWRIGHT_BROWSERS_PATH` 被设过，浏览器会装到那个目录，
换个终端就找不着了。排查时先看它的值：`echo $env:PLAYWRIGHT_BROWSERS_PATH`。

## 卡在「等待执行器领取任务」

说明没人领活。执行器是常驻进程，**关掉终端它就停了**，任务会一直排队。
顶部徽标显示在线数量，中栏也会直接告诉你缺什么。

`runner worker` 不带 `--once` 才是常驻；带了就是领一个任务后退出（CI 用）。

要求开窗但在线的执行器都声明不能开窗（容器、无桌面服务器）时，任务同样领不走。
这是故意的：请求开窗却悄悄改成无头，等于骗人。

## 探针：为什么「页面看着正常」不等于没问题

很多系统接口失败仍返回 HTTP 200，错误藏在响应体的 `errors` 里。不读 body
根本发现不了：页面一切正常，接口测试也没测到那个接口。

探针在浏览器上下文层面注入，覆盖整页刷新与后续导航，抓三类静默错误：
响应体里的业务错误、未捕获的运行时异常、未处理的 Promise 拒绝。

自测一下（会起一个刻意做坏的本地页面）：

```powershell
python scripts\selftest_probe.py
```

## 定位不用单一选择器

一个目标存多个候选，按稳定性排序：`testid` → `role` → `label` → `placeholder`
→ `text` → `css`。哈希 class 不是候选，是被明确排除的做法。

回放时依次尝试。命中低稳定性候选会报「定位漂移」——用例还没坏，但已经在坏的路上。

## 流程状态机

`draft → reviewed → golden → active`。跑成功**不会**自动推进状态，确认是一次
显式动作；没固化基线的流程不能进回归。被测系统一变，回退到 `draft` 重走确认。

## 已经跑通的

- 建站点、存凭证（密文落库，读接口永不回显）、写流程
- 长轮询派任务 + 租约回收失联 Worker 手里的任务
- 真浏览器回放：`goto` / `click` / `fill` / `select` / `waitFor` / `readTable` /
  `pageHealth` / `assert` / `screenshot`
- 开窗与无头同源；请求开窗但环境没有桌面会话时**明确报错，不静默降级**
- SSE 直播：步骤、截图、探针告警、断言结论；断线重连按快照补齐
- 失败才留 trace 与录像，通过的运行不留——证据要有，但不能淹没
- 标签门禁：开窗任务不会派给声明不能开窗的执行器
- 确定性录制、AI 编译、AI 观察者（代码 + 自测）；套件/批次、跨环境导入
- 真实环境「福瑞丝」（`http://192.168.99.165:8000`）：表单登录后从杰克 MES
  导入「新建款式」，无头回放通过（2026-09-20）

## 还没做

- **已知缺陷**
  - 浮层定位主路径已按 change `locator-popup-fix` 收敛（可见性 / 点击回退 / 选择器单一来源 /
    本地 Ant Design fixture 回归）。**真站（福瑞丝）连续回放验收仍待内网环境**
- **下一期**（按依赖顺序，见下节）
  - 真站「现录」验收：意图 → 录制 → 观察者/编译自证 → 保存 → 二次回放
  - CI 闸门：`active` 流程进流水线，失败非零退出
  - 对象库 Spy Web UI（API/派 job 解析已有；可视化捕捉与 Explorer 入库仍待）
  - 失败修复 UI（API：`/failure-heal/propose` 已有；控制台确认面板仍待）
  - L1 接口引擎：导 HAR / OpenAPI、变量提取、批量跑
- 验证码、SSO、**iframe 内元素**明确不支持。
  iframe：回放发现目标只在子 frame 时会报 `IframeNotSupported`（不再伪装成偶发找不到）。
  登录路径已接通检测：命中验证码/滑块/双因素等文案会抛 `UnsupportedLoginChallenge`
  （`reason=login_unsupported`），不再拖到普通登录超时假绿；**不自动破解**
- `packages/adapters/oinone` 保留厂商特例（`oio-` 等）；Ant Design / Element UI 通用选择器
  已迁到 `autotest_executor/ui_selectors.py`，经 `locator_script` 注入录制/回放 JS

## 方向与排期

目标形态是**内网团队版**，不是 SaaS。多副本与对象存储已正式取消；
**多租户暂缓非取消**——`Scope` 的 tenant / project 字段保留但恒为默认值，隔离规则未实现也未承诺，
触发条件见 `docs/platform-restructure-plan.md` §6.6。

三步重构（测试网 → 拆边界 → React 控制台）已完成。下一期**按依赖顺序**，不是并列清单：

1. ~~`restructure-debt`~~ — **已完成（2026-10-12）**：全仓 864 处未用导入清零、2 处重复定义修掉、
   重复路由注册删除（启动警告消失）、一次性脚本删除、lint 门禁进 CI；`pytest` 仍 45 passed。
   仅余真站回放验收待环境
2. ~~`locator-popup-fix`~~ — **代码侧已落地**（本地 Ant Design 浮层 fixture 回归全绿）；余真站连续回放
3. 真站「现录」验收 — 需先在真站确认 2 的浮层路径
4. `ci-daily-gate` — `active` 流程进流水线 — 需先有稳定浮层路径，否则闸门天天红
5. 对象库 + Spy，然后 L1 接口引擎（HAR）；数据驱动与检查点暂缓

理由与完整排期见 `docs/platform-restructure-plan.md`。

功能线文档：

- `docs/katalon-gap-and-requirements.md` — 对标 Katalon 的差距与需求来源
- `docs/p1.1-recording-plan.md` — 确定性录制回放
- `docs/p1.2-ai-compiler-plan.md` — AI 编译（录完润色，不改骨架）
- `docs/p1.2-ai-observer-plan.md` — AI 观察者（认识页面再写脚本）
- `docs/phase-e/failure-heal-ai-patch.md` — 回放失败后 AI/fixture 提案补丁（dry-run → 人工确认写回）
