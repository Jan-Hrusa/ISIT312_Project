"""The accountant's weekly export (Money S3 style CSV)."""

import csv
from datetime import date, timedelta

from generators.finance_docs.util import DATA_END, money_cz, set_business_mtime

COLUMNS = [
    "doc_ref", "supplier_ico", "vs", "issue_date", "due_date", "booking_date",
    "project_code", "cost_centre", "category", "amount_net_czk", "amount_gross_czk",
]  # fmt: skip
COST_CENTRE = "STAVBY"


def week_name(monday: date) -> str:
    y, w, _ = monday.isocalendar()
    return f"money_export_{y}-W{w:02d}.csv"


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def write_weeks(invoices, out_dir, start: date) -> list:
    """One file per ISO week from the week of `start` to the week of DATA_END."""
    by_week: dict[date, list] = {}
    for inv in invoices:
        if inv.booking_date > DATA_END:  # not booked yet - intended
            continue
        by_week.setdefault(monday_of(inv.booking_date), []).append(inv)
    paths = []
    monday = monday_of(start)
    last = monday_of(DATA_END)
    while monday <= last:
        path = out_dir / week_name(monday)
        rows = sorted(by_week.get(monday, []), key=lambda i: (i.booking_date, i.invoice_id))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(COLUMNS)
            for inv in rows:
                w.writerow(
                    [
                        inv.invoice_id,
                        inv.supplier["ico"],
                        inv.vs or "",
                        inv.issue_date.isoformat(),
                        inv.due_date.isoformat(),
                        inv.booking_date.isoformat(),
                        inv.booked_project_code or "",
                        COST_CENTRE,
                        inv.category,
                        money_cz(inv.net),
                        money_cz(inv.gross),
                    ]
                )
        set_business_mtime(path, monday)
        paths.append(path)
        monday += timedelta(days=7)
    return paths
