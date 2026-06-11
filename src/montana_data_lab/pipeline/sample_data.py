from __future__ import annotations

import csv
import math
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from montana_data_lab.config import settings
from montana_data_lab.models import Park


def generate_sample_visits(
    session: Session,
    *,
    days: int = 180,
    seed: int = 42,
    output_path: Path | None = None,
) -> Path:
    """Create reproducible tablet-style records with intentional QA defects."""
    rng = random.Random(seed)
    output_path = output_path or settings.raw_data_dir / "tablet_visits.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parks = session.scalars(select(Park).order_by(Park.id)).all()
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    rows: list[dict[str, object]] = []

    for park_index, park in enumerate(parks):
        base_count = 110 + park_index * 24
        for day_index in range(days):
            visit_date = start_date + timedelta(days=day_index)
            summer = 1.0 + 0.85 * math.sin((visit_date.timetuple().tm_yday - 80) / 365 * math.tau)
            weekend = 1.35 if visit_date.weekday() >= 5 else 1.0
            noise = rng.uniform(0.82, 1.18)
            raw_count = max(5, round(base_count * summer * weekend * noise))
            rows.append(
                {
                    "park_code": park.code,
                    "visit_date": visit_date.isoformat(),
                    "raw_count": raw_count,
                    "device_id": f"tablet-{park_index + 1:02d}",
                    "survey_weight": round(rng.uniform(0.92, 1.18), 3),
                    "source_note": "routine upload",
                }
            )

    # Deliberate defects make the QA dashboard and exercises meaningful.
    rows[9]["raw_count"] = -12
    rows[37]["device_id"] = ""
    rows[81]["raw_count"] = 50000
    rows[126]["survey_weight"] = 0
    duplicate = dict(rows[205])
    duplicate["raw_count"] = int(duplicate["raw_count"]) + 3
    duplicate["source_note"] = "duplicate resubmission"
    rows.append(duplicate)

    fieldnames = [
        "park_code",
        "visit_date",
        "raw_count",
        "device_id",
        "survey_weight",
        "source_note",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def sample_file_metadata(path: Path) -> dict[str, str | int]:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }
