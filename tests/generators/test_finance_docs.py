"""Tests for the finance document generator (Task 5)."""

import csv
import hashlib
import itertools
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree
from openpyxl import load_workbook

from common import config
from generators.finance_docs import master, money_export, plan
from generators.finance_docs.__main__ import generate
from generators.finance_docs.util import CATEGORIES, DATA_END

SEED = config.SEED
NS = {"i": "http://isdoc.cz/namespace/2013"}
# children of InvoiceLine in the order of the ISDOC 6.0.2 schema (the optional ones the generator writes)
ISDOC_LINE_ORDER = [
    "ID",
    "InvoicedQuantity",
    "LineExtensionAmount",
    "LineExtensionAmountTaxInclusive",
    "LineExtensionTaxAmount",
    "UnitPrice",
    "UnitPriceTaxInclusive",
    "ClassifiedTaxCategory",
    "Item",
]


@pytest.fixture(scope="module")
def built():
    return plan.build_plan(random.Random(SEED), 1)


@pytest.fixture(scope="module")
def run_dirs(tmp_path_factory):
    base = tmp_path_factory.mktemp("fin1")
    stats = generate(SEED, 1, base / "sources", base / "ledger")
    return base / "sources", base / "ledger", stats


def _sha_tree(root: Path) -> dict:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _spend(invoices):
    spent = {}
    for inv in invoices:
        key = (inv.project_code, inv.category)
        spent[key] = spent.get(key, 0) + inv.net
    return spent


def test_same_seed_same_bytes(run_dirs, tmp_path):
    src, led, _ = run_dirs
    generate(SEED, 1, tmp_path / "sources", tmp_path / "ledger")
    assert _sha_tree(src) == _sha_tree(tmp_path / "sources")
    assert _sha_tree(led) == _sha_tree(tmp_path / "ledger")


@pytest.mark.parametrize("scale", [1, 10])
def test_project_codes_valid(scale):
    projects = master.make_projects(random.Random(SEED), scale)
    codes = [p["project_code"] for p in projects]
    assert len(codes) == len(set(codes))
    assert all(config.is_project_code(c) for c in codes)
    per_year = {}
    for c in codes:
        per_year[c[4:8]] = per_year.get(c[4:8], 0) + 1
    assert max(per_year.values()) <= 99
    if scale == 1:
        assert all(8 <= n <= 9 for n in per_year.values())
        assert 85 <= len(codes) <= 100


def test_project_sites_do_not_overlap(built):
    projects = built[0]
    for p in projects:
        _, _, tlat, tlon = master.TOWN_BY_NAME[p["town"]]
        assert 1.0 <= master.haversine_km(p["lat"], p["lon"], tlat, tlon) <= 5.05
        assert 300 <= p["radius_m"] <= 800
    for i, a in enumerate(projects):
        for b in projects[i + 1 :]:
            assert master.haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) >= 3.0


def test_traffic_light_mix(built):
    projects, _, budgets, invoices = built
    spent = _spend(invoices)
    signed = [p for p in projects if p["status"] != "NOT_SIGNED"]
    green = 0
    for p in signed:
        code = p["project_code"]
        total_spent = sum(v for (c, _), v in spent.items() if c == code)
        total_budget = sum(budgets[code].values())
        cats_ok = all(spent.get((code, cat), 0) <= budgets[code][cat] * Decimal("1.05") for cat in CATEGORIES)
        if cats_ok and total_spent <= total_budget:
            green += 1
    assert green / len(signed) >= 0.60


def test_not_signed_have_no_invoices(built, run_dirs):
    projects, _, budgets, invoices = built
    not_signed = {p["project_code"] for p in projects if p["status"] == "NOT_SIGNED"}
    assert not_signed
    assert not any(inv.project_code in not_signed for inv in invoices)
    assert not (not_signed & set(budgets))
    src, _, _ = run_dirs
    for code in not_signed:
        assert not (src / "drive" / "budgets" / f"{code}_budget.xlsx").exists()
    for p in projects:
        if p["status"] == "NOT_SIGNED":
            assert p["signed_date"] is None and p["construction_start"] is None


def test_budget_total_is_85_to_92_percent(built, run_dirs):
    projects = {p["project_code"]: p for p in built[0]}
    src, _, _ = run_dirs
    files = sorted((src / "drive" / "budgets").glob("*.xlsx"))
    assert len(files) == len(built[2])
    for f in files:
        ws = load_workbook(f)["Budget"]
        rows = list(ws.iter_rows(values_only=True))
        assert list(rows[0]) == ["project_code", "category", "amount_czk"]
        assert [r[1] for r in rows[1:]] == CATEGORIES
        code = f.name.split("_")[0]
        total = sum(r[2] for r in rows[1:])
        ratio = total / float(projects[code]["contract_value"])
        assert 0.85 <= ratio <= 0.92
        if not projects[code]["has_battery"]:
            assert {r[1]: r[2] for r in rows[1:]}["BATTERIES"] == 0


def test_spend_per_category_85_to_112_percent(built):
    projects, _, budgets, invoices = built
    spent = _spend(invoices)
    completed = [p for p in projects if p["status"] == "COMPLETED"]
    assert completed
    amber = 0
    for p in completed:
        code = p["project_code"]
        for cat in CATEGORIES:
            budget = budgets[code][cat]
            if budget == 0:
                assert (code, cat) not in spent
                continue
            ratio = float(spent[(code, cat)] / budget)
            assert 0.85 <= ratio <= 1.12, (code, cat, ratio)
            amber += ratio > 1.05
    assert 0 < amber <= len(completed)


