"""Bank parser checks against the Task 6.1 fixtures."""

import csv
from datetime import date
from decimal import Decimal

import pytest

from processing.bank import BankParseError, gpc, kpc, run, sta, txt

RB = "mailbox/bank/RB/26141_2101234567_CZK.gpc"
BROKEN = "mailbox/bank/RB/26142_2101234567_CZK.gpc"
CS = "mailbox/bank/CS/26005_2900112233.sta"
ORDER = "drive/payments/PO_2026-05-19_RB.kpc"


@pytest.fixture
def sources(fixtures_dir):
    return fixtures_dir / "sources"


def _statement(parser, path, encoding):
    return parser.parse(path.read_bytes().decode(encoding), str(path))


def _inputs(sources):
    return {
        "bank_gpc": [(sources / path).as_uri() for path in (RB, BROKEN)],
        "bank_sta": [(sources / CS).as_uri()],
        "bank_txt": [path.as_uri() for path in sorted((sources / "mailbox/bank").glob("*/*.txt"))],
        "kpc": [(sources / ORDER).as_uri()],
    }


def test_parse_gpc_sample(sources):
    path = sources / RB
    header, rows = _statement(gpc, path, "ascii")
    assert len(rows) == 5
    assert header["opening_balance"] == Decimal("400000.00")
    assert header["closing_balance"] == Decimal("222305.00")
    assert rows[0] == {
        "tx_id": "RB-20260521-0001",
        "bank": "RB",
        "account": "2101234567",
        "statement_no": 141,
        "statement_date": date(2026, 5, 21),
        "line_no": 1,
        "value_date": date(2026, 5, 21),
        "amount": Decimal("-145200.00"),
        "counterparty_account": "1234509876",
        "counterparty_bank_code": "2010",
        "vs": "202600014",
        "ks": "308",
        "ss": None,
        "note": "Solar Novak s.r.o.",
        "source_file": str(path),
    }


def test_parse_sta_sample(sources):
    path = sources / CS
    text = path.read_bytes().decode("cp852")
    header, rows = sta.parse(text, str(path))
    assert header["statement_no"] == 5
    assert header["statement_date"] == date(2026, 5, 31)
    assert header["closing_balance"] == Decimal("54499.25")
    assert [row["amount"] for row in rows] == list(map(Decimal, ("10000.00", "-2500.50", "-3000.25")))
    assert rows[0]["note"] == "Příchozí platba"
    assert rows[0]["counterparty_bank_code"] == "0100"
    assert rows[0]["counterparty_account"] == "1112233445"
    assert (rows[0]["vs"], rows[0]["ks"], rows[0]["ss"]) == ("92001", "308", "1")
    assert sta.parse(text.replace(":28:", ":28C:"), str(path)) == (header, rows)
    assert sta.parse(text.replace("2605040504CK", "260504C"), str(path)) == (header, rows)


def test_parse_txt_sample(sources):
    text = (sources / RB).with_suffix(".txt").read_text(encoding="utf-8")
    rows = txt.parse(text)
    assert list(rows) == [1, 2, 3, 4, 5]
    assert rows[1] == "Solar Novak s.r.o. invoice 202600014"
    assert rows[5] == "Investor milestone"
    assert txt.parse("1|one|two\r\n") == {1: "one|two"}
    assert txt.parse("") == {}
    with pytest.raises(BankParseError):
        txt.parse("1|one\n1|duplicate")


def test_parse_kpc_sample(sources):
    path = sources / ORDER
    rows = kpc.parse(path.read_text(encoding="ascii"), path.stem, str(path))
    assert len(rows) == 4
    assert rows[0] == {
        "order_id": "PO_2026-05-19_RB-001",
        "bank": "RB",
        "account": "2101234567",
        "order_date": date(2026, 5, 19),
        "due_date": date(2026, 5, 21),
        "amount": Decimal("145200.00"),
        "counterparty_account": "1234509876",
        "counterparty_bank_code": "2010",
        "vs": "202600014",
        "ks": "308",
        "ss": None,
        "source_file": str(path),
    }
    assert rows[-1]["order_id"].endswith("-004")


def test_debit_is_negative(sources):
    _, rows = _statement(gpc, sources / RB, "ascii")
    assert all(row["amount"] < 0 for row in rows[:4])
    assert rows[4]["amount"] > 0
    lines = (sources / RB).read_text(encoding="ascii").splitlines()
    lines[1] = lines[1][:60] + "5" + lines[1][61:]
    assert gpc.parse("\n".join(lines), RB)[1][0]["amount"] == Decimal("-145200.00")
    text = (sources / CS).read_bytes().decode("cp852").replace("DK2500,50", "RCK2500,50")
    assert sta.parse(text, CS)[1][1]["amount"] == Decimal("-2500.50")


