-- E1 version C: transactions and amount per account and month from GPC statements, in HiveQL on YARN.
-- The table reads every file of ${E1_LOCATION} line by line (the folder holds only .gpc files); 075 records are
-- cut at their fixed positions (docs/formats/gpc.md, one-based), amounts signed as in Task 16, haléře / 100.
-- Rendered with warehouse.sql.render(path, E1_LOCATION=...); run_e1 sends the statements through pyhive.

SET hive.execution.engine=mr;
SET mapreduce.framework.name=yarn;
SET hive.exec.mode.local.auto=false;

DROP TABLE IF EXISTS e1_gpc_lines;

CREATE EXTERNAL TABLE e1_gpc_lines (line STRING)
STORED AS TEXTFILE
LOCATION '${E1_LOCATION}';

SELECT
    account,
    month,
    COUNT(*) AS transactions,
    CAST(CAST(SUM(amount_haler) AS DECIMAL(20,0)) / 100 AS DECIMAL(16,2)) AS amount
FROM (
    SELECT
        CAST(CAST(substr(line, 4, 16) AS BIGINT) AS STRING) AS account,
        concat('20', substr(line, 96, 2), '-', substr(line, 94, 2)) AS month,
        CASE WHEN substr(line, 61, 1) IN ('1', '5') THEN -1 ELSE 1 END
            * CAST(substr(line, 49, 12) AS BIGINT) AS amount_haler
    FROM e1_gpc_lines
    WHERE substr(line, 1, 3) = '075'
) t
GROUP BY account, month;
