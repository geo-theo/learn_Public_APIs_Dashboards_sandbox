# Learning Guide

This guide is organized as a sequence of labs. Each lab starts with observation,
then asks you to make a small change, test it, and explain what happened. That
cycle is much closer to real data-systems work than reading API definitions in
isolation.

## Before You Begin

Run the complete setup:

```powershell
uv sync --dev
uv run python -m montana_data_lab refresh
uv run python -m montana_data_lab serve --reload
```

Keep these open:

- Dashboard: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- This repository in your editor
- A PowerShell terminal

The source visitation data is synthetic. NWS forecasts, alerts, and USGS
streamflow are live public data.

## Lab 1: Read an API as a Contract

**Goal:** Understand requests, responses, status codes, and schemas.

1. Open `/docs`.
2. Expand `GET /api/visitation`.
3. Select **Try it out**.
4. Set `days=30`, `metric=weighted`, and `group_by=park`.
5. Execute the request.
6. Inspect the request URL, status code, and response body.

Run the same request without the browser:

```powershell
$result = Invoke-RestMethod `
  "http://127.0.0.1:8000/api/visitation?days=30&metric=weighted&group_by=park"
$result.data | Format-Table
```

Now deliberately send an invalid request:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/visitation?days=-1&metric=banana"
```

Questions:

- Why is the successful status code `200`?
- Why does FastAPI return `422` for the invalid request?
- Which part of `api.py` defines the valid values for `metric`?
- How does generated OpenAPI documentation help Postman or another developer?

**Challenge:** Add `365` as an option in the dashboard's Window control. This
requires only HTML because the API already supports up to 730 days.

## Lab 2: Trace One Record Through ETL

**Goal:** Follow data through extract, transform, load, API, and visualization.

Choose Many Glacier and trace it:

1. Reference coordinates are defined in `reference_data.py`.
2. `NwsClient.forecast_for_point()` calls the NWS `/points` endpoint.
3. The linked forecast URL is then called.
4. `fetch_nws()` maps external JSON fields to `WeatherForecast`.
5. `/api/weather/forecast` queries the table.
6. `loadForecasts()` in `app.js` renders a card.

Inspect the upstream response:

```powershell
$headers = @{
  "User-Agent" = "MyLearningClient/0.1 (your-email@example.com)"
  "Accept" = "application/geo+json"
}
$point = Invoke-RestMethod `
  "https://api.weather.gov/points/48.7957,-113.6578" `
  -Headers $headers
$point.properties.forecast
Invoke-RestMethod $point.properties.forecast -Headers $headers
```

Questions:

- Why are there two NWS requests?
- Why should the `/points` result be cached but periodically refreshed?
- Which fields from the source are intentionally not stored?
- What would you do if NWS changed a field name?

**Challenge:** Store `windDirection` in the database and display it on each
forecast card. You will touch the model, ETL mapping, API response, and
JavaScript. Because this sandbox has no migration framework yet, delete
`data/montana_data_lab.db` and rerun `refresh` after changing the schema.

## Lab 3: Learn Idempotency

**Goal:** Understand why a pipeline must be safe to rerun.

Run this twice:

```powershell
uv run python -m montana_data_lab load-visits
```

The first run may load records. The second should report `loaded=0`. Open
`pipeline/etl.py` and find:

- the SHA-256 source-row hash;
- the database unique constraint;
- `on_conflict_do_nothing`.

Questions:

- Which mechanism detects a repeat?
- Why use both an application-generated hash and a database constraint?
- What happens if a source row is corrected and resent with a different count?
- When would an `update` be more appropriate than `do nothing`?

**Challenge:** Add a `source_file_name` column so lineage can identify the exact
file that supplied each row.

## Lab 4: Work With Messy Field Data

**Goal:** Separate raw preservation from publishable records.

The generated CSV contains intentional defects. Open:

```text
data/raw/tablet_visits.csv
```

Then inspect QA results:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/quality/latest" |
  Format-Table check_name, passed, failed_rows, severity
