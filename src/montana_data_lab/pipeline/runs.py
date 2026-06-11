from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from montana_data_lab.models import PipelineRun


def start_run(session: Session, source: str) -> PipelineRun:
    run = PipelineRun(source=source, status="running", started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_run(
    session: Session,
    run: PipelineRun,
    *,
    status: str,
    extracted: int = 0,
    loaded: int = 0,
    error: str | None = None,
) -> None:
    run.status = status
    run.finished_at = datetime.now(UTC)
    run.rows_extracted = extracted
    run.rows_loaded = loaded
    run.error_message = error
    session.commit()
