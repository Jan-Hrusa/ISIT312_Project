
-- name: q4_overrun_rank
-- Rank categories by how often COMPLETED projects exceed their budgets.
-- Ranking prioritises the number of projects over budget, then average overrun.

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

category_results AS (
    SELECT
        b.category_key,
        b.project_key,
        b.budget,
        COALESCE(s.spent, CAST(0 AS DECIMAL(14,2))) AS spent
    FROM budget_by_category b
    LEFT JOIN spent_by_category s
        ON b.project_key = s.project_key
        AND b.category_key = s.category_key
),

overruns AS (
    SELECT
        category_key,
        CASE
            WHEN spent > budget THEN 1
            ELSE 0
        END AS over_budget,
        CASE
            WHEN budget > 0 AND spent > budget
            THEN (spent - budget) * 100.0 / budget
            ELSE 0
        END AS overrun_pct
    FROM category_results r
    JOIN ${DW_DB}.dim_project p
        ON r.project_key = p.project_key
    WHERE p.status = 'COMPLETED'
),

category_summary AS (
    SELECT
        category_key,
        SUM(over_budget) AS projects_over,
        AVG(overrun_pct) AS avg_overrun_pct
    FROM overruns
    GROUP BY category_key
)

SELECT
    c.category_code,
    s.projects_over,
    ROUND(s.avg_overrun_pct, 2) AS avg_overrun_pct,
    RANK() OVER (
        ORDER BY s.projects_over DESC, s.avg_overrun_pct DESC
    ) AS category_rank
FROM category_summary s
JOIN ${DW_DB}.dim_cost_category c
    ON s.category_key = c.category_key;
