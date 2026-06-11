from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from montana_data_lab.db import session_scope
from montana_data_lab.models import (
    QualityCheck,
    StreamflowObservation,
    VisitRecord,
    WeatherAlert,
    WeatherForecast,
)
from montana_data_lab.pipeline.etl import fetch_nws, fetch_usgs, load_visit_csv
from montana_data_lab.pipeline.quality import run_quality_checks
from montana_data_lab.pipeline.sample_data import generate_sample_visits


class FakeNwsClient:
    def forecast_for_point(self, latitude, longitude):
        return (
            f"https://example.test/forecast/{latitude}/{longitude}",
            [
                {
                    "startTime": "2026-06-10T12:00:00-06:00",
                    "endTime": "2026-06-10T18:00:00-06:00",
                    "isDaytime": True,
                    "temperature": 72,
                    "probabilityOfPrecipitation": {"value": None},
                    "windSpeed": "5 mph",
                    "shortForecast": "Sunny",
                    "detailedForecast": "Clear for this deterministic test.",
                }
            ],
        )

    def active_montana_alerts(self):
        return [
            {
                "id": "https://example.test/alerts/1",
                "properties": {
                    "event": "Test Advisory",
                    "severity": "Minor",
                    "urgency": "Expected",
                    "headline": "A deterministic test alert",
                    "areaDesc": "Test County",
                    "onset": "2026-06-10T12:00:00-06:00",
                    "expires": "2026-06-11T12:00:00-06:00",
                },
            }
        ]


class FakeUsgsClient:
    def streamflow(self, site_numbers):
        return [
            {
                "sourceInfo": {"siteCode": [{"value": site_numbers[0]}]},
                "values": [
                    {
                        "value": [
                            {
                                "value": "1250",
                                "dateTime": "2026-06-10T12:00:00.000-06:00",
                                "qualifiers": ["P"],
                            }
                        ]
                    }
                ],
            }
        ]


def test_visit_load_is_idempotent_and_quality_is_auditable(test_database, tmp_path):
    with session_scope() as session:
        path = generate_sample_visits(
            session,
            days=60,
            seed=42,
            output_path=tmp_path / "visits.csv",
        )
        first_run = load_visit_csv(session, path)
        second_run = load_visit_csv(session, path)
        quality_run = run_quality_checks(session)

        total = session.scalar(select(func.count(VisitRecord.id)))
        invalid = session.scalar(
            select(func.count(VisitRecord.id)).where(VisitRecord.quality_status == "invalid")
        )
        checks = session.scalar(
            select(func.count(QualityCheck.id)).where(
                QualityCheck.pipeline_run_id == quality_run.id
            )
        )

    assert first_run.rows_loaded == 361
    assert second_run.rows_loaded == 0
    assert total == 361
    assert invalid == 6
    assert checks == 7


def test_public_api_etl_accepts_fake_clients(test_database):
    with session_scope() as session:
        nws_run = fetch_nws(session, FakeNwsClient())
        usgs_run = fetch_usgs(session, FakeUsgsClient())
        forecasts = session.scalar(select(func.count(WeatherForecast.id)))
        alerts = session.scalar(select(func.count(WeatherAlert.id)))
        stream_rows = session.scalar(select(func.count(StreamflowObservation.id)))
        nullable_precip = session.scalar(select(WeatherForecast.precipitation_probability))

    assert nws_run.status == "success"
    assert usgs_run.status == "success"
    assert forecasts == 6
    assert alerts == 1
    assert stream_rows == 1
    assert nullable_precip is None


def test_sample_timestamps_are_timezone_aware_in_source_fixture():
    value = datetime.fromisoformat("2026-06-10T12:00:00-06:00")
    assert value.astimezone(UTC).hour == 18
