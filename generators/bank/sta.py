"""Write the project's CP852 Česká spořitelna MT940 variant."""

from pathlib import Path

from common import config
from generators.bank.statements import Statement


def _amount(cents: int) -> str:
    whole, fraction = divmod(abs(cents), 100)
    return f"{whole},{fraction:02d}"


def _direction(cents: int) -> str:
    return "D" if cents < 0 else "C"


def write(path: Path, st: Statement) -> None:
    code = config.BANKS[st.bank].bank_code
    records = [
        f"GIBACZPX {code}",
        "940 N2",
        f":20:{st.account.zfill(16)}",
        f":25:{code}/{st.account.zfill(10)}",
        f":28C:{st.number:05d}/00001",
        f":60F:{_direction(st.opening)}{st.opening_day:%y%m%d}CZK{_amount(st.opening)}",
    ]
    for index, item in enumerate(st.movements, start=1):
        day = item.value_date
        purpose = item.detail.replace("?", " ")[:27]
        records.extend(
            (
                f":61:{day:%y%m%d}{day:%m%d}{_direction(item.cents)}K{_amount(item.cents)}NTRFNONREF",
                f":86:020?00{index}?20KS:{item.ks}?21VS:{item.vs}?22SS:{item.ss}"
                f"?23{item.counterparty_bank_code}/{item.counterparty_account}",
                f"?26{purpose}?30{item.counterparty_bank_code}?31{item.counterparty_account}",
            )
        )
    records.extend((f":62F:{_direction(st.closing)}{st.day:%y%m%d}CZK{_amount(st.closing)}", "-}"))
    path.write_bytes(("\r\n".join(records) + "\r\n").encode("cp852"))
