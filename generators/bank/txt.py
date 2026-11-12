"""Write UTF-8 transaction details in statement order."""

from pathlib import Path

from generators.bank.statements import Statement


def write(path: Path, st: Statement) -> None:
    lines = (f"{index}|{item.detail}\n" for index, item in enumerate(st.movements, start=1))
    path.write_bytes("".join(lines).encode("utf-8"))
