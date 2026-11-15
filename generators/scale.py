"""Dataset statistics and the scaled (x10) experiment dataset (Task 17).

Run in the client container:

    python -m generators.scale --stats              # scale-1 tables of sources/ -> docs/dataset-stats.md
    python -m generators.scale --scale 10           # x10 data -> sources_x10/, out_x10/, then the check
    python -m generators.scale --check              # compare sources_x10/ with docs/x10-MANIFEST.sha256
    python -m generators.scale --scale 10 --record  # once, for the repo: rewrite the manifest and x10 section

The generators run as subprocesses with FVE_DATASET=x10: config reads it at import, so they are never
imported in-process. Paths and the seed come from common.config.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from common import config

GENERATORS = ("generators.finance_docs", "generators.bank", "generators.media")
SCALED_DATASET = "x10"
SCALE = 10  # FVE_DATASET=x10 is the only scaled dataset common.config knows
TYPES = {
    ".csv": "CSV",
    ".xlsx": "XLSX",
    ".isdoc": "ISDOC",
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".dwg": "DWG",
    ".jpg": "JPG",
    ".jpeg": "JPG",
    ".mp4": "MP4",
    ".gpc": "GPC",
    ".sta": "STA",
    ".txt": "TXT",
    ".kpc": "KPC",
}
ORDER = ["CSV", "XLSX", "ISDOC", "PDF", "DOCX", "DWG", "JPG", "MP4", "GPC", "STA", "TXT", "KPC"]
MIN_FREE_GB = 15
DIR_AGGREGATE_ABOVE = 200  # directories with more files get one manifest line
SHOW_MISMATCHES = 20

DOC = config.REPO_ROOT / "docs" / "dataset-stats.md"
MANIFEST = config.REPO_ROOT / "docs" / "x10-MANIFEST.sha256"
STATS_MARK = ("<!-- stats:begin -->", "<!-- stats:end -->")
X10_MARK = ("<!-- x10:begin -->", "<!-- x10:end -->")


def _mb(size: int) -> str:
    return f"{size / 1_000_000:,.1f}"


def collect(root: Path) -> tuple[dict, dict]:
    """Return ({type: [files, bytes]}, {year: [files, bytes]}) for every file under root."""
    by_type = {t: [0, 0] for t in ORDER}
    by_year: dict[int, list[int]] = {}
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        st = path.stat()
        label = TYPES.get(path.suffix.lower(), "other")
        by_type.setdefault(label, [0, 0])
        year = datetime.fromtimestamp(st.st_mtime, timezone.utc).year
        by_year.setdefault(year, [0, 0])
        for bucket in (by_type[label], by_year[year]):
            bucket[0] += 1
            bucket[1] += st.st_size
    return by_type, dict(sorted(by_year.items()))


def planted_counts(ledger_dir: Path) -> dict[str, Counter]:
    result: dict[str, Counter] = {}
    for path in sorted(Path(ledger_dir).glob("planted_*.csv")):
        with path.open(newline="", encoding="utf-8") as fh:
            result[path.name] = Counter(row.get("problem", "?") for row in csv.DictReader(fh))
    return result


def render_stats(sources: Path, ledger_dir: Path) -> str:
    by_type, by_year = collect(sources)
    total_files = sum(v[0] for v in by_type.values())
    total_bytes = sum(v[1] for v in by_type.values())
    lines = ["| File type | Files | Size (MB) |", "|---|---:|---:|"]
    lines += [f"| {t} | {n:,} | {_mb(b)} |" for t, (n, b) in by_type.items()]
    lines.append(f"| **Total** | **{total_files:,}** | **{_mb(total_bytes)}** |")
    lines += ["", "| Year | Files | Size (MB) |", "|---|---:|---:|"]
    lines += [f"| {y} | {n:,} | {_mb(b)} |" for y, (n, b) in by_year.items()]
    lines += ["", "Planted problems:", "", "| Truth file | Problem | Count |", "|---|---|---:|"]
    for name, counts in planted_counts(ledger_dir).items():
        lines += [f"| {name} | {p} | {c:,} |" for p, c in sorted(counts.items())]
    return "\n".join(lines) + "\n"


def write_section(doc: Path, marks: tuple[str, str], title: str, body: str) -> None:
    """Replace (or append) the marked section of the doc, leaving the rest untouched."""
    begin, end = marks
    block = f"{begin}\n## {title}\n\n{body}{end}\n"
    text = doc.read_text(encoding="utf-8") if doc.exists() else "# Dataset statistics\n\n"
    if begin in text and end in text:
        head, rest = text.split(begin, 1)
        tail = rest.split(end, 1)[1].lstrip("\n")
        text = head + block + ("\n" + tail if tail else "")
    else:
        text = text.rstrip("\n") + "\n\n" + block
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(text, encoding="utf-8")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(roots: list[Path], base: Path) -> str:
    """sha256 lines; a directory with very many files (photos) is one aggregate line."""
    lines = []
    for root in roots:
        by_dir: dict[Path, list[Path]] = {}
        for p in sorted(x for x in Path(root).rglob("*") if x.is_file()):
            by_dir.setdefault(p.parent, []).append(p)
        for folder, files in sorted(by_dir.items()):
            if len(files) > DIR_AGGREGATE_ABOVE:
                agg = hashlib.sha256()
                for f in files:
                    agg.update(f"{f.name} {_sha(f)}\n".encode())
                rel = folder.relative_to(base).as_posix()
                lines.append(f"{agg.hexdigest()}  {rel}/* ({len(files)} files)")
            else:
                lines += [f"{_sha(f)}  {f.relative_to(base).as_posix()}" for f in files]
    return "\n".join(lines) + "\n"


def _entries(manifest_text: str) -> dict[str, str]:
    """{file or folder entry: sha256} of a manifest."""
    entries = {}
    for line in manifest_text.splitlines():
        if line.strip():
            sha, name = line.split("  ", 1)
            entries[name] = sha
    return entries


def compare_manifests(expected: str, actual: str) -> list[str]:
    """One line per difference (changed, missing or extra entry); empty when the manifests are identical."""
    exp, act = _entries(expected), _entries(actual)
    problems = [f"different: {name}" for name in sorted(exp.keys() & act.keys()) if exp[name] != act[name]]
    problems += [f"missing:   {name}" for name in sorted(exp.keys() - act.keys())]
    problems += [f"extra:     {name}" for name in sorted(act.keys() - exp.keys())]
    return problems


def _scaled_dirs(sources: Path | None, out: Path | None) -> tuple[Path, Path]:
    default_sources, default_out = config.dataset_dirs(SCALED_DATASET)
    return Path(sources or default_sources), Path(out or default_out)


def _not_empty(folder: Path) -> bool:
    return folder.exists() and any(folder.iterdir())


def check(
    root: Path = config.REPO_ROOT,
    manifest: Path = MANIFEST,
    sources: Path | None = None,
    out: Path | None = None,
) -> bool:
    """Compare the local scaled dataset with the committed manifest and print the result."""
    sources, out = _scaled_dirs(sources, out)
    if not _not_empty(sources):
        print(f"{sources} is empty: generate it first with --scale {SCALE}")
        return False
    problems = compare_manifests(
        Path(manifest).read_text(encoding="utf-8"), build_manifest([sources, out / "ledger"], root)
    )
    if not problems:
        print(f"OK: the local {SCALED_DATASET} dataset matches {Path(manifest).name}")
        return True
    print(f"{len(problems)} manifest lines differ from {Path(manifest).name}:")
    for line in problems[:SHOW_MISMATCHES]:
        print("  " + line)
    if len(problems) > SHOW_MISMATCHES:
        print(f"  ... and {len(problems) - SHOW_MISMATCHES} more")
    return False


def run_generator(module: str, scale: int, seed: int, env: dict, cwd: Path) -> None:
    cmd = [sys.executable, "-m", module, "--seed", str(seed), "--scale", str(scale)]
    subprocess.run(cmd, env=env, cwd=cwd, check=True)


def run_scale(
    scale: int = SCALE,
    seed: int = config.SEED,
    *,
    record: bool = False,
    root: Path = config.REPO_ROOT,
    sources: Path | None = None,
    out: Path | None = None,
    doc: Path = DOC,
    manifest: Path = MANIFEST,
) -> bool:
    """Generate the scaled dataset into empty folders, then check it against the manifest.

    With `record` the manifest and the x10 section of the doc are rewritten instead (once, for the repo). The
    target folders must be empty: files of an earlier run would end up in the statistics and the manifest.
    """
    if scale != SCALE:
        raise ValueError(f"only scale {SCALE}: FVE_DATASET={SCALED_DATASET} is the only scaled dataset")
    sources, out = _scaled_dirs(sources, out)
    for folder in (sources, out):
        if _not_empty(folder):
            raise SystemExit(f"{folder} is not empty: delete {sources.name}/ and {out.name}/ first")
    env = {**os.environ, "FVE_DATASET": SCALED_DATASET}
    start = time.monotonic()
    for module in GENERATORS:  # bank needs the finance ledger, media needs the projects
        print(f"== {module} --scale {scale}", flush=True)
        run_generator(module, scale, seed, env, root)
    minutes = (time.monotonic() - start) / 60
    print(f"generated in {minutes:.1f} minutes", flush=True)
    if not record:
        return check(root, manifest, sources, out)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(build_manifest([sources, out / "ledger"], root), encoding="utf-8")
    body = (
        f"Generate it in the client container, with `{sources.name}/` and `{out.name}/` deleted or empty\n"
        f"and about {MIN_FREE_GB} GB free disk: `python -m generators.scale --scale {scale}`. The run ends\n"
        f"by comparing your data with `docs/{manifest.name}` (it must print `OK`);\n"
        "`python -m generators.scale --check` repeats the comparison.\n\n"
        f"- Seed: {seed}; Python {sys.version.split()[0]} (client container)\n"
        f"- Runtime: {minutes:.1f} minutes\n\n" + render_stats(sources, out / "ledger")
    )
    write_section(doc, X10_MARK, f"Scaled dataset (x{scale})", body)
    print(f"wrote {manifest.name} and the x{scale} section of {doc.name}")
    return True


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="generators.scale")
    ap.add_argument("--stats", action="store_true", help="statistics of sources/ -> docs/dataset-stats.md")
    ap.add_argument("--scale", type=int, help=f"generate the scaled dataset (only {SCALE})")
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--check", action="store_true", help=f"compare sources_x10/ with {MANIFEST.name}")
    ap.add_argument(
        "--record", action="store_true", help=f"with --scale: rewrite {MANIFEST.name} and the x10 section"
    )
    args = ap.parse_args(argv)
    if not (args.stats or args.scale or args.check):
        ap.error("give --stats, --scale 10 and/or --check")
    if args.scale is not None and args.scale != SCALE:
        ap.error(f"only --scale {SCALE}: FVE_DATASET={SCALED_DATASET} is the only scaled dataset")
    if args.record and not args.scale:
        ap.error("--record goes with --scale 10")
    ok = True
    if args.stats:
        sources, out = config.dataset_dirs("main")
        write_section(DOC, STATS_MARK, "Scale 1", render_stats(sources, out / "ledger"))
        print(f"wrote {DOC.name} (scale 1)")
    if args.scale:
        free = shutil.disk_usage(config.REPO_ROOT).free / 1e9
        if free < MIN_FREE_GB:
            raise SystemExit(f"only {free:.0f} GB free; need about {MIN_FREE_GB} GB")
        ok = run_scale(args.scale, args.seed, record=args.record)
    elif args.check:
        ok = check()
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
