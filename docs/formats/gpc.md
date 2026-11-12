# GPC statement (ABO)

Source: [Raiffeisenbank ABO and Gemini specification, §1.2](https://www.rb.cz/attachments/elektronicke-bankovnictvi/27804-Popis-datove-struktury-ABO-a-Gemini-formatu-A.pdf).

The project uses the edition format (account digits in their ordinary order). The name is
`YYNNN_<account>_CZK.gpc`. Use ASCII and CRLF, including after the last record. Each
`074` or `075` record is 128 bytes excluding CRLF. A statement has one `074` followed
by zero or more `075` records. The project supplies supplementary detail via TXT.
Starts below are one-based. Pad numeric fields on the left with zeros and text on the
right with spaces. Normalize parsed accounts and symbols per the contracts. All amounts
are integer haléře (1 CZK = 100 haléře).

## 074 statement header

| Field | Start | Length | Type | Example |
|---|---:|---:|---|---|
| Record type | 1 | 3 | Literal | `074` |
| Account | 4 | 16 | Digits | `0000002101234567` |
| Short client name | 20 | 20 | Text | `Synthetic Solar` (space-padded) |
| Opening balance date | 40 | 6 | DDMMYY | `200526` |
| Opening balance | 46 | 14 | Digits | `00000040000000` |
| Opening sign | 60 | 1 | Sign | `+` |
| Closing balance | 61 | 14 | Digits | `00000022230500` |
| Closing sign | 75 | 1 | Sign | `+` |
| Debit turnover | 76 | 14 | Digits | `00000027769500` |
| Debit turnover sign | 90 | 1 | `0` or `-` | `0` |
| Credit turnover | 91 | 14 | Digits | `00000010000000` |
| Credit turnover sign | 105 | 1 | `0` or `-` | `0` |
| Statement number | 106 | 3 | Digits | `141` |
| Statement date | 109 | 6 | DDMMYY | `210526` |
| Filler | 115 | 14 | Spaces | 14 ASCII spaces |

## 075 transaction

| Field | Start | Length | Type | Example |
|---|---:|---:|---|---|
| Record type | 1 | 3 | Literal | `075` |
| Account | 4 | 16 | Digits | `0000002101234567` |
| Counterparty account | 20 | 16 | Digits | `0000001234509876` |
| Document number | 36 | 13 | Digits | `0000000000001` |
| Amount magnitude | 49 | 12 | Digits | `000014520000` |
| Booking code | 61 | 1 | Digit | `1` |
| VS | 62 | 10 | Digits | `0202600014` |
| Combined bank code and KS | 72 | 10 | Digits | `0020100308` |
| SS | 82 | 10 | Digits | `0000000000` |
| Value date | 92 | 6 | DDMMYY | `210526` |
| Supplementary note | 98 | 20 | Text | `Solar Novak s.r.o.` (space-padded) |
| Change code | 118 | 1 | `0`, `Z`, `C`, or `P` | `0` |
| Data kind | 119 | 4 | Currency code and bank operation code | `1101` in the synthetic sample |
| Due / credit date | 123 | 6 | DDMMYY | `210526` |

Booking codes are `1` debit, `2` credit, `4` debit reversal, and `5` credit reversal.
In the combined field the two leading positions are zero in the fixtures, followed by
the bank code at positions 74–77 and KS at positions 78–81. All-zero symbol fields
represent missing symbols in these fixtures. Use the one-based ordinal of the `075`
within its statement for TXT and transaction IDs. The data-kind example uses the
domestic payment code documented in the linked Air Bank ABO export specification.
Raiffeisenbank defines the field structure and leaves the operation code to its bank
code list. This field is outside the clean transaction schema.
