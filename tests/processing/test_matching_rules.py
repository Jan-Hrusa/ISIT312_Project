import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from processing.matching.rules import Invoice, Issue, Order, Payment, match_invoice

CASES_JSON = Path(__file__).resolve().parent.parent / "fixtures" / "matching" / "cases.json"

ISSUED = date(2026, 9, 1)
DUE = date(2026, 9, 15)
LATER = date(2026, 10, 31)

INVOICE = Invoice(
    invoice_id="12345678-202600001",
    project_code="FVE-2026-03",
    supplier_account="123456789",
    supplier_bank_code="0100",
    vs="202600001",
    gross=Decimal("121000.00"),
    issue_date=ISSUED,
    due_date=DUE,
)


def pay(day: date, amount: str, *, tx_id: str | None = None, bank: str = "RB", vs: str | None = "202600001"):
    return Payment(
        tx_id=tx_id or f"{bank}-{day:%Y%m%d}-0001",
        bank=bank,
        value_date=day,
        amount=-Decimal(amount),
        counterparty_account=INVOICE.supplier_account,
        counterparty_bank_code=INVOICE.supplier_bank_code,
        vs=vs,
    )


def order(due: date, amount: str, *, order_id: str = "PO_2026-09-11_RB-001", ordered: date | None = None):
    return Order(
        order_id=order_id,
        order_date=ordered or due - timedelta(days=3),
        due_date=due,
        amount=Decimal(amount),
        vs=INVOICE.vs,
    )


def match(payments=(), orders=(), other=(), as_of=LATER, invoice=INVOICE):
    return match_invoice(invoice, list(payments), list(orders), list(other), as_of)


def test_paid_exact():
    p = pay(date(2026, 9, 10), "121000.00")
    r = match([p])
    assert r.status == "PAID"
    assert r.paid_amount == Decimal("121000.00")
    assert r.paid_date == date(2026, 9, 10)
    assert (r.days_to_pay, r.days_late) == (9, 0)
    assert r.tx_ids == [p.tx_id]
    assert r.issues == []


def test_paid_within_one_haler():
    assert match([pay(DUE, "120999.99")]).status == "PAID"
    short = match([pay(DUE, "120999.98")])
    assert short.status == "OVERDUE"  # 2 haléře short is a part payment, and on 31 Oct it is past due
    assert short.paid_date is None and short.days_to_pay is None


def test_paid_in_two_instalments():
    first = pay(date(2026, 9, 10), "60500.00", tx_id="RB-20260910-0002")
    second = pay(date(2026, 9, 20), "60500.00", tx_id="KB-20260930-0005", bank="KB")
    r = match([second, first])
    assert r.status == "PAID"
    assert r.paid_amount == Decimal("121000.00")
    assert r.paid_date == date(2026, 9, 20)
    assert (r.days_to_pay, r.days_late) == (19, 5)
    assert r.tx_ids == ["RB-20260910-0002", "KB-20260930-0005"]


def test_partly_paid_before_due():
    r = match([pay(date(2026, 9, 10), "50000.00")], as_of=date(2026, 9, 12))
    assert r.status == "PARTLY_PAID"
    assert r.paid_amount == Decimal("50000.00")
    assert (r.paid_date, r.days_to_pay, r.days_late) == (None, None, 0)


def test_partly_paid_after_due_is_overdue():
    r = match([pay(date(2026, 9, 10), "50000.00")], as_of=date(2026, 9, 20))
    assert r.status == "OVERDUE"
    assert r.paid_amount == Decimal("50000.00")
    assert r.days_late == 5


def test_ordered_not_yet_debited():
    o = order(DUE, "121000.00")
    r = match(orders=[o], as_of=date(2026, 9, 14))
    assert r.status == "ORDERED"
    assert r.paid_amount == Decimal("0")
    assert r.order_ids == [o.order_id]
    assert r.uncleared_order_ids == [o.order_id]  # not debited yet, but not reported either
    assert (r.tx_ids, r.issues, r.days_late) == ([], [], 0)


def test_overdue_after_due_date():
    on_due = match(as_of=DUE)
    assert (on_due.status, on_due.days_late) == ("UNPAID", 0)  # the due date itself is not overdue
    day_after = match(as_of=DUE + timedelta(days=1))
    assert (day_after.status, day_after.days_late) == ("OVERDUE", 1)

    o = order(DUE, "121000.00")
    assert match(orders=[o], as_of=DUE).status == "ORDERED"
    assert match(orders=[o], as_of=DUE + timedelta(days=1)).status == "OVERDUE"


def test_wrong_vs_gives_suggestion():
    stray = pay(date(2026, 9, 16), "121000.00", tx_id="RB-20260916-0004", vs="202600010")
    r = match(other=[stray])
    assert r.status == "OVERDUE"  # a suggestion never changes the status
    assert r.issues == [
        Issue(
            "UNMATCHED_PAYMENT",
            "bank_gpc",
            stray.tx_id,
            "FVE-2026-03",
            "suggested match: 12345678-202600001 (VS differs)",
        )
    ]

    paid = match([pay(DUE, "121000.00")], other=[stray])
    assert paid.status == "PAID" and paid.issues == []  # a paid invoice needs no suggestion


