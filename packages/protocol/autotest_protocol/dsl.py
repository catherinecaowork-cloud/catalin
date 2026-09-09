"""步骤 DSL。

一条流程只能由固定的动作原语构成。这是刻意的限制：将来 AI 探索的输出也必须
落在同一套原语上，这样「探索产物」天生就是「可回放步骤」，不需要翻译层。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Action = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "choose",
    "scroll",
    "upload",
    "waitFor",
    "readTable",
    "pageHealth",
    "assert",
    "screenshot",
]

ACTIONS: tuple[str, ...] = (
    "goto",
    "click",
    "fill",
    "select",
    "choose",
    "scroll",
    "upload",
    "waitFor",
    "readTable",
    "pageHealth",
    "assert",
    "screenshot",
)

CandidateKind = Literal[
    "testid", "field", "matrix", "role", "label", "placeholder", "text", "css"
]

# 定位方式的稳定性排序，数字越小越优先。
# 哈希 class 不在此列——它不是一种候选，而是被明确排除的做法。
CANDIDATE_STABILITY: dict[str, int] = {
    "testid": 0,
    "field": 1,
    "matrix": 1,
    "role": 2,
    "label": 3,
    "placeholder": 4,
    "text": 5,
    "css": 6,
}

AssertKind = Literal[
    "text_contains",
    "element_visible",
    "element_count",
    "no_page_error",
    "table_row_count_min",
]

Phase = Literal["setup", "main", "verify"]

WaitCondition = Literal["load", "visible", "hidden", "network_idle", "probe_ready"]

ChooseMode = Literal["exact", "search_or_first", "other"]


class Candidate(BaseModel):
    """一种定位方式。同一个目标会保存多个候选并按稳定性排序。"""

    kind: CandidateKind
    value: str
    # role 候选的可访问名，例如 role=button + name="保存"
    name: str | None = None

    @property
    def stability(self) -> int:
        return CANDIDATE_STABILITY[self.kind]

    def describe(self) -> str:
        if self.name:
            return f"{self.kind}={self.value!r} name={self.name!r}"
        return f"{self.kind}={self.value!r}"


class TargetScope(BaseModel):
    """点击当下所在的 DOM 范围。每次录制现场爬，不复用上一次的结构。

    kind=page 表示当时不在遮罩层里；modal / drawer / dropdown 回放时先在
    当前页活着的同类层里找，找不到再退回录到的 css。
    """

    kind: Literal["page", "modal", "drawer", "dropdown"] = "page"
    css: str | None = None
    name: str | None = None
    path: str | None = None


class Target(BaseModel):
    """定位目标：一组候选，不是单一选择器。

    回放时按稳定性依次尝试。某次命中更靠后的候选后，执行器会删掉
    已证明失效的首选并写回流程，避免下一次再从坏定位空等。
    """

    candidates: list[Candidate] = Field(min_length=1)
    scope: TargetScope | None = None
    # 录制当场认出的控件/面板类型，回放用来重新打开同一类下拉。
    widget: str | None = None
    panel: str | None = None
    trigger_css: str | None = None

    def ordered(self) -> list[Candidate]:
        # 列表顺序就是回放顺序。学习写回后不再按「理论稳定性」重排，
        # 否则刚删掉的失效 role/css 又会被排回第一。
        return list(self.candidates)


def candidate_key(candidate: Candidate) -> str:
    return candidate.describe()


def learn_candidates(
    candidates: list[Candidate], winner: Candidate, failed: list[Candidate]
) -> list[Candidate]:
    """固化这次命中的定位：好用的放第一个，已证明失效的删掉。

    没试过的候选留下当退路。下次回放按这个列表走，不再从已失败的首选空等。
    """
    failed_keys = {candidate_key(item) for item in failed}
    winner_key = candidate_key(winner)
    kept = [winner]
    for item in candidates:
        key = candidate_key(item)
        if key == winner_key or key in failed_keys:
            continue
        kept.append(item)
    return kept


def sort_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda c: _stability(c))


def _stability(candidate: Candidate) -> int:
    if candidate.kind == "css" and candidate.value.startswith("[data-"):
        return 1
    return CANDIDATE_STABILITY.get(candidate.kind, 9)


class Step(BaseModel):
    """单个步骤。字段按动作校验，缺参数在保存或执行前就失败，而不是跑到一半。"""

    id: str
    action: Action
    phase: Phase | None = None
    label: str | None = None
    target: Target | None = None
    value: str | None = None
    condition: WaitCondition | None = None
    assert_kind: AssertKind | None = None
    expected: str | None = None
    timeout_ms: int = 10_000
    # choose：search_or_first=能搜就搜没有用第一条；other=编辑时换掉已选项
    choose_mode: ChooseMode | None = None
    # True=非必填，选不到就跳过，不中断整次运行。None=回放时看表单项星号。
    optional: bool | None = None
    # 标记会往被测环境写数据的步骤。dry_run 运行时这些步骤被跳过，
    # 避免在共享测试环境里留脏数据。
    mutating: bool = False

    @model_validator(mode="after")
    def _check_required_fields(self) -> Step:
        needs_target = {"click", "fill", "select", "choose", "scroll", "upload"}
        if self.action in needs_target and self.target is None:
            raise ValueError(f"动作 {self.action} 需要 target")
        if self.action in {"fill", "select", "choose", "scroll", "upload"} and self.value is None:
            raise ValueError(f"动作 {self.action} 需要 value")
        if self.action == "goto" and not self.value:
            raise ValueError("动作 goto 需要 value（绝对地址或站点相对路径）")
        if self.action == "waitFor" and self.condition is None:
            raise ValueError("动作 waitFor 需要 condition")
        if self.action == "waitFor" and self.condition in {"visible", "hidden"} and self.target is None:
            raise ValueError(f"waitFor condition={self.condition} 需要 target")
        if self.action == "assert":
            if self.assert_kind is None:
                raise ValueError("动作 assert 需要 assert_kind")
            if self.assert_kind != "no_page_error" and self.expected is None:
                raise ValueError(f"断言 {self.assert_kind} 需要 expected")
            if self.assert_kind in {"element_visible", "element_count"} and self.target is None:
                raise ValueError(f"断言 {self.assert_kind} 需要 target")
        return self

    def display(self) -> str:
        if self.label:
            return self.label
        if self.action == "goto":
            return f"打开 {self.value}"
        if self.action == "fill":
            return f"填值 {self.value!r}"
        if self.action == "assert":
            return f"断言 {self.assert_kind}"
        if self.action == "choose":
            if self.choose_mode == "other":
                return f"选择换一项 {self.value or ''}".strip()
            return f"选择 {self.value}"
        return self.action


class Flow(BaseModel):
    """一条可回放流程。"""

    name: str
    version: int = 1
    steps: list[Step] = Field(min_length=1)