def test_vs_without_leading_zeros(sources):
    _, rows = _statement(gpc, sources / RB, "ascii")
    assert rows[0]["vs"] == "202600014"
    assert rows[0]["ks"] == "308"
    assert rows[0]["ss"] is None
    path = sources / ORDER
    text = path.read_text(encoding="ascii").replace(" 202600014 ", " 0 ", 1)
    assert kpc.parse(text, path.stem, str(path))[0]["vs"] is None


def test_bad_file_gives_parse_error_issue(sources, clean_db):
    from common.tables import read_table

    path = sources / BROKEN
    with pytest.raises(BankParseError, match="invalid GPC 075"):
        _statement(gpc, path, "ascii")
    counts = run(clean_db, {"bank_gpc": [path.as_uri()]})
    assert counts == {"bank_transactions": 0, "bank_tx_details": 0, "payment_orders": 0, "issues": 1}
    (issue,) = read_table(clean_db, "dq_issues").collect()
    assert (issue.job, issue.issue_type, issue.source, issue.record_ref) == (
        "bank",
        "PARSE_ERROR",
        "bank_gpc",
        path.as_uri(),
    )


def test_missing_file_gives_parse_error_issue(sources, clean_db, tmp_path):
    from common.tables import read_table

    # A listed raw file that is gone (or whose whole folder is gone) must not stop the job.
    missing = (tmp_path / "26999_2101234567_CZK.gpc").as_uri()
    missing_folder = (tmp_path / "gone" / "PO_2026-05-20_RB.kpc").as_uri()
    inputs = {
        "bank_gpc": [(sources / RB).as_uri(), missing],
        "kpc": [(sources / ORDER).as_uri(), missing_folder],
    }
    counts = run(clean_db, inputs)
    assert counts == {"bank_transactions": 5, "bank_tx_details": 0, "payment_orders": 4, "issues": 2}
    issues = {
        (issue.issue_type, issue.source, issue.record_ref, issue.detail)
        for issue in read_table(clean_db, "dq_issues").collect()
    }
    assert issues == {
        ("PARSE_ERROR", "bank_gpc", missing, "file not found"),
        ("PARSE_ERROR", "kpc", missing_folder, "file not found"),
    }


def test_totals_mismatch_rejects_file(sources):
    gpc_text = (sources / RB).read_text(encoding="ascii").replace("00000027769500", "00000027769501", 1)
    with pytest.raises(BankParseError, match="^totals mismatch$"):
        gpc.parse(gpc_text, RB)
    sta_text = (sources / CS).read_bytes().decode("cp852").replace("54499,25", "54499,26")
    with pytest.raises(BankParseError, match="^totals mismatch$"):
        sta.parse(sta_text, CS)


def test_account_format_matches_suppliers(sources):
    _, rows = _statement(gpc, sources / RB, "ascii")
    with (sources / "master/suppliers.csv").open(encoding="utf-8", newline="") as stream:
        suppliers = {(row["bank_account"], row["bank_code"]) for row in csv.DictReader(stream)}
    assert {(row["counterparty_account"], row["counterparty_bank_code"]) for row in rows[:4]} <= suppliers


def test_run_on_fixtures(sources, clean_db, tmp_path):
    from common.tables import read_table

    inputs = _inputs(sources)
    # Raw statement and TXT files may have different ingest timestamps.
    for source, name, stamp in (
        ("bank_gpc", RB, "20261114120000"),
        ("bank_txt", str((sources / RB).with_suffix(".txt").relative_to(sources)), "20261114120100"),
    ):
        original = sources / name
        raw = tmp_path / f"{original.stem}__{stamp}{original.suffix}"
        raw.write_bytes(original.read_bytes())
        inputs[source].remove(original.as_uri())
        inputs[source].append(raw.as_uri())

    broken_sta = tmp_path / "broken.sta"
    broken_sta.write_bytes((sources / CS).read_bytes().replace(b"DK2500,50", b"XX2500,50"))
    inputs["bank_sta"].append(broken_sta.as_uri())

    assert run(clean_db, inputs) == {
        "bank_transactions": 8,
        "bank_tx_details": 8,
        "payment_orders": 4,
        "issues": 2,
    }
    assert read_table(clean_db, "bank_transactions").count() == 8
    assert read_table(clean_db, "payment_orders").count() == 4
    details = {row.tx_id: row for row in read_table(clean_db, "bank_tx_details").collect()}
    assert len(details) == 8
    first = details["RB-20260521-0001"]
    assert first.detail_text == "Solar Novak s.r.o. invoice 202600014"
    assert first.source_file.endswith("__20261114120100.txt")
    assert details["CS-20260531-0001"].detail_text == "Příchozí platba"
    issues = read_table(clean_db, "dq_issues").collect()
    assert {(issue.issue_type, issue.source, issue.record_ref) for issue in issues} == {
        ("PARSE_ERROR", "bank_gpc", (sources / BROKEN).as_uri()),
        ("PARSE_ERROR", "bank_sta", broken_sta.as_uri()),
    }
