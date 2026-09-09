# 通用接口 / UI 自动化测试平台

给任意能登录的网站做接口与 UI 自动化回归。不绑定被测系统：站点、登录方式、
流程都是配置出来的。

当前进度是 **P0 纵向切片**：一条链路已经端到端跑通（建站点 → 写流程 → 派任务 →
真浏览器回放 → 直播过程 → 留证据），但 P0 的其余能力还没铺完，见文末。

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

需要 Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
```

三个终端（或者前两个后台跑）：

```powershell
# 1) 控制面
python -m uvicorn autotest_control.main:app --host 127.0.0.1 --port 8910

# 2) 执行器（首次自动注册，身份缓存在 var/worker/）
runner worker --server http://127.0.0.1:8910 --name my-pc

# 3) 造一个不需要登录的示例站点和两条流程
python scripts\seed_demo.py
```

然后打开 <http://127.0.0.1:8910> ，选流程点「开始执行」。

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

## 还没做（P0 剩余）

- L1 接口引擎：导 HAR / OpenAPI 生成用例、变量提取、批量跑
- 表单登录已实现但未接过真实站点；验证码与 SSO 明确不支持
- 站点适配器只有 `generic`，框架专用规则（错误提示、加载指示器、空态）还没抽出来
- 基线比对与 CI 闸门
- 多租户只是带了字段，隔离规则未落地
- 生产形态换 Postgres + MinIO（现在是 SQLite + 本地磁盘）

规格与任务清单在 `openspec/changes/bootstrap-platform-p0/`。
