# Data Warehouse Design — Task 10.1

## Overview

This directory contains the conceptual and logical data warehouse designs for the ISIT312 solar-farm construction
data lake project. The warehouse uses a fact constellation consisting of four fact tables and five shared dimension
tables. Its purpose is to support project budget monitoring, supplier spending analysis, invoice tracking, and
payment reconciliation.

The designs follow the warehouse requirements in `docs/contracts.md` section 8 and the reporting requirements in
`docs/dashboard-design.md`.

## Fact tables

### 1. fact_budget_line

- Grain: one budget record per project and cost category.
- Measure: `budget_amount`.

This fact stores the budget allocated to each cost category within a project. It uses the project and cost-category
dimensions, together with a date reference representing the project's signing date. It answers dashboard views V1
(budget per project and the traffic light), V2 (budget versus actual by category) and V5 (categories most often over
budget).

### 2. fact_invoice_line

- Grain: one invoice line.
- Measures: `amount_net`, `vat_amount`, `amount_gross`.
- Degenerate attributes: `invoice_id`, `line_no`, `payment_status`, `days_late`.

This fact records invoice-line expenditure, including its project, supplier, cost category, issue date, due date,
payment status, and lateness. It answers every dashboard view: spent per project (V1), actual cost per category (V2),
invoiced amounts per supplier (V3), the invoice list with payment status and days late (V4), and the across-project
analyses (V5).

### 3. fact_payment

- Grain: one bank debit representing a supplier payment.
- Measures: `amount` (positive = paid out), `days_late`.
- Degenerate attributes: `tx_id`, `invoice_id`.

This fact records supplier payments from bank statements. It links payments to projects, suppliers, bank accounts,
and value dates. The `invoice_id` attribute is NULL when a payment cannot be matched to an invoice. It answers V3:
the paid and open amounts per supplier come from the matched payments, summed by `invoice_id` before they are
compared with the invoices.

### 4. fact_payment_order

- Grain: one KPC payment-order item.
- Measures: `amount`, `cleared` (1 or 0; NULL when the order matches no invoice).
- Degenerate attributes: `order_id`, `invoice_id`.

This fact records payment instructions and whether they have cleared. It connects each payment-order item to its
project, supplier, bank account, order date, and due date. No dashboard view uses it: it supports the analysis of
outstanding payment instructions (`cleared = 0` are the orders no bank debit cleared, the `ORDER_NOT_CLEARED`
cases) and payment reconciliation.

## Shared dimensions and hierarchies

| Dimension | Attributes | Hierarchy | Used by |
|---|---|---|---|
| `dim_project` | `project_code`, `name`, `town`, `region`, `mwp`, `has_battery`, `contract_value`, `status`, `signed_year`, `construction_start`, `construction_end` | project → region | all four facts |
| `dim_supplier` | `ico`, `name`, `main_category` | supplier → category | invoice line, payment, payment order |
| `dim_cost_category` | `category_code`, `category_name`, `group_name` | category → group | budget line, invoice line |
| `dim_date` | `full_date`, `day`, `month`, `month_name`, `quarter`, `year`, `iso_week` (`YYYY-Www`, e.g. `2026-W45`) | day → month → quarter → year | all four facts |
| `dim_bank_account` | `bank`, `bank_name`, `account`, `bank_code`, `currency` | account → bank | payment, payment order |

The date dimension is reused in different roles: invoice issue date and due date, payment value date, payment-order
date and due date, and project signing date.

Unknown project and supplier records use surrogate key `-1` to preserve facts whose corresponding dimension members
cannot be identified.

## Dashboard support

The warehouse supports the five dashboard views described in `docs/dashboard-design.md`:

| View | Purpose | Main warehouse tables |
|---|---|---|
| V1 | Project list | `dim_project`, `fact_budget_line`, `fact_invoice_line`, `dim_cost_category` (category-level traffic light) |
| V2 | Budget versus actual by category | `fact_budget_line`, `fact_invoice_line`, `dim_project`, `dim_cost_category` |
| V3 | Cost category to suppliers | `fact_invoice_line`, `fact_payment`, `dim_project`, `dim_cost_category`, `dim_supplier` |
| V4 | Supplier to invoices | `fact_invoice_line`, `dim_project`, `dim_supplier`, `dim_date` |
| V5 | Across-project analysis | `fact_budget_line`, `fact_invoice_line`, `dim_project`, `dim_cost_category`, `dim_date` |

Actual spending is calculated using `fact_invoice_line.amount_net`. Budget and actual expenditure can be compared
through their shared project and cost-category dimensions. This is a drill-across operation, with each fact
aggregated to a common grain before comparison.

Invoice issue dates are used for invoice spending trends.

## Planned physical storage

The Hive warehouse database is `fve_dw`. The planned storage format is external ORC tables under `/lake/dw/<table>`.

The planned fact-table partitions are:

