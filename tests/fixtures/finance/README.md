# Finance sample set (Task 5.1)

A small, hand-checked set in the formats of Task 5. Files are in `tests/fixtures/sources/` (same layout as
`sources/`); their business dates are in `tests/fixtures/mtimes_finance.csv`; the truth file is
`tests/fixtures/out/ledger/invoice_ledger.csv`. All data is synthetic (supplier IČOs have a wrong check digit).
`tests/generators/test_finance_fixtures.py` compares every file with the tables below, so change a file and
this README together.

All four invoices belong to project FVE-2026-02, are booked in the week 2026-W20 (Mon 2026-05-11) and have
VAT 21%. No planted problems (Task 17.1) in this set.

## Projects
`master/projects.csv`; FVE-2026-02 is the project of the budget and the invoices. The sites are fixed here so
Tasks 6.1 and 7.1 can use them.

| project_code | town | region | lat | lon | radius_m | mwp | has_battery | contract_value | signed_date | construction_start | construction_end | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FVE-2019-02 | Tábor | Jihočeský | 49.434000 | 14.690000 | 400 | 1.20 | false | 24000000.00 | 2019-03-11 | 2019-05-06 | 2020-03-27 | COMPLETED |
| FVE-2025-04 | Strakonice | Jihočeský | 49.282300 | 13.926400 | 600 | 1.00 | false | 22000000.00 |  |  |  | NOT_SIGNED |
| FVE-2026-02 | Písek | Jihočeský | 49.331000 | 14.165000 | 500 | 1.60 | true | 32000000.00 | 2026-01-20 | 2026-03-02 | 2027-01-29 | ACTIVE |

FVE-2025-04 is an offer that was not won (offer date 2025-05-20, no signing or construction dates). Offer dates:
FVE-2019-02 2019-02-14, FVE-2025-04 2025-05-20, FVE-2026-02 2026-01-07.

## Suppliers
`master/suppliers.csv`, sorted by IČO.

| ico | name | category | bank_account | bank_code |
|---|---|---|---|---|
| 20400013 | Solar Novak s.r.o. | PANELS | 1234509876 | 2010 |
| 30550026 | Konstrukce Dvorak a.s. | STRUCTURES | 2876543 | 0100 |
| 41700032 | Zemni Prace Kral s.r.o. | EARTHWORKS | 5551234 | 5500 |
| 63900051 | Invertech Marek s.r.o. | INVERTERS | 3344556 | 2700 |
| 74100069 | Projekce Svoboda s.r.o. | DESIGN | 9900112 | 6210 |

## Invoices
`mailbox/invoices/<ico>_<number>.pdf` (+ `.isdoc` when `isdoc` is yes). `vs` = the number. mtime = issue date.
Invoice 63900051-202600008 is PDF only (no ISDOC); its numbers are in the PDF and in the Money export.

| invoice_id | ico | number | vs | issue_date | due_date | lines | net | vat | gross | isdoc |
|---|---|---|---|---|---|---|---|---|---|---|
| 20400013-202600014 | 20400013 | 202600014 | 202600014 | 2026-05-04 | 2026-05-22 | 1 | 120000.00 | 25200.00 | 145200.00 | yes |
| 30550026-202600003 | 30550026 | 202600003 | 202600003 | 2026-05-06 | 2026-05-27 | 3 | 40000.00 | 8400.00 | 48400.00 | yes |
| 41700032-202600021 | 41700032 | 202600021 | 202600021 | 2026-05-07 | 2026-05-21 | 5 | 27000.00 | 5670.00 | 32670.00 | yes |
| 63900051-202600008 | 63900051 | 202600008 | 202600008 | 2026-05-08 | 2026-05-29 | 2 | 42500.00 | 8925.00 | 51425.00 | no |

Lines (quantity x unit price = net):
- 202600014: 10 x 12000.00 = 120000.00
- 202600003: 8 x 3125.00 = 25000.00; 40 x 250.00 = 10000.00; 1 x 5000.00 = 5000.00
- 202600021: 100 x 120.00 = 12000.00; 50 x 80.00 = 4000.00; 1 x 4000.00 = 4000.00; 30 x 150.00 = 4500.00; 2 x 1250.00 = 2500.00
- 202600008: 1 x 30000.00 = 30000.00; 1 x 12500.00 = 12500.00

## Budget FVE-2026-02
`drive/budgets/FVE-2026-02_budget.xlsx`, sheet `Budget`, header `project_code, category, amount_czk`; mtime = signed
date 2026-01-20. Total 28160000 = 88% of the contract value 32000000; all 10 categories (the project has a battery).

| category | amount_czk |
|---|---|
| PANELS | 7600000 |
| INVERTERS | 2900000 |
| BATTERIES | 3400000 |
| STRUCTURES | 3000000 |
| CABLES | 1400000 |
| EARTHWORKS | 2100000 |
| GRID | 3400000 |
| DESIGN | 1900000 |
| SURVEY | 800000 |
| OTHER | 1660000 |
| TOTAL | 28160000 |

## Money export 2026-W20
`drive/accounting/money_export_2026-W20.csv` (`;`, decimal comma, mtime = Monday 2026-05-11). Columns after
`doc_ref`: supplier_ico = ico, vs, issue_date, due_date as in the invoice table; cost_centre STAVBY, project_code
FVE-2026-02.

| doc_ref | booking_date | category | amount_net_czk | amount_gross_czk |
|---|---|---|---|---|
| 20400013-202600014 | 2026-05-11 | PANELS | 120000,00 | 145200,00 |
| 30550026-202600003 | 2026-05-12 | STRUCTURES | 40000,00 | 48400,00 |
| 41700032-202600021 | 2026-05-13 | EARTHWORKS | 27000,00 | 32670,00 |
| 63900051-202600008 | 2026-05-14 | INVERTERS | 42500,00 | 51425,00 |

## Invoice ledger
`tests/fixtures/out/ledger/invoice_ledger.csv`: one row per invoice with the supplier account and bank code
from the supplier table, `gross_amount` and `pdf_only` (true only for 63900051-202600008).
