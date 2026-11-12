"""Write domestic CZK payment runs in the project ABO layout."""

from dataclasses import dataclass
from datetime import date
from itertools import groupby
from pathlib import Path

from common import config


@dataclass(frozen=True)
class Order:
    bank: str
    run_date: date
    due_date: date
    cents: int
    counterparty_account: str
    counterparty_bank_code: str
    vs: str
    invoice_id: str
    ks: str = "308"


def validate_vs(order: Order) -> None:
    if not order.vs:
        raise ValueError(f"No approved raw KPC encoding for missing VS on invoice {order.invoice_id}")
    if not order.vs.isascii() or not order.vs.isdecimal() or len(order.vs) > 10:
        raise ValueError(f"Invalid KPC VS on invoice {order.invoice_id}: {order.vs!r}")


def write(path: Path, run: list[Order]) -> None:
    first = run[0]
    bank = config.BANKS[first.bank]
    records = [
        f"UHL1{first.run_date:%d%m%y}{'SYNTHETIC SOLAR':20}1234567890001999111111222222",
        f"1 1501 111111 {bank.bank_code}",
    ]
    for due, group in groupby(run, key=lambda item: item.due_date):
        items = list(group)
        total = sum(item.cents for item in items)
        if not 0 < total < 10**14:
            raise ValueError(f"KPC group total exceeds format limits: {total}")
        records.append(f"2 {bank.account} {total} {due:%d%m%y}")
        for item in items:
            validate_vs(item)
            if not 0 < item.cents < 10**12:
                raise ValueError(f"KPC item amount exceeds format limits: {item.cents}")
            records.append(
                f"{item.counterparty_account} {item.cents} {item.vs} "
                f"{item.counterparty_bank_code}{item.ks.zfill(4)}  AV:Invoice "
                f"{item.invoice_id.rsplit('-', 1)[-1]}"
            )
        records.append("3 +")
    records.append("5 +")
    path.write_bytes(("\r\n".join(records) + "\r\n").encode("ascii"))
