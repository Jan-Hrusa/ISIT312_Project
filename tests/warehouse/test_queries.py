"""Tests for the warehouse OLAP queries and sample data."""

import uuid
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
        "INVERTERS": (1, 10.0, 2),
        "STRUCTURES": (1, 2.5, 3),
        "DESIGN": (0, 0.0, 4),
    }

    assert actual == expected

    # The ACTIVE project must not contribute to the rankings.
    assert all(row.projects_over <= 2 for row in rows)


def test_q5_cost_per_mwp(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q5, DW_DB=database)[0]
    rows = spark.sql(statement).collect()

    actual = {
        row.project_code: (
            int(row.signed_year),
            float(row.mwp),
            float(row.total_spent),
            float(row.cost_per_mwp),
        )
        for row in rows
    }

    expected = {
        "FVE-2024-01": (2024, 2.0, 2300.0, 1150.0),
        "FVE-2025-02": (2025, 1.5, 2095.0, 1396.67),
    }

    assert actual == expected

    # Only COMPLETED projects should be included.
    assert "FVE-2026-03" not in actual
    assert len(rows) == 2


def test_q6_first_month_lag_is_null(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(Q6, DW_DB=database)[0]
    rows = spark.sql(statement).collect()

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
        assert project_rows[0].previous_month_spent is None
        assert project_rows[0].month_on_month_change is None

        actual_spend = [float(row.spent) for row in project_rows]
        assert actual_spend == expected_spend

        # Each later month's previous value equals the preceding month's spend.
        for index in range(1, len(project_rows)):
            assert float(project_rows[index].previous_month_spent) == expected_spend[index - 1]
            assert float(project_rows[index].month_on_month_change) == (
                expected_spend[index] - expected_spend[index - 1]
            )


def test_v1_traffic_lights(sample_warehouse):
    spark, database = sample_warehouse

    statement = render(V1, DW_DB=database)[0]
    rows = spark.sql(statement).collect()

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
