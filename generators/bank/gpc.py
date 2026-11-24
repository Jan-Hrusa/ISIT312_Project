"""Write ASCII ABO statements using the Task 6.1 edition layout."""

from pathlib import Path
from unicodedata import normalize

from generators.bank.statements import Statement


def _digits(value: str | int, width: int) -> str:
    token = str(value) or "0"
    if len(token) > width or not token.isascii() or not token.isdecimal():
        raise ValueError(f"Invalid GPC numeric field ({width} digits): {token!r}")
    return token.zfill(width)


def _sign(value: int) -> str:
    return "-" if value < 0 else "+"


def write(path: Path, st: Statement) -> None:
    debits = -sum(item.cents for item in st.movements if item.cents < 0)
    credits = sum(item.cents for item in st.movements if item.cents > 0)
    account = _digits(st.account, 16)
    header = (
        f"074{account}{'Synthetic Solar':20}{st.opening_day:%d%m%y}"
        f"{_digits(abs(st.opening), 14)}{_sign(st.opening)}"
        f"{_digits(abs(st.closing), 14)}{_sign(st.closing)}"
        f"{_digits(debits, 14)}0{_digits(credits, 14)}0{_digits(st.number, 3)}{st.day:%d%m%y}" + " " * 14
    )
    records = [header]
    for index, item in enumerate(st.movements, start=1):
        note = normalize("NFKD", item.detail).encode("ascii", "ignore").decode("ascii")
        booking = "1" if item.cents < 0 else "2"
        record = (
            f"075{account}{_digits(item.counterparty_account, 16)}{_digits(index, 13)}"
            f"{_digits(abs(item.cents), 12)}{booking}{_digits(item.vs, 10)}"
            f"00{_digits(item.counterparty_bank_code, 4)}{_digits(item.ks, 4)}{_digits(item.ss, 10)}"
            f"{item.value_date:%d%m%y}{note[:20]:20}01101{item.value_date:%d%m%y}"
        )
        records.append(record[:-2] if item.malformed else record)
    path.write_bytes(("\r\n".join(records) + "\r\n").encode("ascii"))
