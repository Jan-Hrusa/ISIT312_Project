"""Run: python -m generators.finance_docs --seed 312 --scale 1"""

import argparse
import dataclasses
import random
from collections import Counter
from pathlib import Path

from common import config
from generators.finance_docs import budgets as budgets_mod
from generators.finance_docs import isdoc, ledger, master, money_export, pdf_invoice, plan, planted
from generators.finance_docs.util import DATA_END, ledger_dir, set_business_mtime, sources_dir


def write_invoice_files(inv, d_invoices: Path) -> None:
    """The PDF, the ISDOC (unless PDF only) and, for a planted DUPLICATE, the resent pair."""
    base = f"{inv.supplier['ico']}_{inv.number}"
    pdf_invoice.write(d_invoices / f"{base}.pdf", inv)
    set_business_mtime(d_invoices / f"{base}.pdf", inv.issue_date)
    if not inv.pdf_only:
        xml = isdoc.to_xml(inv)
        if inv.extra.get("truncated"):  # PARSE_ERROR: cut off right after <InvoiceLines>
            marker = b"<InvoiceLines>"
            xml = xml[: xml.index(marker) + len(marker)]
        (d_invoices / f"{base}.isdoc").write_bytes(xml)
        set_business_mtime(d_invoices / f"{base}.isdoc", inv.issue_date)

    resent = inv.extra.get("resent_date")
    if resent:  # DUPLICATE: same invoice, new UUID, sent again 1-5 days later
        twin = dataclasses.replace(inv, uuid=inv.extra["resent_uuid"])
        pdf_invoice.write(d_invoices / f"{base}_resent.pdf", twin)
        (d_invoices / f"{base}_resent.isdoc").write_bytes(isdoc.to_xml(twin))
        for ext in ("pdf", "isdoc"):
            set_business_mtime(d_invoices / f"{base}_resent.{ext}", resent)


def generate(seed: int, scale: int, out_dir, led_dir, plant: bool = False) -> dict:
    """Write all finance sources. plant=True also plants the Task 17.1 problems (the CLI does by default)."""
    out, led = Path(out_dir), Path(led_dir)
    d_master = out / "master"
    d_budgets = out / "drive" / "budgets"
    d_invoices = out / "mailbox" / "invoices"
    d_acc = out / "drive" / "accounting"
    for d in (d_master, d_budgets, d_invoices, d_acc, led):
        d.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)  # ALL randomness flows from this one object
    projects, suppliers, budgets, invoices = plan.build_plan(rng, scale)
    truth_path = led / "planted_finance.csv"
    truth = []
    if plant:  # after the plan, before any file is written; same rng, so the seed still decides everything
        truth = planted.apply(invoices, projects, rng, budgets=budgets, suppliers=suppliers, scale=scale)
        planted.write(truth, truth_path)
    else:
        truth_path.unlink(missing_ok=True)  # never leave a truth file that doesn't match the data

    master.write_projects_csv(d_master / "projects.csv", projects)
    master.write_suppliers_csv(d_master / "suppliers.csv", suppliers)
    for name in ("projects.csv", "suppliers.csv"):
        set_business_mtime(d_master / name, DATA_END)  # master data "as of" DATA_END

    by_code = {p["project_code"]: p for p in projects}
    for code, budget in budgets.items():
        budgets_mod.write_xlsx(d_budgets / f"{code}_budget.xlsx", code, budget, by_code[code]["signed_date"])

    for inv in invoices:
        write_invoice_files(inv, d_invoices)

    first_signing = min(p["signed_date"] for p in projects if p["signed_date"])
    export_files = money_export.write_weeks(invoices, d_acc, first_signing)
    ledger.write(invoices, led / "invoice_ledger.csv")

    counts = Counter(r["problem"] for r in truth)
    return {
        "projects": dict(Counter(p["status"] for p in projects)),
        "suppliers": len(suppliers),
        "budgets": len(budgets),
        "invoices": len(invoices),
        "pdf_only": sum(1 for i in invoices if i.pdf_only),
        "export_files": len(export_files),
        "planted": {name: counts[name] for name in planted.PROBLEMS if counts[name]},
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic finance documents")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default=str(sources_dir()), help="sources folder")
    ap.add_argument("--ledger", default=str(ledger_dir()), help="truth-file folder")
    ap.add_argument("--no-planted", action="store_true", help="leave out the Task 17.1 planted problems")
    args = ap.parse_args(argv)
    stats = generate(args.seed, args.scale, args.out, args.ledger, plant=not args.no_planted)
    print(f"projects by status: {stats['projects']}")
    print(f"suppliers:          {stats['suppliers']}")
    print(f"budgets:            {stats['budgets']}")
    print(f"invoices:           {stats['invoices']} (PDF only: {stats['pdf_only']})")
    print(f"export files:       {stats['export_files']}")
    print(f"planted problems:   {stats['planted'] or 'none'}")


if __name__ == "__main__":
    main()
