"""Run: python -m generators.finance_docs --seed 312 --scale 1"""

import argparse
import random
from collections import Counter
from pathlib import Path

from common import config
from generators.finance_docs import budgets as budgets_mod
from generators.finance_docs import (
    isdoc,
    ledger,
    master,
    money_export,
    pdf_invoice,
    plan,
)
from generators.finance_docs.util import (
    DATA_END,
    ledger_dir,
    set_business_mtime,
    sources_dir,
)


def generate(seed: int, scale: int, out_dir, led_dir) -> dict:
    out, led = Path(out_dir), Path(led_dir)
    d_master = out / "master"
    d_budgets = out / "drive" / "budgets"
    d_invoices = out / "mailbox" / "invoices"
    d_acc = out / "drive" / "accounting"
    for d in (d_master, d_budgets, d_invoices, d_acc, led):
        d.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)  # ALL randomness flows from this one object
    projects, suppliers, budgets, invoices = plan.build_plan(rng, scale)
    # Task 17.1 hook: planted.apply(invoices, projects, rng) goes here,
    # after the plan and before any file is written.

    master.write_projects_csv(d_master / "projects.csv", projects)
    master.write_suppliers_csv(d_master / "suppliers.csv", suppliers)
    for name in ("projects.csv", "suppliers.csv"):
        set_business_mtime(d_master / name, DATA_END)  # master data "as of" DATA_END

    by_code = {p["project_code"]: p for p in projects}
    for code, budget in budgets.items():
        budgets_mod.write_xlsx(
            d_budgets / f"{code}_budget.xlsx",
            code,
            budget,
            by_code[code]["signed_date"],
        )

    for inv in invoices:
        base = f"{inv.supplier['ico']}_{inv.number}"
        pdf_path = d_invoices / f"{base}.pdf"
        pdf_invoice.write(pdf_path, inv)
        set_business_mtime(pdf_path, inv.issue_date)
        if not inv.pdf_only:
            xml_path = d_invoices / f"{base}.isdoc"
            xml_path.write_bytes(isdoc.to_xml(inv))
            set_business_mtime(xml_path, inv.issue_date)

    first_signing = min(p["signed_date"] for p in projects if p["signed_date"])
    export_files = money_export.write_weeks(invoices, d_acc, first_signing)
    ledger.write(invoices, led / "invoice_ledger.csv")

    stats = {
        "projects": dict(Counter(p["status"] for p in projects)),
        "suppliers": len(suppliers),
        "budgets": len(budgets),
        "invoices": len(invoices),
        "pdf_only": sum(1 for i in invoices if i.pdf_only),
        "export_files": len(export_files),
    }
    return stats


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic finance documents")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default=str(sources_dir()), help="sources folder")
    ap.add_argument("--ledger", default=str(ledger_dir()), help="truth-file folder")
    args = ap.parse_args(argv)
    stats = generate(args.seed, args.scale, args.out, args.ledger)
    print(f"projects by status: {stats['projects']}")
    print(f"suppliers:          {stats['suppliers']}")
    print(f"budgets:            {stats['budgets']}")
    print(f"invoices:           {stats['invoices']} (PDF only: {stats['pdf_only']})")
    print(f"export files:       {stats['export_files']}")


if __name__ == "__main__":
    main()
