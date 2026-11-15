-- name: q5_cost_per_mwp
-- Spending per MWp for COMPLETED projects: one row per project and one row per signed year
-- (project_code NULL; total spending of the year's projects divided by their total MWp).

WITH project_spend AS (
    SELECT
        project_key,
        SUM(amount_net) AS total_spent
    FROM ${DW_DB}.fact_invoice_line
    GROUP BY project_key
),

completed AS (
    SELECT
        p.project_code,
        p.signed_year,
        p.mwp,
        COALESCE(s.total_spent, CAST(0 AS DECIMAL(14,2))) AS total_spent
    FROM ${DW_DB}.dim_project p
    LEFT JOIN project_spend s
        ON p.project_key = s.project_key
    WHERE p.status = 'COMPLETED'
)

SELECT
    project_code,
    signed_year,
    SUM(mwp) AS mwp,
    SUM(total_spent) AS total_spent,
    CASE
        WHEN SUM(mwp) > 0
        THEN ROUND(SUM(total_spent) / SUM(mwp), 2)
        ELSE NULL
    END AS cost_per_mwp
FROM completed
GROUP BY signed_year, project_code
GROUPING SETS ((signed_year, project_code), (signed_year));
