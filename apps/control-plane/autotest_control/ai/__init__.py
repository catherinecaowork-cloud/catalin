"""Anthropic 兼容 AI 编译层。"""

from .client import (
    AIConfigurationError,
    AIRequestError,
    AnthropicClient,
)
from .compiler import (
    AICompiler,
    AIContractError,
    apply_contract,
    parse_contract,
    validate_template_value,
)
from .failure_healer import (
    AIFailureHealer,
    FailureHealContract,
    FailureHealPatch,
    FailureHealResult,
    apply_failure_patches,
    build_failure_context,
    classify_error_class,
    fixture_propose,
    parse_failure_heal_contract,
)
from .observer import AIObserver, parse_observer_contract, validate_observer_steps
from .schemas import (
    AssertionProposal,
    CompileContract,
    CompileResult,
    ImageInput,
    MessageResult,
    StepEdit,
    TokenUsage,
)

__all__ = [
    "AICompiler",
    "AIFailureHealer",
    "AIObserver",
    "AIConfigurationError",
    "AIContractError",
    "AIRequestError",
    "AnthropicClient",
    "AssertionProposal",
    "CompileContract",
    "CompileResult",
    "FailureHealContract",
    "FailureHealPatch",
    "FailureHealResult",
    "ImageInput",
    "MessageResult",
    "StepEdit",
    "TokenUsage",
    "apply_contract",
    "apply_failure_patches",
    "build_failure_context",
    "classify_error_class",
    "fixture_propose",
    "parse_contract",
    "parse_failure_heal_contract",
    "parse_observer_contract",
    "validate_observer_steps",
    "validate_template_value",
]
