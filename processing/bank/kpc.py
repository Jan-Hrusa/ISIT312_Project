"""Parse domestic CZK ABO payment orders."""

import re
from datetime import date

from processing.bank import BankParseError, _account, _bank, _cents, _date, _lines, _symbol

DATE_FORMAT = "%d%m%y"
HEADER = re.compile(r"UHL1([0-9]{6})([ -~]{20})[0-9]{28}")
FILE_NAME = re.compile(r"PO_([0-9]{4}-[0-9]{2}-[0-9]{2})_([A-Z]+)")
BATCH = re.compile(r"1 1501 [0-9]{6} ([0-9]{4})")
GROUP = re.compile(r"2 ([0-9]+) ([0-9]{1,14}) ([0-9]{6})")
ITEM = re.compile(r"([0-9]+) ([0-9]{1,12}) ([0-9]{1,10}) ([0-9]{4})([0-9]{4})(?: ([0-9]{0,10})(?: .*)?)?")


def parse(text: str, base_name: str, source_file: str) -> list[dict]:
    """Return the validated orders, numbered across all groups."""
    lines = _lines(text)
    if len(lines) < 6 or not text.isascii() or lines[-1] != "5 +":
        raise BankParseError("invalid KPC file or batch terminator")
    header = HEADER.fullmatch(lines[0])
    batch = BATCH.fullmatch(lines[1])
    if not batch or not (header or lines[0] == "UHL1"):
        raise BankParseError("invalid KPC header")
    if header:
        order_date = _date(header[1], DATE_FORMAT)
    else:
        name = FILE_NAME.fullmatch(base_name)
        if not name:
            raise BankParseError("short KPC header requires a dated filename")
        try:
            order_date = date.fromisoformat(name[1])
        except ValueError as exc:
            raise BankParseError("invalid KPC filename date") from exc

    orders = []
    group = None
    for line in lines[2:-1]:
        if group is None:
            group = GROUP.fullmatch(line)
            if not group:
                raise BankParseError("invalid KPC group header")
            account = _account(group[1])
            bank = _bank(account, bank_code=batch[1])
            due_date = _date(group[3], DATE_FORMAT)
            total = 0
        elif line == "3 +":
            if total <= 0 or total != int(group[2]):
                raise BankParseError("totals mismatch")
            group = None
        else:
            item = ITEM.fullmatch(line)
            if not item or int(item[2]) == 0:
                raise BankParseError("invalid KPC item")
            amount = int(item[2])
            total += amount
            orders.append(
                {
                    "order_id": f"{base_name}-{len(orders) + 1:03d}",
                    "bank": bank,
                    "account": account,
                    "order_date": order_date,
                    "due_date": due_date,
                    "amount": _cents(amount),
                    "counterparty_account": _account(item[1]),
                    "counterparty_bank_code": item[4],
                    "vs": _symbol(item[3]),
                    "ks": _symbol(item[5]),
                    "ss": _symbol(item[6] or ""),
                    "source_file": source_file,
                }
            )
    if group is not None:
        raise BankParseError("missing KPC group terminator")
    return orders
