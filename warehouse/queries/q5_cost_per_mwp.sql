
-- name: q5_cost_per_mwp
-- Spending per MWp for COMPLETED projects, by project and signed year.

WITH project_spend AS (
    SELECT
        project_key,
        SUM(amount_net) AS total_spent
    FROM ${DW_DB}.fact_invoice_line
    GROUP BY project_key
)

SELECT
    p.project_code,
    p.signed_year,
    p.mwp,
    COALESCE(s.total_spent, CAST(0 AS DECIMAL(14,2))) AS total_spent,
    CASE
        WHEN p.mwp > 0
        THEN ROUND(
            COALESCE(s.total_spent, 0) / p.mwp,
            2
        )
        ELSE NULL
    END AS cost_per_mwp
FROM ${DW_DB}.dim_project p
LEFT JOIN project_spend s
    ON p.project_key = s.project_key
WHERE p.status = 'COMPLETED';