def test_empty_vs_gives_suggestion():
    stray = pay(date(2026, 9, 24), "121000.00", tx_id="CS-20260930-0002", bank="CS", vs=None)
    r = match(other=[stray])
    assert r.issues == [
        Issue(
            "UNMATCHED_PAYMENT",
            "bank_sta",
            stray.tx_id,
            "FVE-2026-03",
            "suggested match: 12345678-202600001 (no VS)",
        )
    ]


def test_suggestion_outside_10_days_ignored():
    def suggested(day: date, amount: str = "121000.00") -> bool:
        return bool(match(other=[pay(day, amount, vs="999")]).issues)

    assert suggested(DUE - timedelta(days=10)) and suggested(DUE + timedelta(days=10))
    assert not suggested(DUE - timedelta(days=11))
    assert not suggested(DUE + timedelta(days=11))
    assert suggested(DUE, "121000.01") and not suggested(DUE, "121000.02")  # amount within one haléř only


def test_order_not_cleared_after_5_days():
    o = order(DUE, "121000.00")
    assert match(orders=[o], as_of=DUE + timedelta(days=5)).issues == []
    r = match(orders=[o], as_of=DUE + timedelta(days=6))
    assert r.uncleared_order_ids == [o.order_id]
    assert r.issues == [
        Issue(
            "ORDER_NOT_CLEARED",
            "kpc",
            o.order_id,
            "FVE-2026-03",
            "no debit of 121000.00 CZK from 2026-09-14 to 2026-09-20 for invoice 12345678-202600001",
        )
    ]

    # A debit too late for the order still pays the invoice, but does not clear the order.
    late = match([pay(DUE + timedelta(days=6), "121000.00")], [o])
    assert late.status == "PAID"
    assert late.uncleared_order_ids == [o.order_id]
    assert [i.issue_type for i in late.issues] == ["ORDER_NOT_CLEARED"]

    # The first day of the window (due date - 1) clears it.
    early = match([pay(DUE - timedelta(days=1), "121000.00")], [o])
    assert early.uncleared_order_ids == [] and early.issues == []


def test_instalment_orders_each_cleared():
    first = order(DUE, "60500.00", order_id="PO_2026-09-11_RB-001")
    second = order(date(2026, 10, 15), "60500.00", order_id="PO_2026-10-12_RB-002")
    payments = [
        pay(DUE, "60500.00", tx_id="RB-20260915-0001"),
        pay(date(2026, 10, 16), "60500.00", tx_id="RB-20261016-0001"),
    ]
    r = match(payments, [second, first])
    assert r.status == "PAID"
    assert r.order_ids == ["PO_2026-09-11_RB-001", "PO_2026-10-12_RB-002"]
    assert r.uncleared_order_ids == []
    assert r.issues == []

    # Two equal orders due the same day need two debits: one debit clears only one of them.
    twin = replace(first, order_id="PO_2026-09-11_RB-002")
    one_debit = match(payments[:1], [first, twin])
    assert one_debit.uncleared_order_ids == ["PO_2026-09-11_RB-002"]
    assert [i.record_ref for i in one_debit.issues] == ["PO_2026-09-11_RB-002"]


def test_payment_after_as_of_ignored():
    as_of = date(2026, 10, 1)
    r = match(
        [pay(date(2026, 10, 2), "121000.00")],
        [order(date(2026, 10, 5), "121000.00", ordered=as_of + timedelta(days=1))],
        [pay(date(2026, 9, 20), "121000.00", tx_id="RB-20260920-0009", vs="1")],
        as_of=as_of,
    )
    # Neither the payment nor the order exists yet on 1 Oct; the stray debit dated before as_of still counts.
    assert r.status == "OVERDUE"
    assert (r.paid_amount, r.tx_ids, r.order_ids) == (Decimal("0"), [], [])
    assert [i.record_ref for i in r.issues] == ["RB-20260920-0009"]
    assert match([pay(date(2026, 10, 2), "121000.00")], as_of=date(2026, 10, 2)).status == "PAID"


def _date(value):
    return date.fromisoformat(value) if value else None


def _invoice(d):
    return Invoice(
        **{
            **d,
            "gross": Decimal(d["gross"]),
            "issue_date": _date(d["issue_date"]),
            "due_date": _date(d["due_date"]),
        }
    )


def _payment(d):
    return Payment(**{**d, "amount": Decimal(d["amount"]), "value_date": _date(d["value_date"])})


def _order(d):
    return Order(
        **{
            **d,
            "amount": Decimal(d["amount"]),
            "order_date": _date(d["order_date"]),
            "due_date": _date(d["due_date"]),
        }
    )


def _cases():
    return json.loads(CASES_JSON.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_cases_json(case):
    r = match_invoice(
        _invoice(case["invoice"]),
        [_payment(p) for p in case["payments"]],
        [_order(o) for o in case["orders"]],
        [_payment(p) for p in case["other_vs_payments"]],
        _date(case["as_of"]),
    )
    want = case["expected"]
    assert r.status == want["status"]
    assert r.paid_amount == Decimal(want["paid_amount"])
    assert r.paid_date == _date(want["paid_date"])
    assert (r.days_to_pay, r.days_late) == (want["days_to_pay"], want["days_late"])
    assert (r.order_ids, r.uncleared_order_ids, r.tx_ids) == (
        want["order_ids"],
        want["uncleared_order_ids"],
        want["tx_ids"],
    )
    assert r.issues == [Issue(*i) for i in want["issues"]]