| Fact table | Partition columns |
|---|---|
| `fact_budget_line` | `signed_year` |
| `fact_invoice_line` | `issue_year` |
| `fact_payment` | `pay_year`, `pay_month` |
| `fact_payment_order` | `order_year` |

The date dimension covers 2016-01-01 through 2026-12-31.

## Design files

- `conceptual.uxf` — editable UMLet conceptual diagram.
- `conceptual.pdf` — exported conceptual diagram.
- `logical.uxf` — editable UMLet logical diagram with keys and data types.
- `logical.pdf` — exported logical diagram.

The conceptual model describes the fact constellation, measures, dimensions, and analytical hierarchies. The logical
model adds primary keys, foreign keys, data types, and role-playing date relationships.

## References

- `docs/contracts.md` — data contracts and warehouse schema requirements.
- `docs/dashboard-design.md` — dashboard views and reporting requirements.
- Drive document *02 Project description* — section 5.4, data warehouse design.

## Physical Warehouse Design (Task 10)

### Overview

The physical warehouse is implemented using Apache Hive and stores structured construction and financial data for the FVE project. It follows the conceptual and logical warehouse designs documented above.

The warehouse contains nine tables: five dimension tables and four fact tables. All tables are defined in `warehouse/ddl/fve_dw.sql`.

The default Hive database is `fve_dw`, with warehouse data stored under `/lake/dw`. The 10× dataset uses `fve_dw_x10` and `/bench/x10/lake/dw`.

### Storage Format: ORC

All warehouse tables are EXTERNAL Hive tables stored in ORC (Optimized Row Columnar) format.

ORC was selected because it provides:

- **Columnar storage:** Queries can read only the required columns rather than processing every column.
- **Compression:** Reduces storage requirements for large datasets.
- **Predicate pushdown:** Allows supported filters to be applied efficiently using ORC statistics.
- **Efficient analytics:** Suitable for aggregation, filtering, and reporting using Hive and Spark SQL.

EXTERNAL tables allow the project to manage warehouse data independently of Hive table definitions.

### Dimension Tables

The warehouse contains five dimension tables:

| Table | Description |
|---|---|
| `dim_project` | Project information, locations, contract values, and construction dates |
| `dim_supplier` | Supplier information and categories |
| `dim_cost_category` | Cost categories used for financial analysis |
| `dim_date` | Calendar attributes used for time-based analysis |
| `dim_bank_account` | Bank account information for financial transactions |

Dimension tables are not partitioned because they are expected to be relatively small. Partitioning these tables would introduce unnecessary metadata and storage-management overhead.

### Fact Tables and Partitioning

The warehouse contains four fact tables:

| Fact table | Partition columns | Purpose |
|---|---|---|
| `fact_budget_line` | `signed_year` | Supports filtering budgets by contract signing year |
| `fact_invoice_line` | `issue_year` | Supports filtering invoices by issue year |
| `fact_payment` | `pay_year`, `pay_month` | Supports monthly and yearly payment analysis |
| `fact_payment_order` | `order_year` | Supports filtering payment orders by year |

Partitioning allows Hive and Spark to skip irrelevant partitions when queries filter on partition columns. This reduces the amount of data scanned during dashboard queries.

The `fact_payment` table uses two partition columns because financial reports commonly analyze payments by both year and month.

### Data Types

The physical design follows the agreed schema in `docs/contracts.md`.

- Surrogate keys and date keys use `INT`.
- Financial amounts use `DECIMAL(14,2)` to preserve decimal precision.
- Project capacity (`mwp`) uses `DECIMAL(5,2)`.
- Calendar and construction dates use `DATE`.
- Battery availability uses `BOOLEAN`.
- Payment-order clearance status uses `TINYINT`.
- Descriptive fields and identifiers use `STRING`.

Partition columns are declared separately using Hive's `PARTITIONED BY` clause.

### SQL Execution and Configuration

The shared SQL runner is implemented in `warehouse/sql.py`.

It provides three functions:

- `render()` substitutes configuration variables and separates SQL statements.
- `named_queries()` extracts named SQL queries.
- `run_file()` executes the rendered statements using Spark SQL.

The DDL uses `${DW_DB}` and `${LAKE_DW}` rather than hard-coded database names or locations.

This supports both the normal dataset and the 10× benchmark dataset using the shared configuration in `common/config.py`.

### Validation

Automated tests are defined in `tests/warehouse/test_ddl.py`.

They verify SQL variable substitution, rejection of unknown variables, named-query parsing, repeatable DDL execution, table existence, partition columns, and EXTERNAL ORC storage.

The DDL uses `CREATE DATABASE IF NOT EXISTS` and `CREATE EXTERNAL TABLE IF NOT EXISTS` so it can be executed repeatedly without recreating existing tables.

Spark/Hive integration validation and screenshots are required before Task 10 can be considered complete.
