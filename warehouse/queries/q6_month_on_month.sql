-- name: q6_month_on_month
-- Monthly spending per project compared with the project's previous month that has spending
-- (a month without invoices has no row, so the comparison skips it).
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
),

with_previous AS (
    SELECT
        project_key,
        year,
        month,
        spent,
        LAG(spent) OVER (
            PARTITION BY project_key
            ORDER BY year * 100 + month
        ) AS previous_spent
    FROM monthly_spend
)

SELECT
    p.project_code AS project_code,
    m.year AS year,
    m.month AS month,
    m.spent AS spent,
    m.previous_spent AS prev_month_with_spend,
    m.spent - m.previous_spent AS month_on_month_change,
    CASE
        WHEN m.previous_spent > 0
        THEN ROUND((m.spent - m.previous_spent) * 100.0 / m.previous_spent, 2)
        ELSE NULL
    END AS month_on_month_pct
FROM with_previous m
JOIN ${DW_DB}.dim_project p
    ON m.project_key = p.project_key;
