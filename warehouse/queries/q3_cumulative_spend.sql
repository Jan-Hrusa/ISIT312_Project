
-- name: q3_cumulative_spend
-- Monthly spending and cumulative spending for each project.
-- Ordering by year * 100 + month handles year boundaries correctly.

WITH monthly_spend AS (
    SELECT
        i.project_key,
        d.year,
        d.month,
        SUM(i.amount_net) AS spent
    FROM ${DW_DB}.fact_invoice_line i
    JOIN ${DW_DB}.dim_date d
        ON i.issue_date_key = d.date_key
    GROUP BY
        i.project_key,
        d.year,
        d.month
)

SELECT
    p.project_code,
    m.year,
    m.month,
    m.spent,
    SUM(m.spent) OVER (
        PARTITION BY m.project_key
        ORDER BY m.year * 100 + m.month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_spend
FROM monthly_spend m
JOIN ${DW_DB}.dim_project p
    ON m.project_key = p.project_key;
