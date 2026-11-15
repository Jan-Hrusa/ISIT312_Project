
-- name: q2_category_by_year
-- Spending by category group and invoice year.
-- CUBE includes group totals, year totals, and the grand total.

SELECT
    c.group_name,
    d.year,
    SUM(i.amount_net) AS spent
FROM ${DW_DB}.fact_invoice_line i
JOIN ${DW_DB}.dim_cost_category c
    ON i.category_key = c.category_key
JOIN ${DW_DB}.dim_date d
    ON i.issue_date_key = d.date_key
GROUP BY c.group_name, d.year WITH CUBE;
