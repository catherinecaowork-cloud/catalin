"""任务描述。

job 必须自包含：Worker 拿到它就能执行，不连数据库。凭证以引用形式下发，
Worker 用受控接口换取，只在内存里解密。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from autotest_protocol.dsl import Flow

JobKind = Literal["replay", "api", "inspect", "record"]


class ProbeConfig(BaseModel):
    """探针配置。

    error_url_patterns 为空表示不限定后端框架：任何 JSON 响应里出现非空
    errors 都算失败。填了模式则只检查匹配的请求。
    """

    enabled: bool = True
    error_url_patterns: list[str] = []


class SiteRef(BaseModel):
    id: str
    base_url: str
    env: str = "test"
    adapter: str = "generic"
    probe: ProbeConfig = ProbeConfig()


class AuthRef(BaseModel):
    """登录方式引用。

    ref 指向控制面的凭证记录，Worker 换取明文；none 表示这条流程不需要登录。
    """

    type: Literal["none", "cookie", "token", "form"] = "none"
    ref: str | None = None


class RunOptions(BaseModel):
    headless: bool = True
    # 每步都截图；失败步骤另外保留录像与 trace
    screenshot_each_step: bool = True
    video: Literal["off", "on_failure"] = "on_failure"
    trace: Literal["off", "on_failure"] = "on_failure"
    # dry_run 只走读操作，写操作步骤会被跳过
    dry_run: bool = False
    viewport_width: int = 1440
    viewport_height: int = 900


class Job(BaseModel):
    run_id: str
    kind: JobKind = "replay"
    site: SiteRef
    auth: AuthRef = AuthRef()
    flow: Flow | None = None
    record_intent: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    options: RunOptions = RunOptions()
    # kind=inspect 时要打开的页面。踩点任务不属于任何已有站点，
    # 所以地址单独带着，而不是从 site 拼。
    inspect_url: str | None = None
    # kind=record 时，登录后从哪个页面开始录（站点相对路径或绝对地址）
    record_start_path: str | None = None
    # 领取租约到期时间（ISO 字符串），超时未完成的任务会被平台回收
    lease_expires_at: str | None = None
