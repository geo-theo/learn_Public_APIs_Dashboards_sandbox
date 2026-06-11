from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from montana_data_lab.config import settings
from montana_data_lab.models import (
    QualityCheck,
    StreamflowObservation,
    VisitRecord,
    WeatherForecast,
)
from montana_data_lab.pipeline.runs import finish_run, start_run


def run_quality_checks(session: Session):
    run = start_run(session, "quality")
    checked_at = datetime.now(UTC)
    try:
        session.execute(update(VisitRecord).values(quality_status="valid"))

        negative_ids = list(
            session.scalars(select(VisitRecord.id).where(VisitRecord.raw_count < 0))
        )
        missing_device_ids = list(
            session.scalars(
                select(VisitRecord.id).where(
                    (VisitRecord.device_id.is_(None)) | (VisitRecord.device_id == "")
                )
            )
        )
        outlier_ids = list(
            session.scalars(
                select(VisitRecord.id).where(
                    VisitRecord.raw_count > settings.visit_outlier_threshold
                )
            )
        )
        invalid_weight_ids = list(
            session.scalars(select(VisitRecord.id).where(VisitRecord.survey_weight <= 0))
        )

        duplicate_groups = session.execute(
            select(
                VisitRecord.park_id,
                VisitRecord.visit_date,
                VisitRecord.device_id,
                func.count(VisitRecord.id).label("row_count"),
            )
            .where(VisitRecord.device_id.is_not(None))
            .group_by(VisitRecord.park_id, VisitRecord.visit_date, VisitRecord.device_id)
            .having(func.count(VisitRecord.id) > 1)
        ).all()
        duplicate_ids: list[int] = []
        for park_id, visit_date, device_id, _row_count in duplicate_groups:
            ids = list(
                session.scalars(
                    select(VisitRecord.id).where(
                        VisitRecord.park_id == park_id,
                        VisitRecord.visit_date == visit_date,
                        VisitRecord.device_id == device_id,
                    )
                )
            )
            duplicate_ids.extend(ids)

        checks = [
            ("non_negative_counts", "error", negative_ids, "Visit counts must be zero or more."),
            (
                "device_id_present",
                "error",
                missing_device_ids,
                "Tablet uploads require a device identifier for traceability.",
            ),
            (
                "plausible_count_range",
                "warning",
                outlier_ids,
                f"Counts above {settings.visit_outlier_threshold:,} require review.",
            ),
            (
                "positive_survey_weight",
                "error",
                invalid_weight_ids,
                "Weights must be greater than zero.",
            ),
            (
                "unique_daily_device_record",
                "error",
                duplicate_ids,
                "Only one record per park, date, and device is publishable.",
            ),
        ]

        all_invalid_ids = set().union(*(set(item[2]) for item in checks))
        if all_invalid_ids:
            session.execute(
                update(VisitRecord)
                .where(VisitRecord.id.in_(all_invalid_ids))
                .values(quality_status="invalid")
            )

        for name, severity, failed_ids, description in checks:
            session.add(
                QualityCheck(
                    pipeline_run_id=run.id,
                    check_name=name,
                    severity=severity,
                    passed=not failed_ids,
                    failed_rows=len(failed_ids),
                    details=json.dumps(
                        {
                            "description": description,
                            "sample_record_ids": failed_ids[:10],
                        }
                    ),
                    checked_at=checked_at,
                )
            )

        freshness_limit = checked_at - timedelta(hours=6)
        freshness_checks = [
            (
                "nws_data_fresh",
                session.scalar(
                    select(func.max(WeatherForecast.fetched_at))
                ),
            ),
            (
                "usgs_data_fresh",
                session.scalar(
                    select(func.max(StreamflowObservation.fetched_at))
                ),
            ),
        ]
        for name, latest_fetch in freshness_checks:
            failed = latest_fetch is None or _as_utc(latest_fetch) < freshness_limit
            session.add(
                QualityCheck(
                    pipeline_run_id=run.id,
                    check_name=name,
                    severity="warning",
                    passed=not failed,
                    failed_rows=int(failed),
                    details=json.dumps(
                        {
                            "description": "Public API data should be refreshed within six hours.",
                            "latest_fetch": latest_fetch.isoformat() if latest_fetch else None,
                        }
                    ),
                    checked_at=checked_at,
                )
            )

        session.commit()
        finish_run(
            session,
            run,
            status="success",
            extracted=len(checks) + len(freshness_checks),
            loaded=len(checks) + len(freshness_checks),
        )
    except Exception as exc:
        session.rollback()
        finish_run(session, run, status="failed", error=str(exc))
        raise
    return run


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
