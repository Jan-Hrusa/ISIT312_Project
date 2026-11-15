"""Task 26: Run warehouse loads and validation checks."""

from pathlib import Path

from common import config
from warehouse.sql import named_queries, run_file

ROOT = Path(__file__).resolve().parents[1]


def run(spark) -> dict[str, int]:
    """Load the warehouse and return row counts; fail on invalid checks."""

    # Allow dynamic partition inserts.
    spark.conf.set("hive.exec.dynamic.partition", "true")
    spark.conf.set("hive.exec.dynamic.partition.mode", "nonstrict")

    # 1. Create warehouse tables.
    run_file(spark, ROOT / "ddl" / "fve_dw.sql")

    # 2. Load dimensions, followed by facts.
    run_file(spark, ROOT / "etl" / "load_dims.sql")
    run_file(spark, ROOT / "etl" / "load_facts.sql")

    # 3. Execute all named validation checks.
    failures = []
    checks = named_queries(ROOT / "etl" / "checks.sql")

    for name, query in checks.items():
        rows = spark.sql(query).collect()

        if len(rows) != 1:
            failures.append(name)
            continue

        result = rows[0]
        print(f"{name}: ok={result['ok']}, {result['detail']}")

        if result["ok"] is not True:
            failures.append(name)

    if failures:
        raise RuntimeError(
            "warehouse checks failed: " + ", ".join(failures)
        )

    # 4. Return row counts.
    tables = [
        "dim_project",
        "dim_supplier",
        "dim_cost_category",
        "dim_date",
        "dim_bank_account",
        "fact_budget_line",
        "fact_invoice_line",
        "fact_payment",
        "fact_payment_order",
    ]

    counts = {
        table: spark.table(f"{config.DW_DB}.{table}").count()
        for table in tables
    }
    counts["checks_failed"] = 0

    return counts
