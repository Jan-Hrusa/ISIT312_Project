# **Data Warehouse Design — Task 10.1**



### Overview



This directory contains the conceptual and logical data warehouse designs for the ISIT312 solar-farm construction data lake project. The warehouse uses a fact constellation consisting of four fact tables and five shared dimension tables. Its purpose is to support project budget monitoring, supplier spending analysis, invoice tracking, and payment reconciliation.



The designs follow the warehouse requirements in `docs/contracts.md` Section 8 and the reporting requirements in `docs/dashboard-design.md`.



### Fact Tables



###### 1\. fact\_budget\_line



Grain: One budget record per project and cost category.



Measure: `budget\_amount`.



This fact stores the budget allocated to each cost category within a project. It uses the project and cost-category dimensions, together with a date reference representing the project's signing date. It supports dashboard View 2, which compares planned budgets against actual invoiced costs by category.



###### 2\. fact\_invoice\_line



Grain: One invoice line.



Measures: `amount\_net`, `vat\_amount`, and `amount\_gross`.



This fact records invoice-line expenditure, including its project, supplier, cost category, issue date, due date, payment status, and lateness. It supports budget-versus-actual reporting, supplier expenditure analysis, invoice drill-down, and comparisons across projects.



###### 3\. fact\_payment



Grain: One bank debit representing a supplier payment.



Measures: `amount` and `days\_late`.



This fact records supplier payments from bank statements. It links payments to projects, suppliers, bank accounts, and value dates. The `invoice\_id` attribute may be NULL when a payment cannot be matched to an invoice. It supports payment tracking and reconciliation analysis.



###### 4\. fact\_payment\_order



Grain: One KPC payment-order item.



Measures: `amount` and `cleared` (0 or 1).



This fact records payment instructions and whether they have cleared. It connects each payment-order item to its project, supplier, bank account, order date, and due date. It supports analysis of outstanding payment instructions and payment reconciliation.



###### Shared Dimensions



The warehouse contains five shared dimensions:



\- `dim\_project` — Project details and project-to-region analysis.

\- `dim\_supplier` — Supplier details and supplier-category analysis.

\- `dim\_cost\_category` — Cost categories and their higher-level groups.

\- `dim\_date` — Calendar analysis by day, month, quarter, and year.

\- `dim\_bank\_account` — Bank account and bank-level analysis.



The date dimension is reused in different roles, including invoice issue date, invoice due date, payment value date, payment-order date, and project signing date.



Unknown project and supplier records use surrogate key `-1` to preserve facts whose corresponding dimension members cannot be identified.



###### Dashboard Support



The warehouse supports the five dashboard views described in `docs/dashboard-design.md`:



| View | Purpose | Main Warehouse Tables |

|---|---|---|

| V1 | Project list | `dim\_project` |

| V2 | Budget versus actual by category | `fact\_budget\_line`, `fact\_invoice\_line`, `dim\_project`, `dim\_cost\_category` |

| V3 | Cost category to suppliers | `fact\_invoice\_line`, `dim\_cost\_category`, `dim\_supplier` |

| V4 | Supplier to invoices | `fact\_invoice\_line`, `dim\_supplier` |

| V5 | Across-project analysis | `fact\_budget\_line`, `fact\_invoice\_line`, `dim\_project`, `dim\_date` |



Actual spending is calculated using `fact\_invoice\_line.amount\_net`. Budget and actual expenditure can be compared through their shared project and cost-category dimensions. This is a drill-across operation, with each fact aggregated to a common grain before comparison.



Invoice issue dates are used for invoice spending trends.



###### Planned Physical Storage



The Hive warehouse database is `fve\_dw`. The planned storage format is external ORC tables under `/lake/dw/<table>`.



The planned fact-table partitions are:



| Fact Table | Partition Columns |

|---|---|

| `fact\_budget\_line` | `signed\_year` |

| `fact\_invoice\_line` | `issue\_year` |

| `fact\_payment` | `pay\_year`, `pay\_month` |

| `fact\_payment\_order` | `order\_year` |



The date dimension covers 2016-01-01 through 2026-12-31.



###### Design Files



\- `conceptual.uxf` — Editable UMLet conceptual diagram.

\- `conceptual.pdf` — Exported conceptual diagram.

\- `logical.uxf` — Editable UMLet logical diagram with keys and data types.

\- `logical.pdf` — Exported logical diagram.



The conceptual model describes the fact constellation, measures, dimensions, and analytical hierarchies. The logical model adds primary keys, foreign keys, data types, and role-playing date relationships.



#### References



\- `docs/contracts.md` — Data contracts and warehouse schema requirements.

\- `docs/dashboard-design.md` — Dashboard views and reporting requirements.

\- `02 Project description.pdf` — Section 5.4, Data Warehouse Design.

