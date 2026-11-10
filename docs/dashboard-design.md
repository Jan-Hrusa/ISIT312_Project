# Management dashboard design — Task 11

**Owner:** Maysoon
**Status:** Draft for review; Task 11 defines the management requirements that Task 10.1 should support
**Scope:** Management cost and budget dashboard, views V1–V5

## 1. Purpose and conventions

The dashboard answers the management question: **How is each project doing financially?** It starts with a portfolio overview and supports drill-down from project to cost category, supplier and invoice.

All amounts are in CZK. The warehouse source is `fve_dw`. The dashboard uses only the warehouse tables and columns listed below; it does not query the clean-zone tables directly.

### Financial definitions

- **Budget:** `SUM(fact_budget_line.budget_amount)`.
- **Spent:** `SUM(fact_invoice_line.amount_net)`; this is net invoiced cost, not cash paid.
- **Paid:** sum of matched `fact_payment.amount` for the invoice(s). `fact_payment.amount` is positive for money paid out.
- **Open:** gross invoiced amount minus matched payments. At invoice level, gross is `SUM(fact_invoice_line.amount_gross)` and paid is the matched payment total.
- **Remaining / difference:** budget minus spent. A negative value means over budget.
- **% budget spent:** spent divided by budget × 100. If budget is zero and spent is positive, display `N/A` and classify as red; if both are zero, display `0%`.
- **Expected margin:** `dim_project.contract_value - GREATEST(total budget, total spent)`. This is the expected margin proxy required by the task, not a recognised accounting profit figure.

**Aggregation rule:** aggregate budget lines and invoice lines independently to the required grain before joining them. Aggregate payments by `invoice_id` before joining to invoice lines. This prevents fact-to-fact joins from multiplying amounts. Never join raw payment rows directly to invoice-line rows.

### Traffic-light rules

Apply the rules at project level and category level:

| Status | Rule |
|---|---|
| 🔴 Red | Any category is over 115% of its budget, **or** total project spend is over 110% of total budget |
| 🟡 Amber | Otherwise, any category is over 105%, **or** total project spend is over 100% of total budget |
| 🟢 Green | Otherwise |

A category with positive spend and zero budget is treated as red. If both category budget and spend are zero, display `0%`. For V1, sort by traffic-light severity (red, amber, green), then by `% budget spent` descending. Within the same traffic-light group, a project with `N/A` (zero total budget and positive spend) appears before projects with a numeric percentage, because its spend cannot be expressed as a finite percentage. The thresholds are strict “over” comparisons: exactly 105%, 110% or 115% does not cross that threshold.

## 2. V1 — Project list

**Purpose:** portfolio-level landing screen. Include projects whose status is `ACTIVE` or `COMPLETED`; exclude `NOT_SIGNED`.

**Displayed columns (in order):**

1. Project code
2. Project name
3. Region
4. Capacity (MWp)
5. Status
6. Contract value (CZK)
7. Budget (CZK)
8. Spent, net (CZK)
9. Budget spent (%)
10. Expected margin (CZK)
11. Traffic light

**Warehouse sources and columns:**

- `dim_project`: `project_key`, `project_code`, `name`, `region`, `mwp`, `contract_value`, `status`
- `fact_budget_line`: `project_key`, `budget_amount`
- `fact_invoice_line`: `project_key`, `amount_net`
- `dim_cost_category`: `category_key` (needed to calculate category-level traffic light)
- `fact_invoice_line.category_key` and `fact_budget_line.category_key` (category grain)

**Calculation and interaction:**

- Aggregate budget by `project_key` from `fact_budget_line`.
- Aggregate net spend by `project_key` from `fact_invoice_line`.
- Separately aggregate budget and spend by `project_key, category_key` to evaluate category thresholds.
- Calculate expected margin using the definition in section 1.
- If total budget is zero and total spend is positive, show `% budget spent` as `N/A`; the project is red under the zero-budget rule above.
- Filter `dim_project.status IN ('ACTIVE', 'COMPLETED')`.
- Sort red → amber → green, then `% budget spent` descending.
- Selecting a project opens V2.

**Query deliverable:** `v1_project_list.sql` (Task 22).

## 3. V2 — Project detail: budget vs actual by category

**Purpose:** show where one selected project’s budget is being consumed.

**Displayed columns:**

