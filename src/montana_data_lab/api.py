from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from montana_data_lab import __version__
from montana_data_lab.db import get_session, init_database, session_scope
from montana_data_lab.models import (
    Park,
    PipelineRun,
    QualityCheck,
    StreamflowObservation,
    StreamGauge,
    VisitRecord,
    WeatherAlert,
    WeatherForecast,
)
from montana_data_lab.pipeline.orchestrator import refresh_all, seed_reference_data

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "web" / "templates")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    with session_scope() as session:
        seed_reference_data(session)
    yield


app = FastAPI(
    title="Montana Public Data Lab API",
    version=__version__,
    description=(
        "A learning API for tourism-style visitation, weather, streamflow, "
        "pipeline operations, and data quality."
    ),
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "web" / "static"), name="static")

SessionDependency = Annotated[Session, Depends(get_session)]


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/api/health", tags=["operations"])
def health(session: SessionDependency) -> dict:
    session.execute(select(1))
    latest_run = session.scalar(select(func.max(PipelineRun.finished_at)))
    return {
        "status": "ok",
        "version": __version__,
        "database": "connected",
        "latest_pipeline_finish": latest_run,
        "checked_at": datetime.now(UTC),
    }


@app.get("/api/parks", tags=["reference"])
def parks(session: SessionDependency) -> list[dict]:
    rows = session.execute(select(Park).where(Park.active.is_(True)).order_by(Park.name)).scalars()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "region": row.region,
            "latitude": row.latitude,
            "longitude": row.longitude,
        }
        for row in rows
    ]


@app.get("/api/summary", tags=["dashboard"])
def summary(session: SessionDependency) -> dict:
    latest_visit_date = session.scalar(
        select(func.max(VisitRecord.visit_date)).where(VisitRecord.quality_status == "valid")
    )
    cutoff = (
        latest_visit_date - timedelta(days=29)
        if latest_visit_date
        else date.today() - timedelta(days=29)
    )
    visit_summary = session.execute(
        select(
            func.sum(VisitRecord.raw_count),
            func.sum(VisitRecord.raw_count * VisitRecord.survey_weight),
            func.count(VisitRecord.id),
        ).where(
            VisitRecord.quality_status == "valid",
            VisitRecord.visit_date >= cutoff,
        )
    ).one()
    invalid_rows = session.scalar(
        select(func.count(VisitRecord.id)).where(VisitRecord.quality_status == "invalid")
    )
    active_alerts = session.scalar(
        select(func.count(WeatherAlert.id)).where(
            (WeatherAlert.expires.is_(None)) | (WeatherAlert.expires >= datetime.now(UTC))
        )
    )
    latest_weather = session.scalar(select(func.max(WeatherForecast.fetched_at)))
    latest_streamflow = session.scalar(select(func.max(StreamflowObservation.fetched_at)))
    return {
        "window_start": cutoff,
        "window_end": latest_visit_date,
        "raw_visits": int(visit_summary[0] or 0),
        "weighted_visits": round(float(visit_summary[1] or 0), 1),
        "valid_records": int(visit_summary[2] or 0),
        "invalid_records": int(invalid_rows or 0),
        "active_weather_alerts": int(active_alerts or 0),
        "latest_weather_fetch": latest_weather,
        "latest_streamflow_fetch": latest_streamflow,
    }


@app.get("/api/visitation", tags=["visitation"])
def visitation(
    session: SessionDependency,
    days: Annotated[int, Query(ge=1, le=730)] = 90,
    park_code: str | None = None,
    metric: Literal["raw", "weighted"] = "raw",
    group_by: Literal["day", "park"] = "day",
) -> dict:
    latest_date = session.scalar(select(func.max(VisitRecord.visit_date))) or date.today()
    cutoff = latest_date - timedelta(days=days - 1)
    value = (
        VisitRecord.raw_count * VisitRecord.survey_weight
        if metric == "weighted"
        else VisitRecord.raw_count
    )
    filters = [
        VisitRecord.quality_status == "valid",
        VisitRecord.visit_date >= cutoff,
    ]
    if park_code:
        filters.append(Park.code == park_code)

    if group_by == "park":
        statement = (
            select(
                Park.code,
                Park.name,
                func.sum(value).label("value"),
                func.count(VisitRecord.id).label("record_count"),
            )
            .join(Park, Park.id == VisitRecord.park_id)
            .where(*filters)
            .group_by(Park.code, Park.name)
            .order_by(desc("value"))
        )
        rows = [
            {
                "park_code": row.code,
                "park_name": row.name,
                "value": round(float(row.value), 2),
                "record_count": row.record_count,
            }
            for row in session.execute(statement)
        ]
    else:
        statement = (
            select(
                VisitRecord.visit_date,
                func.sum(value).label("value"),
                func.count(VisitRecord.id).label("record_count"),
            )
            .join(Park, Park.id == VisitRecord.park_id)
            .where(*filters)
            .group_by(VisitRecord.visit_date)
            .order_by(VisitRecord.visit_date)
        )
        rows = [
            {
                "date": row.visit_date,
                "value": round(float(row.value), 2),
                "record_count": row.record_count,
            }
            for row in session.execute(statement)
        ]
    return {
        "metric": metric,
        "group_by": group_by,
        "days": days,
        "park_code": park_code,
        "data": rows,
    }


