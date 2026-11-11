"""Task 5.1: the finance sample set in tests/fixtures matches its README."""

import csv
import re
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook

from common import config

FIX = Path(__file__).resolve().parents[1] / "fixtures"
SRC = FIX / "sources"
README = FIX / "finance" / "README.md"
NS = {"i": "http://isdoc.cz/namespace/2013"}


def readme_table(heading: str) -> list[dict]:
    """Rows of the first markdown table under '## <heading>' in README.md."""
    lines = README.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"## {heading}")
    rows = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    header, body = rows[0], rows[2:]
    return [dict(zip(header, r, strict=True)) for r in body]


def read_csv(path, delimiter=","):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def isdoc_text(root, path: str) -> str:
    return root.find(path, NS).text


def cz(value: str) -> str:
    return value.replace(".", ",")


def test_finance_fixtures_match_readme():
    projects = read_csv(SRC / "master/projects.csv")
    expected = readme_table("Projects")
    assert [p["project_code"] for p in projects] == [e["project_code"] for e in expected]
    for p, e in zip(projects, expected, strict=True):
        for key, want in e.items():
            assert p[key] == want, (p["project_code"], key)
        assert config.is_project_code(p["project_code"])
        if p["status"] == "NOT_SIGNED":
            assert not p["signed_date"] and not p["construction_start"] and not p["construction_end"]

    assert read_csv(SRC / "master/suppliers.csv") == readme_table("Suppliers")

    check_invoices()
    check_budget()
    check_export_and_ledger()
    check_mtimes()


def check_invoices():
    inv_dir = SRC / "mailbox/invoices"
    expected = readme_table("Invoices")
    assert len(expected) == 4
    for e in expected:
        base = inv_dir / f"{e['ico']}_{e['number']}"
        net, vat, gross = Decimal(e["net"]), Decimal(e["vat"]), Decimal(e["gross"])
        assert net + vat == gross and net * Decimal("0.21") == vat
        pdf = base.with_suffix(".pdf").read_bytes()
        assert cz(e["gross"]).encode() in pdf
        assert e["number"].encode() in pdf  # number and VS
        isdoc_path = base.with_suffix(".isdoc")
        assert isdoc_path.exists() == (e["isdoc"] == "yes")
        if e["isdoc"] == "no":
            continue
        root = etree.parse(str(isdoc_path)).getroot()
        text = partial(isdoc_text, root)
        assert text("i:ID") == e["number"]
        assert text("i:AccountingSupplierParty/i:Party/i:PartyIdentification/i:ID") == e["ico"]
        assert text("i:IssueDate") == e["issue_date"]
        assert text(".//i:Details/i:PaymentDueDate") == e["due_date"]
        assert text(".//i:Details/i:VariableSymbol") == e["vs"]
        lines = root.findall(".//i:InvoiceLine", NS)
        assert len(lines) == int(e["lines"])
        assert sum(Decimal(x.find("i:LineExtensionAmount", NS).text) for x in lines) == net
        assert Decimal(text("i:LegalMonetaryTotal/i:TaxExclusiveAmount")) == net
        assert Decimal(text("i:TaxTotal/i:TaxAmount")) == vat
        assert Decimal(text("i:LegalMonetaryTotal/i:TaxInclusiveAmount")) == gross
        assert Decimal(text("i:LegalMonetaryTotal/i:PayableAmount")) == gross
    stems = {p.stem for p in inv_dir.glob("*.pdf")}
    assert stems == {f"{e['ico']}_{e['number']}" for e in expected}


def check_budget():
    rows = list(
        load_workbook(SRC / "drive/budgets/FVE-2026-02_budget.xlsx")["Budget"].iter_rows(values_only=True)
    )
    assert list(rows[0]) == ["project_code", "category", "amount_czk"]
    expected = readme_table("Budget FVE-2026-02")
    total = expected.pop()
    assert total["category"] == "TOTAL"
    assert [r[1] for r in rows[1:]] == [e["category"] for e in expected]
    assert [r[2] for r in rows[1:]] == [int(e["amount_czk"]) for e in expected]
    assert all(r[0] == "FVE-2026-02" for r in rows[1:])
    assert sum(r[2] for r in rows[1:]) == int(total["amount_czk"]) == 28160000
    assert 0.85 <= int(total["amount_czk"]) / 32000000 <= 0.92


def check_export_and_ledger():
    invoices = {e["invoice_id"]: e for e in readme_table("Invoices")}
    suppliers = {s["ico"]: s for s in readme_table("Suppliers")}
    export = read_csv(SRC / "drive/accounting/money_export_2026-W20.csv", ";")
    expected = readme_table("Money export 2026-W20")
    assert [r["doc_ref"] for r in export] == [e["doc_ref"] for e in expected]
    for r, e in zip(export, expected, strict=True):
        inv = invoices[e["doc_ref"]]
        assert (r["supplier_ico"], r["vs"]) == (inv["ico"], inv["vs"])
        assert (r["issue_date"], r["due_date"]) == (inv["issue_date"], inv["due_date"])
        assert (r["booking_date"], r["category"]) == (e["booking_date"], e["category"])
        assert (r["project_code"], r["cost_centre"]) == ("FVE-2026-02", "STAVBY")
        assert r["amount_net_czk"] == e["amount_net_czk"] == cz(inv["net"])
        assert r["amount_gross_czk"] == e["amount_gross_czk"] == cz(inv["gross"])

    ledger = read_csv(FIX / "out/ledger/invoice_ledger.csv")
    assert [r["invoice_id"] for r in ledger] == list(invoices)
    for r in ledger:
        inv, sup = (
            invoices[r["invoice_id"]],
            suppliers[invoices[r["invoice_id"]]["ico"]],
        )
        assert r["supplier_ico"] == inv["ico"] and r["vs"] == inv["vs"]
        assert r["supplier_account"] == sup["bank_account"]
        assert r["supplier_bank_code"] == sup["bank_code"]
        assert r["gross_amount"] == inv["gross"]
        assert (r["issue_date"], r["due_date"]) == (inv["issue_date"], inv["due_date"])
        assert r["project_code"] == "FVE-2026-02"
        assert r["pdf_only"] == ("true" if inv["isdoc"] == "no" else "false")


def check_mtimes():
    dates = {r["path"]: date.fromisoformat(r["business_date"]) for r in read_csv(FIX / "mtimes_finance.csv")}
    finance_files = {
        str(p.relative_to(SRC)).replace("\\", "/")
        for pattern in (
            "master/*",
            "drive/budgets/*",
            "mailbox/invoices/*",
            "drive/accounting/*",
        )
        for p in SRC.glob(pattern)
        if p.is_file()
    }
    assert set(dates) == finance_files  # every fixture file has a date, none is missing
    for path, day in dates.items():
        m = re.search(r"invoices/\d+_(\d+)\.", path)
        if m:
            number = m.group(1)
            issue = next(e["issue_date"] for e in readme_table("Invoices") if e["number"] == number)
            assert day == date.fromisoformat(issue)
    assert dates["drive/budgets/FVE-2026-02_budget.xlsx"] == date(2026, 1, 20)
    monday = date(2026, 5, 11)
    assert dates["drive/accounting/money_export_2026-W20.csv"] == monday
    assert monday == date.fromisocalendar(2026, 20, 1) and monday.weekday() == 0
    assert dates["master/projects.csv"] == config.DATA_END == dates["master/suppliers.csv"]
    assert timedelta(0) < config.DATA_END - monday