- Cost category
- Budget (CZK)
- Spent, net (CZK)
- Remaining (CZK) = budget − spent
- Budget spent (%)

Include a **TOTAL** row. Show categories over budget first, ordered by highest percentage spent; then the remaining categories by percentage spent descending. The total row is always last.

**Warehouse sources and columns:**

- `dim_project`: `project_key`, `project_code`
- `dim_cost_category`: `category_key`, `category_code`, `category_name`
- `fact_budget_line`: `project_key`, `category_key`, `budget_amount`
- `fact_invoice_line`: `project_key`, `category_key`, `amount_net`

**Calculation and interaction:**

- Filter by the selected `project_code` (resolve to `project_key`).
- Aggregate budget and net spend independently by `category_key`, then combine the aggregates.
- `Remaining = budget − spent`; negative values indicate an overrun.
- Calculate total-row percentage from total spend / total budget. Do not average category percentages.
- For a category with zero budget and positive spend, display `N/A` and classify it as over budget/red. If both budget and spend are zero, display `0%`.
- Selecting a category opens V3.

**Query deliverable:** filtered `q1_budget_vs_actual.sql` (Task 22).

## 4. V3 — Category → suppliers

**Purpose:** explain which suppliers make up the selected project/category spend and what remains unpaid.

**Displayed columns:** supplier, invoiced (CZK), paid (CZK), open (CZK).

**Warehouse sources and columns:**

- `dim_project`: `project_key`, `project_code`
- `dim_cost_category`: `category_key`, `category_code`, `category_name`
- `dim_supplier`: `supplier_key`, `name`, `ico`
- `fact_invoice_line`: `invoice_id`, `project_key`, `category_key`, `supplier_key`, `amount_gross`
- `fact_payment`: `invoice_id`, `amount`

**Calculation and interaction:**

- Filter to the selected project and category.
- Aggregate gross invoiced amount by `invoice_id` and supplier from `fact_invoice_line`.
- Aggregate matched payments by `invoice_id` from `fact_payment` separately; do not join raw payment rows to invoice-line rows.
- **Payment-allocation gap:** `fact_payment` records payment at invoice level, while this view is filtered to one cost category. If an invoice contains lines from more than one category, the contract does not specify how its payment is divided between those categories. In that case, category-level `paid` and `open` cannot be calculated reliably from the listed fields alone. Task 10.1 must establish whether invoices are guaranteed to contain only one category or define an approved allocation rule (for example, proportional allocation by category gross amount). Do not silently assign the full invoice payment to every category. Raise the decision with the Task 10.1 owner and Jan before implementing V3.
- Once the allocation rule is confirmed, sum the category-attributed invoice amounts, paid amounts and `gross − paid` open amounts by supplier.
- Selecting a supplier opens V4.

Here **invoiced** is gross, so `invoiced = paid + open` can be reconciled. This differs intentionally from V1/V2 **spent**, which is net.

**Query deliverable:** `v3_category_suppliers.sql` (Task 30.1).

## 5. V4 — Supplier → invoices

**Purpose:** invoice-level payment follow-up for one selected project and supplier.

**Displayed columns:** invoice number, issue date, due date, gross amount (CZK), payment status, days late.

**Warehouse sources and columns:**

- `dim_project`: `project_key`, `project_code`
- `dim_supplier`: `supplier_key`, `ico`, `name`
- `dim_date`: `date_key`, `full_date`
- `fact_invoice_line`: `invoice_id`, `line_no`, `project_key`, `supplier_key`, `issue_date_key`, `due_date_key`, `amount_gross`, `payment_status`, `days_late`

**Calculation and interaction:**

- Filter to the selected project and supplier.
- Group invoice lines by `invoice_id`; sum `amount_gross` to invoice gross.
- The warehouse contract contains `invoice_id` but does not list a separate invoice-number column. Under the contract's invoice ID format (`<ico>-<number>`), display the portion after the first hyphen as the invoice number; retain `invoice_id` as the unique invoice identifier.
- Use the issue-date and due-date keys to look up `dim_date.full_date`.
- Display the invoice-level payment status and days late. These fields are present on `fact_invoice_line`; confirm in Task 10.1 whether the ETL repeats the invoice-level values consistently across all lines. If not, the warehouse design must define a deterministic invoice-level derivation before this view is implemented.
- Sort by due date, with overdue/unpaid items surfaced first.