@app.get("/api/weather/forecast", tags=["weather"])
def weather_forecast(
    session: SessionDependency,
    periods_per_park: Annotated[int, Query(ge=1, le=14)] = 3,
) -> list[dict]:
    row_number = func.row_number().over(
        partition_by=WeatherForecast.park_id,
        order_by=WeatherForecast.start_time,
    )
    ranked = (
        select(
            WeatherForecast.park_id,
            WeatherForecast.start_time,
            WeatherForecast.is_daytime,
            WeatherForecast.temperature_f,
            WeatherForecast.precipitation_probability,
            WeatherForecast.wind_speed,
            WeatherForecast.short_forecast,
            WeatherForecast.fetched_at,
            row_number.label("position"),
        )
        .where(WeatherForecast.end_time >= datetime.now(UTC))
        .subquery()
    )
    statement = (
        select(Park.code, Park.name, ranked)
        .join(ranked, ranked.c.park_id == Park.id)
        .where(ranked.c.position <= periods_per_park)
        .order_by(Park.name, ranked.c.start_time)
    )
    return [
        {
            "park_code": row.code,
            "park_name": row.name,
            "start_time": row.start_time,
            "is_daytime": row.is_daytime,
            "temperature_f": row.temperature_f,
            "precipitation_probability": row.precipitation_probability,
            "wind_speed": row.wind_speed,
            "short_forecast": row.short_forecast,
            "fetched_at": row.fetched_at,
        }
        for row in session.execute(statement)
    ]


@app.get("/api/weather/alerts", tags=["weather"])
def weather_alerts(session: SessionDependency) -> list[dict]:
    statement = (
        select(WeatherAlert)
        .where((WeatherAlert.expires.is_(None)) | (WeatherAlert.expires >= datetime.now(UTC)))
        .order_by(WeatherAlert.severity, WeatherAlert.expires)
    )
    return [
        {
            "event": row.event,
            "severity": row.severity,
            "urgency": row.urgency,
            "headline": row.headline,
            "area_description": row.area_description,
            "onset": row.onset,
            "expires": row.expires,
        }
        for row in session.scalars(statement)
    ]


@app.get("/api/streamflow/latest", tags=["streamflow"])
def latest_streamflow(session: SessionDependency) -> list[dict]:
    row_number = func.row_number().over(
        partition_by=StreamflowObservation.site_no,
        order_by=StreamflowObservation.observed_at.desc(),
    )
    ranked = select(
        StreamflowObservation.site_no,
        StreamflowObservation.observed_at,
        StreamflowObservation.discharge_cfs,
        StreamflowObservation.qualifiers,
        StreamflowObservation.fetched_at,
        row_number.label("position"),
    ).subquery()
    statement = (
        select(StreamGauge, ranked)
        .join(ranked, ranked.c.site_no == StreamGauge.site_no)
        .where(ranked.c.position == 1)
        .order_by(StreamGauge.name)
    )
    return [
        {
            "site_no": gauge.site_no,
            "name": gauge.name,
            "latitude": gauge.latitude,
            "longitude": gauge.longitude,
            "related_park_code": gauge.related_park_code,
            "observed_at": observed_at,
            "discharge_cfs": discharge_cfs,
            "qualifiers": qualifiers,
            "fetched_at": fetched_at,
        }
        for gauge, site_no, observed_at, discharge_cfs, qualifiers, fetched_at, _position in (
            session.execute(statement)
        )
    ]


@app.get("/api/quality/latest", tags=["operations"])
def latest_quality(session: SessionDependency) -> list[dict]:
    latest_run_id = session.scalar(
        select(PipelineRun.id)
        .where(PipelineRun.source == "quality")
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    if latest_run_id is None:
        return []
    rows = session.scalars(
        select(QualityCheck)
        .where(QualityCheck.pipeline_run_id == latest_run_id)
        .order_by(QualityCheck.passed, QualityCheck.severity, QualityCheck.check_name)
    )
    return [
        {
            "check_name": row.check_name,
            "severity": row.severity,
            "passed": row.passed,
            "failed_rows": row.failed_rows,
            "details": row.details,
            "checked_at": row.checked_at,
        }
        for row in rows
    ]


@app.get("/api/pipeline-runs", tags=["operations"])
def pipeline_runs(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    rows = session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit))
    return [
        {
            "id": row.id,
            "source": row.source,
            "status": row.status,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "rows_extracted": row.rows_extracted,
            "rows_loaded": row.rows_loaded,
            "error_message": row.error_message,
        }
        for row in rows
    ]


@app.get("/api/export/visitation.csv", tags=["exports"])
def export_visitation_csv(
    session: SessionDependency,
    days: Annotated[int, Query(ge=1, le=730)] = 90,
    include_invalid: bool = False,
):
    latest_date = session.scalar(select(func.max(VisitRecord.visit_date))) or date.today()
    cutoff = latest_date - timedelta(days=days - 1)
    statement = (
        select(
            Park.code,
            Park.name,
            Park.region,
            VisitRecord.visit_date,
            VisitRecord.raw_count,
            VisitRecord.survey_weight,
            (VisitRecord.raw_count * VisitRecord.survey_weight).label("weighted_count"),
            VisitRecord.device_id,
            VisitRecord.quality_status,
        )
        .join(Park, Park.id == VisitRecord.park_id)
        .where(VisitRecord.visit_date >= cutoff)
        .order_by(VisitRecord.visit_date, Park.name)
    )
    if not include_invalid:
        statement = statement.where(VisitRecord.quality_status == "valid")

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "park_code",
            "park_name",
            "region",
            "visit_date",
            "raw_count",
            "survey_weight",
            "weighted_count",
            "device_id",
            "quality_status",
        ]
    )
    for row in session.execute(statement):
        writer.writerow(row)
    output.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="visitation_export.csv"'}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)


@app.post("/api/admin/refresh", tags=["operations"])
def refresh_pipeline() -> dict:
    return {"message": "Pipeline refresh finished.", "sources": refresh_all()}
