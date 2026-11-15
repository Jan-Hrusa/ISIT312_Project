"""Parse fixed-width edition-format ABO statements."""

from processing.bank import (
    BankParseError,
    _account,
    _bank,
    _cents,
    _date,
    _digits,
    _lines,
    _symbol,
    _transaction,
)

WIDTH = 128
DATE_FORMAT = "%d%m%y"
ACCOUNT = slice(3, 19)
OPENING_DATE = slice(39, 45)
OPENING = slice(45, 59)
OPENING_SIGN = 59
CLOSING = slice(60, 74)
CLOSING_SIGN = 74
DEBIT = slice(75, 89)
DEBIT_SIGN = 89
CREDIT = slice(90, 104)
CREDIT_SIGN = 104
NUMBER = slice(105, 108)
STATEMENT_DATE = slice(108, 114)
FILLER = slice(114, 128)
COUNTERPARTY = slice(19, 35)
DOCUMENT = slice(35, 48)
AMOUNT = slice(48, 60)
BOOKING = 60
VS = slice(61, 71)
BANK_AND_KS = slice(71, 81)
SS = slice(81, 91)
VALUE_DATE = slice(91, 97)
NOTE = slice(97, 117)
CHANGE = 117
DATA_KIND = slice(118, 122)
DUE_DATE = slice(122, 128)
DIRECTIONS = {"1": -1, "2": 1, "4": 1, "5": -1}


def _record(line: str, kind: str) -> None:
    if len(line) != WIDTH or not line.isascii() or not line.startswith(kind):
        raise BankParseError(f"invalid GPC {kind} record (expected {WIDTH} ASCII characters)")


def parse(text: str, source_file: str) -> tuple[dict, list[dict]]:
    """Return the statement fields and all its validated transactions."""
    header, *lines = _lines(text)
    _record(header, "074")
    account = _account(header[ACCOUNT])
    statement = {
        "bank": _bank(account, statement_format="GPC"),
        "account": account,
        "statement_no": int(_digits(header[NUMBER], "statement number")),
        "statement_date": _date(header[STATEMENT_DATE], DATE_FORMAT),
        "source_file": source_file,
    }
    opening_date = _date(header[OPENING_DATE], DATE_FORMAT)
    opening = int(_digits(header[OPENING], "opening balance"))
    closing = int(_digits(header[CLOSING], "closing balance"))
    if (
        header[OPENING_SIGN] not in "+-"
        or header[CLOSING_SIGN] not in "+-"
        or header[DEBIT_SIGN] not in "0-"
        or header[CREDIT_SIGN] not in "0-"
        or header[FILLER] != " " * 14
    ):
        raise BankParseError("invalid GPC header sign or filler")
    debits = int(_digits(header[DEBIT], "debit turnover"))
    credits = int(_digits(header[CREDIT], "credit turnover"))
    if header[DEBIT_SIGN] == "-":
        debits = -debits
    if header[CREDIT_SIGN] == "-":
        credits = -credits

    transactions = []
    for line_no, line in enumerate(lines, 1):
        _record(line, "075")
        booking = line[BOOKING]
        if _account(line[ACCOUNT]) != account or booking not in DIRECTIONS or line[CHANGE] not in "0ZCP":
            raise BankParseError(f"invalid account, booking or change code at transaction {line_no}")
        _digits(line[DOCUMENT], "document number")
        _digits(line[DATA_KIND], "data kind")
        _date(line[DUE_DATE], DATE_FORMAT)
        combined = _digits(line[BANK_AND_KS], "bank code and KS")
        amount = _cents(DIRECTIONS[booking] * int(_digits(line[AMOUNT], "amount")))
        transactions.append(
            _transaction(
                statement,
                line_no,
                value_date=_date(line[VALUE_DATE], DATE_FORMAT),
                amount=amount,
                counterparty_account=_account(line[COUNTERPARTY]),
                counterparty_bank_code=combined[2:6],
                vs=_symbol(line[VS]),
                ks=_symbol(combined[6:]),
                ss=_symbol(line[SS]),
                note=line[NOTE].rstrip() or None,
            )
        )
    if sum(row["amount"] for row in transactions if row["amount"] < 0) != -_cents(debits) or sum(
        row["amount"] for row in transactions if row["amount"] > 0
    ) != _cents(credits):
        raise BankParseError("totals mismatch")
    return {
        **statement,
        "opening_date": opening_date,
        "opening_balance": _cents(-opening if header[OPENING_SIGN] == "-" else opening),
        "closing_balance": _cents(-closing if header[CLOSING_SIGN] == "-" else closing),
        "debit_turnover": _cents(debits),
        "credit_turnover": _cents(credits),
    }, transactions
