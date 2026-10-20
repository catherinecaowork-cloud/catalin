"""P1.2 AI 观察者自测：契约、任选策略、润色路径隔离。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotest_control.ai import AIContractError, apply_contract, validate_observer_steps
from autotest_control.compilation_worker import CompilationWorker
from autotest_control.models import RecordingCompilation
from autotest_control.ai.schemas import CompileContract, StepEdit
from autotest_control.deps import Scope
from autotest_control.domain.observer import apply_snapshot_to_run, attach_model_to_flow, load_site_widget_models
from autotest_control.models import Base, Flow, Run, Site
from autotest_protocol import Step, Target, Candidate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


def _raises(error_type: type[Exception], call, message: str) -> None:
    try:
        call()
    except error_type:
        print(f"√ {message}")
        return
    raise SystemExit(f"× {message}")


def main() -> int:
    choose = Step(
        id="s1",
        action="choose",
        label="尺码",
        value="155",
        choose_mode="search_or_first",
        target=Target(candidates=[Candidate(kind="label", value="尺码")]),
    )
    _raises(
        AIContractError,
        lambda: validate_observer_steps(
            [choose.model_copy(update={"choose_mode": "exact"})],
            sample_steps=[choose],
        ),
        "样例点了 155 时不得输出 exact",
    )
    validated = validate_observer_steps([choose], sample_steps=[choose])
    _assert(validated[0].choose_mode == "search_or_first", "任选策略保留 search_or_first")

    original = Step(
        id="s2",
        action="click",
        target=Target(candidates=[Candidate(kind="text", value="保存")]),
    )
    polished = apply_contract(
        [original],
        CompileContract(step_edits=[StepEdit(source_id="s2", label="保存款式", mutating=True)]),
    )
    _assert(polished[0].action == "click" and polished[0].target == original.target, "仅润色路径仍禁止改 target")

    temp = tempfile.mkdtemp()
    engine = create_engine(f"sqlite:///{Path(temp) / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session: Session = factory()
    session.add(
        Site(
            id="site",
            tenant_id="default",
            project_id="default",
            name="自测",
            base_url="http://example.test",
            env="test",
            adapter="generic",
            probe_error_url_patterns=[],
        )
    )
    run = Run(
        id="run-1",
        tenant_id="default",
        project_id="default",
        site_id="site",
        kind="record",
        status="passed",
        job={},
    )
    session.add(run)
    session.commit()
    updated = apply_snapshot_to_run(
        run,
        {
            "trigger": "form_visible",
            "url": "http://example.test/",
            "layer": {"kind": "modal", "name": "新增"},
            "fields": [
                {"label": "尺码", "widget_kind": "tab", "sample_options": ["155", "160"]},
                {"label": "155", "widget_kind": "tab"},
            ],
        },
    )
    _assert(updated is not None and any(e.display_name == "尺码" for e in updated.entries), "快照合并认识尺码")
    _assert(all(e.display_name != "155" for e in updated.entries), "动态选项未建成组件")

    flow = Flow(
        id="flow-1",
        tenant_id="default",
        project_id="default",
        site_id="site",
        name="款式",
        steps=[{"id": "s1", "action": "click", "label": "保存"}],
    )
    session.add(flow)
    session.commit()
    attach_model_to_flow(flow, run)
    session.commit()
    saved = session.get(Flow, "flow-1")
    _assert(saved is not None and saved.page_widget_model is not None, "保存流程带上页面模型")

    site_model = load_site_widget_models(session, Scope("default", "default"), "site")
    _assert(any(entry.display_name == "尺码" for entry in site_model.entries), "同站点可读已有模型")

    row = RecordingCompilation(
        id="comp-1",
        tenant_id="default",
        project_id="default",
        recording_run_id="run-1",
        intent="新增",
        deterministic_steps=[{"id": "s1", "action": "goto", "value": "/"}],
        observer_steps=[{"id": "s1", "action": "choose", "value": "155", "choose_mode": "other", "target": {"candidates": [{"kind": "label", "value": "尺码"}]}}],
        compile_mode="observer",
    )
    CompilationWorker._fallback(row, "验证失败")
    _assert(row.compile_mode == "fallback" and row.observer_steps is None, "观察者失败可降级样例")

    session.close()
    engine.dispose()
    print("selftest_ai_observer: 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
