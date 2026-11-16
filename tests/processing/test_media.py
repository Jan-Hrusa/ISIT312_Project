"""Photo filing, documents and the media job (Task 19)."""

from __future__ import annotations

import csv
import io
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from common import config, tables
from common.projects import load_projects
from ingest.seqfile import write_seq
from processing.media import documents, filing, run, thumbs

FILED_AT = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
# FVE-2026-02 of the samples: centre 49.331000, 14.165000, radius 500 m, construction 2026-03-02 - 2027-01-29.
PISEK = filing.site("FVE-2026-02", 49.331, 14.165, 500, date(2026, 3, 2), date(2027, 1, 29))

# tests/fixtures/media/README.md: photo -> (filed to, issue).
EXPECTED_PHOTOS = {
    "IMG_20260415_093000_00001.jpg": ("FVE-2026-02", None),
    "IMG_20260520_101500_00001.jpg": ("FVE-2026-02", None),
    "IMG_20260520_101800_00002.jpg": ("UNASSIGNED", "NO_GPS"),
    "IMG_20260520_143000_00003.jpg": ("UNASSIGNED", "UNASSIGNED_PHOTO"),
    "IMG_20260610_110000_00001.jpg": ("UNASSIGNED", "UNASSIGNED_PHOTO"),
    "IMG_20190715_083000_00001.jpg": ("FVE-2019-02", None),
    "IMG_20260705_120000_00001.jpg": ("UNASSIGNED", "UNASSIGNED_PHOTO"),
    "IMG_20260708_073000_00001.jpg": ("FVE-2026-02", None),
    "IMG_20260916_131500_00001.jpg": ("FVE-2026-02", None),
    "IMG_20260415_140000_00002.jpg": ("UNASSIGNED", "NO_GPS"),
    "IMG_20260520_151000_00004.jpg": ("UNASSIGNED", "UNASSIGNED_PHOTO"),
}


def write_projects(spark, sources: Path) -> None:
    """fve_clean.projects (redirected by clean_db) from the samples' master/projects.csv."""
    path = sources / "master" / "projects.csv"
    rows = [{**asdict(p), "source_file": f"master/{path.name}"} for p in load_projects(path)]
    tables.write_table(spark, spark.createDataFrame(rows), "projects")


def pack_photos(spark, sources: Path, dest: Path) -> list[tuple[str, str]]:
    """The sample photos in one temporary SequenceFile; returns the job's inputs [(seq_path, key), ...]."""
    photos = sorted((sources / "mailbox" / "photos").glob("*.jpg"))
    seq = (dest / "photos.seq").as_uri()
    write_seq(spark, seq, [(p.name, p.read_bytes()) for p in photos])
    return [(seq, p.name) for p in photos]


def media_inputs(spark, sources: Path, tmp_path: Path) -> dict:
    projects = sources / "drive" / "projects"
    return {
        "photos": pack_photos(spark, sources, tmp_path),
        "video": [p.as_uri() for p in sorted(projects.glob("*/videos/*.mp4"))],
        "docs": [p.as_uri() for p in sorted(projects.glob("*/*.*"))],
    }


def test_haversine_known_distance():
    prague, brno = (50.0755, 14.4378), (49.1951, 16.6068)
    assert abs(filing.haversine_m(*prague, *brno) - 185_000) <= 1_000
    assert filing.haversine_m(*prague, *prague) == 0


def test_photo_inside_site_filed():
    filed = filing.file_photo(FILED_AT, 49.332078, 14.165, [PISEK])
    assert (filed.project_code, filed.filing_rule) == ("FVE-2026-02", "GPS")
    assert abs(filed.distance_m - 120) < 1
    # Inside two sites at once: the nearest centre wins.
    near = filing.site("FVE-2026-05", 49.3325, 14.165, 500, date(2026, 1, 1), date(2026, 12, 31))
    assert filing.file_photo(FILED_AT, 49.332078, 14.165, [PISEK, near]).project_code == "FVE-2026-05"
    assert filing.file_photo(FILED_AT, 49.331, 14.165, [PISEK, near]).project_code == "FVE-2026-02"


def test_photo_outside_every_site_unassigned():
    filed = filing.file_photo(FILED_AT, 49.331, 14.15604, [PISEK])
    assert (filed.project_code, filed.filing_rule) == (config.UNASSIGNED, "NONE")
    assert abs(filed.distance_m - 649) < 1  # to the nearest site, also when unassigned
    assert filing.file_photo(FILED_AT, 49.7, 16.2, []) == (config.UNASSIGNED, "NONE", None)