def test_nothing_after_data_end(built, run_dirs):
    _, _, _, invoices = built
    assert all(inv.issue_date <= DATA_END for inv in invoices)
    src, _, _ = run_dirs
    for f in (src / "drive" / "accounting").glob("*.csv"):
        with open(f, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                assert date.fromisoformat(row["booking_date"]) <= DATA_END
                assert date.fromisoformat(row["issue_date"]) <= DATA_END
    limit = datetime(DATA_END.year, DATA_END.month, DATA_END.day, 23, 59, tzinfo=timezone.utc)
    for f in src.rglob("*"):
        if f.is_file():
            assert f.stat().st_mtime <= limit.timestamp(), f


def test_isdoc_parses_and_totals_match_lines(run_dirs):
    src, _, _ = run_dirs
    files = sorted((src / "mailbox" / "invoices").glob("*.isdoc"))
    assert files
    for f in files:
        root = etree.parse(str(f)).getroot()
        nets = [float(x.text) for x in root.findall(".//i:InvoiceLine/i:LineExtensionAmount", NS)]
        vats = [float(x.text) for x in root.findall(".//i:InvoiceLine/i:LineExtensionTaxAmount", NS)]
        for line in root.findall(".//i:InvoiceLine", NS):
            assert [etree.QName(c).localname for c in line] == ISDOC_LINE_ORDER
        net = float(root.find("i:LegalMonetaryTotal/i:TaxExclusiveAmount", NS).text)
        gross = float(root.find("i:LegalMonetaryTotal/i:TaxInclusiveAmount", NS).text)
        pay = float(root.find("i:LegalMonetaryTotal/i:PayableAmount", NS).text)
        assert abs(sum(nets) - net) < 0.005
        assert abs(net + sum(vats) - gross) < 0.005
        assert pay == gross
        number = root.find("i:ID", NS).text
        vs = root.find(".//i:Details/i:VariableSymbol", NS)
        assert vs is not None and vs.text == number
        assert f.name.endswith(f"_{number}.isdoc")
        # the PDF shows the same total and VS
        pdf = f.with_suffix(".pdf").read_bytes()
        assert f"{gross:.2f}".replace(".", ",").encode() in pdf
        assert number.encode() in pdf


def test_ten_percent_pdf_only(run_dirs):
    src, _, stats = run_dirs
    d = src / "mailbox" / "invoices"
    pdfs = {p.stem for p in d.glob("*.pdf")}
    isdocs = {p.stem for p in d.glob("*.isdoc")}
    assert isdocs <= pdfs
    share = len(pdfs - isdocs) / len(pdfs)
    assert 0.08 <= share <= 0.12
    assert len(pdfs) == stats["invoices"]


def test_money_export_weeks_have_no_gaps(built, run_dirs):
    src, _, _ = run_dirs
    first = min(p["signed_date"] for p in built[0] if p["signed_date"])
    weeks = []
    for f in sorted((src / "drive" / "accounting").glob("money_export_*.csv")):
        y, w = f.stem.removeprefix("money_export_").split("-W")
        weeks.append(date.fromisocalendar(int(y), int(w), 1))
    assert weeks[0] == first - timedelta(days=first.weekday())
    assert weeks[-1] == DATA_END - timedelta(days=DATA_END.weekday())
    for a, b in itertools.pairwise(weeks):
        assert (b - a).days == 7
    header = ";".join(money_export.COLUMNS)
    empty = [
        f
        for f in (src / "drive" / "accounting").glob("*.csv")
        if f.read_text(encoding="utf-8").strip() == header
    ]
    assert empty  # empty weeks get a header-only file


def test_mtime_is_business_date(built, run_dirs):
    projects, _, _, invoices = built
    src, _, _ = run_dirs

    def noon(d):
        return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp()

    for inv in invoices:
        base = src / "mailbox" / "invoices" / f"{inv.supplier['ico']}_{inv.number}"
        assert base.with_suffix(".pdf").stat().st_mtime == noon(inv.issue_date)
        if not inv.pdf_only:
            assert base.with_suffix(".isdoc").stat().st_mtime == noon(inv.issue_date)
    for p in projects:
        if p["signed_date"]:
            f = src / "drive" / "budgets" / f"{p['project_code']}_budget.xlsx"
            assert f.stat().st_mtime == noon(p["signed_date"])
    for f in (src / "drive" / "accounting").glob("*.csv"):
        y, w = f.stem.removeprefix("money_export_").split("-W")
        assert f.stat().st_mtime == noon(date.fromisocalendar(int(y), int(w), 1))
    for f in (src / "master").glob("*.csv"):
        assert f.stat().st_mtime == noon(DATA_END)


def test_ledger_one_row_per_invoice(built, run_dirs):
    _, led, _ = run_dirs
    with open(led / "invoice_ledger.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(built[3]) == len({r["invoice_id"] for r in rows})
    assert list(rows[0]) == [
        "invoice_id", "supplier_ico", "supplier_account", "supplier_bank_code", "vs",
        "gross_amount", "issue_date", "due_date", "project_code", "pdf_only",
    ]  # fmt: skip
