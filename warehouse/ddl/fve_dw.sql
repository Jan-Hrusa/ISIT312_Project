
CREATE DATABASE IF NOT EXISTS ${DW_DB}
LOCATION '${LAKE_DW}';

-- Dimension: Project
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.dim_project (
    project_key INT,
    project_code STRING,
    name STRING,
    town STRING,
    region STRING,
    mwp DECIMAL(5,2),
    has_battery BOOLEAN,
    contract_value DECIMAL(14,2),
    status STRING,
    signed_year INT,
    construction_start DATE,
    construction_end DATE
)
STORED AS ORC
LOCATION '${LAKE_DW}/dim_project';

-- Dimension: Supplier
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.dim_supplier (
    supplier_key INT,
    ico STRING,
    name STRING,
    main_category STRING
)
STORED AS ORC
LOCATION '${LAKE_DW}/dim_supplier';

-- Dimension: Cost Category
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.dim_cost_category (
    category_key INT,
    category_code STRING,
    category_name STRING,
    group_name STRING
)
STORED AS ORC
LOCATION '${LAKE_DW}/dim_cost_category';

-- Dimension: Date
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.dim_date (
    date_key INT,
    full_date DATE,
    day INT,
    month INT,
    month_name STRING,
    quarter INT,
    year INT,
    iso_week STRING
)
STORED AS ORC
LOCATION '${LAKE_DW}/dim_date';

-- Dimension: Bank Account
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.dim_bank_account (
    account_key INT,
    bank STRING,
    bank_name STRING,
    account STRING,
    bank_code STRING,
    currency STRING
)
STORED AS ORC
LOCATION '${LAKE_DW}/dim_bank_account';

-- Fact: Budget Line
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.fact_budget_line (
    project_key INT,
    category_key INT,
    date_key INT,
    budget_amount DECIMAL(14,2)
)
PARTITIONED BY (signed_year INT)
STORED AS ORC
LOCATION '${LAKE_DW}/fact_budget_line';

-- Fact: Invoice Line
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.fact_invoice_line (
    invoice_id STRING,
    line_no INT,
    project_key INT,
    supplier_key INT,
    category_key INT,
    issue_date_key INT,
    due_date_key INT,
    amount_net DECIMAL(14,2),
    vat_amount DECIMAL(14,2),
    amount_gross DECIMAL(14,2),
    payment_status STRING,
    days_late INT
)
PARTITIONED BY (issue_year INT)
STORED AS ORC
LOCATION '${LAKE_DW}/fact_invoice_line';

-- Fact: Payment
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.fact_payment (
    tx_id STRING,
    account_key INT,
    date_key INT,
    supplier_key INT,
    invoice_id STRING,
    project_key INT,
    amount DECIMAL(14,2),
    days_late INT
)
PARTITIONED BY (
    pay_year INT,
    pay_month INT
)
STORED AS ORC
LOCATION '${LAKE_DW}/fact_payment';

-- Fact: Payment Order
CREATE EXTERNAL TABLE IF NOT EXISTS ${DW_DB}.fact_payment_order (
    order_id STRING,
    account_key INT,
    order_date_key INT,
    due_date_key INT,
    supplier_key INT,
    invoice_id STRING,
    project_key INT,
    amount DECIMAL(14,2),
    cleared TINYINT
)
PARTITIONED BY (order_year INT)
STORED AS ORC
LOCATION '${LAKE_DW}/fact_payment_order';
