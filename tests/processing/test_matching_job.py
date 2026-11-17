"""Matching job checks on small hand-made clean tables (clean_db: a temporary database, no stack)."""

from datetime import date
from decimal import Decimal

from common import schemas
from common.tables import read_table, write_table
from processing.matching.job import run

AS_OF = date(2026, 10, 31)
SUPPLIER = {"ico": "12345678", "bank_account": "123456789", "bank_code": "0100"}
OTHER_SUPPLIER = {"ico": "87654321", "bank_account": "5544332211", "bank_code": "2700"}


def _write(spark, table, rows):
    names = schemas.column_names(table)
    ddl = ", ".join(f"{name} {hive_type}" for name, hive_type in schemas.CLEAN_TABLES[table])
    df = spark.createDataFrame([tuple(row.get(name) for name in names) for row in rows], ddl)
    write_table(spark, df, table)


def _invoice(number, gross, due, *, supplier=SUPPLIER, vs="same", project="FVE-2026-03"):
    invoice_id = f"{supplier['ico']}-{number}"
    return {
        "invoice_id": invoice_id,
        "supplier_ico": supplier["ico"],
        "number": number,
        "vs": number if vs == "same" else vs,
        "issue_date": date(2026, 9, 1),
        "due_date": due,
        "total_gross": None if gross is None else Decimal(gross),
        "currency": "CZK",
        "project_code": project,
        "has_isdoc": True,
    }


def _debit(tx_id, day, amount, vs, *, supplier=SUPPLIER, statement_date=None):
    bank = tx_id.split("-", 1)[0]
    return {
        "tx_id": tx_id,
        "bank": bank,
        "account": "2101234567",
        "statement_no": 1,
        "statement_date": statement_date or day,
        "line_no": int(tx_id.rsplit("-", 1)[1]),
        "value_date": day,
        "amount": -Decimal(amount),
        "counterparty_account": supplier["bank_account"],
        "counterparty_bank_code": supplier["bank_code"],
        "vs": vs,
    }


def _order(order_id, ordered, due, amount, vs, *, supplier=SUPPLIER):
    return {
        "order_id": order_id,
        "bank": "RB",
        "account": "2101234567",
        "order_date": ordered,
        "due_date": due,
        "amount": Decimal(amount),
        "counterparty_account": supplier["bank_account"],
        "counterparty_bank_code": supplier["bank_code"],
        "vs": vs,
    }


def _load(spark, invoices, debits=(), orders=()):
    supplier_rows = [
        {**s, "name": f"Supplier {s['ico']}", "category": "PANELS"} for s in (SUPPLIER, OTHER_SUPPLIER)
    ]
    _write(spark, "suppliers", supplier_rows)
    _write(spark, "invoices", invoices)
    _write(spark, "bank_transactions", list(debits))
    _write(spark, "payment_orders", list(orders))


def _statuses(spark):
    return {row.invoice_id: row for row in read_table(spark, "invoice_status").collect()}


def _issues(spark):
    return sorted(
        (row.issue_type, row.source, row.record_ref, row.project_code, row.detail)
        for row in read_table(spark, "dq_issues").collect()
    )


def test_job_statuses_on_fixture(clean_db):
    _load(
        clean_db,
        [
            _invoice("202600001", "1000.00", date(2026, 9, 15)),  # paid by its VS
            _invoice("202600002", "1000.00", date(2026, 11, 15)),  # 400 paid, not due yet
            _invoice("202600003", "500.00", date(2026, 11, 10)),  # ordered, not debited yet
            _invoice("202600004", "800.00", date(2026, 11, 20)),  # nothing yet
            _invoice("202600005", "700.00", date(2026, 9, 30)),  # ordered, the order never cleared
        ],
        [
            _debit("RB-20260914-0001", date(2026, 9, 14), "1000.00", "202600001"),
            _debit("RB-20261020-0001", date(2026, 10, 20), "400.00", "202600002"),
            # A credit with an invoice's VS is not a payment.
            {
                **_debit("RB-20261021-0001", date(2026, 10, 21), "800.00", "202600004"),
                "amount": Decimal("800.00"),
            },
        ],
        [
            _order("PO_2026-10-30_RB-001", date(2026, 10, 30), date(2026, 11, 10), "500.00", "202600003"),
            _order("PO_2026-09-28_RB-001", date(2026, 9, 28), date(2026, 9, 30), "700.00", "202600005"),
        ],
    )

    counts = run(clean_db, AS_OF)

    assert counts == {"invoices": 5, "paid": 1, "due": 2, "issues": 1}
    rows = _statuses(clean_db)
    assert {key: row.status for key, row in rows.items()} == {
        "12345678-202600001": "PAID",
        "12345678-202600002": "PARTLY_PAID",
        "12345678-202600003": "ORDERED",
        "12345678-202600004": "UNPAID",
        "12345678-202600005": "OVERDUE",
    }
    paid = rows["12345678-202600001"]
    assert (paid.paid_amount, paid.paid_date, paid.days_to_pay, paid.days_late) == (
        Decimal("1000.00"),
        date(2026, 9, 14),
        13,
        0,
    )
    assert (paid.tx_ids, paid.order_ids, paid.as_of) == (["RB-20260914-0001"], [], AS_OF)
    assert rows["12345678-202600002"].paid_amount == Decimal("400.00")
    assert rows["12345678-202600003"].order_ids == ["PO_2026-10-30_RB-001"]
    overdue = rows["12345678-202600005"]
    assert (overdue.days_late, overdue.uncleared_order_ids) == (31, ["PO_2026-09-28_RB-001"])
    assert _issues(clean_db) == [
        (
            "ORDER_NOT_CLEARED",
            "kpc",
            "PO_2026-09-28_RB-001",
            "FVE-2026-03",
            "no debit of 700.00 CZK from 2026-09-29 to 2026-10-05 for invoice 12345678-202600005",
        )
    ]


