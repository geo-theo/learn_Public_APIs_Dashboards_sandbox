# Data Dictionary

## `parks`

Reference table for dashboard locations.

| Column | Meaning |
|---|---|
| `id` | Internal integer key |
| `code` | Stable human-readable identifier |
| `name` | Display name |
| `region` | Tourism region used for grouping |
| `latitude`, `longitude` | WGS84 point coordinates |
| `active` | Whether the park participates in current ETL |

## `stream_gauges`

Reference table for selected USGS sites.

| Column | Meaning |
|---|---|
| `site_no` | USGS site identifier |
| `name` | Gauge display name |
| `latitude`, `longitude` | WGS84 point coordinates |
| `related_park_code` | Optional learning-project association |

## `visit_records`

Synthetic tablet visitation at one row per source upload.

| Column | Meaning |
|---|---|
| `park_id` | Location foreign key |
| `visit_date` | Date represented by the count |
| `raw_count` | Unweighted source count |
| `device_id` | Tablet or counter identifier |
| `survey_weight` | Training adjustment factor |
| `source_note` | Source-provided context |
| `source_row_hash` | SHA-256 identifier for exact-row idempotency |
| `quality_status` | `unchecked`, `valid`, or `invalid` |
| `loaded_at` | Warehouse load timestamp |
| `pipeline_run_id` | Load lineage |

## `weather_forecasts`

NWS forecast periods by park.

| Column | Meaning |
|---|---|
| `park_id` | Forecast location |
| `start_time`, `end_time` | Forecast period in ISO-8601 time |
| `is_daytime` | Day/night period flag |
| `temperature_f` | Forecast temperature in Fahrenheit |
| `precipitation_probability` | Probability from 0 to 100, nullable |
| `wind_speed` | NWS display string |
| `short_forecast` | Brief forecast label |
| `detailed_forecast` | Longer NWS narrative |
| `fetched_at` | ETL retrieval time |
| `source_url` | NWS forecast endpoint |

## `weather_alerts`

Active NWS Montana alerts observed by a pipeline run. Alerts remain stored after
expiration for lineage and are filtered by expiration in the public endpoint.

## `streamflow_observations`

USGS instantaneous discharge observations.

| Column | Meaning |
|---|---|
| `site_no` | USGS gauge identifier |
| `observed_at` | Measurement timestamp |
| `discharge_cfs` | Discharge in cubic feet per second |
| `qualifiers` | USGS data qualifiers |
| `fetched_at` | ETL retrieval time |
| `pipeline_run_id` | Load lineage |

## `pipeline_runs`

Operational audit table.

| Column | Meaning |
|---|---|
| `source` | Pipeline stage name |
| `status` | `running`, `success`, or `failed` |
| `started_at`, `finished_at` | Execution timing |
| `rows_extracted`, `rows_loaded` | Volume metrics |
| `error_message` | Failure detail, if present |

## `quality_checks`

One row per QA rule per QA run.

| Column | Meaning |
|---|---|
| `check_name` | Stable rule identifier |
| `severity` | `warning` or `error` |
| `passed` | Overall rule result |
| `failed_rows` | Number of affected records |
| `details` | JSON text with description and samples |
| `checked_at` | Rule execution time |
