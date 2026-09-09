"""给已有站点补表单登录：定位字段抽取。"""

from __future__ import annotations

from autotest_control.api import _form_login_locators


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    target = {"candidates": [{"kind": "placeholder", "value": "账号"}]}
    locators = _form_login_locators(
        {
            "username_target": target,
            "password_target": target,
            "submit_target": target,
            "username": "secret-should-drop",
        }
    )
    _assert(locators is not None and "username" not in locators, "只拿走定位，不带走账号")
    _assert(_form_login_locators({"username_target": target}) is None, "缺密码框则不能当登录表单")
    _assert(_form_login_locators(None) is None, "空内容不能当登录表单")
    print("selftest_form_credential ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
