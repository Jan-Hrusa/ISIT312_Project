"""Matching job (Task 25.1): the payment status of every invoice, written to `fve_clean.invoice_status`.

Spark joins find each invoice's debits and payment orders by variabilní symbol and its other-VS candidates;
`rules.match_invoice` (Task 9) then decides status and issues per invoice inside `applyInPandas`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from common import dq, schemas, tables
from processing.matching import rules

JOB = "matching"

INVOICE, PAYMENT, ORDER, CANDIDATE = "INVOICE", "PAYMENT", "ORDER", "CANDIDATE"

# One long frame per invoice group: an INVOICE row, then its PAYMENT, ORDER and CANDIDATE rows. The columns
# are shared: account/bank_code are the supplier's on the INVOICE row and the counterparty's on the others,
# amount is the invoice's gross or the debit/order amount, day is the value date or order date.
_ITEM_COLUMNS = [
    ("invoice_id", "STRING"),
    ("kind", "STRING"),
    ("ref", "STRING"),
    ("project_code", "STRING"),
    ("bank", "STRING"),
    ("account", "STRING"),
    ("bank_code", "STRING"),
    ("vs", "STRING"),
    ("amount", schemas.MONEY),
    ("issue_date", "DATE"),
    ("day", "DATE"),
    ("due_date", "DATE"),
]
_STATUS_COLUMNS = schemas.column_names("invoice_status")
# The status columns (as_of is added afterwards), the issue columns, and which kind of row it is; is_due marks
# an invoice due by as_of, for the match rate.
_OUT_COLUMNS = ["row_kind", "is_due", *[c for c in _STATUS_COLUMNS if c != "as_of"], *dq.ISSUE_COLUMNS]
_OUT_DDL = ", ".join(
    ["row_kind STRING", "is_due BOOLEAN"]
    + [f"{name} {hive_type}" for name, hive_type in schemas.CLEAN_TABLES["invoice_status"] if name != "as_of"]
    + [f"{name} STRING" for name in dq.ISSUE_COLUMNS]
)


def run(spark: SparkSession, as_of: date | None = None) -> dict[str, int]:
    """Match every invoice with its payments and orders on `as_of` and replace `invoice_status` and the
    `matching` issues.

    as_of: default the last statement date in `bank_transactions` (the newest day the bank data covers).
    Returns {"invoices", "paid", "due", "issues"}: rows written, invoices due by as_of that are PAID, invoices
    due by as_of, issues written.
    """
    if as_of is None:
        as_of = _last_statement_date(spark)

    result = _match(spark, as_of).cache()
    try:
        status = result.where(F.col("row_kind") == "STATUS").withColumn("as_of", F.lit(as_of))
        issues = result.where(F.col("row_kind") == "ISSUE").select(*dq.ISSUE_COLUMNS)
        tables.write_table(spark, status, "invoice_status")
        written_issues = dq.write_issues(spark, issues, job=JOB)
        counts = status.agg(
            F.count("*").alias("invoices"),
            F.count(F.when(F.col("is_due"), 1)).alias("due"),
            F.count(F.when(F.col("is_due") & (F.col("status") == rules.PAID), 1)).alias("paid"),
        ).first()
    finally:
        result.unpersist()

    invoices, due, paid = counts["invoices"], counts["due"], counts["paid"]
    pct = 100 * paid / due if due else 0.0
    print(f"match rate: {paid}/{due} = {pct:.1f}% of invoices due by {as_of} are paid")
    return {"invoices": invoices, "paid": paid, "due": due, "issues": written_issues}


def _last_statement_date(spark: SparkSession) -> date:
    last = tables.read_table(spark, "bank_transactions").agg(F.max("statement_date")).first()[0]
    if last is None:
        raise ValueError("bank_transactions is empty: run the bank step first or pass as_of")
    return last


def _match(spark: SparkSession, as_of: date) -> DataFrame:
    suppliers = tables.read_table(spark, "suppliers").select(
        F.col("ico"),
        F.col("bank_account").alias("supplier_account"),
        F.col("bank_code").alias("supplier_bank_code"),
    )
    invoices = tables.read_table(spark, "invoices").join(
        suppliers, F.col("supplier_ico") == F.col("ico"), "left"
    )
    # PDF-only invoices not booked yet have no amount or due date: nothing to match them against.
    complete = invoices.where(F.col("total_gross").isNotNull() & F.col("due_date").isNotNull())
    debits = tables.read_table(spark, "bank_transactions").where(
        (F.col("amount") < 0) & (F.col("value_date") <= F.lit(as_of))
    )
    orders = tables.read_table(spark, "payment_orders").where(F.col("order_date") <= F.lit(as_of))

    keys = complete.select(
        "invoice_id",
        F.col("vs").alias("inv_vs"),
        "supplier_account",
        "supplier_bank_code",
        "total_gross",
        F.col("due_date").alias("inv_due"),
    )

    def by_vs(df: DataFrame) -> DataFrame:
        return df.join(
            keys,
            (F.col("vs") == F.col("inv_vs"))
            & (F.col("counterparty_account") == F.col("supplier_account"))
            & (F.col("counterparty_bank_code") == F.col("supplier_bank_code")),
        )

    vs_debits = by_vs(debits).cache()
    vs_orders = by_vs(orders)

    paid_by_vs = (
        vs_debits.groupBy("invoice_id", "total_gross")
        .agg(F.sum(F.abs("amount")).alias("paid"))
        .where(F.col("paid") >= F.col("total_gross") - F.lit(rules.TOLERANCE))
        .select("invoice_id")
    )
    open_keys = keys.join(paid_by_vs, "invoice_id", "left_anti")
    unmatched = debits.join(vs_debits.select("tx_id").distinct(), "tx_id", "left_anti")
    distance = F.abs(F.datediff("value_date", "inv_due"))
    # A debit with another or no VS suggests only the invoice whose due date is closest to its value date.
    candidates = (
        unmatched.join(
            open_keys,
            (F.col("counterparty_account") == F.col("supplier_account"))
            & (F.col("counterparty_bank_code") == F.col("supplier_bank_code"))
            & (F.abs(F.abs("amount") - F.col("total_gross")) <= F.lit(rules.TOLERANCE))
            & (distance <= rules.SUGGESTION_WINDOW.days),
        )
        .withColumn(
            "rank",
            F.row_number().over(Window.partitionBy("tx_id").orderBy(distance, "inv_due", "invoice_id")),
        )
        .where(F.col("rank") == 1)
    )

    def debit_items(df: DataFrame, kind: str) -> DataFrame:
        return df.select(
            "invoice_id",
            F.lit(kind).alias("kind"),
            F.col("tx_id").alias("ref"),
            "bank",
            F.col("counterparty_account").alias("account"),
            F.col("counterparty_bank_code").alias("bank_code"),
            "vs",
            "amount",
            F.col("value_date").alias("day"),
        )

    items = (
        invoices.select(
            "invoice_id",
            F.lit(INVOICE).alias("kind"),
            "project_code",
            F.col("supplier_account").alias("account"),
            F.col("supplier_bank_code").alias("bank_code"),
            "vs",
            F.col("total_gross").alias("amount"),
            "issue_date",
            "due_date",
        )
        .unionByName(debit_items(vs_debits, PAYMENT), allowMissingColumns=True)
        .unionByName(debit_items(candidates, CANDIDATE), allowMissingColumns=True)
        .unionByName(
            vs_orders.select(
                "invoice_id",
                F.lit(ORDER).alias("kind"),
                F.col("order_id").alias("ref"),
                "vs",
                "amount",
                F.col("order_date").alias("day"),
                "due_date",
            ),
            allowMissingColumns=True,
        )
    )
    # Fixed column order and types, as the pandas function reads them by name.
    items = items.select([F.col(name).cast(hive_type) for name, hive_type in _ITEM_COLUMNS])
    return items.groupBy("invoice_id").applyInPandas(lambda group: _match_group(group, as_of), _OUT_DDL)


def _match_group(group: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """One invoice's rows -> its STATUS row and ISSUE rows."""
    rows = [{k: _value(v) for k, v in row.items()} for row in group.to_dict("records")]
    head = next(r for r in rows if r["kind"] == INVOICE)
    out = {c: None for c in _OUT_COLUMNS}

    if head["amount"] is None or head["due_date"] is None:
        status = {**out, "row_kind": "STATUS", "is_due": False, "invoice_id": head["invoice_id"]}
        status.update(
            status=rules.UNPAID, paid_amount=Decimal("0"), order_ids=[], uncleared_order_ids=[], tx_ids=[]
        )
        return pd.DataFrame([status], columns=_OUT_COLUMNS)

    invoice = rules.Invoice(
        invoice_id=head["invoice_id"],
        project_code=head["project_code"],
        supplier_account=head["account"],
        supplier_bank_code=head["bank_code"],
        vs=head["vs"],
        gross=head["amount"],
        issue_date=head["issue_date"],
        due_date=head["due_date"],
    )

    def payments(kind: str) -> list[rules.Payment]:
        return [
            rules.Payment(r["ref"], r["bank"], r["day"], r["amount"], r["account"], r["bank_code"], r["vs"])
            for r in rows
            if r["kind"] == kind
        ]

    orders = [
        rules.Order(r["ref"], r["day"], r["due_date"], r["amount"], r["vs"])
        for r in rows
        if r["kind"] == ORDER
    ]
    result = rules.match_invoice(invoice, payments(PAYMENT), orders, payments(CANDIDATE), as_of)

    records = [
        {
            **out,
            "row_kind": "STATUS",
            "is_due": invoice.due_date <= as_of,
            "invoice_id": invoice.invoice_id,
            "status": result.status,
            "paid_amount": result.paid_amount,
            "paid_date": result.paid_date,
            "days_to_pay": result.days_to_pay,
            "days_late": result.days_late,
            "order_ids": result.order_ids,
            "uncleared_order_ids": result.uncleared_order_ids,
            "tx_ids": result.tx_ids,
        }
    ]
    records += [
        {**out, "row_kind": "ISSUE", "invoice_id": invoice.invoice_id, **i._asdict()} for i in result.issues
    ]
    return pd.DataFrame(records, columns=_OUT_COLUMNS)


def _value(value):
    """pandas gives NaN/NaT/None for a NULL; the rules want None."""
    if isinstance(value, (list, tuple)):
        return value
    return None if pd.isna(value) else value
