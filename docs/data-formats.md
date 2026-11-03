# Data formats

The lecturer approved these types. Confirmed in the interview: accounting in Money S3 (external accountant);
banks Raiffeisenbank (primary, GPC daily), UniCredit, Česká spořitelna, Komerční banka; one bank delivers MT940 (STA).

| Type | What it is | Structure | Likely use at the company |
|---|---|---|---|
| XLS / XLSX | Excel workbook | Structured (tables) | Budgets, schedules, material lists, reports |
| DOC / DOCX | Word document | Unstructured text | Contracts, technical reports, permits |
| PDF | Document | Unstructured (text or scanned images) | Contracts, permits, datasheets, signed documents |
| ISDOC | Czech national e-invoice standard (XML, by ICT Unie); `.isdocx` is a zipped variant with attachments | Semi-structured (XML schema) | Issued and received invoices |
| XML | Generic XML | Semi-structured | Exports from accounting/ERP, bank statements (Czech banks also offer an XML statement format) |
| DWG | AutoCAD drawing | Binary | Site layouts, electrical and construction drawings |
| JPG (and other images) | Photo | Binary + EXIF metadata (time, GPS, camera) | Site and construction progress photos |
| MP4 (and other video) | Video | Binary + metadata | Site inspections, drone footage |
| TXT | Plain text | Unstructured or ad-hoc structured | Logs, notes, exports |
| KPC | ABO format **domestic payment orders** (Czech banking standard, originally by Komerční banka) | Fixed-width text, ASCII, CRLF | Exported from accounting software (e.g. Pohoda) and uploaded to internet banking to pay suppliers |
| GPC | ABO format **bank statement** | Fixed-width text records: 074 statement header, 075 transaction, 078/079 transaction details; file name `YYNNN_<account>_<currency>.GPC` | Downloaded from the bank and imported into accounting |
| STA | **MT940** (SWIFT) bank statement | Tagged text fields (`:20:`, `:25:`, `:28:`, `:60F:` opening balance, `:61:` transaction, `:86:` details, `:62F:` closing balance); Czech banks use CP852/ANSI encoding | Same as GPC, from a bank or service that exports MT940 |

## Why this matters for the design
- KPC, GPC, STA, ISDOC and part of the XML are **structured financial data** that can be joined: invoice
  (ISDOC) -> payment order (KPC) -> bank statement line (GPC/STA), typically linked by the Czech *variabilní symbol*
  (payment reference). This suits a Hive warehouse (fact tables for invoices and payments; dimensions for supplier,
  project, date).
- DOC, PDF and TXT need text extraction before they can be queried; DWG, JPG and MP4 are stored as raw files with
  only their metadata in tables.
- Many small files (photos, PDFs) are a known HDFS problem (NameNode memory), which is a point for the
  architecture and tool-fit sections.
- Bank files contain account numbers and personal names: anonymise them before they leave the company.

## Format specifications (sources)
- Raiffeisenbank, ABO and Gemini data structure: https://www.rb.cz/attachments/elektronicke-bankovnictvi/27804-Popis-datove-struktury-ABO-a-Gemini-formatu-A.pdf
- Raiffeisenbank, MT940 data structure (.STA): https://www.rb.cz/attachments/elektronicke-bankovnictvi/17372_RB_RFB-MT940-Data-structure_ENG_nahled.pdf
- Air Bank, ABO import (.kpc) and statement export: https://www.airbank.cz/file-download/technicke-pozadavky-a-specifikace-hromadnych-plateb-a-export-vypisu
- POHODA portal, homebanking with GPC and KPC: https://portal.pohoda.cz/dane-ucetnictvi-mzdy/ucetnictvi/spravujte-sve-bankovni-pohyby-diky-homebankingu/
- ČSOB, statements in the MT940 format (.STA): https://www.csob.cz/documents/10710/4165543/mt940-statements-en.pdf
