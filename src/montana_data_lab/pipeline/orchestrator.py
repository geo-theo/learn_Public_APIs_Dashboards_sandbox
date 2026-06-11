from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from montana_data_lab.config import settings
from montana_data_lab.db import init_database, session_scope
from montana_data_lab.models import Park, StreamGauge
from montana_data_lab.pipeline.etl import fetch_nws, fetch_usgs, load_visit_csv
from montana_data_lab.pipeline.quality import run_quality_checks
from montana_data_lab.pipeline.sample_data import generate_sample_visits
from montana_data_lab.reference_data import PARKS, STREAM_GAUGES


def seed_reference_data(session: Session) -> None:
    for row in PARKS:
        statement = sqlite_insert(Park).values(**row, active=True)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name": statement.excluded.name,
                    "region": statement.excluded.region,
                    "latitude": statement.excluded.latitude,
                    "longitude": statement.excluded.longitude,
                    "active": statement.excluded.active,
                },
            )
        )
    for row in STREAM_GAUGES:
        statement = sqlite_insert(StreamGauge).values(**row)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["site_no"],
                set_={
                    "name": statement.excluded.name,
                    "latitude": statement.excluded.latitude,
                    "longitude": statement.excluded.longitude,
                    "related_park_code": statement.excluded.related_park_code,
                },
            )
        )
    session.commit()


def initialize() -> None:
    init_database()
    with session_scope() as session:
        seed_reference_data(session)


def ensure_sample_file(session: Session, *, days: int = 180, seed: int = 42) -> Path:
    path = settings.raw_data_dir / "tablet_visits.csv"
    if not path.exists():
        generate_sample_visits(session, days=days, seed=seed, output_path=path)
    return path


def refresh_all() -> dict[str, str]:
    initialize()
    results: dict[str, str] = {}
    with session_scope() as session:
        sample_path = ensure_sample_file(session)
        results["tablet_visits"] = load_visit_csv(session, sample_path).status
        results["nws"] = fetch_nws(session).status
        results["usgs"] = fetch_usgs(session).status
        results["quality"] = run_quality_checks(session).status
    return results


def database_has_visits(session: Session) -> bool:
    return session.scalar(select(VisitRecord.id).limit(1)) is not None


# Imported last to keep the main orchestration imports easy to scan.
from montana_data_lab.models import VisitRecord  # noqa: E402