def test_no_gps_issue(clean_db, sources_tree, tmp_path):
    assert filing.file_photo(FILED_AT, None, None, [PISEK]) == (config.UNASSIGNED, "NONE", None)
    write_projects(clean_db, sources_tree)
    run(clean_db, media_inputs(clean_db, sources_tree, tmp_path))
    issues = clean_db.table(f"{config.CLEAN_DB}.dq_issues").where("job = 'media' AND issue_type = 'NO_GPS'")
    got = {(r.record_ref, r.detail) for r in issues.collect()}
    assert got == {
        ("a8f6f5932d61ea52", "IMG_20260520_101800_00002.jpg taken 2026-05-20 10:18:00"),
        ("2d88f6713e9cee82", "IMG_20260415_140000_00002.jpg taken 2026-04-15 14:00:00"),
    }
    no_gps = tables.read_table(clean_db, "media_files").where("lat IS NULL AND kind = 'PHOTO'").collect()
    assert {(r.project_code, r.filing_rule, r.distance_m) for r in no_gps} == {
        (config.UNASSIGNED, "NONE", None)
    }


def test_date_window_30_days():
    def filed_on(day: date) -> str:
        at = datetime(day.year, day.month, day.day, 23, 59, tzinfo=timezone.utc)
        return filing.file_photo(at, 49.331, 14.165, [PISEK]).project_code

    start, end = date(2026, 3, 2), date(2027, 1, 29)
    assert filed_on(start - timedelta(days=30)) == "FVE-2026-02"
    assert filed_on(start - timedelta(days=31)) == config.UNASSIGNED
    assert filed_on(end + timedelta(days=30)) == "FVE-2026-02"
    assert filed_on(end + timedelta(days=31)) == config.UNASSIGNED


def test_video_project_from_folder():
    path = "drive/projects/FVE-2026-02/videos/VID_20260520_00001.mp4"
    assert documents.project_from_folder(path, videos=True) == "FVE-2026-02"
    assert documents.video_date(path) == date(2026, 5, 20)
    local = "/tmp/x/sources/drive/projects/FVE-2019-02/videos/VID_20190801_00003.mp4"
    assert documents.project_from_folder(local, videos=True) == "FVE-2019-02"
    with pytest.raises(ValueError):
        documents.project_from_folder("drive/projects/FVE-2026-02/VID_20260520_00001.mp4", videos=True)
    with pytest.raises(ValueError):
        documents.video_date("drive/projects/FVE-2026-02/videos/clip.mp4")


def test_version_from_name():
    day = date(2026, 2, 14)
    expected = {
        "contract.docx": ("CONTRACT", None, None),
        "building_permit.pdf": ("PERMIT", None, None),
        "grid_connection.pdf": ("GRID", None, None),
        "handover_protocol.pdf": ("HANDOVER", None, None),
        "site_layout_v1.dwg": ("DRAWING", "v1", False),
        "site_layout_v2.dwg": ("DRAWING", "v2", False),
        "site_layout_final.dwg": ("DRAWING", "final", True),
    }
    for name, (doc_type, version, is_final) in expected.items():
        d = documents.describe(f"drive/projects/FVE-2026-02/{name}", day, 100)
        assert (d["doc_type"], d["version"], d["is_final"]) == (doc_type, version, is_final), name
        assert (d["project_code"], d["file_date"], d["size_bytes"]) == ("FVE-2026-02", day, 100)
    assert (
        documents.describe("drive/projects/FVE-2026-02/site_layout_v2.dwg", day, 1)["title"]
        == "Site layout v2"
    )


def test_wrong_version_issue():
    def drawing(project, version, day):
        return documents.describe(f"drive/projects/{project}/site_layout_{version}.dwg", day, 1)

    docs = [
        drawing("FVE-2019-02", "v1", date(2019, 3, 21)),
        drawing("FVE-2019-02", "v2", date(2019, 4, 5)),
        drawing("FVE-2019-02", "final", date(2019, 3, 16)),  # planted: 20 days before v2
        drawing("FVE-2026-02", "v1", date(2026, 1, 30)),
        drawing("FVE-2026-02", "v2", date(2026, 2, 14)),
        drawing("FVE-2026-02", "final", date(2026, 2, 25)),
    ]
    assert documents.wrong_versions(docs) == [
        ("FVE-2019-02", "site_layout_final dated 2019-03-16 is older than site_layout_v2 dated 2019-04-05")
    ]
    assert documents.wrong_versions(docs[3:]) == []