**Query deliverable:** `v4_supplier_invoices.sql` (Task 30.1).

## 6. V5 — Across-project analysis

| Analysis | Display / grain | Warehouse sources and columns |
|---|---|---|
| Cost per MWp by project and signed year | Project, signed year, net spend, MWp, cost per MWp | `dim_project`: `project_key`, `project_code`, `name`, `mwp`, `signed_year`; `fact_invoice_line`: `project_key`, `amount_net` |
| Categories most often over budget | Category, number of projects over budget, optionally average overrun % | `dim_cost_category`: `category_key`, `category_code`, `category_name`; `fact_budget_line`: `project_key`, `category_key`, `budget_amount`; `fact_invoice_line`: `project_key`, `category_key`, `amount_net` |
| Spending curve for one project | Date, daily spend and cumulative net spend | `dim_project`: `project_key`, `project_code`; `dim_date`: `date_key`, `full_date`; `fact_invoice_line`: `project_key`, `issue_date_key`, `amount_net` |
| Spend by category group × year | Year, category group, net spend | `dim_date`: `date_key`, `year`; `dim_cost_category`: `category_key`, `group_name`; `fact_invoice_line`: `issue_date_key`, `category_key`, `amount_net` |
| Month-on-month change | Month, net spend, previous-month spend, absolute and percentage change | `dim_date`: `date_key`, `year`, `month`, `month_name`; `fact_invoice_line`: `issue_date_key`, `amount_net` |

**Calculation notes:**

- Cost per MWp = project net spend / `dim_project.mwp`; guard against zero or NULL MWp.
- “Most often over budget” counts projects for which category spend exceeds category budget; aggregate each fact to project/category first.
- Spending curve uses invoice issue date (`issue_date_key`) and a running sum ordered by `dim_date.full_date`.
- Category-group annual spend uses the invoice issue year and `dim_cost_category.group_name`.
- Month-on-month change is portfolio-wide by default, comparing each month with the immediately preceding calendar month, including months with zero spend. If dashboard filters are provided, the same calculation may be scoped to the selected project(s). Use a complete month series so a missing month is not mistaken for the previous month.
- The phrase “signed year” maps to `dim_project.signed_year`, not invoice issue year.

**Query deliverables:** Task 22 queries `q2`–`q6`; exact filenames should follow the Task 22 task description.

## 7. Screen flow and labels

`V1 Project list → V2 Project detail → V3 Category suppliers → V4 Supplier invoices`.

V5 is a separate analysis area reachable from the dashboard navigation. Use Czech labels with English in brackets, for example:

- Projekty (projects)
- Rozpočet (budget)
- Utraceno – netto (spent – net)
- Zbývá (remaining)
- Dodavatel (supplier)
- Faktury (invoices)
- Zaplaceno (paid)
- Otevřeno (open)
- Očekávaná marže (expected margin)

## 8. Contract mapping / review required

The design maps to the warehouse contract in `docs/contracts.md` §8. Task 11 is the management-requirements baseline; Task 10.1 should support these views. Before implementation, the Task 10.1 owner (Gokulsanjay) should compare the reviewed warehouse design with these requirements, confirm the listed fields and grains where present, and identify any gaps, especially:

1. `fact_invoice_line.payment_status` and `days_late` at invoice-level consistency across line rows.
2. `fact_payment.invoice_id` populated for matched payments and payment amounts positive for paid-out debits.
3. The intended date semantics for V5 spending analyses (invoice issue date, as designed here).
4. The `dim_project.signed_year` source and handling of projects without a signed date.
5. The V3 payment-allocation rule when one invoice contains multiple cost categories. The current contract links payments to invoices, not directly to invoice categories.

No changes to shared contracts are proposed by this Task 11 design. Any disagreement with §8 of the contract must be raised with Jan rather than silently changing names.

## 9. Acceptance checklist

- [ ] V1 and V2 mock-up reviewed for layout and labels.
- [ ] Every view’s warehouse tables, columns and required grains compared by Gokulsanjay against the reviewed Task 10.1 design; gaps are recorded for resolution rather than treated as a reason to reverse the Task 11 requirements.
- [ ] Jan reviews the design and mock-up (Task 15.1).
- [ ] `docs/dashboard-design.md` and `docs/dashboard-mockup.png` included in the Task 11 PR.
- [ ] Three-line Task 11 entry added to `log.md` with actual checks performed.
