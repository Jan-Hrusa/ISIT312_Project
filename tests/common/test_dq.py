import pytest

from common.dq import ISSUE_TYPES, JOBS, issue_rows, write_issues
from common.tables import read_table


def _issues(spark, *types):
    return issue_rows(spark, [(t, "isdoc", f"ref-{i}", "FVE-2026-02", "detail") for i, t in enumerate(types)])


def _count(spark, job):
    return read_table(spark, "dq_issues").where(f"job = '{job}'").count()


def test_issue_types_and_jobs():
    assert len(ISSUE_TYPES) == 10 and "WRONG_VERSION" in ISSUE_TYPES
    assert JOBS == ("ingest", "bank", "finance", "matching", "media")


def test_write_issues_rejects_unknown_type(clean_db):
    spark = clean_db
    with pytest.raises(ValueError, match="unknown issue_type: TYPO"):
        write_issues(spark, _issues(spark, "DUPLICATE", "TYPO"), "finance")
    with pytest.raises(ValueError, match="unknown job: nightly"):
        write_issues(spark, _issues(spark, "DUPLICATE"), "nightly")
    assert read_table(spark, "dq_issues").count() == 0


def test_write_issues_overwrites_only_its_job(clean_db):
    spark = clean_db
    assert write_issues(spark, _issues(spark, "DUPLICATE", "MISSING_VS", "NO_PROJECT"), "finance") == 3
    assert write_issues(spark, _issues(spark, "UNMATCHED_PAYMENT", "ORDER_NOT_CLEARED"), "matching") == 2

    # Re-running finance replaces its issues and leaves matching alone.
    assert write_issues(spark, _issues(spark, "OVERRUN"), "finance") == 1
    assert (_count(spark, "finance"), _count(spark, "matching")) == (1, 2)

    rows = read_table(spark, "dq_issues").collect()
    assert len({r.issue_id for r in rows}) == 3
    assert all(r.detected_at is not None for r in rows)
    assert {r.issue_type for r in rows if r.job == "finance"} == {"OVERRUN"}


def test_write_issues_empty_df_clears_partition(clean_db):
    spark = clean_db
    write_issues(spark, _issues(spark, "NO_GPS", "UNASSIGNED_PHOTO"), "media")
    write_issues(spark, _issues(spark, "PARSE_ERROR"), "bank")
    assert write_issues(spark, issue_rows(spark, []), "media") == 0
    assert (_count(spark, "media"), _count(spark, "bank")) == (0, 1)
