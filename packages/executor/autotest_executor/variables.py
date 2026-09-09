"""步骤变量的单次运行解析。

只解析步骤的 value / expected；定位 target 永远保持录制时的原值。
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Mapping, Sequence

from autotest_protocol import Step

_TIME_DIRECTIVES = set("aAwdbBmyYHIMSpfzZjUWcxX%GVu")


class VariableResolutionError(ValueError):
    """变量表达式无效或无法解析。"""


class VariableResolver:
    """持有一次 run 的变量状态，保证同名 unique 始终得到同一个值。"""

    def __init__(self, variables: Mapping[str, str] | None = None) -> None:
        self._variables = dict(variables or {})
        self._unique_values: dict[str, str] = {}
        self._now = datetime.now()

    def resolve(self, value: str | None) -> str | None:
        if value is None:
            return None

        parts: list[str] = []
        cursor = 0
        while True:
            start = value.find("{{", cursor)
            stray_close = value.find("}}", cursor)
            if stray_close != -1 and (start == -1 or stray_close < start):
                raise VariableResolutionError("变量表达式存在未配对的结束标记")
            if start == -1:
                parts.append(value[cursor:])
                break

            parts.append(value[cursor:start])
            end = value.find("}}", start + 2)
            if end == -1:
                raise VariableResolutionError("变量表达式存在未配对的开始标记")

            expression = value[start + 2 : end]
            if "{{" in expression or "}}" in expression:
                raise VariableResolutionError("不允许嵌套变量表达式")
            parts.append(self._resolve_expression(expression))
            cursor = end + 2

        return "".join(parts)

    def _resolve_expression(self, expression: str) -> str:
        kind, separator, argument = expression.partition(":")
        if not separator or not argument:
            raise VariableResolutionError(f"无效变量表达式：{{{{{expression}}}}}")
        if any(char in argument for char in "{}"):
            raise VariableResolutionError("不允许嵌套变量表达式")

        if kind == "unique":
            self._check_key(argument, kind)
            return self._unique_values.setdefault(
                argument, f"AT_{argument}_{secrets.token_hex(6)}"
            )
        if kind == "now":
            self._check_time_format(argument)
            try:
                return self._now.strftime(argument)
            except (TypeError, ValueError) as exc:
                raise VariableResolutionError(f"无效时间格式：{argument}") from exc
        if kind == "env":
            self._check_key(argument, kind)
            if argument not in self._variables:
                raise VariableResolutionError(f"缺少环境变量：{argument}")
            resolved = self._variables[argument]
            if "{{" in resolved or "}}" in resolved:
                raise VariableResolutionError(f"环境变量 {argument} 不允许包含变量表达式")
            return resolved
        raise VariableResolutionError(f"未知变量类型：{kind}")

    @staticmethod
    def _check_time_format(value: str) -> None:
        index = 0
        while index < len(value):
            if value[index] != "%":
                index += 1
                continue
            index += 1
            if index >= len(value) or value[index] not in _TIME_DIRECTIVES:
                bad = value[index] if index < len(value) else "<结尾>"
                raise VariableResolutionError(f"无效时间格式指令：%{bad}")
            index += 1

    @staticmethod
    def _check_key(key: str, kind: str) -> None:
        if not all(char.isalnum() or char in "._-" for char in key):
            raise VariableResolutionError(f"{kind} 变量名包含非法字符：{key}")


def resolve_steps(
    steps: Sequence[Step], variables: Mapping[str, str] | None = None
) -> list[Step]:
    """深拷贝并解析一组步骤，不改变调用方持有的 Step 对象。"""

    resolver = VariableResolver(variables)
    resolved: list[Step] = []
    for step in steps:
        copied = step.model_copy(deep=True)
        copied.value = resolver.resolve(copied.value)
        copied.expected = resolver.resolve(copied.expected)
        resolved.append(copied)
    return resolved
