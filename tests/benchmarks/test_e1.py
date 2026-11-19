"""Experiment E1 (benchmarks/e1) on the valid GPC fixture statement: each version's logic gives what Task 16's
parser gives, plus the runner's helpers. The timed runs on YARN need the stack."""

from __future__ import annotations

import shutil
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.e1 import compare_outputs, gpc_spark, run_e1
from benchmarks.e1.gpc_mrjob import GpcMonthly
from processing.bank.gpc import parse
from warehouse.sql import render

GPC_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "sources" / "mailbox" / "bank" / "RB"
# 26142 is Task 16's broken statement (a record cut short); E1 leaves its planted twin out of the input too.
GPC_FILES = [GPC_DIR / "26141_2101234567_CZK.gpc"]
ALL_GPC = sorted(GPC_DIR.glob("*.gpc"))


def _reference() -> list[tuple]:
    """(account, month, transactions, amount) straight from the Task 16 parser."""
    groups = defaultdict(lambda: [0, Decimal("0")])
    for path in GPC_FILES:
        _, transactions = parse(path.read_text(encoding="ascii"), str(path))
        for t in transactions:
            group = groups[(t["account"], t["value_date"].strftime("%Y-%m"))]
            group[0] += 1
            group[1] += t["amount"]
    return compare_outputs.normalize((a, m, n, s) for (a, m), (n, s) in groups.items())


def _gpc_only(tmp_path: Path) -> Path:
    """The valid fixture statement without its TXT twin, as one folder (the Hive table reads every file)."""
    folder = tmp_path / "gpc"
    folder.mkdir()
    for path in GPC_FILES:
        shutil.copy(path, folder / path.name)
    return folder


def test_fixture_has_debits_and_credits():
    # The other tests mean something only if both signs occur.
    amounts = [t["amount"] for p in GPC_FILES for t in parse(p.read_text(encoding="ascii"), str(p))[1]]
    assert min(amounts) < 0 < max(amounts)


def test_mrjob_matches_parser():
    job = GpcMonthly(args=["-r", "inline", "--no-conf", *map(str, GPC_FILES)])
    with job.make_runner() as runner:
        runner.run()
        rows = [tuple(value) for _, value in job.parse_output(runner.cat_output())]
    assert compare_outputs.normalize(rows) == _reference()


def test_mrjob_mapper_fields_and_signs():
    line = next(
        line for line in GPC_FILES[0].read_text(encoding="ascii").splitlines() if line.startswith("075")
    )
    job = GpcMonthly(args=[])
    for booking, sign in (("1", -1), ("2", 1), ("4", 1), ("5", -1)):
        changed = f"{line[:60]}{booking}{line[61:]}\r"
        ((key, (count, amount)),) = job.mapper(None, changed)
        assert key == (str(int(line[3:19])), f"20{line[95:97]}-{line[93:95]}")
        assert (count, amount) == (1, sign * int(line[48:60]))
    # CombineTextInputFormat on YARN puts the byte offset in front of the line.
    assert list(job.mapper(None, f"4096\t{line}\r")) == list(job.mapper(None, line))
    assert list(job.mapper(None, line[:126])) == []  # a shortened record is skipped
    assert list(job.mapper(None, "074" + line[3:])) == []


def test_czk():
    from benchmarks.e1.gpc_mrjob import czk

    assert [czk(h) for h in (0, 5, 12345, -12345, -7)] == ["0.00", "0.05", "123.45", "-123.45", "-0.07"]


def test_spark_matches_parser(spark, tmp_path):
    rows = gpc_spark.monthly(spark, _gpc_only(tmp_path).as_uri())
    assert compare_outputs.normalize(rows) == _reference()


def test_hive_query_matches_parser(spark_hive, tmp_path):
    # Spark with Hive support runs the same HiveQL (the SET lines are accepted and ignored here).
    statements = render(run_e1.HERE / "gpc_hive.sql", E1_LOCATION=_gpc_only(tmp_path).as_uri())
    for statement in statements[:-1]:
        spark_hive.sql(statement)
    rows = [tuple(r) for r in spark_hive.sql(statements[-1]).collect()]
    spark_hive.sql("DROP TABLE IF EXISTS e1_gpc_lines")
    assert compare_outputs.normalize(rows) == _reference()


def test_compare_outputs():
    a = [("2101234567", "2026-05", 3, "100.00")]
    assert compare_outputs.compare({"mrjob": a, "spark": [("002101234567", "2026-05", "3", "100")]}) == []
    problems = compare_outputs.compare({"mrjob": a, "hive": [("2101234567", "2026-05", 3, "100.01")]})
    assert len(problems) == 1 and problems[0].startswith("hive differs from mrjob")


def test_output_round_trip(tmp_path):
    rows = [("2101234567", "2026-05", 3, Decimal("-1.5")), ("1", "2026-04", 1, "2")]
    path = tmp_path / "e1" / "spark.tsv"
    compare_outputs.write_output(path, rows)
    assert compare_outputs.read_output(path) == compare_outputs.normalize(rows)


def test_broken_files(tmp_path):
    bank = tmp_path / "RB"
    bank.mkdir()
    for path in ALL_GPC:
        shutil.copy(path, bank / path.name)
    files = sorted(bank.glob("*.gpc"))
    header_date = files[1].read_bytes()[108:114].decode()  # DDMMYY of 26142, the broken statement
    planted = tmp_path / "planted_payments.csv"
    planted.write_text(
        "problem,invoice_id,tx_or_order_ref,detail\n"
        f"BAD_FILE,,RB-20{header_date[4:]}{header_date[2:4]}{header_date[:2]}-0001,shortened\n"
        "LATE,1-1,RB-20260101-0001,late\n",
        encoding="utf-8",
    )
    assert run_e1.broken_files(files, planted) == {files[1]}
    assert run_e1.broken_files(files, tmp_path / "missing.csv") == set()


def test_lines_of_code(tmp_path):
    py, sql = tmp_path / "a.py", tmp_path / "b.sql"
    py.write_text("# comment\nimport os\n\n    # indented comment\nx = 1  # trailing\n", encoding="utf-8")
    sql.write_text("-- comment\nSELECT 1\n\n;\n", encoding="utf-8")
    assert (run_e1.lines_of_code(py), run_e1.lines_of_code(sql)) == (2, 2)


def test_check_deletable():
    run_e1.check_deletable("/bench/x10/e1/out_mrjob")
    for path in ("/lake/raw", "/bench", "/bench/", "/bench/../lake"):
        with pytest.raises(ValueError, match="refusing"):
            run_e1.check_deletable(path)


def test_summary():
    rows = [
        {
            "version": v,
            "run": r,
            "seconds": s,
            "input_files": 10,
            "input_mb": "1.50",
            "output_rows": 4,
            "loc": 30,
        }
        for v, runs in (("mrjob", (50, 40, 60)), ("spark", (20, 30, 25)), ("hive", (70, 80, 75)))
        for r, s in enumerate(runs, 1)
    ]
    table = run_e1.summary(rows)
    assert "| A MapReduce (mrjob) | 50.0 | 40.0 | 60.0 | 3 | 30 | 4 |" in table
    assert "| B Spark | 25.0 | 20.0 | 30.0 | 3 | 30 | 4 |" in table
    assert "10 GPC files, 1.5 MB" in table
