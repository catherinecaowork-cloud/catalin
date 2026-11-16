"""阶段 C：登录挑战检测接通（无浏览器 / 无内网）。"""

from __future__ import annotations

import pytest

from autotest_executor.auth import (
    UnsupportedLoginChallenge,
    detect_login_challenge,
    raise_if_login_challenge,
)


def test_detect_login_challenge_hits_common_hints() -> None:
    assert detect_login_challenge("请输入验证码后继续") == "验证码"
    assert detect_login_challenge("Please complete the CAPTCHA") == "captcha"
    assert detect_login_challenge("拖动滑块完成验证") == "滑块"
    assert detect_login_challenge("短信验证已发送") == "短信验证"
    assert detect_login_challenge("Enable two-factor authentication") == "two-factor"
    assert detect_login_challenge("请完成双因素认证") == "双因素"


def test_detect_login_challenge_ignores_normal_login() -> None:
    assert detect_login_challenge("用户名 密码 登录") is None
    assert detect_login_challenge("") is None


def test_raise_if_login_challenge_is_clear_error() -> None:
    with pytest.raises(UnsupportedLoginChallenge) as caught:
        raise_if_login_challenge("页面出现验证码，请刷新")
    message = str(caught.value)
    assert "验证码" in message
    assert "不支持" in message


def test_raise_if_login_challenge_noop_without_hint() -> None:
    raise_if_login_challenge("欢迎登录企业内部系统")
