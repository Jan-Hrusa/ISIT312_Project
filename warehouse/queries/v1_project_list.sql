
-- name: v1_project_list
-- Main dashboard project list with budget, actual spending and traffic lights.
-- Budget and invoice facts are aggregated independently to avoid fan-out joins.

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

category_totals AS (
    SELECT
        project_key,
        category_key,
        SUM(budget) AS budget,
        SUM(spent) AS spent
    FROM combined
    GROUP BY project_key, category_key
),

category_flags AS (
    SELECT
        project_key,
        MAX(
            CASE
                WHEN budget = 0 AND spent > 0 THEN 1
                WHEN budget > 0 AND spent > budget * 1.15 THEN 1
                ELSE 0
            END
        ) AS category_red,
        MAX(
            CASE
                WHEN budget > 0 AND spent > budget * 1.05 THEN 1
                ELSE 0
            END
        ) AS category_amber
    FROM category_totals
    GROUP BY project_key
),

project_totals AS (
    SELECT
        project_key,
        SUM(budget) AS budget,
        SUM(spent) AS spent
    FROM category_totals
    GROUP BY project_key
),

dashboard AS (
    SELECT
        p.project_code,
        p.name,
        p.region,
        p.mwp,
        p.status,
        p.contract_value,
        COALESCE(t.budget, CAST(0 AS DECIMAL(14,2))) AS budget,
        COALESCE(t.spent, CAST(0 AS DECIMAL(14,2))) AS spent,
        CASE
            WHEN COALESCE(t.budget, 0) = 0 THEN NULL
            ELSE ROUND(t.spent * 100.0 / t.budget, 2)
        END AS pct_spent,
        p.contract_value -
            CASE
                WHEN COALESCE(t.budget, 0) > COALESCE(t.spent, 0)
                    THEN COALESCE(t.budget, 0)
                ELSE COALESCE(t.spent, 0)
            END AS expected_margin,
        CASE
            WHEN COALESCE(f.category_red, 0) = 1
                OR COALESCE(t.spent, 0) > COALESCE(t.budget, 0) * 1.10
                THEN 'RED'
            WHEN COALESCE(f.category_amber, 0) = 1
                OR COALESCE(t.spent, 0) > COALESCE(t.budget, 0)
                THEN 'AMBER'
            ELSE 'GREEN'
        END AS traffic_light
    FROM ${DW_DB}.dim_project p
    LEFT JOIN project_totals t
        ON p.project_key = t.project_key
    LEFT JOIN category_flags f
        ON p.project_key = f.project_key
    WHERE p.status IN ('ACTIVE', 'COMPLETED')
)

SELECT
    project_code,
    name,
    region,
    mwp,
    status,
    contract_value,
    budget,
    spent,
    pct_spent,
    expected_margin,
    traffic_light
FROM dashboard
ORDER BY
    CASE traffic_light
        WHEN 'RED' THEN 1
        WHEN 'AMBER' THEN 2
        ELSE 3
    END,
    CASE WHEN pct_spent IS NULL THEN 0 ELSE 1 END,
    pct_spent DESC;
