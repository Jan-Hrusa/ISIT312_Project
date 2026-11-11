"""Truth file for Task 6: one row per invoice (not collected into the lake)."""

import csv

from generators.finance_docs.util import money

COLUMNS = [
    "invoice_id", "supplier_ico", "supplier_account", "supplier_bank_code", "vs",
    "gross_amount", "issue_date", "due_date", "project_code", "pdf_only",
]  # fmt: skip


def write(invoices, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        for inv in invoices:
            w.writerow(
                [
                    inv.invoice_id,
                    inv.supplier["ico"],
                    inv.supplier["bank_account"],
                    inv.supplier["bank_code"],
                    inv.vs or "",
                    money(inv.gross),
                    inv.issue_date.isoformat(),
                    inv.due_date.isoformat(),
                    inv.project_code,
                    "true" if inv.pdf_only else "false",
                ]
            )
