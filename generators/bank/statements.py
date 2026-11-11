"""Group bank movements into dated statements with running balances."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from common import config

DAY = timedelta(days=1)


@dataclass(frozen=True)
class Movement:
    bank: str
    value_date: date
    cents: int
    counterparty_account: str
    counterparty_bank_code: str
    vs: str
    detail: str
    invoice_id: str = ""
    ks: str = ""
    ss: str = ""
    malformed: bool = False


@dataclass(frozen=True)
class Statement:
    bank: str
    account: str
    number: int
    day: date
    opening_day: date
    opening: int
    closing: int
    movements: tuple[Movement, ...]

    @property
    def basename(self) -> str:
        stem = f"{self.day:%y}{self.number:03d}_{self.account}"
        return stem + "_CZK" if config.BANKS[self.bank].format == "GPC" else stem


def _month_end(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1) - DAY


def build(debits, credits, banks) -> list[Statement]:
    start, end = config.DATA_START, config.DATA_END
    grouped = defaultdict(list)
    for movement in (*debits, *credits):
        day = movement.value_date
        if not start <= day <= end:
            raise ValueError(f"Movement outside dataset: {movement}")
        bank = banks[movement.bank]
        statement_day = day if bank.frequency == "daily" else min(_month_end(day), end)
        grouped[movement.bank, statement_day].append(movement)

    statements = []
    for code, bank in banks.items():
        daily = bank.frequency == "daily"
        day = start if daily else min(_month_end(start), end)
        previous = start - DAY
        balance = number = 0
        while day <= end:
            number = number + 1 if day.year == previous.year else 1
            items = tuple(
                sorted(
                    grouped[code, day],
                    key=lambda item: (item.value_date, item.invoice_id, item.vs, item.cents),
                )
            )
            closing = balance + sum(item.cents for item in items)
            statements.append(Statement(code, bank.account, number, day, previous, balance, closing, items))
            previous, balance = day, closing
            if day == end:
                break
            day = day + DAY if daily else min(_month_end(day + DAY), end)
    return statements
