# KPC payment orders (ABO)

Sources: [Air Bank ABO import, pp. 1–4](https://www.airbank.cz/file-download/technicke-pozadavky-a-specifikace-hromadnych-plateb-a-export-vypisu)
and [Raiffeisenbank ABO, §1.1](https://www.rb.cz/attachments/elektronicke-bankovnictvi/27804-Popis-datove-struktury-ABO-a-Gemini-formatu-A.pdf).
Use ASCII and CRLF. The project filename `PO_YYYY-MM-DD_<BANK>.kpc` gives the
order-run date and payer bank. The RB sample uses the RB batch bank code and AV
syntax. Both references describe the same single-payer group and item structure.

| Record | Fields in order |
|---|---|
| File header | `UHL1` followed for RB by creation date DDMMYY (6), uppercase client name (20, space-padded), client ID (10), interval bounds (3 each), and processing fields (6 each) |
| Batch header | `1`, `1501` (domestic CZK payments), six-digit batch number (`111111` for RB), four-digit payer bank code (`5500` for RB) |
| Single-payer group header | `2`, payer account, sum of item amounts in haléře, due date DDMMYY |
| Item | Recipient account, amount in haléře, VS, four-digit recipient bank code immediately followed by four-digit KS, optional SS, optional message |
| Group end | `3 +` |
| Batch end | `5 +` |

Fields use one ASCII space as the separator. An empty SS before an RB AV message
leaves two consecutive spaces before `AV:`. The project uses prefix-free
accounts. The group total is 1–14 digits, an RB item amount is 1–12 digits,
VS is 1–10 digits (a missing VS is written as `0`, which parsers read as NULL), and SS is 0–10 digits. Amounts are positive integers in
haléře. The group due date applies to every item and can differ from the
order-run date. A payment run can contain multiple groups. Item numbering
starts at one and counts only payment items across the file.

The RB fixture header uses the published default values for the unused client ID,
interval bounds, and processing fields. Air Bank's importer also shows a short
`UHL1` header in its example.

Example item: `1234509876 14520000 202600014 20100308  AV:Invoice 202600014`.
