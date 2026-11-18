"""Tests for the management dashboard drill-down queries."""

import csv
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from warehouse.sql import render, run_file

ROOT = Path(__file__).resolve().parents[2]
DDL = ROOT / "warehouse" / "ddl" / "fve_dw.sql"
QUERIES = ROOT / "warehouse" / "queries"
SAMPLE = QUERIES / "sample_fill.sql"
V3 = QUERIES / "v3_category_suppliers.sql"
V4 = QUERIES / "v4_supplier_invoices.sql"
NOTE = ROOT / "notebooks" / "management_dashboard_2N8K6MZZH.zpln"

# Paragraph of the dashboard note -> the query file it wraps (Task 30.1: the note reuses the merged queries
# and only adds Czech (English) labels, the traffic-light symbols and the project filter).
NOTE_QUERIES = {
    1: "v1_project_list",
    2: "v1_project_list",
    4: "q1_budget_vs_actual",
    5: "v3_category_suppliers",
    6: "v4_supplier_invoices",
    7: "q3_cumulative_spend",
    8: "q5_cost_per_mwp",
    9: "q4_overrun_rank",
    10: "q2_category_by_year",
}
# Zeppelin fills $${name} from the note form's current value, else from the default in the same paragraph, so
# every paragraph repeats the default (a bare $${project} would be empty until the form is used).
NOTE_FORMS = {
    "project": "$${project=FVE-2026-02}",
    "category": "$${category=PANELS}",
    "supplier": "$${supplier=}",
}
LIGHTS = {"RED": "🔴 červená (red)", "AMBER": "🟡 oranžová (amber)", "GREEN": "🟢 zelená (green)"}


def _words(sql):
    return " ".join(sql.split())


def _note_paragraphs():
    return json.loads(NOTE.read_text(encoding="utf-8"))["paragraphs"]


def _run_paragraph(spark, database, index, **forms):
    """Run one %sparksql paragraph of the note on the sample database with the note forms filled in."""
    text = _note_paragraphs()[index]["text"]
    assert text.startswith("%sparksql\n")
    sql = text.split("\n", 1)[1].replace("fve_dw.", f"{database}.")
    for name, value in forms.items():
        sql = re.sub(r"\$\$\{" + name + r"(=[^}]*)?\}", value, sql)
    assert "$${" not in sql
    return spark.sql(sql).collect()


@pytest.fixture
def dashboard_sample_warehouse(spark_hive, tmp_path):
    """Create an isolated warehouse containing the dashboard sample data."""
    database = f"fve_dw_dashboard_test_{uuid.uuid4().hex[:8]}"
    location = (tmp_path / "dw").as_uri()

    run_file(spark_hive, DDL, DW_DB=database, LAKE_DW=location)
    run_file(spark_hive, SAMPLE, DW_DB=database)

    yield spark_hive, database

    spark_hive.sql(f"DROP DATABASE IF EXISTS {database} CASCADE")


def test_v3_v4_on_sample(dashboard_sample_warehouse):
    """Check supplier totals and invoice details against hand-computed sample values."""
    spark, database = dashboard_sample_warehouse

    project = "FVE-2026-03"
    category = "PANELS"

    # V3: selected project and category -> supplier totals.
    v3_statement = render(
        V3,
        DW_DB=database,
        project=project,
        category=category,
    )[0]
    suppliers = spark.sql(v3_statement).collect()

    assert len(suppliers) == 1
    supplier = suppliers[0]

    assert supplier.supplier == "Fictional Solar Supplies"
    assert supplier.ico == "10000001"
    assert supplier.invoiced == Decimal("1089.00")
    assert supplier.paid == Decimal("847.00")
    assert supplier.open == Decimal("242.00")
    assert supplier.paid + supplier.open == supplier.invoiced

    # V4: selected project and supplier -> invoice-level details.
    v4_statement = render(
        V4,
        DW_DB=database,
        project=project,
        supplier=supplier.ico,
    )[0]
    invoices = spark.sql(v4_statement).collect()

    assert invoices[0].__fields__ == [
        "invoice_id",
        "invoice_number",
        "issue_date",
        "due_date",
        "gross_amount",
        "payment_status",
        "days_late",
    ]

    actual = [
        (
            row.invoice_id,
            row.invoice_number,
            str(row.issue_date),
            str(row.due_date),
            row.gross_amount,
            row.payment_status,
            row.days_late,
        )
        for row in invoices
    ]

    expected = [
        (
            "10000001-202600006",
            "202600006",
            "2026-02-15",
            "2026-03-01",
            Decimal("242.00"),
            "UNPAID",
            0,
        ),
        (
            "10000001-202500003",
            "202500003",
            "2025-11-15",
            "2025-11-29",
            Decimal("242.00"),
            "PAID",
            0,
        ),
        (
            "10000001-202500006",
            "202500006",
            "2025-12-15",
            "2025-12-29",
            Decimal("302.50"),
            "PAID",
            0,
        ),
        (
            "10000001-202600003",
            "202600003",
            "2026-01-15",
            "2026-01-29",
            Decimal("302.50"),
            "PAID",
            0,
        ),
    ]

    assert actual == expected
    assert len({row.invoice_id for row in invoices}) == 4
    assert sum(row.gross_amount for row in invoices) == supplier.invoiced


