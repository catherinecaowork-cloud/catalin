"""登录器。

同一份凭证同时服务浏览器回放与接口请求——一处登录，两边都能用。
不支持的登录挑战（验证码、二次验证、SSO 跳转）要明确报「不支持」，
而不是以超时或普通失败的形式表现，否则使用者会去查错的方向。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from autotest_protocol import AuthRef, Candidate, Step, Target


class UnsupportedLoginChallenge(RuntimeError):
    """检测到本期不支持的登录挑战。"""


@dataclass
class AuthMaterial:
    """登录所需的运行时材料。"""

    cookies: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    form: dict[str, Any] | None = None


_CHALLENGE_HINTS = (
    "验证码",
    "captcha",
    "滑块",
    "短信验证",
    "verification code",
    "two-factor",
    "双因素",
)


def build_material(auth: AuthRef, payload: dict[str, Any] | None, base_url: str) -> AuthMaterial:
    if auth.type == "none" or payload is None:
        return AuthMaterial()

    if auth.type == "cookie":
        return AuthMaterial(cookies=_parse_cookie_header(payload.get("cookie", ""), base_url))

    if auth.type == "token":
        header = payload.get("header") or "Authorization"
        value = payload.get("value") or ""
        if not value:
            raise ValueError("token 凭证缺少 value")
        return AuthMaterial(headers={header: value})

    if auth.type == "form":
        return AuthMaterial(form=payload)

    raise ValueError(f"不支持的登录方式：{auth.type}")


def _parse_cookie_header(cookie_header: str, base_url: str) -> list[dict[str, Any]]:
    host = urlparse(base_url).hostname or "localhost"
    cookies: list[dict[str, Any]] = []
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {"name": name.strip(), "value": value.strip(), "domain": host, "path": "/"}
        )
    return cookies


def _target(spec: Any) -> Target:
    """把凭证里声明的定位方式转成 Target。

    支持简写 {"testid": "username"} 或完整 {"candidates": [...]}。
    """
    if isinstance(spec, dict) and "candidates" in spec:
        return Target.model_validate(spec)
    if isinstance(spec, dict):
        candidates = [
            Candidate(kind=kind, value=value)  # type: ignore[arg-type]
            for kind, value in spec.items()
            if kind in {"testid", "field", "role", "label", "placeholder", "text", "css"}
        ]
        if candidates:
            return Target(candidates=candidates)
    raise ValueError(f"无法解析的定位声明：{spec!r}")


def form_login_steps(form: dict[str, Any], base_url: str) -> list[Step]:
    """把表单登录表达成普通步骤。

    登录不是特例：它也走同一套动作原语，这样直播里能看到每一步。
    """
    login_url = urljoin(base_url + "/", str(form.get("login_path", "/")).lstrip("/"))
    steps = [
        Step(id="login.goto", action="goto", value=login_url, label="打开登录页"),
        Step(
            id="login.username",
            action="fill",
            target=_target(form["username_target"]),
            value=str(form["username"]),
            label="填写用户名",
        ),
        Step(
            id="login.password",
            action="fill",
            target=_target(form["password_target"]),
            value=str(form["password"]),
            label="填写密码",
        ),
        Step(
            id="login.submit",
            action="click",
            target=_target(form["submit_target"]),
            label="提交登录",
        ),
        # 用「密码框消失」判断登录成功，而不是等 load 事件：
        # 单页应用登录后往往不触发整页导航，load 会立刻返回，
        # 于是密码错误也会被当成登录成功，后面的步骤全是错的。
        Step(
            id="login.wait",
            action="waitFor",
            condition="hidden",
            target=_target(form["password_target"]),
            label="等待登录完成（登录框消失）",
            timeout_ms=int(form.get("login_timeout_ms", 20_000)),
        ),
    ]
    success_text = form.get("success_text")
    if success_text:
        steps.append(
            Step(
                id="login.assert",
                action="assert",
                assert_kind="text_contains",
                expected=str(success_text),
                label="断言登录成功",
            )
        )
    return steps


def detect_login_challenge(page_text: str) -> str | None:
    lowered = page_text.lower()
    for hint in _CHALLENGE_HINTS:
        if hint.lower() in lowered:
            return hint
    return None
