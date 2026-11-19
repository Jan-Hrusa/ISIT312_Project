-- E4: file arrival rates from the collected-file log (one row per collected file, photos one row each).
-- Monthly totals measure the number and size of files arriving per source.
-- Daily totals measure the distribution of arrivals; the runner fills missing calendar days with zero before
-- calculating peak, median and the share of days with no file.
-- Source totals are the per-source table of the README (and the Validate screenshot in beeline).
--
-- benchmarks.e4.run_e4 renders the placeholders with warehouse.sql (CLEAN_DB from common.config, DATA_START and
-- DATA_END from config.DATA_START / DATA_END). The queries run unchanged on Spark SQL and on Hive.

-- name: monthly_arrivals
SELECT
    source,
    YEAR(business_date) AS arrival_year,
    MONTH(business_date) AS arrival_month,
    COUNT(*) AS files,
    SUM(size_bytes) AS bytes
FROM ${CLEAN_DB}.ingest_log
WHERE business_date BETWEEN DATE '${DATA_START}' AND DATE '${DATA_END}'
GROUP BY
    source,
    YEAR(business_date),
    MONTH(business_date)
ORDER BY
    source,
    arrival_year,
    arrival_month;

-- name: daily_arrivals
SELECT
    source,
    business_date,
    COUNT(*) AS files
FROM ${CLEAN_DB}.ingest_log
WHERE business_date BETWEEN DATE '${DATA_START}' AND DATE '${DATA_END}'
GROUP BY
    source,
    business_date
ORDER BY
    source,
    business_date;

-- name: source_totals
SELECT
    source,
    COUNT(*) AS files,
    ROUND(SUM(size_bytes) / 1000000.0, 2) AS mb,
    COUNT(DISTINCT business_date) AS days_with_files,
    MIN(business_date) AS first_day,
    MAX(business_date) AS last_day
FROM ${CLEAN_DB}.ingest_log
WHERE business_date BETWEEN DATE '${DATA_START}' AND DATE '${DATA_END}'
GROUP BY source
ORDER BY source;
