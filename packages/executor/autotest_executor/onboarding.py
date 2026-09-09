"""登录表单识别。

接入新站点时，由执行器打开页面、猜出账号框 / 密码框 / 提交按钮，
把候选定位交回控制面让人确认。控制面自己不开浏览器。

定位候选与录制共用 locator_candidates.js，两处各写一份迟早会漂移。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Page

_LOCATOR_JS = (Path(__file__).resolve().parent / "browser" / "locator_candidates.js").read_text(
    encoding="utf-8"
)

# 只找登录表单需要的三个东西；候选计算交给 __atpDescribe。
JS_FIND_LOGIN_FORM = """
() => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };

  const inputs = Array.from(document.querySelectorAll('input')).filter(visible);
  const password = inputs.find((el) => el.type === 'password');
  if (!password) return { found: false, reason: '页面上没有可见的密码输入框' };

  const passwordIndex = inputs.indexOf(password);
  const username = inputs.slice(0, passwordIndex).reverse()
    .find((el) => ['text', 'email', 'tel', ''].includes((el.type || '').toLowerCase()));
  if (!username) return { found: false, reason: '没找到账号输入框' };

  const buttons = Array.from(
    document.querySelectorAll('button, input[type=submit], [role=button]')
  ).filter(visible);
  const submit = buttons.find(
    (el) => /登\\s*录|登\\s*入|sign\\s*in|log\\s*in/i.test(el.innerText || el.value || '')
  ) || buttons[0];
  if (!submit) return { found: false, reason: '没找到提交按钮' };

  const bodyText = document.body.innerText || '';
  const challenge = ['验证码', '滑块', '短信验证', 'captcha'].find((k) => bodyText.includes(k));

  return {
    found: true,
    challenge: challenge || null,
    username_target: window.__atpDescribe(username, 'textbox'),
    password_target: window.__atpDescribe(password, null),
    submit_target: window.__atpDescribe(submit, 'button'),
    submit_text: (submit.innerText || submit.value || '').trim(),
  };
}
"""


def detect_login_form(page: Page) -> dict[str, Any]:
    page.evaluate(_LOCATOR_JS)
    return page.evaluate(JS_FIND_LOGIN_FORM)


def describe_candidates(target: dict[str, Any] | None) -> str:
    if not target:
        return "—"
    return " | ".join(f"{c['kind']}={c['value']!r}" for c in target["candidates"])
