"""Parse the project MultiCash MT940 statement layout."""

import re
from decimal import Decimal

from common import config
from processing.bank import BankParseError, _account, _bank, _date, _lines, _symbol, _transaction

DATE_FORMAT = "%y%m%d"
MONEY = r"[0-9]{1,12},[0-9]{0,2}"
BALANCE = re.compile(rf"([CD])([0-9]{{6}}){config.CURRENCY}({MONEY})")
ENTRY = re.compile(rf"([0-9]{{6}})([0-9]{{4}})?(RC|RD|C|D)K?({MONEY})N[A-Z0-9]{{3}}.+")
ACCOUNT = re.compile(r"([0-9]{4})/([0-9]+)")
NUMBER = re.compile(r":28C?:([0-9]{1,5})/([0-9]{1,5})")
SUBFIELD = re.compile(r"\?([0-9]{2})")
DEBITS = {"D", "RC"}


def _amount(direction: str, value: str) -> Decimal:
    amount = Decimal(value.replace(",", ".")).quantize(Decimal("0.01"))
    return -amount if direction in DEBITS else amount


def _balance(line: str, tag: str):
    match = BALANCE.fullmatch(line.removeprefix(tag)) if line.startswith(tag) else None
    if not match:
        raise BankParseError(f"invalid STA {tag} balance")
    direction, day, amount = match.groups()
    return _date(day, DATE_FORMAT), _amount(direction, amount)


def _details(text: str) -> dict:
    parts = SUBFIELD.split(text)
    if parts[0] != "020":
        raise BankParseError("invalid STA :86: business code or subfield")
    fields = dict(zip(parts[1::2], parts[2::2], strict=True))
    if len(fields) != len(parts[1::2]):
        raise BankParseError("duplicate STA :86: subfield")
    bank_code = fields.get("30", "").strip()
    account = fields.get("31", "").strip()
    combined = fields.get("23", "").strip()
    if combined not in ("", "."):
        match = ACCOUNT.fullmatch(combined)
        if not match:
            raise BankParseError("invalid STA :86: counterparty")
        combined_bank, combined_account = match.groups()
        if bank_code not in ("", ".", combined_bank) or (
            account not in ("", ".") and _account(account) != _account(combined_account)
        ):
            raise BankParseError("inconsistent STA :86: counterparty")
        bank_code, account = combined_bank, combined_account
    if bank_code not in ("", ".") and not re.fullmatch(r"[0-9]{4}", bank_code):
        raise BankParseError("invalid STA :86: bank code")

    def symbol(key: str, prefix: str) -> str | None:
        value = fields.get(key, "").removeprefix(prefix).strip()
        return _symbol(value) if value != "." else None

    note = fields.get("26", "").strip()
    return {
        "counterparty_account": _account(account) if account not in ("", ".") else None,
        "counterparty_bank_code": bank_code if bank_code not in ("", ".") else None,
        "vs": symbol("21", "VS:"),
        "ks": symbol("20", "KS:"),
        "ss": symbol("22", "SS:"),
        "note": note if note not in ("", ".") else None,
    }


def parse(text: str, source_file: str) -> tuple[dict, list[dict]]:
    """Return the statement fields and all its validated transactions."""
    lines = _lines(text)
    if len(lines) < 8 or lines[1] != "940 N2" or lines[-1] != "-}":
        raise BankParseError("invalid STA preamble or terminator")
    match = ACCOUNT.fullmatch(lines[3].removeprefix(":25:")) if lines[3].startswith(":25:") else None
    number = NUMBER.fullmatch(lines[4])
    if not match or not number:
        raise BankParseError("invalid STA account or statement number")
    bank_code, account = match.groups()
    account = _account(account)
    bank = _bank(account, statement_format="STA", bank_code=bank_code)
    if lines[0] != f"GIBACZPX {bank_code}" or lines[2] != f":20:{account.zfill(16)}":
        raise BankParseError("invalid STA preamble or account reference")
    opening_date, opening = _balance(lines[5], ":60F:")
    statement_date, closing = _balance(lines[-2], ":62F:")
    statement = {
        "bank": bank,
        "account": account,
        "statement_no": int(number[1]),
        "statement_date": statement_date,
        "source_file": source_file,
    }
    transactions = []
    index = 6
    end = len(lines) - 2
    while index < end:
        entry = lines[index]
        movement = ENTRY.fullmatch(entry.removeprefix(":61:")) if entry.startswith(":61:") else None
        if not movement or index + 1 >= end or not lines[index + 1].startswith(":86:"):
            raise BankParseError("invalid STA :61: or missing :86:")
        value_date, posting_date, direction, amount = movement.groups()
        day = _date(value_date, DATE_FORMAT)
        if posting_date:
            _date(value_date[:2] + posting_date, DATE_FORMAT)
        start = index + 1
        index += 2
        while index < end and not lines[index].startswith(":"):
            index += 1
        details = _details("".join(lines[start:index]).removeprefix(":86:"))
        transactions.append(
            _transaction(
                statement,
                len(transactions) + 1,
                value_date=day,
                amount=_amount(direction, amount),
                **details,
            )
        )
    if opening + sum(row["amount"] for row in transactions) != closing:
        raise BankParseError("totals mismatch")
    return {
        **statement,
        "opening_date": opening_date,
        "opening_balance": opening,
        "closing_balance": closing,
    }, transactions
