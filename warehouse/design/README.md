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
