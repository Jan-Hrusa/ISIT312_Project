"""Task 25: the "to fix" and overdue queries on small clean tables, and every planted payment problem found
after a full pipeline run."""

import csv
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from common import config, schemas
from common.dq import issue_rows, write_issues
from common.tables import write_table
from warehouse.sql import named_queries

QUERIES = Path(__file__).resolve().parents[2] / "warehouse" / "queries"
TO_FIX = QUERIES / "to_fix.sql"
OVERDUE = QUERIES / "overdue_by_supplier.sql"
NOTEBOOKS = QUERIES.parents[1] / "notebooks"
TO_FIX_NOTE = NOTEBOOKS / "to_fix_2NAFGU2WC.zpln"
OVERDUE_NOTE = NOTEBOOKS / "overdue_by_supplier_2N9ESAMYY.zpln"

SUPPLIER = {
    "ico": "12345678",
    "name": "Panely s.r.o.",
    "category": "PANELS",
    "bank_account": "123456789",
    "bank_code": "0100",
}

# Expected on as_of = DATA_END: the generator keeps every case due well before it.
EXPECTED_STATUS = {
    "LATE": "PAID",
    "INSTALMENTS": "PAID",
    "PARTIAL": "OVERDUE",
    "NEVER": "OVERDUE",
    "WRONG_VS": "OVERDUE",
    "ORDER_LOST": "OVERDUE",
    "NO_VS": "OVERDUE",
}
# The issue whose record_ref is the planted transaction or order, and whose detail names the invoice.
EXPECTED_ISSUE = {
    "WRONG_VS": "UNMATCHED_PAYMENT",
    "ORDER_LOST": "ORDER_NOT_CLEARED",
    "NO_VS": "UNMATCHED_PAYMENT",
}


def _write(spark, table, rows):
    names = schemas.column_names(table)
    ddl = ", ".join(f"{name} {hive_type}" for name, hive_type in schemas.CLEAN_TABLES[table])
    write_table(spark, spark.createDataFrame([tuple(row.get(n) for n in names) for row in rows], ddl), table)


def _invoice(number, gross, due, project="FVE-2026-03"):
    return {
        "invoice_id": f"{SUPPLIER['ico']}-{number}",
        "supplier_ico": SUPPLIER["ico"],
        "number": number,
        "vs": number,
        "issue_date": date(2026, 8, 1),
        "due_date": due,
        "total_gross": Decimal(gross),
        "currency": "CZK",
        "project_code": project,
        "has_isdoc": True,
        "source_file": f"/lake/raw/invoices/2026/08/{number}.isdoc",
    }


def _status(number, status, paid="0.00", days_late=None):
    return {
        "invoice_id": f"{SUPPLIER['ico']}-{number}",
        "status": status,
        "paid_amount": Decimal(paid),
        "days_late": days_late,
        "order_ids": [],
        "uncleared_order_ids": [],
        "tx_ids": [],
        "as_of": date(2026, 10, 31),
    }


