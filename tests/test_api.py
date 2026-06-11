from __future__ import annotations

from fastapi.testclient import TestClient

from montana_data_lab.api import app
from montana_data_lab.db import session_scope
from montana_data_lab.pipeline.etl import load_visit_csv
from montana_data_lab.pipeline.quality import run_quality_checks
from montana_data_lab.pipeline.sample_data import generate_sample_visits


def test_dashboard_and_analytical_endpoints(test_database, tmp_path):
    with session_scope() as session:
        path = generate_sample_visits(
            session,
            days=60,
            output_path=tmp_path / "visits.csv",
        )
        load_visit_csv(session, path)
        run_quality_checks(session)

    with TestClient(app) as client:
        dashboard = client.get("/")
        summary = client.get("/api/summary")
        visitation = client.get(
            "/api/visitation",
            params={"days": 30, "metric": "weighted", "group_by": "park"},
        )
        export = client.get("/api/export/visitation.csv", params={"days": 30})

    assert dashboard.status_code == 200
    assert "Montana recreation" in dashboard.text
    assert summary.status_code == 200
    assert summary.json()["invalid_records"] == 6
    assert visitation.status_code == 200
    assert len(visitation.json()["data"]) == 6
    assert export.status_code == 200
    assert export.text.startswith("park_code,park_name,region")


def test_request_validation_rejects_bad_parameters(test_database):
    with TestClient(app) as client:
        response = client.get(
            "/api/visitation",
            params={"days": -2, "metric": "not-a-metric"},
        )
    assert response.status_code == 422