```

The pipeline does not delete bad records. It sets `quality_status=invalid`, and
the public endpoint filters to `valid`.

Questions:

- Why preserve a negative count instead of deleting it?
- Which failures should block publication?
- Is a count above 10,000 always wrong, or does it require review?
- What additional context would help resolve a duplicate tablet upload?

Change the threshold:

```powershell
$env:MTDL_VISIT_OUTLIER_THRESHOLD = "300"
uv run python -m montana_data_lab qa
```

Restart the API so it reads the new environment setting.

**Challenge:** Add a check for records dated in the future.

## Lab 5: Write Analytical SQL

**Goal:** Become comfortable moving between ORM code and SQL.

Open `sql/learning_queries.sql` in a SQLite client. Useful options include:

- the SQLite extension in VS Code;
- DBeaver;
- Tableau's SQLite connector or exported CSV;
- Python's built-in `sqlite3` module.

From PowerShell, you can run a query through Python:

```powershell
@'
import sqlite3
connection = sqlite3.connect("data/montana_data_lab.db")
query = """
SELECT p.name, SUM(v.raw_count * v.survey_weight) AS weighted_visits
FROM visit_records v
JOIN parks p ON p.id = v.park_id
WHERE v.quality_status = 'valid'
GROUP BY p.name
ORDER BY weighted_visits DESC
"""
for row in connection.execute(query):
    print(row)
'@ | uv run python -
```

Questions:

- Why does the query join `parks`?
- Why is `SUM(raw_count * survey_weight)` different from
  `SUM(raw_count) * AVG(survey_weight)`?
- Which index helps a date-and-park query?
- What is the grain of `visit_records`?

**Challenge:** Write a query that compares weekday and weekend visitation by
park. SQLite's `strftime('%w', visit_date)` returns day of week.

## Lab 6: Weighted Metrics

**Goal:** Understand estimates, not just calculations.

The sandbox uses:

```text
weighted_count = raw_count * survey_weight
```

This is intentionally simple. In real research, a weight may adjust for
sampling probability, nonresponse, site selection, season, or calibration to a
known population total.

Compare metrics:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/visitation?days=90&metric=raw&group_by=park"

Invoke-RestMethod `
  "http://127.0.0.1:8000/api/visitation?days=90&metric=weighted&group_by=park"
```

Questions:

- Which parks move most between the two rankings?
- Should a dashboard label a weighted value as a count or an estimate?
- What metadata should be published with a weighted metric?
- How would you validate weights supplied by an external researcher?

**Challenge:** Add a tooltip or note to the dashboard explaining the selected
metric in plain language.

## Lab 7: Handle Upstream Failures

**Goal:** Build pipelines that fail visibly and recover cleanly.

`PublicApiClient.get_json()` has:

- a timeout;
- status-code validation;
- three attempts;
- exponential delay between attempts.

Temporarily replace an API base URL with an invalid hostname and run:

```powershell
uv run python -m montana_data_lab fetch-live
uv run python -m montana_data_lab serve
```

Inspect `/api/pipeline-runs`.

Questions:

- Why does the pipeline log a failed run instead of silently returning no rows?
- Why should NWS failure not prevent the USGS stage from running?
- When should retries stop?
- Which HTTP status codes are usually worth retrying?

**Challenge:** Modify the base client so only timeouts, connection errors, `429`,
and `5xx` responses are retried. A `404` should fail immediately.

## Lab 8: Add an Endpoint

**Goal:** Design a useful, constrained analytical API.

Build:

```text
GET /api/visitation/monthly
```

Suggested response:

```json
{
  "park_code": "many-glacier",
  "data": [
    {"month": "2026-01", "raw_visits": 1234, "weighted_visits": 1301.2}
  ]
}
```

Requirements:

- optional `park_code`;
- only valid records;
- chronological order;
- both raw and weighted values;
- a test for the endpoint.

Questions:

- Should the endpoint return an error for an unknown park or an empty list?
- What is the response grain?
- Would clients benefit from start and end date parameters?

## Lab 9: Build a New Visualization

**Goal:** Turn a stakeholder question into a chart.

Stakeholder question:

> Which locations account for the most estimated visitation in the selected
> period?

The endpoint already supports:

```text
/api/visitation?days=90&metric=weighted&group_by=park
```

Add a horizontal bar chart below the trend. Recommended steps:

1. Add a `<canvas>` to `dashboard.html`.
2. Add a JavaScript variable to hold the chart.
3. Fetch the park-grouped endpoint.
4. Sort or preserve the API's descending order.
5. Use park names as labels.
6. Reload the chart when controls change.
7. Check mobile layout.

Questions:

- Is the chart title explicit about synthetic and weighted data?
- Can a color-blind user distinguish what matters?
- Does the chart answer one clear question?
- What context would prevent misinterpretation?

## Lab 10: Test APIs Without Calling the Internet

**Goal:** Learn test doubles and deterministic tests.

Read `tests/test_pipeline.py`. The fake NWS and USGS clients return small,
controlled payloads. This makes tests:

- fast;
- repeatable;
- independent of network availability;
- able to simulate edge cases.

Run:

```powershell
uv run pytest -vv
```

**Challenge:** Add a fake client response with a missing precipitation value and
confirm the ETL stores `NULL` without failing.

## Lab 11: Connect a BI Tool

**Goal:** Treat the application as a data provider for Tableau, Power BI, or
Excel.

Export a clean file:

```powershell
Invoke-WebRequest `
  "http://127.0.0.1:8000/api/export/visitation.csv?days=180" `
  -OutFile data/visitation_for_bi.csv
