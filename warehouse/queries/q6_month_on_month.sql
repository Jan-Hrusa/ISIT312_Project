
-- name: q6_month_on_month
-- Monthly spending and previous-month spending for each project.
-- Months are ordered by year * 100 + month to handle year boundaries.

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
    LAG(m.spent) OVER (
        PARTITION BY m.project_key
        ORDER BY m.year * 100 + m.month
    ) AS previous_month_spent,
    m.spent - LAG(m.spent) OVER (
        PARTITION BY m.project_key
        ORDER BY m.year * 100 + m.month
    ) AS month_on_month_change
FROM monthly_spend m
JOIN ${DW_DB}.dim_project p
    ON m.project_key = p.project_key;
