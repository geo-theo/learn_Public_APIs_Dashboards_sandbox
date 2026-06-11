from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from montana_data_lab.clients.nws import NwsClient
from montana_data_lab.clients.usgs import UsgsClient
from montana_data_lab.config import settings
from montana_data_lab.models import (
    Park,
    PipelineRun,
    StreamflowObservation,
    StreamGauge,
    VisitRecord,
    WeatherAlert,
    WeatherForecast,
)
from montana_data_lab.pipeline.runs import finish_run, start_run


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_visit_csv(session: Session, path: Path | None = None) -> PipelineRun:
    path = path or settings.raw_data_dir / "tablet_visits.csv"
    run = start_run(session, "tablet_visits")
    extracted = 0
    loaded = 0
    try:
        parks = {park.code: park.id for park in session.scalars(select(Park)).all()}
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                extracted += 1
                park_id = parks.get(row["park_code"])
                if park_id is None:
                    raise ValueError(f"Unknown park code: {row['park_code']}")
                row_hash = hashlib.sha256(
                    json.dumps(row, sort_keys=True).encode("utf-8")
                ).hexdigest()
                statement = sqlite_insert(VisitRecord).values(
                    park_id=park_id,
                    visit_date=datetime.strptime(row["visit_date"], "%Y-%m-%d").date(),
                    raw_count=int(row["raw_count"]),
                    device_id=row["device_id"].strip() or None,
                    survey_weight=float(row["survey_weight"]),
                    source_note=row.get("source_note") or None,
                    source_row_hash=row_hash,
                    quality_status="unchecked",
                    loaded_at=datetime.now(UTC),
                    pipeline_run_id=run.id,
                )
                result = session.execute(
                    statement.on_conflict_do_nothing(index_elements=["source_row_hash"])
                )
                loaded += result.rowcount
        session.commit()
        finish_run(session, run, status="success", extracted=extracted, loaded=loaded)
    except Exception as exc:
        session.rollback()
        finish_run(
            session,
            run,
            status="failed",
            extracted=extracted,
            loaded=loaded,
            error=str(exc),
        )
        raise
    return run


def fetch_nws(session: Session, client: NwsClient | None = None) -> PipelineRun:
    run = start_run(session, "nws")
    extracted = 0
    loaded = 0
    owns_client = client is None
    client = client or NwsClient()
    fetched_at = datetime.now(UTC)
    try:
        parks = session.scalars(select(Park).where(Park.active.is_(True))).all()
        for park in parks:
            source_url, periods = client.forecast_for_point(park.latitude, park.longitude)
            extracted += len(periods)
            for period in periods:
                probability = period.get("probabilityOfPrecipitation") or {}
                statement = sqlite_insert(WeatherForecast).values(
                    park_id=park.id,
                    start_time=_parse_datetime(period["startTime"]),
                    end_time=_parse_datetime(period["endTime"]),
                    is_daytime=bool(period["isDaytime"]),
                    temperature_f=period.get("temperature"),
                    precipitation_probability=probability.get("value"),
                    wind_speed=period.get("windSpeed"),
                    short_forecast=period.get("shortForecast", "Unknown"),
                    detailed_forecast=period.get("detailedForecast"),
                    fetched_at=fetched_at,
                    source_url=source_url,
                    pipeline_run_id=run.id,
                )
                result = session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["park_id", "start_time"],
                        set_={
                            "end_time": statement.excluded.end_time,
                            "is_daytime": statement.excluded.is_daytime,
                            "temperature_f": statement.excluded.temperature_f,
                            "precipitation_probability": (
                                statement.excluded.precipitation_probability
                            ),
                            "wind_speed": statement.excluded.wind_speed,
                            "short_forecast": statement.excluded.short_forecast,
                            "detailed_forecast": statement.excluded.detailed_forecast,
                            "fetched_at": statement.excluded.fetched_at,
                            "source_url": statement.excluded.source_url,
                            "pipeline_run_id": statement.excluded.pipeline_run_id,
                        },
                    )
                )
                loaded += result.rowcount

        alerts = client.active_montana_alerts()
        extracted += len(alerts)
        for feature in alerts:
            properties = feature.get("properties", {})
            statement = sqlite_insert(WeatherAlert).values(
                alert_id=feature["id"],
                event=properties.get("event", "Weather alert"),
                severity=properties.get("severity"),
                urgency=properties.get("urgency"),
                headline=properties.get("headline"),
                area_description=properties.get("areaDesc"),
                onset=_parse_datetime(properties.get("onset")),
                expires=_parse_datetime(properties.get("expires")),
                fetched_at=fetched_at,
                pipeline_run_id=run.id,
            )
            result = session.execute(
                statement.on_conflict_do_update(
                    index_elements=["alert_id"],
                    set_={
                        "event": statement.excluded.event,
                        "severity": statement.excluded.severity,
                        "urgency": statement.excluded.urgency,
                        "headline": statement.excluded.headline,
                        "area_description": statement.excluded.area_description,
                        "onset": statement.excluded.onset,
                        "expires": statement.excluded.expires,
                        "fetched_at": statement.excluded.fetched_at,
                        "pipeline_run_id": statement.excluded.pipeline_run_id,
                    },
                )
            )
            loaded += result.rowcount
        session.commit()
        finish_run(session, run, status="success", extracted=extracted, loaded=loaded)
    except Exception as exc:
        session.rollback()
        finish_run(
            session,
            run,
            status="failed",
            extracted=extracted,
            loaded=loaded,
            error=str(exc),
        )
    finally:
        if owns_client:
            client.close()
    return run


def fetch_usgs(session: Session, client: UsgsClient | None = None) -> PipelineRun:
    run = start_run(session, "usgs")
    extracted = 0
    loaded = 0
    owns_client = client is None
    client = client or UsgsClient()
    fetched_at = datetime.now(UTC)
    try:
        site_numbers = session.scalars(select(StreamGauge.site_no)).all()
        series_list = client.streamflow(list(site_numbers))
        for series in series_list:
            site_no = series["sourceInfo"]["siteCode"][0]["value"]
            for value_group in series.get("values", []):
                for value in value_group.get("value", []):
                    extracted += 1
                    statement = sqlite_insert(StreamflowObservation).values(
                        site_no=site_no,
                        observed_at=_parse_datetime(value["dateTime"]),
                        discharge_cfs=float(value["value"]) if value["value"] else None,
                        qualifiers=",".join(value.get("qualifiers", [])) or None,
                        fetched_at=fetched_at,
                        pipeline_run_id=run.id,
                    )
                    result = session.execute(
                        statement.on_conflict_do_update(
                            index_elements=["site_no", "observed_at"],
                            set_={
                                "discharge_cfs": statement.excluded.discharge_cfs,
                                "qualifiers": statement.excluded.qualifiers,
                                "fetched_at": statement.excluded.fetched_at,
                                "pipeline_run_id": statement.excluded.pipeline_run_id,
                            },
                        )
                    )
                    loaded += result.rowcount
        session.commit()
        finish_run(session, run, status="success", extracted=extracted, loaded=loaded)
    except Exception as exc:
        session.rollback()
        finish_run(
            session,
            run,
            status="failed",
            extracted=extracted,
            loaded=loaded,
            error=str(exc),
        )
    finally:
        if owns_client:
            client.close()
    return run
