from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Park(Base):
    __tablename__ = "parks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(80))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StreamGauge(Base):
    __tablename__ = "stream_gauges"

    id: Mapped[int] = mapped_column(primary_key=True)
    site_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    related_park_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_extracted: Mapped[int] = mapped_column(Integer, default=0)
    rows_loaded: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class VisitRecord(Base):
    __tablename__ = "visit_records"
    __table_args__ = (
        UniqueConstraint("source_row_hash", name="uq_visit_source_row_hash"),
        Index("ix_visit_date_park", "visit_date", "park_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    park_id: Mapped[int] = mapped_column(ForeignKey("parks.id"), index=True)
    visit_date: Mapped[date] = mapped_column(Date, index=True)
    raw_count: Mapped[int] = mapped_column(Integer)
    device_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    survey_weight: Mapped[float] = mapped_column(Float, default=1.0)
    source_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_row_hash: Mapped[str] = mapped_column(String(64))
    quality_status: Mapped[str] = mapped_column(String(20), default="unchecked", index=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint("park_id", "start_time", name="uq_forecast_park_start"),
        Index("ix_forecast_start_park", "start_time", "park_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    park_id: Mapped[int] = mapped_column(ForeignKey("parks.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_daytime: Mapped[bool] = mapped_column(Boolean)
    temperature_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[str | None] = mapped_column(String(60), nullable=True)
    short_forecast: Mapped[str] = mapped_column(String(180))
    detailed_forecast: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(Text)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))


class WeatherAlert(Base):
    __tablename__ = "weather_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[str] = mapped_column(Text, unique=True)
    event: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(40), nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    onset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))


class StreamflowObservation(Base):
    __tablename__ = "streamflow_observations"
    __table_args__ = (
        UniqueConstraint("site_no", "observed_at", name="uq_stream_site_observed"),
        Index("ix_stream_observed_site", "observed_at", "site_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_no: Mapped[str] = mapped_column(ForeignKey("stream_gauges.site_no"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    discharge_cfs: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualifiers: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))


class QualityCheck(Base):
    __tablename__ = "quality_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    passed: Mapped[bool] = mapped_column(Boolean)
    failed_rows: Mapped[int] = mapped_column(Integer)
    details: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
