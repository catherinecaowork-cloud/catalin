"""定位解析：弹窗多 root 不应把单步预算乘 4 倍。"""

from __future__ import annotations

from autotest_executor.browser.locator import _root_wait_ms
from autotest_executor.compiler import _prune_redundant_candidates


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    budget = 5_000
    waits = [_root_wait_ms(i, 4, budget) for i in range(4)]
    _assert(sum(waits) <= budget + 50, f"四 root 总预算不超过 {budget}ms：{waits}={sum(waits)}")
    _assert(waits[0] >= waits[1], "首选 root 应比后备 root 等更久")

    pruned = _prune_redundant_candidates(
        [
            {"kind": "label", "value": "颜色尺码"},
            {"kind": "css", "value": "#315ac707-e508-4e63-810d-01f6c53d1df1-0-0"},
            {"kind": "matrix", "value": "SAD BLUE|160", "name": "颜色尺码"},
        ]
    )
    kinds = {item["kind"] for item in pruned}
    _assert(kinds == {"matrix"}, "有 matrix 时去掉表格标题 label 与 vxe uuid css")

    pruned_anchor = _prune_redundant_candidates(
        [
            {"kind": "label", "value": "PO单号"},
            {
                "kind": "css",
                "value": 'div:has(> .label:text-is("PO单号")) input',
            },
            {"kind": "css", "value": ".ant-picker-input input"},
        ]
    )
    values = [item.get("value") for item in pruned_anchor]
    _assert("PO单号" not in values, "有锚定 css 时去掉同名 label")
    _assert(".ant-picker-input input" not in values, "有锚定 css 时去掉泛化 picker css")

    print("\n定位预算自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