def test_incomplete_invoice_is_unpaid(clean_db):
    _load(
        clean_db,
        [
            _invoice("202600010", None, date(2026, 9, 15)),  # PDF only, not booked: no amount
            _invoice("202600011", "500.00", None),  # no due date
        ],
        [
            _debit("RB-20260914-0001", date(2026, 9, 14), "500.00", "202600010"),
            _debit("RB-20260914-0002", date(2026, 9, 14), "500.00", "202600011"),
        ],
        [_order("PO_2026-09-10_RB-001", date(2026, 9, 10), date(2026, 9, 14), "500.00", "202600011")],
    )

    counts = run(clean_db, AS_OF)

    assert counts == {"invoices": 2, "paid": 0, "due": 0, "issues": 0}
    for row in _statuses(clean_db).values():
        assert (row.status, row.paid_amount, row.paid_date, row.days_to_pay, row.days_late) == (
            "UNPAID",
            Decimal("0.00"),
            None,
            None,
            None,
        )
        assert (row.tx_ids, row.order_ids, row.uncleared_order_ids) == ([], [], [])
    assert _issues(clean_db) == []


def test_suggestion_picks_closest_invoice(clean_db):
    _load(
        clean_db,
        [
            _invoice("202600020", "1210.00", date(2026, 9, 10)),
            _invoice("202600021", "1210.00", date(2026, 9, 20)),
            # Closest of all, but already paid by its own VS: never a target.
            _invoice("202600022", "1210.00", date(2026, 9, 18)),
            # Same amount and date, other supplier's account: not a candidate.
            _invoice("202600023", "1210.00", date(2026, 9, 18), supplier=OTHER_SUPPLIER),
        ],
        [
            _debit("RB-20260918-0001", date(2026, 9, 18), "1210.00", "202600022"),
            _debit("KB-20260918-0002", date(2026, 9, 18), "1210.00", "202600099"),  # mistyped VS
        ],
    )

    counts = run(clean_db, AS_OF)

    assert counts["issues"] == 1
    assert _issues(clean_db) == [
        (
            "UNMATCHED_PAYMENT",
            "bank_gpc",
            "KB-20260918-0002",
            "FVE-2026-03",
            "suggested match: 12345678-202600021 (VS differs)",
        )
    ]
    rows = _statuses(clean_db)
    assert rows["12345678-202600022"].status == "PAID"
    # The suggestion changes no status and pays nothing.
    assert (rows["12345678-202600021"].status, rows["12345678-202600021"].tx_ids) == ("OVERDUE", [])


def test_as_of_defaults_to_last_statement(clean_db):
    last = date(2026, 10, 30)
    _load(
        clean_db,
        [
            _invoice("202600030", "300.00", last),  # due on the last statement day: not overdue yet
            _invoice("202600031", "300.00", date(2026, 10, 29)),
        ],
        [
            # A monthly statement dated 30 Oct: its value dates are earlier, as_of is the statement date.
            _debit("CS-20261030-0001", date(2026, 10, 2), "50.00", "1", statement_date=last),
            _debit("RB-20261005-0001", date(2026, 10, 5), "50.00", "2"),
        ],
    )

    run(clean_db)

    rows = _statuses(clean_db)
    assert {row.as_of for row in rows.values()} == {last}
    assert rows["12345678-202600030"].status == "UNPAID"
    assert (rows["12345678-202600031"].status, rows["12345678-202600031"].days_late) == ("OVERDUE", 1)


def test_rerun_gives_same_result(clean_db):
    _load(
        clean_db,
        [
            _invoice("202600040", "900.00", date(2026, 9, 15)),
            _invoice("202600041", "450.00", date(2026, 9, 25)),
        ],
        [
            _debit("RB-20260915-0001", date(2026, 9, 15), "900.00", "202600040"),
            _debit("UCB-20260925-0001", date(2026, 9, 25), "450.00", None),  # no VS: suggestion
        ],
        [_order("PO_2026-09-22_RB-001", date(2026, 9, 22), date(2026, 9, 25), "450.00", "202600041")],
    )

    first = run(clean_db, AS_OF)
    statuses, issues = sorted(map(tuple, _statuses(clean_db).values())), _issues(clean_db)
    second = run(clean_db, AS_OF)

    assert first == second == {"invoices": 2, "paid": 1, "due": 2, "issues": 2}
    assert sorted(map(tuple, _statuses(clean_db).values())) == statuses
    assert _issues(clean_db) == issues
    assert [i[0] for i in issues] == ["ORDER_NOT_CLEARED", "UNMATCHED_PAYMENT"]
