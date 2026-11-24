"""Unit tests for Task 13 finance parsers and processing.finance.run."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from py4j.protocol import Py4JJavaError

from common import config, tables
from processing.finance import (
    FinanceParseError,
    budgets,
    invoice_pdf,
    isdoc,
    money_export,
    run,
)


def _fixture_inputs(root: Path) -> dict[str, list[str]]:
    return {
        "master": [
            (root / "master/projects.csv").as_uri(),
            (root / "master/suppliers.csv").as_uri(),
        ],
        "budgets": [p.as_uri() for p in sorted((root / "drive/budgets").glob("*.xlsx"))],
        "isdoc": [p.as_uri() for p in sorted((root / "mailbox/invoices").glob("*.isdoc"))],
        "invoice_pdf": [p.as_uri() for p in sorted((root / "mailbox/invoices").glob("*.pdf"))],
        "accounting": [p.as_uri() for p in sorted((root / "drive/accounting").glob("*.csv"))],
    }


def test_parse_isdoc_sample(fixtures_dir: Path) -> None:
    """Verify header fields and exact line count on the sample ISDOC fixture."""
    path1 = fixtures_dir / "sources/mailbox/invoices/20400013_202600014.isdoc"
    inv1, lines1 = isdoc.parse(path1.read_bytes(), "raw/20400013_202600014.isdoc")

    assert inv1["invoice_id"] == "20400013-202600014"
    assert inv1["supplier_ico"] == "20400013"
    assert inv1["number"] == "202600014"
    assert inv1["vs"] == "202600014"
    assert inv1["issue_date"] == date(2026, 5, 4)
    assert inv1["due_date"] == date(2026, 5, 22)
    assert inv1["total_net"] == Decimal("120000.00")
    assert inv1["total_vat"] == Decimal("25200.00")
    assert inv1["total_gross"] == Decimal("145200.00")
    assert inv1["currency"] == "CZK"
    assert inv1["category"] is None
    assert inv1["project_code"] is None
    assert inv1["project_rule"] is None
    assert inv1["has_isdoc"] is True
    assert inv1["source_file"] == "raw/20400013_202600014.isdoc"
    assert len(lines1) == 1
    assert lines1[0]["line_no"] == 1
    assert lines1[0]["description"] == "Fotovoltaicky panel 545 Wp mono"
    assert lines1[0]["quantity"] == Decimal("10.000")
    assert lines1[0]["unit_price"] == Decimal("12000.00")
    assert lines1[0]["amount_net"] == Decimal("120000.00")
    assert lines1[0]["vat_rate"] == Decimal("21.00")
    assert lines1[0]["vat_amount"] == Decimal("25200.00")

    path2 = fixtures_dir / "sources/mailbox/invoices/30550026_202600003.isdoc"
    inv2, lines2 = isdoc.parse(path2.read_bytes(), "raw/30550026_202600003.isdoc")
    assert inv2["invoice_id"] == "30550026-202600003"
    assert len(lines2) == 3

    path3 = fixtures_dir / "sources/mailbox/invoices/41700032_202600021.isdoc"
    inv3, lines3 = isdoc.parse(path3.read_bytes(), "raw/41700032_202600021.isdoc")
    assert inv3["invoice_id"] == "41700032-202600021"
    assert len(lines3) == 5


def test_isdoc_totals_equal_lines(fixtures_dir: Path) -> None:
    """Invoice net and VAT totals must equal the sum of their lines."""
    invoices_dir = fixtures_dir / "sources/mailbox/invoices"
    for path in sorted(invoices_dir.glob("*.isdoc")):
        inv, lines = isdoc.parse(path.read_bytes(), str(path))
        sum_net = sum((ln["amount_net"] for ln in lines), Decimal("0.00"))
        sum_vat = sum((ln["vat_amount"] for ln in lines), Decimal("0.00"))
        assert inv["total_net"] == sum_net
        assert inv["total_vat"] == sum_vat
        assert inv["total_gross"] == inv["total_net"] + inv["total_vat"]


def test_isdoc_missing_vs_is_null(fixtures_dir: Path) -> None:
    """Missing, empty, or all-zero VariableSymbol becomes None; leading zeros are stripped."""
    path = fixtures_dir / "sources/mailbox/invoices/20400013_202600014.isdoc"
    raw_xml = path.read_text(encoding="utf-8")

    xml_empty = raw_xml.replace(
        "<VariableSymbol>202600014</VariableSymbol>",
        "<VariableSymbol>   </VariableSymbol>",
    ).encode("utf-8")
    inv_empty, _ = isdoc.parse(xml_empty, "raw/empty_vs.isdoc")
    assert inv_empty["vs"] is None

    xml_removed = raw_xml.replace("<VariableSymbol>202600014</VariableSymbol>", "").encode("utf-8")
    inv_removed, _ = isdoc.parse(xml_removed, "raw/no_vs.isdoc")
    assert inv_removed["vs"] is None

    # Leading zeros stripped
    xml_leading = raw_xml.replace(
        "<VariableSymbol>202600014</VariableSymbol>",
        "<VariableSymbol>000202600014</VariableSymbol>",
    ).encode("utf-8")
    inv_leading, _ = isdoc.parse(xml_leading, "raw/leading_vs.isdoc")
    assert inv_leading["vs"] == "202600014"


def test_decimal_comma() -> None:
    """Decimal comma with spaces or non-breaking spaces parses to Decimal(14,2)."""
    assert money_export.parse_decimal_comma("1234,50") == Decimal("1234.50")
    assert money_export.parse_decimal_comma("1 234,50") == Decimal("1234.50")
    assert money_export.parse_decimal_comma("1\u00a0234,50") == Decimal("1234.50")


def test_budget_has_10_categories(fixtures_dir: Path) -> None:
    """Budget XLSX parses all 10 categories; unknown category raises FinanceParseError."""
    path = fixtures_dir / "sources/drive/budgets/FVE-2026-02_budget.xlsx"
    rows = budgets.parse_budget(path.read_bytes(), "raw/FVE-2026-02_budget.xlsx")
    assert len(rows) == 10
    assert {r["category"] for r in rows} == set(config.CATEGORIES)
    assert all(r["project_code"] == "FVE-2026-02" for r in rows)
    assert sum((r["amount"] for r in rows), Decimal("0.00")) == Decimal("28160000.00")


def test_pdf_only_invoice_row() -> None:
    """PDF-only invoice header has IDs filled, amounts/dates/vs NULL, and has_isdoc=False."""
    source_path = "/lake/raw/invoice_pdf/2026/05/63900051_202600008__20261114093000.pdf"
    row = invoice_pdf.header("63900051_202600008.pdf", source_path)
    assert row["invoice_id"] == "63900051-202600008"
    assert row["supplier_ico"] == "63900051"
    assert row["number"] == "202600008"
    assert row["vs"] is None
    assert row["issue_date"] is None
    assert row["due_date"] is None
    assert row["total_net"] is None
    assert row["total_vat"] is None
    assert row["total_gross"] is None
    assert row["currency"] == "CZK"
    assert row["category"] is None
    assert row["project_code"] is None
    assert row["project_rule"] is None
    assert row["has_isdoc"] is False
    assert row["source_file"] == source_path


def test_bad_xml_gives_parse_error() -> None:
    """Corrupted or non-ISDOC XML raises FinanceParseError."""
    with pytest.raises(FinanceParseError):
        isdoc.parse(b"<Invoice><unclosed>", "raw/broken.isdoc")

    with pytest.raises(FinanceParseError):
        isdoc.parse(b"<OtherRoot xmlns='http://isdoc.cz/namespace/2013'/>", "raw/wrong.isdoc")


def test_run_on_fixtures(clean_db, sources_tree: Path) -> None:
    """Running processing.finance.run on the sample fixtures populates all 6 tables accurately."""
    inputs = _fixture_inputs(sources_tree)
    counts = run(clean_db, inputs=inputs)

    assert counts["projects"] == 3
    assert counts["suppliers"] == 5
    assert counts["budget_lines"] == 10
    assert counts["invoices"] == 4
    # 1 + 3 + 5 ISDOC lines plus the PDF-only invoice's line from its booking (Task 20.1)
    assert counts["invoice_lines"] == 10
    assert counts["booked_costs"] == 4
    assert counts["dq_issues"] == 0

    inv_df = tables.read_table(clean_db, "invoices")
    assert inv_df.count() == 4
    pdf_only = inv_df.filter("invoice_id = '63900051-202600008'").first()
    assert pdf_only is not None
    assert pdf_only.has_isdoc is False


def test_run_reads_only_listed_files(clean_db, sources_tree: Path) -> None:
    """run() reads only the listed files (not their neighbours in the same folder), and the PDF of a parsed
    ISDOC gives no second invoice row. A listed file that doesn't exist stops the run: the raw zone is
    write-once, so it is an error of the input list, not a PARSE_ERROR."""
    invoices = sources_tree / "mailbox/invoices"
    inputs = {
        "master": [(sources_tree / "master/projects.csv").as_uri()],
        "isdoc": [(invoices / "20400013_202600014.isdoc").as_uri()],
        "invoice_pdf": [
            (invoices / "20400013_202600014.pdf").as_uri(),
            (invoices / "63900051_202600008.pdf").as_uri(),
        ],
    }
    counts = run(clean_db, inputs=inputs)

    assert counts["projects"] == 3
    assert counts["suppliers"] == 0
    assert counts["invoices"] == 2  # one ISDOC invoice, one PDF-only invoice; the other ISDOCs aren't listed
    assert counts["invoice_lines"] == 1
    # No bookings listed, so neither invoice gets a project: two NO_PROJECT issues (Task 20)
    assert counts["dq_issues"] == 2

    inputs["isdoc"].append((invoices / "99999999_202600001.isdoc").as_uri())
    with pytest.raises(Py4JJavaError, match="Input path does not exist"):
        run(clean_db, inputs=inputs)