```

In your BI tool:

1. Connect to the CSV.
2. Confirm field types.
3. Create a time-series chart of `weighted_count`.
4. Add park and region filters.
5. Create a QA note stating that invalid rows are excluded.
6. Refresh the extract after running the pipeline again.

For direct SQLite access, connect to:

```text
data/montana_data_lab.db
```

Questions:

- Should Tableau calculate weighted values or receive them precomputed?
- What changes when an extract is used instead of a live connection?
- How will a dashboard user know when data was last refreshed?

## Lab 12: Add a New Public Source

**Goal:** Practice source evaluation and system extension.

Potential additions:

- National Park Service data;
- wildfire or air-quality conditions;
- recreation permits;
- trail conditions;
- state economic indicators;
- lodging or transportation statistics.

Before coding, write a one-page source assessment:

- owner and authoritative status;
- authentication and cost;
- terms of use;
- update frequency and latency;
- geographic coverage;
- historical depth;
- rate limits;
- expected schema stability;
- missing-data behavior;
- privacy or disclosure concerns.

Then follow the existing pattern:

1. Add a client in `clients/`.
2. Add source and warehouse models.
3. Add an idempotent ETL function.
4. Record a `PipelineRun`.
5. Add QA and freshness checks.
6. Add an API endpoint.
7. Add tests with a fake client.
8. Add a dashboard component.
9. Document the source and caveats.

## Capstone Ideas

### Capstone A: State Parks Operations Dashboard

Add upload handling for monthly park spreadsheets, validate each file, produce
an exception report, and publish approved counts.

### Capstone B: Recreation Conditions Index

Combine weather, alerts, streamflow, and seasonality into a clearly documented
index. Avoid presenting it as objective truth; show components and assumptions.

### Capstone C: Research Data Release

Create a versioned public data extract, metadata file, methodology note, data
dictionary, and reproducible analysis notebook.

### Capstone D: SQL Server Migration

Replace SQLite with SQL Server or PostgreSQL. Add migrations, connection
pooling, secrets management, and environment-specific configuration.

## Interview Practice

After completing the labs, practice explaining:

- how your ETL remains idempotent;
- how you preserve raw data while excluding invalid records;
- how you monitor freshness and failures;
- how you test without relying on live APIs;
- how weighted estimates differ from raw counts;
- how API endpoints support both dashboards and BI tools;
- what you would change before production deployment.