@pytest.fixture
def lake(clean_db):
    """One row behind every paragraph: an invoice per status, a debit, an order, a booked cost, a photo, and
    an issue of every type the "to fix" list shows."""
    spark = clean_db
    _write(spark, "suppliers", [SUPPLIER])
    _write(
        spark,
        "invoices",
        [
            _invoice("202600001", "1210.00", date(2026, 9, 10)),
            _invoice("202600002", "500.00", date(2026, 9, 20)),
            _invoice("202600003", "300.00", date(2026, 10, 1)),
            _invoice("202600004", "800.00", date(2026, 11, 20), project=None),
        ],
    )
    _write(
        spark,
        "invoice_status",
        [
            _status("202600001", "OVERDUE", days_late=51),
            _status("202600002", "OVERDUE", paid="200.00", days_late=41),
            _status("202600003", "PAID", paid="300.00", days_late=0),
            _status("202600004", "UNPAID"),
        ],
    )
    _write(
        spark,
        "bank_transactions",
        [
            {
                "tx_id": "KB-20260912-0001",
                "bank": "KB",
                "statement_date": date(2026, 9, 12),
                "value_date": date(2026, 9, 12),
                "amount": Decimal("-1210.00"),
                "counterparty_account": SUPPLIER["bank_account"],
                "counterparty_bank_code": SUPPLIER["bank_code"],
                "vs": "202600099",
            }
        ],
    )
    _write(
        spark,
        "payment_orders",
        [
            {
                "order_id": "PO_2026-09-18_RB-001",
                "bank": "RB",
                "order_date": date(2026, 9, 18),
                "due_date": date(2026, 9, 20),
                "amount": Decimal("500.00"),
                "counterparty_account": SUPPLIER["bank_account"],
                "counterparty_bank_code": SUPPLIER["bank_code"],
                "vs": "202600002",
            }
        ],
    )
    _write(
        spark,
        "booked_costs",
        [
            {
                "doc_ref": "FP-2026-0042",
                "supplier_ico": SUPPLIER["ico"],
                "issue_date": date(2026, 9, 3),
                "amount": Decimal("100.00"),
                "amount_gross": Decimal("121.00"),
            },
            {
                "doc_ref": "FP-2026-0042",
                "supplier_ico": SUPPLIER["ico"],
                "issue_date": date(2026, 9, 3),
                "amount": Decimal("50.00"),
                "amount_gross": Decimal("60.50"),
            },
        ],
    )
    _write(
        spark,
        "media_files",
        [
            {
                "file_id": "f1",
                "kind": "PHOTO",
                "original_name": "IMG_0001.jpg",
                "taken_at": datetime(2026, 9, 5, 10, 0),
                "project_code": config.UNASSIGNED,
            }
        ],
    )
    issues = {
        "matching": [
            (
                "UNMATCHED_PAYMENT",
                "bank_gpc",
                "KB-20260912-0001",
                "FVE-2026-03",
                "suggested match: 12345678-202600001 (VS differs)",
            ),
            (
                "ORDER_NOT_CLEARED",
                "kpc",
                "PO_2026-09-18_RB-001",
                "FVE-2026-03",
                "no debit of 500.00 CZK from 2026-09-19 to 2026-09-25 for invoice 12345678-202600002",
            ),
        ],
        "finance": [
            ("NO_PROJECT", "isdoc", "12345678-202600004", None, "no rule assigned a project"),
            ("NO_PROJECT", "accounting", "FP-2026-0042", None, "booked cost without project code"),
            (
                "DUPLICATE",
                "isdoc",
                "12345678-202600003",
                "FVE-2026-03",
                "/lake/raw/invoices/2026/08/copy.isdoc",
            ),
            ("PARSE_ERROR", "isdoc", "/lake/raw/invoices/2026/08/broken.isdoc", None, "not XML"),
            (
                "MISSING_VS",
                "isdoc",
                "12345678-202600001",
                "FVE-2026-03",
                "no variable symbol in /lake/raw/invoices/2026/08/202600001.isdoc",
            ),
        ],
        "media": [
            ("NO_GPS", "photos", "f0", None, "IMG_0000.jpg taken 2026-09-04"),
            (
                "UNASSIGNED_PHOTO",
                "photos",
                "f1",
                "FVE-2026-03",
                "IMG_0001.jpg taken 2026-09-05, 900 m from x",
            ),
            ("WRONG_VERSION", "docs", "FVE-2026-03/drawing", "FVE-2026-03", "drawing_final is older than v2"),
        ],
    }
    for job, rows in issues.items():
        write_issues(spark, issue_rows(spark, rows), job=job)
    return spark


def _run(spark, path, **params):
    return {name: spark.sql(sql).collect() for name, sql in named_queries(path, **params).items()}


def test_to_fix_queries_parse(lake):
    to_fix = _run(lake, TO_FIX)

    assert list(to_fix) == [
        "issue_counts",
        "unmatched_payments",
        "no_project",
        "orders_not_cleared",
        "photos",
        "wrong_versions",
        "duplicates",
        "parse_errors",
        "missing_vs",
    ]
    counts = {(r.issue_type, r.job): r.issues for r in to_fix["issue_counts"]}
    assert counts[("NO_PROJECT", "finance")] == 2
    assert sum(counts.values()) == 10
    (payment,) = to_fix["unmatched_payments"]
    assert (payment.tx_id, payment.amount, payment.suggested_invoice) == (
        "KB-20260912-0001",
        Decimal("1210.00"),
        "12345678-202600001",
    )
    # A booked cost of two lines is one row with its gross summed.
    assert [(r.source, r.supplier, r.amount_gross) for r in to_fix["no_project"]] == [
        ("accounting", "Panely s.r.o.", Decimal("181.50")),
        ("isdoc", "Panely s.r.o.", Decimal("800.00")),
    ]
    (order,) = to_fix["orders_not_cleared"]
    assert (order.order_id, order.invoice_id, order.amount) == (
        "PO_2026-09-18_RB-001",
        "12345678-202600002",
        Decimal("500.00"),
    )
    assert [(r.issue_type, r.original_name, r.nearest_project) for r in to_fix["photos"]] == [
        ("UNASSIGNED_PHOTO", "IMG_0001.jpg", "FVE-2026-03"),
        ("NO_GPS", None, None),
    ]
    assert [r.drawing for r in to_fix["wrong_versions"]] == ["FVE-2026-03/drawing"]
    (duplicate,) = to_fix["duplicates"]
    assert (duplicate.supplier, duplicate.dropped_file) == (
        "Panely s.r.o.",
        "/lake/raw/invoices/2026/08/copy.isdoc",
    )
    assert [r.raw_path for r in to_fix["parse_errors"]] == ["/lake/raw/invoices/2026/08/broken.isdoc"]
    # The invoice without a VS, with the debit the matching job suggested for it.
    (missing,) = to_fix["missing_vs"]
    assert (missing.invoice_id, missing.supplier, missing.status, missing.suggested_payment) == (
        "12345678-202600001",
        "Panely s.r.o.",
        "OVERDUE",
        "KB-20260912-0001",
    )

    overdue = _run(lake, OVERDUE, supplier=SUPPLIER["name"])

    # OVERDUE only: the PAID and the not-yet-due invoice are left out.
    (row,) = overdue["overdue_by_supplier"]
    assert (row.supplier, row.overdue_invoices, row.open_amount, row.oldest_due_date, row.avg_days_late) == (
        "Panely s.r.o.",
        2,
        Decimal("1510.00"),
        date(2026, 9, 10),
        46.0,
    )
    assert [r.invoice_id for r in overdue["supplier_invoices"]] == [
        "12345678-202600004",
        "12345678-202600003",
        "12345678-202600002",
        "12345678-202600001",
    ]
    by_ico = _run(lake, OVERDUE, supplier=SUPPLIER["ico"])["supplier_invoices"]
    assert len(by_ico) == 4


