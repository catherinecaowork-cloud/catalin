"""AI 编译持久化状态机自测，不访问模型或浏览器。"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import autotest_control.compilation_worker as module
from autotest_control.ai import CompileResult, TokenUsage
from autotest_control.models import Base, RecordingCompilation, Run, Site
from autotest_protocol import Step


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"× {message}")
    print(f"√ {message}")


class FakeCompiler:
    def compile(self, steps, **_kwargs):
        compiled = [step.model_copy(deep=True) for step in steps]
        compiled[-1].label = "AI：保存款式"
        return CompileResult(
            steps=compiled,
            notes=["模型建议已应用"],
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            attempts=1,
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        engine = create_engine(f"sqlite:///{(Path(temp) / 'test.db').as_posix()}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        @contextmanager
        def sessions():
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        module.session_scope = sessions
        module.AICompiler = FakeCompiler

        steps = [
            {"id": "s1", "action": "goto", "value": "http://example.test/"},
            {
                "id": "s2",
                "action": "click",
                "label": "保存",
                "target": {"candidates": [{"kind": "text", "value": "保存"}]},
                "mutating": True,
            },
        ]
        with sessions() as session:
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
            session.add(
                Run(
                    id="record",
                    tenant_id="default",
                    project_id="default",
                    site_id="site",
                    kind="record",
                    status="passed",
                    job={
                        "auth": {"type": "none", "ref": None},
                        "site": {"probe": {"enabled": True, "error_url_patterns": []}},
                    },
                    summary={"steps": steps, "compiler_context": {}},
                    required_labels=["headed"],
                )
            )
            session.add(
                RecordingCompilation(
                    id="compile",
                    tenant_id="default",
                    project_id="default",
                    recording_run_id="record",
                    status="queued",
                    intent="保存款式",
                    deterministic_steps=steps,
                )
            )

        worker = module.CompilationWorker()
        _assert(worker.run_once(), "领取 queued 编译")
        with sessions() as session:
            row = session.get(RecordingCompilation, "compile")
            _assert(row.status == "validating", "编译成功后进入回放验证")
            _assert(row.attempt == 1 and row.validation_run_id, "记录轮次和验证 run")
            validation = session.get(Run, row.validation_run_id)
            _assert(validation is not None and validation.status == "queued", "验证任务已入队")
            _assert(
                validation.job["flow"]["steps"][-1]["label"] == "AI：保存款式",
                "验证 job 携带 AI 步骤",
            )
            validation.status = "passed"

        _assert(worker.run_once(), "推进已完成的验证")
        with sessions() as session:
            row = session.get(RecordingCompilation, "compile")
            _assert(row.status == "passed", "回放通过后编译状态为 passed")
            _assert(row.usage == {"input_tokens": 10, "output_tokens": 5}, "累计 token usage")

            failed = session.get(Run, row.validation_run_id)
            failed.status = "failed"
            failed.summary = {
                "steps": [
                    {"step_id": "s2", "status": "failed", "message": "找不到保存按钮"}
                ]
            }
            row.status = "validating"
            row.attempt = 3

        worker.run_once()
        with sessions() as session:
            row = session.get(RecordingCompilation, "compile")
            _assert(row.status == "fallback", "第三轮失败后回退确定性步骤")
            _assert(row.compiled_steps == row.deterministic_steps, "回退内容正确")

        with Session(engine) as session:
            _assert(
                session.scalar(select(RecordingCompilation).where(RecordingCompilation.id == "compile"))
                is not None,
                "状态持久化在数据库",
            )
        engine.dispose()

    print("\n编译状态机自测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