def test_thumbnail_size(fixtures_dir):
    photo = fixtures_dir / "sources" / "mailbox" / "photos" / "IMG_20260415_093000_00001.jpg"
    thumb = thumbs.thumbnail(photo.read_bytes())
    image = Image.open(io.BytesIO(thumb))
    assert (image.format, image.size) == ("JPEG", (96, 72))
    assert "exif" not in image.info
    # Another shape is cropped to 4:3 around the centre, not stretched.
    buf = io.BytesIO()
    Image.new("RGB", (400, 100), "red").save(buf, format="JPEG")
    assert Image.open(io.BytesIO(thumbs.thumbnail(buf.getvalue()))).size == (96, 72)


def test_run_on_samples(clean_db, sources_tree, tmp_path):
    """Every sample photo, video and document as tests/fixtures/media/README.md expects."""
    write_projects(clean_db, sources_tree)
    counts = run(clean_db, media_inputs(clean_db, sources_tree, tmp_path))
    assert counts == {"media_files": 12, "documents": 6, "issues": 6}

    media = {r.original_name: r for r in tables.read_table(clean_db, "media_files").collect()}
    for name, (project, _issue) in EXPECTED_PHOTOS.items():
        row = media[name]
        assert (row.kind, row.project_code) == ("PHOTO", project), name
        assert row.filing_rule == ("NONE" if project == config.UNASSIGNED else "GPS"), name
        assert row.seq_key == name and row.raw_path.endswith("photos.seq")
    assert media["IMG_20260415_093000_00001.jpg"].file_id == "00c7ce529644981b"
    assert abs(media["IMG_20260520_101500_00001.jpg"].distance_m - 449) < 1
    assert media["IMG_20260415_093000_00001.jpg"].device == "Samsung Galaxy A54"
    video = media["VID_20260520_00001.mp4"]
    assert (video.kind, video.project_code, video.filing_rule, video.lat, video.file_id) == (
        "VIDEO",
        "FVE-2026-02",
        "FOLDER",
        None,
        "5c3286dcd620f43c",
    )

    docs = {r.file_id: r for r in tables.read_table(clean_db, "documents").collect()}
    assert docs["9359aa8452131a64"].version == "final" and docs["9359aa8452131a64"].is_final is True
    assert docs["9359aa8452131a64"].file_date == date(2026, 2, 25)
    assert docs["5f0db876d7038852"].doc_type == "CONTRACT"

    issues = clean_db.table(f"{config.CLEAN_DB}.dq_issues").where("job = 'media'").collect()
    expected = {(media[n].file_id, issue) for n, (_p, issue) in EXPECTED_PHOTOS.items() if issue is not None}
    assert {(r.record_ref, r.issue_type) for r in issues} == expected


@pytest.mark.integration
def test_planted_media_found():
    """After a scale-1 pipeline run: every planted media problem is in dq_issues (WRONG_SITE counted as
    UNASSIGNED_PHOTO)."""
    planted_csv = config.LEDGER_DIR / "planted_media.csv"
    if not planted_csv.exists():
        pytest.skip(f"no {planted_csv}: run the media generator and the pipeline first")
    from common.spark import get_spark

    spark = get_spark("test-planted-media")
    if not spark.catalog.tableExists(f"{config.CLEAN_DB}.dq_issues"):
        pytest.skip(f"no {config.CLEAN_DB}.dq_issues: run the pipeline first")
    with planted_csv.open(encoding="utf-8", newline="") as f:
        planted = [r["problem"] for r in csv.DictReader(f)]
    expected = {
        "NO_GPS": planted.count("NO_GPS"),
        "UNASSIGNED_PHOTO": planted.count("WRONG_SITE"),
        "WRONG_VERSION": planted.count("WRONG_VERSION"),
    }
    found = {
        r.issue_type: r["count"]
        for r in spark.table(f"{config.CLEAN_DB}.dq_issues")
        .where("job = 'media'")
        .groupBy("issue_type")
        .count()
        .collect()
    }
    assert {t: found.get(t, 0) for t in expected} == expected
