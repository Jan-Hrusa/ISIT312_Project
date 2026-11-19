-- E4: file arrival rates from the collected-file log.
-- Monthly totals measure the number and size of files arriving per source.
-- Daily totals measure the distribution of arrivals, including days with no files.
--
-- The Python runner supplies CLEAN_DB, DATA_START and DATA_END.
-- The daily query returns observed days; the runner fills missing calendar days
-- with zero before calculating peak, median and no-file-day share.

-- name: monthly_arrivals
SELECT
    source,
    YEAR(business_date) AS arrival_year,
    MONTH(business_date) AS arrival_month,
    COUNT(*) AS files,
    SUM(size_bytes) AS bytes,
    ROUND(SUM(size_bytes) / 1000000.0, 3) AS mb
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