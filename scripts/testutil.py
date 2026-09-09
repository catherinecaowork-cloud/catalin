"""自测与 pytest 共用的断言 helper。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pytest

E = TypeVar("E", bound=BaseException)


def assert_ok(condition: bool, message: str) -> None:
    assert condition, message


def rejects(call: Callable[[], object], exc_type: type[E]) -> None:
    with pytest.raises(exc_type):
        call()
