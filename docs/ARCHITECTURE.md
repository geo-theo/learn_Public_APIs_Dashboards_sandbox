# Architecture Notes

## System Boundaries

The project has three source systems:

1. NWS forecasts and alerts, fetched over JSON/GeoJSON HTTP endpoints.
2. USGS instantaneous streamflow, fetched as WaterML represented in JSON.
3. A synthetic CSV that resembles tablet-collected visitation counts.

The SQLite database is the system of record for the learning application. The
dashboard never calls NWS or USGS directly; it calls the local FastAPI service.
That separation lets source APIs change or fail without forcing dashboard code
to understand provider-specific response formats.

## Pipeline Stages

### Extract

Clients own HTTP concerns: URL construction, headers, timeouts, retries, status
validation, and JSON parsing.

### Transform

ETL functions:

- select fields relevant to analysis;
- parse ISO-8601 timestamps;
- coerce numeric values;
- attach source and pipeline lineage;
- map source identifiers to local reference records.

### Load

SQLite unique constraints and upsert statements make loads idempotent. A rerun
updates mutable public observations and ignores exact duplicate CSV records.

### Validate

QA is a separate, auditable stage. Source rows remain available even when they
are not publishable. Each check records severity, pass/fail state, failed-row
count, details, and check time.

### Serve

FastAPI exposes a stable local contract. The dashboard, CSV exports, Postman,
and BI tools are all clients of this layer.

## Production Extensions

This sandbox intentionally avoids infrastructure that would distract from the
first learning pass. A production system would normally add:

- Alembic database migrations;
- PostgreSQL or SQL Server;
- secrets management;
- structured logs and centralized monitoring;
- asynchronous or queue-backed pipeline execution;
- authentication and authorization for admin endpoints;
- request rate limiting;
- persistent raw-response storage;
- formal data contracts and schema-change alerts;
- separate development, test, staging, and production environments;
- accessibility, browser, load, and security testing;
- deployment automation and rollback procedures.

## Design Decisions

### Why SQLite?

It supports real SQL, joins, constraints, indexes, window functions, and
transactions while remaining easy to inspect and reset. The SQL and SQLAlchemy
patterns transfer to larger relational databases.

### Why FastAPI?

It provides request validation and OpenAPI documentation with little ceremony.
That makes the API contract visible while keeping most code focused on data.

### Why Vanilla JavaScript?

The dashboard demonstrates browser API calls without requiring a frontend build
tool. Network requests and JSON transformations remain easy to inspect.

### Why Synthetic Visitation?

It creates a safe dataset with known defects and no risk of confusing the
training artifact with official public statistics.
