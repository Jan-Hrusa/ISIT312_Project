"""Dataset statistics and the scaled (x10) experiment dataset (Task 17).

    python -m generators.scale --stats       # scale-1 tables -> docs/dataset-stats.md
    python -m generators.scale --scale 10    # x10 data -> sources_x10/, manifest, x10 section

The generators run as subprocesses with FVE_DATASET=x10: config reads it at import,
so they are never imported in-process.
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
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 312
GENERATORS = ("generators.finance_docs", "generators.bank", "generators.media")
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
        year = datetime.fromtimestamp(st.st_mtime, UTC).year
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
        text = head + block + rest.split(end, 1)[1].lstrip("\n")
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


def run_generator(module: str, scale: int, seed: int, env: dict, cwd: Path) -> None:
    cmd = [sys.executable, "-m", module, "--seed", str(seed), "--scale", str(scale)]
    subprocess.run(cmd, env=env, cwd=cwd, check=True)


def run_scale(
    scale: int,
    seed: int = SEED,
    root: Path = ROOT,
    doc: Path | None = None,
    manifest: Path | None = None,
) -> None:
    doc = doc or root / "docs" / "dataset-stats.md"
    manifest = manifest or root / "docs" / "x10-MANIFEST.sha256"
    env = {**os.environ, "FVE_DATASET": "x10"}
    start = time.monotonic()
    for module in GENERATORS:  # bank needs the finance ledger, media needs the projects
        print(f"== {module} --scale {scale}", flush=True)
        run_generator(module, scale, seed, env, root)
    minutes = (time.monotonic() - start) / 60
    sources, out = root / "sources_x10", root / "out_x10"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(build_manifest([sources, out / "ledger"], root), encoding="utf-8")
    body = (
        f"Command (repo root): `FVE_DATASET=x10 python -m generators.scale --scale {scale}`\n\n"
        f"- Seed: {seed}; Python {sys.version.split()[0]}\n"
        f"- Runtime: {minutes:.1f} minutes\n"
        f"- Compare your regenerated data with `docs/x10-MANIFEST.sha256`.\n\n"
        + render_stats(sources, out / "ledger")
    )
    write_section(doc, X10_MARK, f"Scaled dataset (x{scale})", body)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="generators.scale")
    ap.add_argument("--stats", action="store_true", help="statistics of sources/ -> docs/dataset-stats.md")
    ap.add_argument("--scale", type=int, help="generate the scaled dataset (FVE_DATASET=x10)")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    if not args.stats and not args.scale:
        ap.error("give --stats and/or --scale N")
    if args.stats:
        body = render_stats(ROOT / "sources", ROOT / "out" / "ledger")
        write_section(ROOT / "docs" / "dataset-stats.md", STATS_MARK, "Scale 1", body)
        print("wrote docs/dataset-stats.md (scale 1)")
    if args.scale:
        free = shutil.disk_usage(ROOT).free / 1e9
        if free < MIN_FREE_GB:
            raise SystemExit(f"only {free:.0f} GB free; need about {MIN_FREE_GB} GB")
        run_scale(args.scale, args.seed)


if __name__ == "__main__":
    main()