def test_dashboard_note_reuses_query_files():
    """The note wraps the merged query files (no own copies), reads the note forms in every drill-down
    paragraph, refreshes every table it reads, and is committed with titles on, code hidden and no results."""
    note = json.loads(NOTE.read_text(encoding="utf-8"))
    paragraphs = note["paragraphs"]
    texts = [p["text"] for p in paragraphs]

    for index, name in NOTE_QUERIES.items():
        (statement,) = render(QUERIES / f"{name}.sql", DW_DB="fve_dw", **NOTE_FORMS)
        assert _words(statement) in _words(texts[index]), (index, name)

    assert texts[0].startswith("%sparksql\nREFRESH TABLE ")
    refreshed = set(re.findall(r"REFRESH TABLE fve_dw\.(\w+);", texts[0]))
    queried = {table for text in texts[1:] for table in re.findall(r"fve_dw\.(\w+)", text)}
    assert queried <= refreshed, sorted(queried - refreshed)

    # Task 30.1: note forms ($${...}) shared by every paragraph; a fixed project or supplier = no drill-down.
    for index in (4, 5, 6, 7):
        assert "'$${project=FVE-2026-02}'" in texts[index], index
    assert "'$${category=PANELS}'" in texts[5]
    assert "'$${supplier=}'" in texts[6]
    assert not re.search(r"'FVE-\d{4}-\d{2}'|'\d{8}'", "".join(texts))
    assert "$${project=FVE-2026-02}" in texts[3]
    assert "$${category=PANELS,PANELS|INVERTERS|" in texts[3]
    assert "$${supplier=}" in texts[3]
    assert set(note["noteForms"]) == {"project", "category", "supplier"}

    for paragraph in paragraphs:
        assert paragraph["title"] and paragraph["config"]["title"], paragraph["id"]
        assert paragraph["config"]["editorHide"], paragraph["title"]
        assert "results" not in paragraph and paragraph["status"] == "READY", paragraph["title"]


def test_dashboard_note_on_sample(dashboard_sample_warehouse):
    """Every SQL paragraph of the note runs on the sample warehouse; P1 shows the Task 11 traffic lights of
    v1_project_list in its order, V2 ends with the project total, V3/V4 give the hand-computed rows."""
    spark, database = dashboard_sample_warehouse
    forms = {"project": "FVE-2024-01", "category": "PANELS", "supplier": "10000001"}
    # P0 holds several REFRESH statements (Zeppelin splits them; spark.sql runs one at a time).
    for index, paragraph in enumerate(_note_paragraphs()[1:], start=1):
        if paragraph["text"].startswith("%sparksql"):
            assert _run_paragraph(spark, database, index, **forms) is not None, paragraph["title"]

    with (QUERIES / "expected" / "v1_project_list.csv").open(encoding="utf-8", newline="") as handle:
        expected_v1 = [(row["project_code"], LIGHTS[row["traffic_light"]]) for row in csv.DictReader(handle)]
    projects = _run_paragraph(spark, database, 1)
    assert [(row["Projekt (project)"], row["Semafor (traffic light)"]) for row in projects] == expected_v1

    # FVE-2024-01 is red through INVERTERS (120 % of its budget): that category comes first, the total last.
    detail = _run_paragraph(spark, database, 4, project="FVE-2024-01")
    assert detail[0]["Kategorie (category)"] == "INVERTERS"
    assert detail[0]["Semafor (traffic light)"] == LIGHTS["RED"]
    assert detail[-1]["Kategorie (category)"] == "Celkem (total)"
    # The total row of every project carries the project's light from V1 (Task 11: a category counts too).
    for project, light in expected_v1:
        total = _run_paragraph(spark, database, 4, project=project)[-1]
        assert (total["Kategorie (category)"], total["Semafor (traffic light)"]) == ("Celkem (total)", light)
    assert detail[-1]["Utraceno (spent)"] == sum(row["Utraceno (spent)"] for row in detail[:-1])

    suppliers = _run_paragraph(spark, database, 5, project="FVE-2026-03", category="PANELS")
    assert [(row["IČO (company ID)"], row["Neuhrazeno (open)"]) for row in suppliers] == [
        ("10000001", Decimal("242.00"))
    ]
    invoices = _run_paragraph(spark, database, 6, project="FVE-2026-03", supplier="10000001")
    numbers = [row["Faktura (invoice)"] for row in invoices]
    assert numbers == ["202600006", "202500003", "202500006", "202600003"]

    curve = _run_paragraph(spark, database, 7, project="FVE-2024-01")
    months = [row["Měsíc (month)"] for row in curve]
    assert months == sorted(months) and len(months) > 1
    assert curve[-1]["Utraceno celkem (cumulative spend)"] == sum(
        row["Utraceno v měsíci (spent in the month)"] for row in curve
    )
