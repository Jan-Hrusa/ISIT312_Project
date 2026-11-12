"""Tests for the planted finance problems (Task 17.1)."""

import csv
import hashlib
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree

from common import config
from generators.finance_docs import plan, planted
from generators.finance_docs.__main__ import generate
from generators.finance_docs.util import DATA_END

SEED = config.SEED
NS = {"i": "http://isdoc.cz/namespace/2013"}
EXPECTED = {"OVERRUN": 6, "NO_PROJECT": 25, "DUPLICATE": 5, "MISSING_VS": 10, "PARSE_ERROR": 2}


def noon(day: date) -> float:
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp()


def read_csv(path, delimiter=","):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def sha_tree(root: Path) -> dict:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def planted_plan(scale=1):
    rng = random.Random(SEED)
    projects, suppliers, budgets, invoices = plan.build_plan(rng, scale)
    truth = planted.apply(invoices, projects, rng, budgets=budgets, suppliers=suppliers, scale=scale)
    return SimpleNamespace(
        projects={p["project_code"]: p for p in projects}, budgets=budgets, invoices=invoices, truth=truth
    )


@pytest.fixture(scope="module")
def pplan():
    return planted_plan()


@pytest.fixture(scope="module")
def run_dirs(tmp_path_factory):
    base = tmp_path_factory.mktemp("planted")
    stats = generate(SEED, 1, base / "sources", base / "ledger", plant=True)
    return base / "sources", base / "ledger", stats


def test_planted_counts(run_dirs):
    _, led, stats = run_dirs
    rows = read_csv(led / "planted_finance.csv")
    assert list(rows[0]) == ["problem", "ref", "project_code", "detail"]
    assert dict(Counter(r["problem"] for r in rows)) == EXPECTED
    assert stats["planted"] == EXPECTED
    overruns = Counter(r["ref"].split("/")[1] for r in rows if r["problem"] == "OVERRUN")
    assert overruns == {"EARTHWORKS": 3, "CABLES": 2, "GRID": 1}
    assert len({r["project_code"] for r in rows if r["problem"] == "OVERRUN"}) == 6


def test_planted_counts_scale_2():
    rows = planted_plan(scale=2).truth
    assert dict(Counter(r["problem"] for r in rows)) == {k: 2 * v for k, v in EXPECTED.items()}


def test_planted_is_deterministic(run_dirs, tmp_path):
    src, led, _ = run_dirs
    generate(SEED, 1, tmp_path / "sources", tmp_path / "ledger", plant=True)
    assert (led / "planted_finance.csv").read_bytes() == (
        tmp_path / "ledger" / "planted_finance.csv"
    ).read_bytes()
    assert sha_tree(src) == sha_tree(tmp_path / "sources")
    assert sha_tree(led) == sha_tree(tmp_path / "ledger")


def test_overrun_projects_exceed_115_percent(pplan):
    spent = defaultdict(Decimal)
    for inv in pplan.invoices:
        spent[(inv.project_code, inv.category)] += inv.net
    pairs = [tuple(r["ref"].split("/")) for r in pplan.truth if r["problem"] == "OVERRUN"]
    assert len(pairs) == 6
    for code, cat in pairs:
        ratio = spent[(code, cat)] / pplan.budgets[code][cat]
        assert Decimal("1.18") <= ratio <= Decimal("1.30"), (code, cat, ratio)
        p = pplan.projects[code]
        assert p["status"] in ("COMPLETED", "ACTIVE")
        assert (min(p["construction_end"], DATA_END) - p["construction_start"]).days >= 183
        for inv in pplan.invoices:  # every invoice stays inside the construction period and DATA_END
            if inv.project_code == code:
                assert p["construction_start"] <= inv.issue_date <= min(p["construction_end"], DATA_END)
    # nothing else goes above 115%: the planted overruns are the only red projects
    for (code, cat), value in spent.items():
        if (code, cat) not in set(pairs):
            assert value / pplan.budgets[code][cat] <= Decimal("1.12"), (code, cat)


def test_no_invoice_planted_twice(pplan):
    refs = [r["ref"] for r in pplan.truth if r["problem"] != "OVERRUN"]
    assert len(refs) == 42 == len(set(refs))
    ids = {inv.invoice_id for inv in pplan.invoices}
    assert set(refs) <= ids
    for inv in pplan.invoices:
        flags = [
            inv.vs is None,
            inv.booked_project_code is None,
            "resent_date" in inv.extra,
            "truncated" in inv.extra,
        ]
        assert sum(flags) <= 1, inv.invoice_id
    assert len(ids) == len(pplan.invoices)  # invoice ids stay unique, also for the added overrun invoices


