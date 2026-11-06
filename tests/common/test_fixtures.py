import os
from datetime import date, datetime, timezone

import pytest

from tests.fixtures.make_sources import make_sources


def test_fixtures_run_without_stack(request):
    spark = request.getfixturevalue("spark")
    conf = spark.sparkContext.getConf()
    assert conf.get("spark.sql.catalogImplementation") == "in-memory"
    assert spark.sparkContext._jsc.hadoopConfiguration().get("fs.defaultFS") == "file:///"
    assert spark.range(5).count() == 5

    spark_hive = request.getfixturevalue("spark_hive")
    hadoop = spark_hive.sparkContext._jsc.hadoopConfiguration()
    assert spark_hive.sparkContext.getConf().get("spark.sql.catalogImplementation") == "hive"
    assert hadoop.get("fs.defaultFS") == "file:///"
    assert (hadoop.get("hive.metastore.uris") or "") == ""
    assert "derby" in hadoop.get("javax.jdo.option.ConnectionURL")
    spark_hive.sql("CREATE DATABASE IF NOT EXISTS fixture_check")
    assert "fixture_check" in [r.namespace for r in spark_hive.sql("SHOW DATABASES").collect()]
    spark_hive.sql("DROP DATABASE fixture_check")


def _fixture_set(root):
    sources = root / "sources"
    (sources / "master").mkdir(parents=True)
    (sources / "mailbox" / "bank" / "RB").mkdir(parents=True)
    (sources / "master" / "projects.csv").write_text("project_code\n", encoding="utf-8")
    (sources / "mailbox" / "bank" / "RB" / "26001_2101234567_CZK.gpc").write_bytes(b"074")
    (sources / ".gitkeep").write_text("", encoding="utf-8")
    (root / "mtimes_test.csv").write_text(
        "path,business_date\nmaster/projects.csv,2026-10-31\nmailbox/bank/RB/26001_2101234567_CZK.gpc,2026-01-02\n",
        encoding="utf-8",
    )
    return root


def test_make_sources_sets_mtimes(tmp_path):
    fixtures = _fixture_set(tmp_path / "fixtures")
    out = make_sources(tmp_path / "out", fixtures)

    gpc = out / "mailbox" / "bank" / "RB" / "26001_2101234567_CZK.gpc"
    assert gpc.read_bytes() == b"074"
    assert datetime.fromtimestamp(os.stat(gpc).st_mtime, timezone.utc) == datetime(
        2026, 1, 2, 12, tzinfo=timezone.utc
    )
    projects = out / "master" / "projects.csv"
    assert datetime.fromtimestamp(projects.stat().st_mtime, timezone.utc).date() == date(2026, 10, 31)
    assert not (out / ".gitkeep").exists()


def test_make_sources_rejects_undated_files(tmp_path):
    fixtures = _fixture_set(tmp_path / "fixtures")
    (fixtures / "sources" / "master" / "suppliers.csv").write_text("ico\n", encoding="utf-8")
    with pytest.raises(ValueError, match="without a business date.*master/suppliers.csv"):
        make_sources(tmp_path / "out", fixtures)


def test_sources_tree_fixture(sources_tree):
    assert sources_tree.is_dir()
