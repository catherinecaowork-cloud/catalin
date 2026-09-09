"""控制面与执行器共享的数据结构。

单独成包，是为了让 job / event / 步骤 DSL 只有一份定义：
平台发什么、Worker 认什么，由同一组模型保证。
"""

from autotest_protocol.dsl import (
    ACTIONS,
    CANDIDATE_STABILITY,
    AssertKind,
    Candidate,
    ChooseMode,
    Flow,
    Phase,
    Step,
    Target,
    TargetScope,
    learn_candidates,
    sort_candidates,
)
from autotest_protocol.events import Event, EventType, new_event
from autotest_protocol.job import AuthRef, Job, JobKind, RunOptions, SiteRef

__all__ = [
    "ACTIONS",
    "CANDIDATE_STABILITY",
    "AssertKind",
    "AuthRef",
    "Candidate",
    "ChooseMode",
    "Event",
    "EventType",
    "Flow",
    "Job",
    "JobKind",
    "Phase",
    "RunOptions",
    "SiteRef",
    "Step",
    "Target",
    "TargetScope",
    "new_event",
    "learn_candidates",
    "sort_candidates",
]
