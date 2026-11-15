"""Tests for the warehouse OLAP queries and sample data."""

import csv
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from warehouse.sql import render, run_file

ROOT = Path(__file__).resolve().parents[2]
DDL = ROOT / "warehouse" / "ddl" / "fve_dw.sql"
SAMPLE = ROOT / "warehouse" / "queries" / "sample_fill.sql"
Q1 = ROOT / "warehouse" / "queries" / "q1_budget_vs_actual.sql"
Q2 = ROOT / "warehouse" / "queries" / "q2_category_by_year.sql"
Q3 = ROOT / "warehouse" / "queries" / "q3_cumulative_spend.sql"
Q4 = ROOT / "warehouse" / "queries" / "q4_overrun_rank.sql"
Q5 = ROOT / "warehouse" / "queries" / "q5_cost_per_mwp.sql"
Q6 = ROOT / "warehouse" / "queries" / "q6_month_on_month.sql"
V1 = ROOT / "warehouse" / "queries" / "v1_project_list.sql"
EXPECTED = ROOT / "warehouse" / "queries" / "expected"


def _value(value):
    """A cell for comparison: numbers as Decimal (2000 equals 2000.00), an empty CSV cell as None."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return str(value)


def _sort_key(row):
    return tuple((value is None, 0 if value is None else value) for value in row)


def _assert_matches_expected(rows, query, ordered=False):
    """Compare a query result with the hand-computed `expected/<query>.csv`: same column names in the same
    order and the same rows (in the same order too when the query has an ORDER BY)."""
    with (EXPECTED / f"{query.stem}.csv").open(encoding="utf-8", newline="") as f:
        header, *lines = list(csv.reader(f))
    assert rows[0].__fields__ == header
    actual = [tuple(_value(value) for value in row) for row in rows]
    expected = [tuple(_value(value) for value in line) for line in lines]
    if not ordered:
        actual, expected = sorted(actual, key=_sort_key), sorted(expected, key=_sort_key)
    assert actual == expected


@pytest.fixture
def sample_warehouse(spark_hive, tmp_path):
    """Create a fresh warehouse and load the synthetic sample data."""
    database = f"fve_dw_test_{uuid.uuid4().hex[:8]}"
    location = (tmp_path / "dw").as_uri()

    run_file(spark_hive, DDL, DW_DB=database, LAKE_DW=location)
    run_file(spark_hive, SAMPLE, DW_DB=database)

    yield spark_hive, database

    spark_hive.sql(f"DROP DATABASE IF EXISTS {database} CASCADE")


def test_sample_fill_loads_expected_data(sample_warehouse):
    spark, database = sample_warehouse

    assert spark.sql(f"SELECT COUNT(*) FROM {database}.dim_project").first()[0] == 3

    assert spark.sql(f"SELECT COUNT(*) FROM {database}.dim_cost_category").first()[0] == 4

    assert spark.sql(f"SELECT COUNT(*) FROM {database}.fact_budget_line").first()[0] == 12

    assert spark.sql(f"SELECT COUNT(*) FROM {database}.fact_invoice_line").first()[0] == 36

    # One line per invoice, ids in the contract form <ico>-<number>.
    invoices = spark.sql(f"SELECT invoice_id, supplier_key FROM {database}.fact_invoice_line").collect()
    assert len({row.invoice_id for row in invoices}) == 36
    assert all(row.invoice_id.startswith(f"1000000{row.supplier_key}-20") for row in invoices)

    statuses = spark.sql(
        f"SELECT payment_status, COUNT(*) AS n FROM {database}.fact_invoice_line GROUP BY payment_status"
    ).collect()
    assert {row.payment_status: row.n for row in statuses} == {
        "PAID": 26,
        "PARTLY_PAID": 1,
        "UNPAID": 8,
        "OVERDUE": 1,
    }

    # Every PAID invoice has debits adding up to its gross amount; the PARTLY_PAID one is half paid;
    # UNPAID and OVERDUE invoices have none.
    paid = spark.sql(
        f"""
        SELECT i.payment_status, i.amount_gross, COALESCE(p.paid, 0) AS paid
        FROM {database}.fact_invoice_line i
        LEFT JOIN (
            SELECT invoice_id, SUM(amount) AS paid
            FROM {database}.fact_payment
            GROUP BY invoice_id
        ) p
          ON i.invoice_id = p.invoice_id
        """
    ).collect()
    for row in paid:
        if row.payment_status == "PAID":
            assert row.paid == row.amount_gross
        elif row.payment_status == "PARTLY_PAID":
            assert row.paid == row.amount_gross / 2
        else:
            assert row.paid == 0
    assert spark.sql(f"SELECT COUNT(*) FROM {database}.fact_payment").first()[0] == 27

    # Every date key used by a fact has its dim_date row (the queries join on it).
    missing = spark.sql(
        f"""
        SELECT k.date_key
        FROM (
            SELECT issue_date_key AS date_key FROM {database}.fact_invoice_line
            UNION SELECT due_date_key FROM {database}.fact_invoice_line
            UNION SELECT date_key FROM {database}.fact_payment
            UNION SELECT date_key FROM {database}.fact_budget_line
        ) k
        LEFT JOIN {database}.dim_date d
          ON k.date_key = d.date_key
        WHERE d.date_key IS NULL
        """
    ).collect()
    assert missing == []
    budget_rows = spark.sql(
        f"""
        SELECT p.project_code, SUM(b.budget_amount) AS budget
        FROM {database}.fact_budget_line b
        JOIN {database}.dim_project p
          ON b.project_key = p.project_key
        GROUP BY p.project_code
        """
    ).collect()

    actual_budgets = {row.project_code: float(row.budget) for row in budget_rows}

    assert actual_budgets == {
        "FVE-2024-01": 2000.0,
        "FVE-2025-02": 2000.0,
        "FVE-2026-03": 2000.0,
    }
    rows = spark.sql(
        f"""
        SELECT p.project_code, SUM(i.amount_net) AS spent
        FROM {database}.fact_invoice_line i
        JOIN {database}.dim_project p
          ON i.project_key = p.project_key
        GROUP BY p.project_code
        """
    ).collect()

    actual = {row.project_code: float(row.spent) for row in rows}

    expected = {
        "FVE-2024-01": 2300.0,
        "FVE-2025-02": 2095.0,
        "FVE-2026-03": 1800.0,
    }

    assert actual == expected


def test_q1_rollup_totals(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q1, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q1)

    # Check the exact output column names and order.
    assert rows[0].__fields__ == [
        "project_code",
        "category_code",
        "budget",
        "spent",
        "difference",
        "pct_spent",
    ]

    # 12 project/category rows, 3 project subtotals, 1 grand total.
    assert len(rows) == 16

    # Check the grand total.
    grand_total = next(row for row in rows if row.project_code is None and row.category_code is None)

    assert float(grand_total.budget) == 6000.0
    assert float(grand_total.spent) == 6195.0
    assert float(grand_total.difference) == -195.0

    # Check each project's subtotal.
    expected = {
        "FVE-2024-01": (2000.0, 2300.0),
        "FVE-2025-02": (2000.0, 2095.0),
        "FVE-2026-03": (2000.0, 1800.0),
    }

    for project_code, (budget, spent) in expected.items():
        subtotal = next(row for row in rows if row.project_code == project_code and row.category_code is None)

        assert float(subtotal.budget) == budget
        assert float(subtotal.spent) == spent


def test_q2_cube_has_all_combinations(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q2, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q2)

    # Five group/year combinations, three group totals,
    # two year totals, and one grand total.
    assert len(rows) == 11

    actual = {(row.group_name, row.year): float(row.spent) for row in rows}

    expected = {
        ("technology", 2025): 2370.0,
        ("technology", 2026): 2360.0,
        ("construction", 2025): 580.0,
        ("construction", 2026): 305.0,
        ("services", 2026): 580.0,
        ("technology", None): 4730.0,
        ("construction", None): 885.0,
        ("services", None): 580.0,
        (None, 2025): 2950.0,
        (None, 2026): 3245.0,
        (None, None): 6195.0,
    }

    assert actual == expected


def test_q3_running_total_last_equals_total(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q3, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q3)

    expected_totals = {
        "FVE-2024-01": 2300.0,
        "FVE-2025-02": 2095.0,
        "FVE-2026-03": 1800.0,
    }

    for project_code, expected_total in expected_totals.items():
        project_rows = sorted(
            [row for row in rows if row.project_code == project_code],
            key=lambda row: row.year * 100 + row.month,
        )

        # Each project has four months of sample spending.
        assert len(project_rows) == 4

        # The last cumulative value must equal total project spending.
        assert float(project_rows[-1].cumulative_spend) == expected_total

        # Cumulative spending must never decrease.
        cumulative_values = [float(row.cumulative_spend) for row in project_rows]
        assert cumulative_values == sorted(cumulative_values)

        # The dates must cross from 2025 into 2026 in the correct order.
        assert [(row.year, row.month) for row in project_rows] == [
            (2025, 11),
            (2025, 12),
            (2026, 1),
            (2026, 2),
        ]


def test_q4_rank_order(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q4, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q4)

    actual = {
        row.category_code: (
            int(row.projects_over),
            float(row.avg_overrun_pct),
            int(row.category_rank),
        )
        for row in rows
    }

    expected = {
        "PANELS": (2, 14.0, 1),
        "INVERTERS": (1, 20.0, 2),
        "STRUCTURES": (1, 5.0, 3),
        "DESIGN": (0, 0.0, 4),
    }

    # avg_overrun_pct averages only the projects that are over: INVERTERS is 20% over in one of the two
    # COMPLETED projects (not 10%), PANELS 20% and 8% (14%).
    assert actual == expected

    # The ACTIVE project must not contribute to the rankings.
    assert all(row.projects_over <= 2 for row in rows)


def test_q5_cost_per_mwp(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q5, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q5)

    actual = {
        (row.project_code, int(row.signed_year)): (
            float(row.mwp),
            float(row.total_spent),
            float(row.cost_per_mwp),
        )
        for row in rows
    }

    expected = {
        ("FVE-2024-01", 2024): (2.0, 2300.0, 1150.0),
        ("FVE-2025-02", 2025): (1.5, 2095.0, 1396.67),
        # One row per signed year (project_code NULL): the year's spending divided by the year's MWp.
        (None, 2024): (2.0, 2300.0, 1150.0),
        (None, 2025): (1.5, 2095.0, 1396.67),
    }

    assert actual == expected

    # Only COMPLETED projects should be included.
    assert all(row.project_code != "FVE-2026-03" for row in rows)
    assert all(row.signed_year != 2026 for row in rows)


def test_q5_year_row_divides_totals(sample_warehouse):
    spark, database = sample_warehouse

    # A second COMPLETED project signed in 2024: 1 MWp and 100 spent.
    spark.sql(
        f"""
        INSERT INTO {database}.dim_project
        SELECT 4, 'FVE-2024-09', 'Solar Project Delta', 'Brno', 'South Moravia',
            CAST(1.00 AS DECIMAL(5,2)), FALSE, CAST(900000.00 AS DECIMAL(14,2)),
            'COMPLETED', 2024, CAST('2024-05-01' AS DATE), CAST('2025-08-31' AS DATE)
        """
    )
    spark.sql(
        f"""
        INSERT INTO {database}.fact_invoice_line PARTITION (issue_year=2025)
        SELECT '10000001-202500099', 1, 4, 1, 1, 20251115, 20251129, 100.00, 21.00, 121.00, 'PAID', 0
        """
    )

    rows = spark.sql(render(Q5, DW_DB=database)[0]).collect()
    year = next(row for row in rows if row.project_code is None and row.signed_year == 2024)

    # (2300 + 100) / (2.00 + 1.00), not the average of 1150 and 100.
    assert (float(year.mwp), float(year.total_spent), float(year.cost_per_mwp)) == (3.0, 2400.0, 800.0)


def test_q6_first_month_lag_is_null(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q6, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, Q6)

    expected_monthly_spend = {
        "FVE-2024-01": [500.0, 600.0, 600.0, 600.0],
        "FVE-2025-02": [500.0, 500.0, 500.0, 595.0],
        "FVE-2026-03": [400.0, 450.0, 450.0, 500.0],
    }

    for project_code, expected_spend in expected_monthly_spend.items():
        project_rows = sorted(
            [row for row in rows if row.project_code == project_code],
            key=lambda row: row.year * 100 + row.month,
        )

        assert len(project_rows) == 4

        # First available month has no previous month.
        assert project_rows[0].prev_month_with_spend is None
        assert project_rows[0].month_on_month_change is None
        assert project_rows[0].month_on_month_pct is None

        actual_spend = [float(row.spent) for row in project_rows]
        assert actual_spend == expected_spend

        # Each later month's previous value equals the preceding month's spend.
        for index in range(1, len(project_rows)):
            assert float(project_rows[index].prev_month_with_spend) == expected_spend[index - 1]
            assert float(project_rows[index].month_on_month_change) == (
                expected_spend[index] - expected_spend[index - 1]
            )
            assert float(project_rows[index].month_on_month_pct) == round(
                (expected_spend[index] - expected_spend[index - 1]) * 100 / expected_spend[index - 1], 2
            )


def test_v1_traffic_lights(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(V1, DW_DB=database)[0]
    rows = spark.sql(statement).collect()
    _assert_matches_expected(rows, V1, ordered=True)

    # Check the exact dashboard column names and order.
    assert rows[0].__fields__ == [
        "project_code",
        "name",
        "region",
        "mwp",
        "status",
        "contract_value",
        "budget",
        "spent",
        "pct_spent",
        "expected_margin",
        "traffic_light",
    ]

    # Results should be ordered RED, AMBER, GREEN.
    assert [row.traffic_light for row in rows] == [
        "RED",
        "AMBER",
        "GREEN",
    ]

    expected = {
        "FVE-2024-01": (2300.0, 115.0, "RED"),
        "FVE-2025-02": (2095.0, 104.75, "AMBER"),
        "FVE-2026-03": (1800.0, 90.0, "GREEN"),
    }

    actual = {
        row.project_code: (
            float(row.spent),
            float(row.pct_spent),
            row.traffic_light,
        )
        for row in rows
    }

    assert actual == expected
    expected_details = {
        "FVE-2024-01": (2000.0, 2997700.0, "COMPLETED"),
        "FVE-2025-02": (2000.0, 2497905.0, "COMPLETED"),
        "FVE-2026-03": (2000.0, 1798000.0, "ACTIVE"),
    }
    actual_details = {
        row.project_code: (
            float(row.budget),
            float(row.expected_margin),
            row.status,
        )
        for row in rows
    }
    assert actual_details == expected_details
    # NOT_SIGNED projects should not appear.
    assert len(rows) == 3


def test_q6_compares_with_previous_month_with_spend(sample_warehouse):
    spark, database = sample_warehouse

    # A project invoiced in November and February only: the comparison skips the empty months.
    spark.sql(
        f"""
        INSERT INTO {database}.dim_project
        SELECT 4, 'FVE-2024-09', 'Solar Project Delta', 'Brno', 'South Moravia',
            CAST(1.00 AS DECIMAL(5,2)), FALSE, CAST(900000.00 AS DECIMAL(14,2)),
            'COMPLETED', 2024, CAST('2024-05-01' AS DATE), CAST('2025-08-31' AS DATE)
        """
    )
    spark.sql(
        f"""
        INSERT INTO {database}.fact_invoice_line PARTITION (issue_year=2025)
        SELECT '10000001-202500099', 1, 4, 1, 1, 20251115, 20251129, 100.00, 21.00, 121.00, 'PAID', 0
        """
    )
    spark.sql(
        f"""
        INSERT INTO {database}.fact_invoice_line PARTITION (issue_year=2026)
        SELECT '10000001-202600099', 1, 4, 1, 1, 20260215, 20260301, 150.00, 31.50, 181.50, 'UNPAID', 0
        """
    )

    rows = spark.sql(render(Q6, DW_DB=database)[0]).collect()
    february = next(row for row in rows if row.project_code == "FVE-2024-09" and row.month == 2)

    assert float(february.prev_month_with_spend) == 100.0
    assert float(february.month_on_month_change) == 50.0
    assert float(february.month_on_month_pct) == 50.0
