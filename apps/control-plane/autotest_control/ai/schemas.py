"""AI 编译层的严格输入输出契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from autotest_protocol.dsl import AssertKind, Step


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepEdit(StrictModel):
    """只允许通过确定性步骤的 id 修改安全字段。"""

    source_id: str = Field(min_length=1)
    label: str | None = None
    phase: str | None = None
    mutating: bool | None = None
    value: str | None = None

    @model_validator(mode="after")
    def _has_an_edit(self) -> StepEdit:
        if not (self.model_fields_set - {"source_id"}):
            raise ValueError("step edit 至少需要提供一个修改字段")
        return self


class AssertionProposal(StrictModel):
    """要追加的断言；target 是已有步骤 id，不是新定位器。"""

    id: str = Field(min_length=1)
    assert_kind: AssertKind
    target: str | None = None
    expected: str | None = None
    label: str | None = None
    phase: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> AssertionProposal:
        if self.assert_kind == "no_page_error":
            if self.expected is not None:
                raise ValueError("no_page_error 不接受 expected")
        elif self.expected is None:
            raise ValueError(f"断言 {self.assert_kind} 需要 expected")
        if self.assert_kind in {"element_visible", "element_count"} and self.target is None:
            raise ValueError(f"断言 {self.assert_kind} 需要 target")
        return self


class CompileContract(StrictModel):
    step_edits: list[StepEdit] = Field(default_factory=list)
    assertions: list[AssertionProposal] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ImageInput(StrictModel):
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
    data: str = Field(min_length=1, description="Base64 编码的图片数据")


class TokenUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class MessageResult(StrictModel):
    text: str
    usage: TokenUsage
    attempts: int = Field(ge=1)


class CompileResult(StrictModel):
    steps: list[Step]
    notes: list[str]
    usage: TokenUsage
    attempts: int = Field(ge=1)
