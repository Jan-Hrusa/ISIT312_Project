"""Payment matching rules: decide from one invoice's payments and orders whether it is paid.

Pure Python (no Spark, no I/O), so the rules are tested on hand-made cases before any data exists. The
matching job (Task 25.1) groups the clean tables per invoice and calls `match_invoice` once per group; it
writes the result to `invoice_status` and the issues with `common.dq.write_issues(job="matching")`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple

from common import config

PAID = "PAID"
PARTLY_PAID = "PARTLY_PAID"
ORDERED = "ORDERED"
UNPAID = "UNPAID"
OVERDUE = "OVERDUE"
STATUSES = (PAID, PARTLY_PAID, ORDERED, UNPAID, OVERDUE)

# One haléř: amounts within it count as equal.
TOLERANCE = Decimal("0.01")
# An order is cleared by a debit dated from its due date - 1 day to due date + 5 days; later it is reported.
ORDER_CLEAR_BEFORE = timedelta(days=1)
ORDER_CLEAR_AFTER = timedelta(days=5)
# A debit with another VS is suggested for an invoice when it is dated within due date +- 10 days.
SUGGESTION_WINDOW = timedelta(days=10)


@dataclass(frozen=True)
class Invoice:
    invoice_id: str
    project_code: str | None
    supplier_account: str
    supplier_bank_code: str
    vs: str | None
    gross: Decimal
    issue_date: date
    due_date: date


@dataclass(frozen=True)
class Payment:
    """One bank debit (`bank_transactions` row): amount < 0."""

    tx_id: str
    bank: str
    value_date: date
    amount: Decimal
    counterparty_account: str
    counterparty_bank_code: str
    vs: str | None

    @property
    def source(self) -> str:
        """The raw source the debit came from: `bank_sta` for STA statements, else `bank_gpc`."""
        return "bank_sta" if config.BANKS[self.bank].format == "STA" else "bank_gpc"


@dataclass(frozen=True)
class Order:
    """One KPC payment order item (`payment_orders` row): amount > 0."""

    order_id: str
    order_date: date
    due_date: date
    amount: Decimal
    vs: str | None


class Issue(NamedTuple):
    """One "to fix" row, in the column order of `common.dq.ISSUE_COLUMNS`."""

    issue_type: str
    source: str
    record_ref: str
    project_code: str | None
    detail: str


@dataclass(frozen=True)
class MatchResult:
    """One `invoice_status` row (without `invoice_id` and `as_of`, which the job adds) plus its issues."""

    status: str
    paid_amount: Decimal
    paid_date: date | None
    days_to_pay: int | None
    days_late: int
    order_ids: list[str] = field(default_factory=list)
    uncleared_order_ids: list[str] = field(default_factory=list)
    tx_ids: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def match_invoice(
    invoice: Invoice,
    payments: list[Payment],
    orders: list[Order],
    other_vs_payments: list[Payment],
    as_of: date,
) -> MatchResult:
    """Status, payment figures and issues of `invoice` on the day `as_of`.

    payments: debits with the invoice's VS to the supplier's account.
    orders: KPC orders with the invoice's VS to the supplier's account.
    other_vs_payments: debits to the supplier's account with a different or empty VS, matched to no invoice.
    Only payments and orders dated on or before `as_of` count.
    """
    payments = sorted((p for p in payments if p.value_date <= as_of), key=lambda p: (p.value_date, p.tx_id))
    orders = sorted((o for o in orders if o.order_date <= as_of), key=lambda o: (o.order_date, o.order_id))
    paid_amount = sum((abs(p.amount) for p in payments), Decimal("0"))
    overdue = as_of > invoice.due_date  # the due date itself is not overdue

    if payments and paid_amount >= invoice.gross - TOLERANCE:
        status = PAID
    elif payments:
        status = OVERDUE if overdue else PARTLY_PAID
    elif orders:
        status = OVERDUE if overdue else ORDERED
    else:
        status = OVERDUE if overdue else UNPAID

    if status == PAID:
        paid_date = payments[-1].value_date
        days_to_pay = (paid_date - invoice.issue_date).days
        days_late = max(0, (paid_date - invoice.due_date).days)
    else:
        # The task defines paid_date for PAID only; a part payment's date stays in tx_ids, not here.
        paid_date = None
        days_to_pay = None
        days_late = max(0, (as_of - invoice.due_date).days)

    uncleared = _uncleared_orders(orders, payments)
    issues = [
        Issue(
            "ORDER_NOT_CLEARED",
            "kpc",
            o.order_id,
            invoice.project_code,
            f"no debit of {o.amount} CZK from {o.due_date - ORDER_CLEAR_BEFORE}"
            f" to {o.due_date + ORDER_CLEAR_AFTER} for invoice {invoice.invoice_id}",
        )
        for o in uncleared
        if as_of > o.due_date + ORDER_CLEAR_AFTER
    ]
    if status != PAID:
        issues = _suggestions(invoice, other_vs_payments, as_of) + issues

    return MatchResult(
        status=status,
        paid_amount=paid_amount,
        paid_date=paid_date,
        days_to_pay=days_to_pay,
        days_late=days_late,
        order_ids=[o.order_id for o in orders],
        uncleared_order_ids=[o.order_id for o in uncleared],
        tx_ids=[p.tx_id for p in payments],
        issues=issues,
    )


def _uncleared_orders(orders: list[Order], payments: list[Payment]) -> list[Order]:
    """Orders that no payment clears; each payment clears at most one order (both lists sorted by date)."""
    used: set[str] = set()
    uncleared = []
    for order in orders:
        start, end = order.due_date - ORDER_CLEAR_BEFORE, order.due_date + ORDER_CLEAR_AFTER
        match = next(
            (
                p
                for p in payments
                if p.tx_id not in used
                and abs(abs(p.amount) - order.amount) <= TOLERANCE
                and start <= p.value_date <= end
            ),
            None,
        )
        if match is None:
            uncleared.append(order)
        else:
            used.add(match.tx_id)
    return uncleared


def _suggestions(invoice: Invoice, other_vs_payments: list[Payment], as_of: date) -> list[Issue]:
    """UNMATCHED_PAYMENT issues for debits with another or no VS that fit the invoice's amount and due."""
    candidates = sorted(
        (
            p
            for p in other_vs_payments
            if p.value_date <= as_of
            and abs(abs(p.amount) - invoice.gross) <= TOLERANCE
            and abs(p.value_date - invoice.due_date) <= SUGGESTION_WINDOW
        ),
        key=lambda p: (p.value_date, p.tx_id),
    )
    return [
        Issue(
            "UNMATCHED_PAYMENT",
            p.source,
            p.tx_id,
            invoice.project_code,
            f"suggested match: {invoice.invoice_id} ({'VS differs' if p.vs else 'no VS'})",
        )
        for p in candidates
    ]
