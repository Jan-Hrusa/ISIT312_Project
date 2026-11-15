
-- name: q1_budget_vs_actual
-- Budget versus actual spending by project and category.
-- Budget and invoice facts are aggregated separately to avoid fan-out joins.

WITH budget_by_category AS (
    SELECT
        project_key,
        category_key,
        SUM(budget_amount) AS budget
    FROM ${DW_DB}.fact_budget_line
    GROUP BY project_key, category_key
),

spent_by_category AS (
    SELECT
        project_key,
        category_key,
        SUM(amount_net) AS spent
    FROM ${DW_DB}.fact_invoice_line
    GROUP BY project_key, category_key
),

combined AS (
    SELECT
        project_key,
        category_key,
        budget,
        CAST(0 AS DECIMAL(14,2)) AS spent
    FROM budget_by_category

    UNION ALL

    SELECT
        project_key,
        category_key,
        CAST(0 AS DECIMAL(14,2)) AS budget,
        spent
    FROM spent_by_category
),

totals AS (
    SELECT
        project_key,
        category_key,
        SUM(budget) AS budget,
        SUM(spent) AS spent
    FROM combined
    GROUP BY project_key, category_key
)

SELECT
    p.project_code,
    c.category_code,
    SUM(t.budget) AS budget,
    SUM(t.spent) AS spent,
    SUM(t.budget) - SUM(t.spent) AS difference,
    CASE
        WHEN SUM(t.budget) = 0 THEN NULL
        ELSE ROUND(
            SUM(t.spent) * 100.0 / SUM(t.budget),
            2
        )
    END AS pct_spent
FROM totals t
JOIN ${DW_DB}.dim_project p
    ON t.project_key = p.project_key
JOIN ${DW_DB}.dim_cost_category c
    ON t.category_key = c.category_key
GROUP BY p.project_code, c.category_code WITH ROLLUP;
