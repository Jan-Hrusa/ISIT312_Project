# STA statement (MT940)

Source: [Česká spořitelna MultiCash MT940 specification, §§1.2–1.4](https://www.csas.cz/content/dam/cz/csas/www_csas_cz/dokumenty/produkty/podnikatele-a-firmy/ucty-a-platby/internetove-bankovnictvi/produktova-stranka/multicash/MCC_popis_formatu_vypisu_MT940.pdf).
Use CP852 and CRLF. The project filename is `YYNNN_<account>.sta`.

| Record | Fixture layout |
|---|---|
| File preamble | `GIBACZPX 0800`, then `940 N2` |
| `:20:` | Reference containing the account in the six-position prefix and ten-position account format |
| `:25:` | Bank code, slash, account, e.g. `0800/2900112233` |
| `:28C:` | Statement and page number separated by a slash, e.g. `00005/00001` |
| `:60F:` | Opening balance: `C` or `D`, YYMMDD, `CZK`, amount with decimal comma |
| `:61:` | One per transaction: value date YYMMDD, optional posting date MMDD, direction, optional third currency character (`K`), amount with decimal comma, four-character transaction key beginning with `N`, reference |
| `:86:` | Structured transaction details immediately after its `:61:`; may continue on the next physical line |
| `:62F:` | Closing balance in the same format as the opening balance |
| `-}` | Statement terminator |

**For Jan’s review:** Česká spořitelna documents `:28:`. Task 6 explicitly uses
`:28C:`, so Task 6.1 and the planned Task 6 generator use `:28C:` with the bank's
statement/page value structure. Task 16 should parse the project tag.

## Domestic transaction details

The three-digit business code `020` precedes the question-mark-delimited subfields.
Join continuation lines before splitting on `?`. Each subfield starts with its
two-digit identifier. Subfields are optional; a dot is an unused value.

| Subfield | Content | Example |
|---|---|---|
| 00 | Transaction number | `?001` |
| 20 | Constant symbol | `?20KS:308` |
| 21 | Variable symbol | `?21VS:92001` |
| 22 | Specific symbol | `?22SS:1` |
| 23 | Counterparty bank code / account | `?230100/1112233445` |
| 26 | Payment purpose | `?26Příchozí platba` |
| 30 | Counterparty bank code | `?300100` |
| 31 | Counterparty account | `?311112233445` |

When present together, the fixture's subfields 23 and 30/31 identify the same
counterparty. Normalize account and symbol values per the contracts and preserve
the bank code's leading zeros. The ordinal of the `:61:` is the transaction
line number used by the matching TXT file.
