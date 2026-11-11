import csv
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from common import config
from generators.bank import kpc, payments
from generators.bank.__main__ import generate


@pytest.fixture
def bank_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_START", date(2025, 12, 29))
    monkeypatch.setattr(config, "DATA_END", date(2026, 3, 31))
    sources = tmp_path / "sources"
    ledger = tmp_path / "ledger"
    monkeypatch.setattr(config, "SOURCES_DIR", sources)
    monkeypatch.setattr(config, "LEDGER_DIR", ledger)
    suppliers = [{"ico": "20400013", "name": "Solární dodavatel"}]
    projects = [
        {
            "project_code": "FVE-2025-01",
            "signed_date": "2025-12-29",
            "construction_end": "2026-03-20",
            "contract_value": "1200000.00",
        }
    ]
    invoices = [
        {
            "invoice_id": f"20400013-2026{index:05d}",
            "supplier_ico": "20400013",
            "supplier_account": "1234509876",
            "supplier_bank_code": "0100",
            "vs": str(202600000 + index),
            "gross_amount": "1000.01",
            "issue_date": "2026-01-01",
            "due_date": "2026-02-01",
        }
        for index in range(1, 101)
    ]
    for path, rows in (
        (ledger / "invoice_ledger.csv", invoices),
        (sources / "master" / "suppliers.csv", suppliers),
        (sources / "master" / "projects.csv", projects),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return invoices, suppliers, projects


@pytest.fixture
def generated(bank_inputs):
    generate(312)
    return config.SOURCES_DIR


def _records(path, encoding="ascii"):
    raw = path.read_bytes()
    assert raw.endswith(b"\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b"")
    return raw.decode(encoding).split("\r\n")[:-1]


def _signed(cents, sign):
    return int(cents) * (-1 if sign == "-" else 1)


def test_gpc_line_length_matches_spec(generated):
    lengths = Counter(len(record) for path in generated.rglob("*.gpc") for record in _records(path))
    assert set(lengths) == {126, 128}
    assert lengths[126] == 1


def test_gpc_totals_match_items(generated):
    for path in generated.rglob("*.gpc"):
        header, *items = _records(path)
        assert header.startswith("074")
        assert all(item.startswith("075") for item in items)
        debit = sum(int(item[48:60]) for item in items if item[60] == "1")
        credit = sum(int(item[48:60]) for item in items if item[60] == "2")
        assert (debit, credit) == (int(header[75:89]), int(header[90:104]))
        assert _signed(header[45:59], header[59]) - debit + credit == _signed(header[60:74], header[74])


def test_sta_opening_plus_items_equals_closing(generated):
    for path in generated.rglob("*.sta"):
        rows = _records(path, "cp852")
        assert rows[4].startswith(":28C:")
        assert rows[-1] == "-}"
        opening = Decimal(rows[5][15:].replace(",", "."))
        balance = -opening if rows[5][5] == "D" else opening
        for row in rows:
            if row.startswith(":61:"):
                amount = Decimal(row[16:].split("NTRF")[0].replace(",", "."))
                balance += amount if row[14] == "C" else -amount
        closing = Decimal(rows[-2][15:].replace(",", "."))
        assert balance == (-closing if rows[-2][5] == "D" else closing)


def test_every_statement_has_a_txt(generated):
    for pattern, encoding, prefix in (("*.gpc", "ascii", "075"), ("*.sta", "cp852", ":61:")):
        for path in generated.rglob(pattern):
            records = _records(path, encoding)
            lines = path.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
            assert len(lines) == sum(record.startswith(prefix) for record in records)
            assert [line.partition("|")[0] for line in lines] == [
                str(index) for index in range(1, len(lines) + 1)
            ]


def test_rb_has_one_statement_per_day(generated):
    files = list((generated / "mailbox" / "bank" / "RB").glob("*.gpc"))
    days = {datetime.strptime(_records(path)[0][108:114], "%d%m%y").date() for path in files}
    expected = {
        config.DATA_START + timedelta(days=index)
        for index in range((config.DATA_END - config.DATA_START).days + 1)
    }
    assert len(files) == len(days) == len(expected)
    assert days == expected
    assert any(path.name.startswith("26001_") for path in files)
    for bank, extension in (("UCB", "gpc"), ("KB", "gpc"), ("CS", "sta")):
        assert len(list((generated / "mailbox" / "bank" / bank).glob(f"*.{extension}"))) == 4


def test_kpc_order_before_debit(bank_inputs):
    debits, _, orders, planted = payments.plan(*bank_inputs, random.Random(312))
    lost = {case.invoice_id for case in planted if case.problem == "ORDER_LOST"}
    for order in orders:
        assert order.run_date.weekday() in (1, 4)
        assert order.run_date <= order.due_date
        if order.invoice_id in lost:
            continue
        (debit,) = (
            item for item in debits if (item.invoice_id, -item.cents) == (order.invoice_id, order.cents)
        )
        assert debit.vs == order.vs
        assert debit.counterparty_account == order.counterparty_account
        assert debit.counterparty_bank_code == order.counterparty_bank_code
        assert 0 <= (debit.value_date - order.run_date).days <= 3
        assert debit.value_date in (order.due_date, payments._next_business_day(order.due_date))
    assert list(payments.schedules(date(2026, 1, 3), date(2026, 1, 3), date(2026, 1, 4))) == []


def test_planted_counts(bank_inputs):
    invoices, _, _ = bank_inputs
    for row in invoices[:2]:
        row["vs"] = ""
    debits, _, orders, planted = payments.plan(*bank_inputs, random.Random(312))
    assert Counter(case.problem for case in planted) == {
        "LATE": 3,
        "INSTALMENTS": 2,
        "PARTIAL": 1,
        "NEVER": 1,
        "WRONG_VS": 15,
        "ORDER_LOST": 10,
        "NO_VS": 2,
        "BAD_FILE": 1,
    }
    ids = [case.invoice_id for case in planted if case.invoice_id]
    assert len(ids) == len(set(ids))
    for case in planted:
        items = sorted(
            (item for item in debits if item.invoice_id == case.invoice_id),
            key=lambda item: item.value_date,
        )
        if case.problem == "INSTALMENTS":
            assert [item.cents for item in items] == [-60001, -40000]
            assert items[0].value_date < items[1].value_date
        if case.problem == "LATE":
            assert 5 <= (items[0].value_date - date(2026, 2, 1)).days <= 40
    missing = [order for order in orders if not order.vs]
    assert len(missing) == 2
    with pytest.raises(ValueError, match="No approved raw KPC encoding"):
        kpc.validate_vs(missing[0])


def test_bad_file_statement_has_no_invoice_payment(generated):
    records = (_records(path) for path in generated.rglob("*.gpc"))
    malformed = [statement for statement in records if any(len(row) == 126 for row in statement)]
    assert len(malformed) == 1
    header, credit = malformed[0]
    assert len(header) == 128
    assert len(credit) == 126 and credit[60] == "2"


def test_same_seed_same_bytes(generated, tmp_path, monkeypatch):
    ledger_dir = config.LEDGER_DIR
    second = tmp_path / "second"
    monkeypatch.setattr(config, "SOURCES_DIR", second)
    (second / "master").mkdir(parents=True)
    for path in (generated / "master").glob("*.csv"):
        (second / "master" / path.name).write_bytes(path.read_bytes())
    truth = ledger_dir / "planted_payments.csv"
    expected_truth = truth.read_bytes()
    generate(312)
    assert {
        path.relative_to(generated): path.read_bytes() for path in generated.rglob("*") if path.is_file()
    } == {path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()}
    assert truth.read_bytes() == expected_truth


def test_mtime_is_statement_date(generated):
    for path in generated.rglob("*"):
        if path.suffix == ".gpc":
            day = datetime.strptime(_records(path)[0][108:114], "%d%m%y").date()
        elif path.suffix == ".sta":
            day = datetime.strptime(_records(path, "cp852")[-2][6:12], "%y%m%d").date()
        elif path.suffix == ".kpc":
            day = date.fromisoformat(path.name.split("_")[1])
        else:
            continue
        expected = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
        assert datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) == expected
        if path.suffix in (".sta", ".gpc"):
            assert datetime.fromtimestamp(path.with_suffix(".txt").stat().st_mtime, timezone.utc) == expected
