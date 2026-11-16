"""Tests for run_pipeline.py: the steps are fake modules and Spark is never started."""

from __future__ import annotations

import importlib
import os
import sys
import types

import pytest

import run_pipeline
from common import config


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Fake step modules recording their calls; logs go to tmp_path; no Spark session."""
    calls: list[str] = []
    fake_steps = []
    for name, _, function in run_pipeline.STEPS:
        module_name = f"fake_steps.{name}"
        module = types.ModuleType(module_name)

        def run(spark, _name=name):
            calls.append(_name)
            return {"rows": len(calls)}

        setattr(module, function, run)
        monkeypatch.setitem(sys.modules, module_name, module)
        fake_steps.append((name, module_name, function))
    monkeypatch.setattr(run_pipeline, "STEPS", tuple(fake_steps))

    class FakeSpark:
        stopped = False

        def stop(self):
            FakeSpark.stopped = True

    monkeypatch.setattr(run_pipeline, "_spark", FakeSpark)
    monkeypatch.setattr(config, "OUT_DIR", tmp_path)
    monkeypatch.setenv("FVE_DATASET", config.DATASET)
    return types.SimpleNamespace(calls=calls, spark=FakeSpark, out=tmp_path)


def _log(out) -> list[str]:
    (path,) = out.glob("pipeline_*.log")
    return path.read_text(encoding="utf-8").splitlines()


def test_order_of_steps(pipeline):
    assert run_pipeline.main(["--all"]) == 0
    assert pipeline.calls == list(run_pipeline.STEP_NAMES)
    lines = _log(pipeline.out)
    assert [line.split()[0] for line in lines[1:-1]] == list(run_pipeline.STEP_NAMES)
    assert lines[1].startswith("collect OK in ") and lines[1].endswith(" s – rows=1")
    assert lines[-1].startswith("pipeline OK in ") and lines[-1].endswith("(7 steps, 0 skipped)")
    assert pipeline.spark.stopped


def test_steps_option_keeps_order(pipeline):
    assert run_pipeline.main(["--steps", "finance,collect, bank"]) == 0
    assert pipeline.calls == ["collect", "bank", "finance"]


def test_missing_step_is_skipped(pipeline, monkeypatch, capsys):
    steps = list(run_pipeline.STEPS)
    steps[3] = ("matching", "fake_steps.not_merged_module", "run")  # module does not exist
    no_run = types.ModuleType("fake_steps.no_run")  # module exists without run(), like processing.media
    monkeypatch.setitem(sys.modules, "fake_steps.no_run", no_run)
    steps[4] = ("media", "fake_steps.no_run", "run")
    monkeypatch.setattr(run_pipeline, "STEPS", tuple(steps))

    assert run_pipeline.main(["--all"]) == 0
    assert pipeline.calls == ["collect", "bank", "finance", "warehouse", "catalogue"]
    out = capsys.readouterr().out
    assert "SKIPPED matching: not merged yet" in out
    assert "SKIPPED media: not merged yet" in out
    assert _log(pipeline.out)[-1].endswith("(5 steps, 2 skipped)")


def test_broken_import_is_a_failure_not_a_skip(pipeline, monkeypatch, tmp_path):
    # A merged module that fails to import (here: it imports a missing module) is a failure, not "not merged".
    (tmp_path / "broken_step.py").write_text(
        "import a_module_that_does_not_exist\n\ndef run(spark):\n    pass\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    steps = list(run_pipeline.STEPS)
    steps[1] = ("bank", "broken_step", "run")
    monkeypatch.setattr(run_pipeline, "STEPS", tuple(steps))

    assert run_pipeline.main(["--all"]) == 1
    assert pipeline.calls == ["collect"]
    assert _log(pipeline.out)[-1].startswith("bank FAILED: ModuleNotFoundError")


def test_failure_stops_with_exit_1(pipeline, monkeypatch):
    def boom(spark):
        raise RuntimeError("totals mismatch\nsecond line")

    monkeypatch.setattr(sys.modules["fake_steps.bank"], "run", boom)
    assert run_pipeline.main(["--all"]) == 1
    assert pipeline.calls == ["collect"]
    assert _log(pipeline.out)[-1] == "bank FAILED: RuntimeError: totals mismatch"
    assert pipeline.spark.stopped


def test_unknown_step_exit_2(pipeline, capsys):
    assert run_pipeline.main(["--steps", "collect,parse"]) == 2
    assert pipeline.calls == []
    err = capsys.readouterr().err
    assert "parse" in err and ", ".join(run_pipeline.STEP_NAMES) in err
    with pytest.raises(SystemExit) as exit_info:  # neither --all nor --steps
        run_pipeline.main([])
    assert exit_info.value.code == 2


def test_dry_run_starts_nothing(pipeline, capsys):
    assert run_pipeline.main(["--all", "--dry-run"]) == 0
    assert pipeline.calls == []
    assert not list(pipeline.out.glob("pipeline_*.log"))
    assert "collect would run (fake_steps.collect.run)" in capsys.readouterr().out


def test_dataset_flag_sets_env(pipeline):
    other = "x10" if config.DATASET == "main" else "main"
    try:
        assert run_pipeline.main(["--steps", "collect", "--dataset", other, "--dry-run"]) == 0
        assert os.environ["FVE_DATASET"] == other
        assert config.DATASET == other  # common.config was already imported, so the runner reloaded it
        assert config.OUT_DIR.name == ("out_x10" if other == "x10" else "out")
    finally:
        os.environ["FVE_DATASET"] = "main" if other == "x10" else "x10"
        importlib.reload(config)
