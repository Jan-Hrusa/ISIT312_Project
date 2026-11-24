-- Task 26: Warehouse dimension loads
-- Project dimension

INSERT OVERWRITE TABLE ${DW_DB}.dim_project
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY project_code) AS INT) AS project_key,
    project_code,
    name,
    town,
    region,
    mwp,
    has_battery,
    contract_value,
    status,
    CASE
        WHEN status = 'NOT_SIGNED' THEN CAST(NULL AS INT)
        ELSE YEAR(signed_date)
    END AS signed_year,
    construction_start,
    construction_end
FROM ${CLEAN_DB}.projects

UNION ALL

SELECT
    -1,
    'UNKNOWN',
    'Unknown project',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'UNKNOWN',
    NULL,
    NULL,
    NULL;

-- Supplier dimension
INSERT OVERWRITE TABLE ${DW_DB}.dim_supplier
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY ico) AS INT) AS supplier_key,
    ico,
    name,
    category AS main_category
FROM ${CLEAN_DB}.suppliers

UNION ALL

SELECT
    -1,
    'UNKNOWN',
    'Unknown supplier',
    'UNKNOWN';

-- Cost category dimension (the codes of common/config.CATEGORIES; keys by code, as every surrogate key)
INSERT OVERWRITE TABLE ${DW_DB}.dim_cost_category
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY category_code) AS INT) AS category_key,
    category_code,
    category_name,
    group_name
FROM VALUES
    ('PANELS', 'Panels', 'technology'),
    ('INVERTERS', 'Inverters', 'technology'),
    ('BATTERIES', 'Batteries', 'technology'),
    ('STRUCTURES', 'Mounting structures', 'construction'),
    ('CABLES', 'Cables', 'construction'),
    ('EARTHWORKS', 'Earthworks', 'construction'),
    ('GRID', 'Grid connection', 'construction'),
    ('DESIGN', 'Design', 'services'),
    ('SURVEY', 'Survey', 'services'),
    ('OTHER', 'Other', 'services')
AS categories(category_code, category_name, group_name);

-- Date dimension: 2016-01-01 through 2026-12-31; iso_week = ISO week-year and week as YYYY-Www (contracts)
INSERT OVERWRITE TABLE ${DW_DB}.dim_date
SELECT
    CAST(date_format(full_date, 'yyyyMMdd') AS INT) AS date_key,
    full_date,
    DAY(full_date) AS day,
    MONTH(full_date) AS month,
    date_format(full_date, 'MMMM') AS month_name,
    QUARTER(full_date) AS quarter,
    YEAR(full_date) AS year,
    concat(
           CAST(YEAR(date_add(full_date, 4 - ((dayofweek(full_date) + 5) % 7 + 1))) AS STRING),
           '-W',
           lpad(CAST(weekofyear(full_date) AS STRING), 2, '0')
       ) AS iso_week
FROM (
    SELECT explode(
        sequence(
            DATE '2016-01-01',
            DATE '2026-12-31',
            INTERVAL 1 DAY
        )
    ) AS full_date
) dates;

-- Bank account dimension (the company accounts of common/config.BANKS; keys by account number)
INSERT OVERWRITE TABLE ${DW_DB}.dim_bank_account
SELECT
    CAST(ROW_NUMBER() OVER (ORDER BY account) AS INT) AS account_key,
    bank,
    bank_name,
    account,
    bank_code,
    currency
FROM VALUES
    ('RB', 'Raiffeisenbank', '2101234567', '5500', 'CZK'),
    ('UCB', 'UniCredit Bank', '1387654321', '2700', 'CZK'),
    ('KB', 'Komerční banka', '1234567890', '0100', 'CZK'),
    ('CS', 'Česká spořitelna', '2900112233', '0800', 'CZK')
AS accounts(bank, bank_name, account, bank_code, currency);
