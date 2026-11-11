import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from tests.fixtures.make_sources import read_mtimes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SOURCES = FIXTURES / "sources"


def _crlf_records(path, encoding):
    records = path.read_bytes().decode(encoding).split("\r\n")
    assert records.pop() == ""
    assert all("\r" not in record and "\n" not in record for record in records)
    return records


def _gpc_debit_key(item):
    return (
        item[19:35].lstrip("0"),
        item[73:77],
        item[61:71].lstrip("0"),
        int(item[48:60]),
        item[91:97],
    )


def _check_rb(valid, broken):
    header, *items = _crlf_records(valid, "ascii")
    assert len(items) == 5
    assert all(len(record) == 128 for record in [header, *items])
    assert header[:19] == "0740000002101234567"
    assert header[105:] == "141210526" + " " * 14
    assert all(item[:19] == "0750000002101234567" for item in items)
    assert [item[60] for item in items] == ["1", "1", "1", "1", "2"]
    assert items[0][35:48] == "0000000000001"
    assert items[0][71:91] == "00201003080000000000"
    assert items[0][97:117].rstrip() == "Solar Novak s.r.o."
    assert items[4][61:71].lstrip("0") == "91001"
    assert items[4][19:35].lstrip("0") == "7788990011"
    assert items[4][73:77] == "0800"
    debit_total = sum(int(item[48:60]) for item in items[:4])
    credit_total = int(items[4][48:60])
    assert int(header[75:89]) == debit_total == 27769500
    assert int(header[90:104]) == credit_total == 10000000
    assert header[59] == header[74] == "+"
    assert header[89] == header[104] == "0"
    assert int(header[45:59]) == 40000000
    closing = int(header[60:74])
    assert closing == 40000000 - debit_total + credit_total == 22230500

    broken_header, short_item = _crlf_records(broken, "ascii")
    assert [len(broken_header), len(short_item)] == [128, 126]
    assert broken_header.startswith("074") and short_item.startswith("075")
    assert broken_header[105:114] == "142220526"
    assert short_item[60:71] == "20000091002"
    assert short_item[122:] == "2205"
    assert int(broken_header[45:59]) == closing
    assert int(broken_header[75:89]) == 0
    assert int(broken_header[90:104]) == int(short_item[48:60]) == 2500000
    assert int(broken_header[60:74]) == closing + 2500000 == 24730500
    return [_gpc_debit_key(item) for item in items[:4]]


def _check_sta(path):
    records = _crlf_records(path, "cp852")
    assert len(records) == 17
    assert records[:6] == [
        "GIBACZPX 0800",
        "940 N2",
        ":20:0000002900112233",
        ":25:0800/2900112233",
        ":28C:00005/00001",
        ":60F:C260430CZK50000,00",
    ]
    assert records[-2:] == [":62F:C260531CZK54499,25", "-}"]
    amounts = []
    for index, (value_date, counterparty) in enumerate(
        [("260504", "0100/1112233445"), ("260512", "2700/2223344556"), ("260525", "5500/3334455667")],
        start=1,
    ):
        start = 6 + (index - 1) * 3
        item, detail, continuation = records[start : start + 3]
        match = re.fullmatch(r":61:(\d{6})\d{4}([CD])K(\d+,\d{2})NTRFNONREF", item)
        assert match is not None
        assert match[1] == value_date
        amount = Decimal(match[3].replace(",", "."))
        amounts.append(amount if match[2] == "C" else -amount)
        assert detail.startswith(":86:020?")
        subfields = {part[:2]: part[2:] for part in (detail + continuation).split("?")[1:]}
        assert subfields["00"] == str(index)
        assert subfields["20"] == "KS:308"
        assert subfields["21"] == f"VS:{92000 + index}"
        assert subfields["22"] == f"SS:{index}"
        assert subfields["23"] == counterparty == f"{subfields['30']}/{subfields['31']}"
        if index == 1:
            assert subfields["26"] == "Příchozí platba"
    assert amounts == [Decimal("10000.00"), Decimal("-2500.50"), Decimal("-3000.25")]
    assert Decimal("50000.00") + sum(amounts) == Decimal("54499.25")


def _check_kpc(path, debits):
    uhl, batch, group, *items, group_end, batch_end = _crlf_records(path, "ascii")
    assert uhl == "UHL1190526" + "SYNTHETIC SOLAR".ljust(20) + "1234567890001999111111222222"
    assert len(uhl) == 58
    assert (batch, group_end, batch_end) == ("1 1501 111111 5500", "3 +", "5 +")
    assert group == "2 2101234567 27769500 210526"
    assert len(items) == 4
    orders = []
    for item in items:
        account, amount, vs, bank_and_ks, ss, message = item.split(" ", 5)
        assert len(bank_and_ks) == 8 and bank_and_ks[4:] == "0308"
        assert ss == "" and message == f"AV:Invoice {vs}"
        orders.append((account, bank_and_ks[:4], vs, int(amount), group.split()[-1]))
    assert sum(order[3] for order in orders) == int(group.split()[2])
    assert (
        orders
        == debits
        == [
            ("1234509876", "2010", "202600014", 14520000, "210526"),
            ("2876543", "0100", "202600003", 4840000, "210526"),
            ("5551234", "5500", "202600021", 3267000, "210526"),
            ("3344556", "2700", "202600008", 5142500, "210526"),
        ]
    )


def test_bank_fixtures_match_readme():
    valid = SOURCES / "mailbox/bank/RB/26141_2101234567_CZK.gpc"
    broken = SOURCES / "mailbox/bank/RB/26142_2101234567_CZK.gpc"
    sta = SOURCES / "mailbox/bank/CS/26005_2900112233.sta"
    kpc = SOURCES / "drive/payments/PO_2026-05-19_RB.kpc"

    _check_kpc(kpc, _check_rb(valid, broken))
    _check_sta(sta)

    dates = read_mtimes(FIXTURES)
    assert dates[kpc.relative_to(SOURCES).as_posix()] == date(2026, 5, 19)
    for statement, business_date, expected in (
        (
            valid,
            date(2026, 5, 21),
            [
                "Solar Novak s.r.o. invoice 202600014",
                "Konstrukce Dvorak a.s. invoice 202600003",
                "Zemni Prace Kral s.r.o. invoice 202600021",
                "Invertech Marek s.r.o. invoice 202600008",
                "Investor milestone",
            ],
        ),
        (broken, date(2026, 5, 22), ["Investor milestone"]),
        (sta, date(2026, 5, 31), ["Příchozí platba", "Odchozí platba 92002", "Odchozí platba 92003"]),
    ):
        companion = statement.with_suffix(".txt")
        assert companion.read_text(encoding="utf-8").splitlines() == [
            f"{index}|{detail}" for index, detail in enumerate(expected, start=1)
        ]
        assert dates[statement.relative_to(SOURCES).as_posix()] == business_date
        assert dates[companion.relative_to(SOURCES).as_posix()] == business_date
