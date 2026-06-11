from __future__ import annotations

import argparse
import json

import uvicorn
from apscheduler.schedulers.blocking import BlockingScheduler

from montana_data_lab.config import settings
from montana_data_lab.db import session_scope
from montana_data_lab.pipeline.etl import fetch_nws, fetch_usgs, load_visit_csv
from montana_data_lab.pipeline.orchestrator import (
    ensure_sample_file,
    initialize,
    refresh_all,
)
from montana_data_lab.pipeline.quality import run_quality_checks
from montana_data_lab.pipeline.sample_data import generate_sample_visits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="montana-data-lab",
        description="Learn public APIs, ETL, SQL, QA, and dashboard development.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create database tables and reference data.")

    sample = subparsers.add_parser("generate-sample", help="Generate tablet visitation CSV.")
    sample.add_argument("--days", type=int, default=180)
    sample.add_argument("--seed", type=int, default=42)

    subparsers.add_parser("load-visits", help="Load the local tablet CSV.")
    subparsers.add_parser("fetch-live", help="Fetch NWS and USGS public data.")
    subparsers.add_parser("qa", help="Run data-quality rules.")
    subparsers.add_parser("refresh", help="Run the complete pipeline.")

    serve = subparsers.add_parser("serve", help="Start the dashboard and REST API.")
    serve.add_argument("--host", default=settings.host)
    serve.add_argument("--port", type=int, default=settings.port)
    serve.add_argument("--reload", action="store_true")

    schedule = subparsers.add_parser("schedule", help="Run the pipeline on an interval.")
    schedule.add_argument("--minutes", type=int, default=60)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "init":
        initialize()
        print("Database and reference data are ready.")
    elif args.command == "generate-sample":
        initialize()
        with session_scope() as session:
            path = generate_sample_visits(session, days=args.days, seed=args.seed)
        print(f"Generated {path}")
    elif args.command == "load-visits":
        initialize()
        with session_scope() as session:
            path = ensure_sample_file(session)
            run = load_visit_csv(session, path)
        print(
            f"Tablet load: {run.status}; "
            f"extracted={run.rows_extracted}, loaded={run.rows_loaded}"
        )
    elif args.command == "fetch-live":
        initialize()
        with session_scope() as session:
            nws = fetch_nws(session)
            usgs = fetch_usgs(session)
        print(json.dumps({"nws": nws.status, "usgs": usgs.status}, indent=2))
    elif args.command == "qa":
        initialize()
        with session_scope() as session:
            run = run_quality_checks(session)
        print(f"Quality checks: {run.status}")
    elif args.command == "refresh":
        print(json.dumps(refresh_all(), indent=2))
    elif args.command == "serve":
        initialize()
        uvicorn.run(
            "montana_data_lab.api:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "schedule":
        refresh_all()
        scheduler = BlockingScheduler()
        scheduler.add_job(
            refresh_all,
            "interval",
            minutes=args.minutes,
            id="montana-data-refresh",
            max_instances=1,
            coalesce=True,
        )
        print(f"Scheduler running every {args.minutes} minutes. Press Ctrl+C to stop.")
        scheduler.start()
