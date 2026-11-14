"""Run: python -m generators.media --seed 312 --scale 1

Reads <SOURCES_DIR>/master/projects.csv (Task 5) and writes the site photos to sources/mailbox/photos/,
each project's documents, drawings and videos to sources/drive/projects/<project_code>/, and the planted
problems to <OUT_DIR>/ledger/planted_media.csv.
"""

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

from common import config
from common.projects import load_projects
from generators.media import documents, drawings, exif, photos, videos
from generators.media.util import set_business_mtime

PLANTED_COLUMNS = ("problem", "ref", "project_code", "detail")
WRONG_VERSION_PER_SCALE = 1


def generate(
    seed: int, scale: int, out_dir, led_dir, projects_csv=None, sample_mp4=videos.SAMPLE_MP4
) -> dict:
    """Write all media sources and planted_media.csv; return counts for the summary."""
    out, led = Path(out_dir), Path(led_dir)
    projects_csv = Path(projects_csv) if projects_csv else out / "master" / "projects.csv"
    projects = load_projects(projects_csv)
    sample = Path(sample_mp4).read_bytes()
    d_photos = out / "mailbox" / "photos"
    d_projects = out / "drive" / "projects"
    for d in (d_photos, d_projects, led):
        d.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)  # all randomness flows from this one object, in a fixed order
    specs = photos.plan(projects, rng, scale)
    completed = [p for p in projects if p.status == "COMPLETED"]
    wrong_version = {
        p.project_code for p in rng.sample(completed, min(WRONG_VERSION_PER_SCALE * scale, len(completed)))
    }

    truth = []
    for s in specs:
        if s.planted == "NO_GPS":
            detail = f"taken {s.taken_at:%Y-%m-%d %H:%M:%S} UTC on site, no GPS position"
        elif s.planted == "WRONG_SITE":
            km = photos.nearest_site_m(s.lat, s.lon, projects) / 1000
            detail = f"GPS {s.lat:.6f},{s.lon:.6f}, nearest project site {km:.1f} km away"
        else:
            continue
        truth.append({"problem": s.planted, "ref": s.name, "project_code": s.project_code, "detail": detail})

    per_day: dict = {}
    n_videos = n_documents = n_drawings = 0
    for p in projects:
        if not p.is_signed:
            continue
        folder = d_projects / p.project_code
        n_documents += len(documents.write(p, folder, rng))
        dated = drawings.write(p, folder, rng, wrong_version=p.project_code in wrong_version)
        n_drawings += len(dated)
        if p.project_code in wrong_version:
            truth.append(
                {
                    "problem": "WRONG_VERSION",
                    "ref": p.project_code,
                    "project_code": p.project_code,
                    "detail": f"site_layout_final.dwg {dated['final']} is older than "
                    f"site_layout_v2.dwg {dated['v2']}",
                }
            )
        for day in videos.plan_days(p, rng, photos.photo_period(p, config.DATA_END)):
            n = per_day[day] = per_day.get(day, 0) + 1
            set_business_mtime(videos.make(folder, day, n, sample), day)
            n_videos += 1

    for s in specs:
        path = d_photos / s.name
        path.write_bytes(exif.add(photos.render(s, rng), s.taken_at, s.lat, s.lon, s.device))
        set_business_mtime(path, s.taken_at.date())

    with (led / "planted_media.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PLANTED_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(truth)

    planted = Counter(s.planted for s in specs)
    return {
        "photos": len(specs),
        "photos_gps": len(specs) - planted["NO_GPS"],
        "photos_no_gps": planted["NO_GPS"],
        "photos_wrong_site": planted["WRONG_SITE"],
        "videos": n_videos,
        "documents": n_documents,
        "drawings": n_drawings,
        "wrong_version": sorted(wrong_version),
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Generate the synthetic site photos, videos, documents, drawings"
    )
    ap.add_argument("--seed", type=int, default=config.SEED)
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--out", default=str(config.SOURCES_DIR), help="sources folder")
    ap.add_argument("--ledger", default=str(config.LEDGER_DIR), help="truth-file folder")
    args = ap.parse_args(argv)
    stats = generate(args.seed, args.scale, args.out, args.ledger)
    print(f"photos:        {stats['photos']}")
    print(f"  with GPS:    {stats['photos_gps']} (of them wrong site: {stats['photos_wrong_site']})")
    print(f"  without GPS: {stats['photos_no_gps']}")
    print(f"videos:        {stats['videos']}")
    print(f"documents:     {stats['documents']}")
    print(
        f"drawings:      {stats['drawings']} (wrong version: {', '.join(stats['wrong_version']) or 'none'})"
    )


if __name__ == "__main__":
    main()
