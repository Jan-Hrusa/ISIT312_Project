# Company description

*Summary for the team, based on the company interview (3 Nov 2026). The interview recording and transcript are confidential and are not shared. Do not put the company's name or any real company data in code, data or screenshots.*

## Who the company is
- Czech company that builds solar power plants (FVE) **turnkey**: design (with external designers), building permits, procurement, construction, grid connection and commissioning.
- Also delivers **battery storage** and is developing battery services for grid balancing.
- About **8 employees**; no IT department, everyone looks after their own computer.
- Builds **8–10 plants a year**, typically **1–2 MW** each; construction takes about a year, most of it permits and administration.
- After handover it offers **servicing** (contracted response times), **mandatory inspections** and, as a paid extra, **24/7 monitoring** of the plants.
- Land search is usually done by the investor; the company checks whether a site is suitable (zoning, grid connection capacity).
- Wins projects through **tenders**: it offers a price it can deliver plus its margin.

## How the company handles data today (the spec's six points)
| Point | Today |
|---|---|
| 1. How much data | About 10 years of history; 100–150 photos at the start of each project and continuous photos during construction; roughly 80 bank statement files a month from 4 banks; 30–40 suppliers; offer documents of 80–90 pages; drawings and documents per project. Total storage size not yet known. |
| 2. How it is collected | Banks email a statement file (GPC) every day; suppliers email invoices, often as ISDOC data plus PDF; subcontractors email PDFs and post paper originals with official stamps; the site manager emails photos or uploads them to the shared drive – often a month late. |
| 3. Where it is stored | Google Drive with the same folder structure for every project; accounting in **Money S3**, run by an **external accountant**; emails kept per person, not centrally. No backup against human deletion: Google can restore only 60 days back, and an administrator once nearly deleted everyone's folders. |
| 4. How it is processed | Bank statements imported semi-automatically; matching payments to invoices by *variabilní symbol* is semi-automatic and often needs a person; handover documentation assembled by hand; cost vs budget kept in a spreadsheet that is updated by hand every 2–3 months. |
| 5. Integration | Bank to accounting through data files with a person assisting; **no single project number** across accounting, Drive folders and documents; supplier and project lists split between accounting and Drive; no project management tool. |
| 6. Issues | Photos and documents filed late or missing; once a wrong drawing version was used; no protection against deletion; data quality depends on people having time to file things. |

## What management wants
- First and most important: **an overview of costs and budget per project** – how much a project has cost so far against what it should cost.
- Constraints: cloud is fine (data should stay in the EU); the solution must be **as simple as possible, need no maintenance and not require hiring anyone**. Current spend on software and IT is about 3,000 CZK a month plus about 15,000 CZK a year.
- Anonymised sample files are not needed; we work with synthetic data shaped like theirs. The company agreed to evaluate our solution at the end and give feedback we may quote.

## The company's file types (approved by the lecturer)
| Type | What it is | Used for |
|---|---|---|
| XLS / XLSX | Excel workbook | budgets, schedules, cost tracking |
| DOC / DOCX | Word document | contracts, offers, reports |
| PDF | document | contracts, permits, invoices, signed documents |
| ISDOC | Czech e-invoice standard (XML) | supplier invoices |
| XML | structured data | ISDOC invoices, accounting exports |
| DWG | AutoCAD drawing | site layouts, electrical drawings (v1, v2, final) |
| JPG | photo | construction progress photos (with GPS and date if the phone allows) |
| MP4 | video | site and drone videos (a few minutes) |
| TXT | text | supplementary information from the banks |
| KPC | ABO payment orders (Czech banking format) | paying suppliers |
| GPC | ABO bank statement (Czech banking format) | daily/monthly statements |
| STA | MT940 bank statement (SWIFT format) | statements from one bank |

Banks: Raiffeisenbank (primary account), UniCredit, Česká spořitelna, Komerční banka.
