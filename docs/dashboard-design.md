# Management dashboard design — Task 11

**Owner:** Maysoon
**Status:** Reviewed by Jan (Task 15.1, 10 Nov); Task 11 defines the management requirements that Task 10.1 should support
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
- **One project and one category per invoice:** every invoice has exactly one project and one cost category (Task 20.1: the category comes from the booking, else from the supplier's category, and the invoice's lines inherit both; `docs/contracts.md` sections 6 and 8). A payment matched to an invoice therefore belongs entirely to that invoice's project and category, so no allocation rule is needed.
- Sum invoiced (gross), paid and open (`gross − paid`) per invoice, then by supplier.
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
- Display payment status and days late. They are the invoice's values from the matching job (`invoice_status`), repeated on every line of the invoice (`docs/contracts.md` section 8), so any line gives them (e.g. `MAX(payment_status)` in the invoice grouping).
- Sort by due date, with overdue/unpaid items surfaced first.

**Query deliverable:** `v4_supplier_invoices.sql` (Task 30.1).

## 6. V5 — Across-project analysis

| Analysis | Display / grain | Warehouse sources and columns | Query file (Task 22) |
|---|---|---|---|
| Cost per MWp by project and signed year | COMPLETED projects: project, signed year, net spend, MWp, cost per MWp; also per signed year | `dim_project`: `project_key`, `project_code`, `name`, `mwp`, `signed_year`, `status`; `fact_invoice_line`: `project_key`, `amount_net` | `q5_cost_per_mwp.sql` |
| Categories most often over budget | COMPLETED projects: category, number of projects over budget, average overrun %, rank | `dim_project`: `project_key`, `status`; `dim_cost_category`: `category_key`, `category_code`, `category_name`; `fact_budget_line`: `project_key`, `category_key`, `budget_amount`; `fact_invoice_line`: `project_key`, `category_key`, `amount_net` | `q4_overrun_rank.sql` |
| Spending curve of a project | Per project and month: net spend and cumulative net spend | `dim_project`: `project_key`, `project_code`; `dim_date`: `date_key`, `year`, `month`; `fact_invoice_line`: `project_key`, `issue_date_key`, `amount_net` | `q3_cumulative_spend.sql` |
| Spend by category group × year | Category group, year, net spend, with subtotals and grand total (`CUBE`) | `dim_date`: `date_key`, `year`; `dim_cost_category`: `category_key`, `group_name`; `fact_invoice_line`: `issue_date_key`, `category_key`, `amount_net` | `q2_category_by_year.sql` |
| Month-on-month change | Per project and month: net spend, previous month's spend, absolute and percentage change | `dim_project`: `project_key`, `project_code`; `dim_date`: `date_key`, `year`, `month`, `month_name`; `fact_invoice_line`: `project_key`, `issue_date_key`, `amount_net` | `q6_month_on_month.sql` |

**Calculation notes:**

- Cost per MWp = project net spend / `dim_project.mwp`; guard against zero or NULL MWp. COMPLETED projects only: an ACTIVE project is still spending, so its cost per MWp is not comparable.
- “Most often over budget” counts COMPLETED projects for which category spend exceeds category budget; aggregate each fact to project/category first; rank by number of projects, then average overrun %.
- Spending curve uses the invoice issue month (`issue_date_key` → `dim_date.year`, `month`) and a running sum per project ordered by `year * 100 + month` (never by `month` alone: projects cross year boundaries).
- Category-group annual spend uses the invoice issue year and `dim_cost_category.group_name`.
- Month-on-month change is per project: `LAG` of the monthly spend ordered by `year * 100 + month`; the first month's previous value is NULL.
- Note for Task 22: `LAG` returns the previous month *with invoices*. If a project has a month without invoices, the comparison skips it. Either fill each project's month series from `dim_date` (first to last invoice month, spend 0) before `LAG`, or label the column “previous month with spend”.
- The phrase “signed year” maps to `dim_project.signed_year`, not invoice issue year.

**Query deliverables:** Task 22 queries `q2`–`q6`, as named in the table.

## 7. Screen flow and labels

`V1 Project list → V2 Project detail → V3 Category suppliers → V4 Supplier invoices`.

V5 is a separate analysis area reachable from the dashboard navigation. The mock-up shows the layout; the dashboard itself is a Zeppelin note (Task 30.1) whose filters are the note forms project, category and supplier, so the mock-up's region filter and search box are not built. Use Czech labels with English in brackets, for example:

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

1. `fact_payment.invoice_id` populated for matched payments and payment amounts positive for paid-out debits.
2. The intended date semantics for V5 spending analyses (invoice issue date, as designed here).
3. The `dim_project.signed_year` source and handling of projects without a signed date.

Settled in the review (Task 15.1, 10 Nov), now in `docs/contracts.md` sections 6 and 8: every invoice has one project and one category, so V3 needs no payment-allocation rule; `payment_status` and `days_late` are the same on every line of an invoice. Any other disagreement with §8 of the contract must be raised with Jan rather than silently changing names.

## 9. Acceptance checklist

- [ ] V1 and V2 mock-up reviewed for layout and labels.
- [ ] Every view’s warehouse tables, columns and required grains compared by Gokulsanjay against the reviewed Task 10.1 design; gaps are recorded for resolution rather than treated as a reason to reverse the Task 11 requirements.
- [x] Jan reviews the design and mock-up (Task 15.1).
- [x] `docs/dashboard-design.md` and `docs/dashboard-mockup.png` included in the Task 11 PR.
- [x] Three-line Task 11 entry added to `log.md` with actual checks performed.
