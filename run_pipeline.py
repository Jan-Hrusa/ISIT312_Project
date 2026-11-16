"""Run the data lake's steps in their fixed order: `python run_pipeline.py --all` in the client container.

    run_pipeline.py (--all | --steps a,b) [--dry-run] [--dataset main|x10]

Each step's module is imported only when its turn comes, so a step whose task is not merged yet is reported as
`SKIPPED <step>: not merged yet` and the rest still runs. Every line is printed and appended to
`<OUT_DIR>/pipeline_<UTC yyyyMMddHHmmss>.log` (`out/` for the main dataset, `out_x10/` for the 10x one).
The first failing step stops the run with exit code 1; an unknown step name or a usage error: exit code 2.

Only the standard library is imported at the top: `--dataset` sets `FVE_DATASET` before anything from
`common/` is imported, because `common.config` reads it at import.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from datetime import datetime, timezone

# (step, module, function) in the order the pipeline runs them (docs/contracts.md, module map).
STEPS = (
    ("collect", "ingest", "run"),
    ("bank", "processing.bank", "run"),
    ("finance", "processing.finance", "run"),
    ("matching", "processing.matching.job", "run"),
    ("media", "processing.media", "run"),
    ("warehouse", "warehouse.etl.run", "run"),
    ("catalogue", "hbase.load", "run"),
)
STEP_NAMES = tuple(name for name, _, _ in STEPS)
DATASETS = ("main", "x10")


class _Skipped(Exception):
    """The step's module or its run() is not merged yet."""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the data lake's steps in their fixed order.")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="run every step")
    which.add_argument(
        "--steps", help=f"comma-separated steps, run in the fixed order: {','.join(STEP_NAMES)}"
    )
    parser.add_argument("--dry-run", action="store_true", help="list what would run or be skipped; no Spark")
    parser.add_argument(
        "--dataset",
        choices=DATASETS,
        default=os.environ.get("FVE_DATASET", "main"),
        help="main (default, or FVE_DATASET if set) or x10",
    )
    return parser.parse_args(argv)


def _chosen_steps(args: argparse.Namespace) -> list[str] | None:
    """The chosen step names in fixed order, or None (after printing the valid names) if one is unknown."""
    if args.all:
        return list(STEP_NAMES)
    wanted = [name.strip() for name in args.steps.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in STEP_NAMES]
    if unknown or not wanted:
        print(
            f"unknown step(s): {', '.join(unknown) or '(none given)'}; valid steps: {', '.join(STEP_NAMES)}",
            file=sys.stderr,
        )
        return None
    return [name for name in STEP_NAMES if name in wanted]


def _select_dataset(dataset: str) -> None:
    """Set FVE_DATASET; reload common.config if something imported it already, so its paths follow."""
    os.environ["FVE_DATASET"] = dataset
    config = sys.modules.get("common.config")
    if config is not None and config.DATASET != dataset:
        importlib.reload(config)


def _load(module_name: str, function: str):
    """The step's run function. Only a missing module of the step itself counts as "not merged yet"; an import
    error inside an existing module is a real failure and propagates."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name is not None and (module_name == exc.name or module_name.startswith(exc.name + ".")):
            raise _Skipped from exc
        raise
    run = getattr(module, function, None)
    if not callable(run):
        raise _Skipped
    return run


def _spark():
    from common.spark import get_spark

    return get_spark("pipeline")


def _summary(result) -> str:
    if isinstance(result, dict) and result:
        return " – " + ", ".join(f"{key}={value}" for key, value in result.items())
    return ""


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text.splitlines()[0]}" if text else type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    steps = _chosen_steps(args)
    if steps is None:
        return 2
    _select_dataset(args.dataset)

    from common import config

    started = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    log_path = None if args.dry_run else config.OUT_DIR / f"pipeline_{stamp}.log"

    def emit(line: str) -> None:
        print(line, flush=True)
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    emit(
        f"pipeline {stamp} dataset={config.DATASET} steps={','.join(steps)}"
        + (" (dry run)" if args.dry_run else "")
    )
    spark = None
    ran = skipped = 0
    try:
        modules = {name: (module, function) for name, module, function in STEPS}
        for name in steps:
            module, function = modules[name]
            try:
                run = _load(module, function)
            except _Skipped:
                emit(f"SKIPPED {name}: not merged yet")
                skipped += 1
                continue
            except Exception as exc:  # a merged module that doesn't import is a failure of its step
                emit(f"{name} FAILED: {_first_line(exc)}")
                return 1
            if args.dry_run:
                emit(f"{name} would run ({module}.{function})")
                continue
            if spark is None:
                spark = _spark()
            step_start = time.monotonic()
            try:
                result = run(spark)
            except Exception as exc:
                emit(f"{name} FAILED: {_first_line(exc)}")
                return 1
            emit(f"{name} OK in {time.monotonic() - step_start:.1f} s{_summary(result)}")
            ran += 1
        if args.dry_run:
            emit(f"dry run: {len(steps) - skipped} would run, {skipped} skipped")
        else:
            emit(f"pipeline OK in {time.monotonic() - started:.1f} s ({ran} steps, {skipped} skipped)")
        return 0
    finally:
        if spark is not None:
            spark.stop()


if __name__ == "__main__":
    sys.exit(main())
