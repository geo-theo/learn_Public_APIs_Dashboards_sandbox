-- Montana Public Data Lab: SQL learning queries
-- Open data/montana_data_lab.db in SQLite, DBeaver, or a BI tool.

-- 1. Confirm table volumes.
SELECT 'parks' AS table_name, COUNT(*) AS row_count FROM parks
UNION ALL
SELECT 'visit_records', COUNT(*) FROM visit_records
UNION ALL
SELECT 'weather_forecasts', COUNT(*) FROM weather_forecasts
UNION ALL
SELECT 'streamflow_observations', COUNT(*) FROM streamflow_observations;

-- 2. Compare valid and invalid tablet rows.
SELECT
    quality_status,
    COUNT(*) AS records,
    SUM(raw_count) AS raw_count_sum
FROM visit_records
GROUP BY quality_status;

-- 3. Calculate raw and weighted visitation by park.
SELECT
    p.name AS park_name,
    SUM(v.raw_count) AS raw_visits,
    ROUND(SUM(v.raw_count * v.survey_weight), 1) AS weighted_visits
FROM visit_records AS v
JOIN parks AS p ON p.id = v.park_id
WHERE v.quality_status = 'valid'
GROUP BY p.name
ORDER BY weighted_visits DESC;

-- 4. Aggregate monthly visitation.
SELECT
    strftime('%Y-%m', v.visit_date) AS visit_month,
    p.name AS park_name,
    SUM(v.raw_count) AS raw_visits,
    ROUND(SUM(v.raw_count * v.survey_weight), 1) AS weighted_visits
FROM visit_records AS v
JOIN parks AS p ON p.id = v.park_id
WHERE v.quality_status = 'valid'
GROUP BY visit_month, p.name
ORDER BY visit_month, p.name;

-- 5. Find source defects for an exception report.
SELECT
    v.id,
    p.name AS park_name,
    v.visit_date,
    v.raw_count,
    v.device_id,
    v.survey_weight,
    v.source_note
FROM visit_records AS v
JOIN parks AS p ON p.id = v.park_id
WHERE v.quality_status = 'invalid'
ORDER BY v.visit_date, p.name;

-- 6. Show the latest streamflow reading for every gauge.
WITH ranked AS (
    SELECT
        site_no,
        observed_at,
        discharge_cfs,
        qualifiers,
        ROW_NUMBER() OVER (
            PARTITION BY site_no
            ORDER BY observed_at DESC
        ) AS position
    FROM streamflow_observations
)
SELECT
    g.name,
    r.observed_at,
    r.discharge_cfs,
    r.qualifiers
FROM ranked AS r
JOIN stream_gauges AS g ON g.site_no = r.site_no
WHERE r.position = 1
ORDER BY g.name;

-- 7. Review recent pipeline reliability.
SELECT
    source,
    status,
    started_at,
    finished_at,
    rows_extracted,
    rows_loaded,
    error_message
FROM pipeline_runs
ORDER BY id DESC
LIMIT 20;

-- 8. Calculate pipeline duration in seconds.
SELECT
    source,
    status,
    ROUND((julianday(finished_at) - julianday(started_at)) * 86400, 2)
        AS duration_seconds,
    rows_loaded
FROM pipeline_runs
WHERE finished_at IS NOT NULL
ORDER BY id DESC;

-- 9. Examine duplicate tablet submissions.
SELECT
    p.name,
    v.visit_date,
    v.device_id,
    COUNT(*) AS duplicate_rows,
    GROUP_CONCAT(v.raw_count) AS submitted_counts
FROM visit_records AS v
JOIN parks AS p ON p.id = v.park_id
WHERE v.device_id IS NOT NULL
GROUP BY p.name, v.visit_date, v.device_id
HAVING COUNT(*) > 1;

-- 10. Exercise: compare weekday and weekend weighted visitation.
-- Hint: CAST(strftime('%w', visit_date) AS INTEGER) IN (0, 6)
