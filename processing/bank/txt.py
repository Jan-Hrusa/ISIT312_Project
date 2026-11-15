"""Parse UTF-8 statement companion text after decoding."""

from processing.bank import BankParseError, _digits, _lines


def parse(text: str) -> dict[int, str]:
    if not text:
        return {}
    details = {}
    for expected, line in enumerate(_lines(text), 1):
        ordinal, separator, detail = line.partition("|")
        if not separator or _digits(ordinal, "TXT line number").lstrip("0") != str(expected):
            raise BankParseError(f"invalid TXT record at line {expected}")
        details[expected] = detail
    return details
