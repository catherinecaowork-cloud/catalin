"""定位学习：失败过的候选要删掉，下次从命中的那个开始。"""

from __future__ import annotations

from autotest_protocol import Candidate, learn_candidates


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def main() -> int:
    role = Candidate(kind="role", value="button", name="新增")
    text = Candidate(kind="text", value="新增")
    css = Candidate(kind="css", value="button.ant-btn")
    learned = learn_candidates([role, text, css], winner=text, failed=[role])
    _assert(learned[0].kind == "text", "命中的候选排第一")
    _assert(all(item.kind != "role" for item in learned), "已空等失败的候选被删掉")
    _assert(any(item.kind == "css" for item in learned), "没试过的候选留着当退路")

    only = learn_candidates([role, text], winner=text, failed=[role])
    _assert(len(only) == 1 and only[0].kind == "text", "没有退路时只保留命中项")
    print("\n定位学习自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
