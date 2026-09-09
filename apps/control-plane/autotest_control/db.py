from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from autotest_control.models import Base
from autotest_control.settings import settings
from autotest_control.storage import prune_retained_runs

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    settings.ensure_dirs()
    Base.metadata.create_all(engine)
    _ensure_sqlite_columns()
    prune_retained_runs()


def _ensure_sqlite_columns() -> None:
    """create_all 不会给已有表加列。开发期 SQLite 在这里补。"""
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(run)")).fetchall()}
        if "stop_requested" not in cols:
            conn.execute(text("ALTER TABLE run ADD COLUMN stop_requested BOOLEAN DEFAULT 0"))
        if "batch_id" not in cols:
            conn.execute(text("ALTER TABLE run ADD COLUMN batch_id VARCHAR(36)"))
        if "batch_index" not in cols:
            conn.execute(text("ALTER TABLE run ADD COLUMN batch_index INTEGER"))
        flow_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(flow)")).fetchall()}
        if "setup_flow_id" not in flow_cols:
            conn.execute(text("ALTER TABLE flow ADD COLUMN setup_flow_id VARCHAR(36)"))
        if "imported_from" not in flow_cols:
            conn.execute(text("ALTER TABLE flow ADD COLUMN imported_from VARCHAR(200)"))
        if "page_widget_model" not in flow_cols:
            conn.execute(text("ALTER TABLE flow ADD COLUMN page_widget_model JSON"))
        run_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(run)")).fetchall()}
        if "observation_model" not in run_cols:
            conn.execute(text("ALTER TABLE run ADD COLUMN observation_model JSON"))
        comp_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(recording_compilation)")).fetchall()
        }
        if "observer_steps" not in comp_cols:
            conn.execute(text("ALTER TABLE recording_compilation ADD COLUMN observer_steps JSON"))
        if "compile_mode" not in comp_cols:
            conn.execute(
                text("ALTER TABLE recording_compilation ADD COLUMN compile_mode VARCHAR(20) DEFAULT 'observer'")
            )


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI 依赖。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