def test_no_project_cannot_be_decided_by_the_fallback(pplan, run_dirs):
    src, _, _ = run_dirs
    by_supplier = defaultdict(list)
    for inv in pplan.invoices:
        by_supplier[inv.supplier["ico"]].append(inv)
    blank = [inv for inv in pplan.invoices if inv.booked_project_code is None]
    assert len(blank) == 25
    for inv in blank:
        assert inv.booking_date <= DATA_END
        active = set()
        for other in by_supplier[inv.supplier["ico"]]:
            if other.booked_project_code is None or other.booking_date > DATA_END:
                continue
            if abs((other.issue_date - inv.issue_date).days) > 90:
                continue
            p = pplan.projects[other.booked_project_code]
            if p["construction_start"] <= inv.issue_date <= p["construction_end"]:
                active.add(other.booked_project_code)
        assert len(active) >= 2, inv.invoice_id
    rows = []
    for f in (src / "drive" / "accounting").glob("*.csv"):
        rows += read_csv(f, ";")
    assert sorted(r["doc_ref"] for r in rows if not r["project_code"]) == sorted(i.invoice_id for i in blank)


def test_duplicate_and_parse_error_files(pplan, run_dirs):
    src, _, _ = run_dirs
    d = src / "mailbox" / "invoices"
    resent = sorted(d.glob("*_resent.isdoc"))
    assert len(resent) == 5 == len(list(d.glob("*_resent.pdf")))
    for f in resent:
        orig = f.with_name(f.name.replace("_resent", ""))
        a, b = etree.parse(str(orig)).getroot(), etree.parse(str(f)).getroot()
        for path in ("i:ID", "i:IssueDate", "i:LegalMonetaryTotal/i:PayableAmount", ".//i:VariableSymbol"):
            assert a.find(path, NS).text == b.find(path, NS).text
        assert a.find("i:UUID", NS).text != b.find("i:UUID", NS).text
        issue = date.fromisoformat(a.find("i:IssueDate", NS).text)
        sent = [issue + timedelta(days=k) for k in range(1, 6)]
        days = [s for s in sent if f.stat().st_mtime == noon(s)]
        assert len(days) == 1 and days[0] <= DATA_END  # sent 1-5 days later, never after DATA_END
    broken = []
    for f in sorted(d.glob("*.isdoc")):
        try:
            etree.parse(str(f))
        except etree.XMLSyntaxError:
            broken.append(f)
    assert len(broken) == 2
    for f in broken:
        assert f.read_bytes().endswith(b"<InvoiceLines>")
        assert f.with_suffix(".pdf").exists()  # its PDF and booking still exist


def test_missing_vs_everywhere(pplan, run_dirs):
    src, led, _ = run_dirs
    d = src / "mailbox" / "invoices"
    ids = [r["ref"] for r in pplan.truth if r["problem"] == "MISSING_VS"]
    assert len(ids) == 10
    export = {}
    for f in (src / "drive" / "accounting").glob("*.csv"):
        export.update({r["doc_ref"]: r for r in read_csv(f, ";")})
    ledger = {r["invoice_id"]: r for r in read_csv(led / "invoice_ledger.csv")}
    for invoice_id in ids:
        ico, number = invoice_id.split("-")
        root = etree.parse(str(d / f"{ico}_{number}.isdoc")).getroot()
        assert root.find(".//i:VariableSymbol", NS) is None
        assert b"Variabilni symbol" not in (d / f"{ico}_{number}.pdf").read_bytes()
        assert export[invoice_id]["vs"] == ""
        assert ledger[invoice_id]["vs"] == ""
    others = [r for k, r in ledger.items() if k not in ids]
    assert all(r["vs"] for r in others)


@pytest.mark.parametrize("scale", [1, 2])
def test_missing_vs_invoices_are_due_in_time_to_be_paid(scale, pplan):
    # Task 6 pays them with an empty VS; Task 25 sees OVERDUE + UNMATCHED_PAYMENT on DATA_END only then.
    p = pplan if scale == 1 else planted_plan(scale=scale)
    by_id = {inv.invoice_id: inv for inv in p.invoices}
    ids = [r["ref"] for r in p.truth if r["problem"] == "MISSING_VS"]
    assert len(ids) == 10 * scale
    assert all(by_id[i].due_date <= DATA_END - timedelta(days=6) for i in ids)


def test_ledger_has_one_row_per_invoice(pplan, run_dirs):
    _, led, stats = run_dirs
    ledger = read_csv(led / "invoice_ledger.csv")
    ids = [r["invoice_id"] for r in ledger]
    assert len(ids) == len(set(ids)) == stats["invoices"] == len(pplan.invoices)
    assert not any("resent" in i for i in ids)  # a resent duplicate is not a second ledger row
    assert all(config.is_project_code(r["project_code"]) for r in ledger)  # the ledger keeps the true project


def test_nothing_after_data_end_with_planted_problems(run_dirs):
    src, _, _ = run_dirs
    limit = datetime(DATA_END.year, DATA_END.month, DATA_END.day, 23, 59, tzinfo=timezone.utc).timestamp()
    for f in src.rglob("*"):
        if f.is_file():
            assert f.stat().st_mtime <= limit, f
    for f in (src / "drive" / "accounting").glob("*.csv"):
        for r in read_csv(f, ";"):
            assert date.fromisoformat(r["booking_date"]) <= DATA_END
            assert date.fromisoformat(r["issue_date"]) <= DATA_END


def test_default_generate_has_no_planted_problems(tmp_path):
    stats = generate(SEED, 1, tmp_path / "s", tmp_path / "l")
    assert stats["planted"] == {} and stats["invoices"] == 4655
    assert not (tmp_path / "l" / "planted_finance.csv").exists()
