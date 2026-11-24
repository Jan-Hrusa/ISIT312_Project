# Bank fixtures (Task 6.1)

Paths below are relative to `tests/fixtures/sources/`. All data is synthetic.
The four invoice rows and supplier details come from Task 5.1 commit `7c6f873`.
All four invoices belong to `FVE-2026-02`. The KPC run is on 19 May 2026,
with a common payment due date of 21 May. The invoice due dates remain as
recorded in the ledger.

## Valid RB GPC

`mailbox/bank/RB/26141_2101234567_CZK.gpc`, business date 2026-05-21.
Six ASCII records of 128 bytes each (excluding CRLF): one `074` and five
`075`. Header account `2101234567`, statement 141. Opening balance on
2026-05-20 is CZK 400000.00. Debit turnover is CZK 277695.00 and credit
turnover is CZK 100000.00. Closing balance is CZK 222305.00.

| Line | Invoice ID | VS | Counterparty account | Bank | Signed CZK | Invoice due |
|---:|---|---|---|---|---:|---|
| 1 | 20400013-202600014 | 202600014 | 1234509876 | 2010 | -145200.00 | 2026-05-22 |
| 2 | 30550026-202600003 | 202600003 | 2876543 | 0100 | -48400.00 | 2026-05-27 |
| 3 | 41700032-202600021 | 202600021 | 5551234 | 5500 | -32670.00 | 2026-05-21 |
| 4 | 63900051-202600008 | 202600008 | 3344556 | 2700 | -51425.00 | 2026-05-29 |
| 5 | — | 91001 | 7788990011 | 0800 | +100000.00 | — |

All five value dates are 2026-05-21. The first debit has document number 1,
booking code `1`, combined field `0020100308`, an absent SS and the note
`Solar Novak s.r.o.`. Its TXT begins
`1|Solar Novak s.r.o. invoice 202600014`. TXT line 5 is `5|Investor milestone`.

## Broken RB GPC

`mailbox/bank/RB/26142_2101234567_CZK.gpc`, business date 2026-05-22.
One 128-byte `074` and one 126-byte `075`, excluding CRLF. The header
opens at CZK 222305.00 and closes at CZK 247305.00. The only transaction
is a CZK 25000.00 investor credit (code `2`, VS `91002`). Its final date
field retains only `2205` after the last two characters are removed.
The TXT has one line, `1|Investor milestone`.

## CS STA

`mailbox/bank/CS/26005_2900112233.sta`, business date 2026-05-31.
CP852 with CRLF. The fixture has 17 physical lines, including three
`:61:` records and their three `:86:` records with one continuation each.
Account `0800/2900112233`, statement tag `:28:00005/00001`.
Opening balance is CZK 50000.00 on 2026-04-30. Closing balance is
CZK 54499.25 on 2026-05-31.

| Line | Value date | Signed CZK | VS | KS | SS | Counterparty |
|---:|---|---:|---|---|---|---|
| 1 | 2026-05-04 | +10000.00 | 92001 | 308 | 1 | 0100/1112233445 |
| 2 | 2026-05-12 | -2500.50 | 92002 | 308 | 2 | 2700/2223344556 |
| 3 | 2026-05-25 | -3000.25 | 92003 | 308 | 3 | 5500/3334455667 |

The first transaction's `?26` purpose is `Příchozí platba`. Its TXT
is UTF-8 with three lines, starting with `1|Příchozí platba`.

## RB KPC

`drive/payments/PO_2026-05-19_RB.kpc`, business date 2026-05-19.
Nine ASCII records with CRLF: file header, batch header, group header,
four items, group end and batch end. The batch is `1 1501 111111 5500`;
the 58-byte `UHL1` header includes creation date `190526`;
the group is `2 2101234567 27769500 210526`. Items match valid GPC
debits 1–4 by recipient account, bank code, VS, amount and payment date.
Item 1 has KS `0308`, blank SS and message `AV:Invoice 202600014`.

Every fixture has a business-date entry in `tests/fixtures/mtimes_bank.csv`.