def test_notes_match_sql_files():
    """Each Zeppelin note runs exactly the queries of its .sql file, in order, after its hidden REFRESH
    paragraph; it is committed without results (Zeppelin adds them again when it runs); and every column has
    a plain name, so HiveServer2 shows the same headers as Spark (no `t.value_date`)."""
    for sql_file, note_file in ((TO_FIX, TO_FIX_NOTE), (OVERDUE, OVERDUE_NOTE)):
        note = json.loads(note_file.read_text(encoding="utf-8"))
        refresh, *paragraphs = note["paragraphs"]
        assert refresh["text"].startswith("%sparksql\nREFRESH TABLE "), note_file.name
        queries = named_queries(sql_file, CLEAN_DB="fve_clean", supplier="${supplier=}")
        expected = [f"%sparksql\n{q}" for q in queries.values()]
        assert [p["text"] for p in paragraphs] == expected, note_file.name
        for p in note["paragraphs"]:
            assert "results" not in p and p["status"] == "READY", (note_file.name, p.get("title"))
        # The REFRESH paragraph must cover every table the queries read, or the Thrift Server shows old data.
        refreshed = set(re.findall(r"REFRESH TABLE fve_clean\.(\w+);", refresh["text"]))
        queried = {t for q in queries.values() for t in re.findall(r"fve_clean\.(\w+)", q)}
        assert queried <= refreshed, (note_file.name, sorted(queried - refreshed))
        for query in queries.values():
            select_list = query.split("\nFROM ", 1)[0]
            assert not re.findall(r"^\s+[a-z]+\.[a-z_]+,?$", select_list, re.MULTILINE), query[:60]


@pytest.mark.integration
def test_planted_payment_problems_found(_spark_sessions):
    """After a scale-1 pipeline run: every row of planted_payments.csv has its expected status or issue."""
    planted_csv = config.LEDGER_DIR / "planted_payments.csv"
    if not planted_csv.exists():
        pytest.skip(f"no {planted_csv}: run the bank generator and the pipeline first")
    from common.spark import get_spark

    # This test reads the stack's metastore: stop the test sessions first, or get_spark returns one of them.
    _spark_sessions.stop()
    spark = get_spark("test-planted-payments")
    try:
        if not spark.catalog.tableExists(f"{config.CLEAN_DB}.invoice_status"):
            pytest.skip(
                f"no {config.CLEAN_DB}.invoice_status: run the pipeline, then this test with -m integration"
            )
        status = {r.invoice_id: r for r in spark.table(f"{config.CLEAN_DB}.invoice_status").collect()}
        issues = spark.table(f"{config.CLEAN_DB}.dq_issues").where("job IN ('matching', 'bank')").collect()
        by_ref = {(i.issue_type, i.record_ref): i for i in issues}
        parse_errors = [i.record_ref for i in issues if i.issue_type == "PARSE_ERROR" and i.job == "bank"]

        missed = []
        with planted_csv.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                problem, invoice_id, ref = row["problem"], row["invoice_id"], row["tx_or_order_ref"]
                if problem == "NO_VS" and not ref:
                    continue  # an invoice due outside the data period: no bank movement was generated
                if problem == "BAD_FILE":
                    # The broken record's file: <bank folder>/<year>/<month>/ of its transaction date.
                    day = ref.split("-")[1]
                    found = any(f"/{day[:4]}/{day[4:6]}/" in path for path in parse_errors)
                else:
                    s = status.get(invoice_id)
                    found = s is not None and s.status == EXPECTED_STATUS[problem]
                    if problem == "LATE":
                        found = found and s.days_late > 0
                    if problem in EXPECTED_ISSUE:
                        issue = by_ref.get((EXPECTED_ISSUE[problem], ref))
                        found = found and issue is not None and invoice_id in (issue.detail or "")
                if not found:
                    missed.append((problem, invoice_id, ref))
        assert missed == []
    finally:
        spark.stop()
