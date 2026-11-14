"""Tests for the media generator (Task 7), run on the three Task 5.1 sample projects."""

import csv
import hashlib
import random
import re
import shutil
import struct
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from common import config
from common.projects import load_projects
from generators.media import exif, photos
from generators.media.__main__ import generate
from generators.media.util import distance_m

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PROJECTS_CSV = FIXTURES / "sources" / "master" / "projects.csv"
SAMPLE = FIXTURES / "media" / "sample.mp4"
PHOTO_NAME = re.compile(r"^IMG_\d{8}_\d{6}_\d{5}\.jpg$")
VIDEO_NAME = re.compile(r"^VID_\d{8}_\d{5}\.mp4$")


def _run(base: Path, seed: int = config.SEED, scale: int = 1):
    stats = generate(seed, scale, base / "sources", base / "ledger", projects_csv=PROJECTS_CSV)
    return base / "sources", base / "ledger", stats


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return _run(tmp_path_factory.mktemp("media1"))


@pytest.fixture(scope="module")
def projects():
    return {p.project_code: p for p in load_projects(PROJECTS_CSV)}


@pytest.fixture(scope="module")
def planted(run):
    with (run[1] / "planted_media.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and list(rows[0]) == ["problem", "ref", "project_code", "detail"]
    return rows


@pytest.fixture(scope="module")
def photo_exif(run):
    return {p.name: exif.read(p.read_bytes()) for p in sorted((run[0] / "mailbox" / "photos").glob("*.jpg"))}


def _refs(planted, problem):
    return {r["ref"]: r for r in planted if r["problem"] == problem}


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _midday(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)


def _owner(meta, projects):
    """The signed project whose site and construction period contain the photo (None if no such project)."""
    for p in projects.values():
        if p.is_signed and p.construction_start <= meta["taken_at"].date() <= p.construction_end:
            if distance_m(meta["lat"], meta["lon"], p.lat, p.lon) <= p.radius_m:
                return p.project_code
    return None


def test_gps_inside_radius(photo_exif, planted, projects):
    wrong_site = _refs(planted, "WRONG_SITE")
    with_gps = {n: m for n, m in photo_exif.items() if m["lat"] is not None and n not in wrong_site}
    assert with_gps
    for name, meta in with_gps.items():
        assert _owner(meta, projects) is not None, name


def test_wrong_site_far_from_every_project(photo_exif, planted, projects):
    wrong_site = _refs(planted, "WRONG_SITE")
    assert len(wrong_site) == photos.WRONG_SITE_PER_SCALE
    for name, row in wrong_site.items():
        meta = photo_exif[name]
        assert meta["lat"] is not None
        for p in projects.values():
            assert distance_m(meta["lat"], meta["lon"], p.lat, p.lon) >= photos.WRONG_SITE_MIN_M
        assert projects[row["project_code"]].is_signed


def test_dates_inside_construction(photo_exif, planted, projects):
    planted_owner = {r["ref"]: r["project_code"] for r in planted if r["problem"] != "WRONG_VERSION"}
    for name, meta in photo_exif.items():
        code = planted_owner.get(name) or _owner(meta, projects)
        p = projects[code]
        assert p.construction_start <= meta["taken_at"].date() <= p.construction_end, name
        assert meta["taken_at"].weekday() < 5


def test_nothing_after_data_end(run, photo_exif, projects):
    sources = run[0]
    limit = _midday(config.DATA_END)
    files = [p for p in sources.rglob("*") if p.is_file()]
    assert files
    assert all(_mtime(p) <= limit for p in files)
    assert all(m["taken_at"].date() <= config.DATA_END for m in photo_exif.values())
    # FVE-2026-02 is ACTIVE until 2027: its photos stop at DATA_END and it has no grid connection yet
    active = [m for n, m in photo_exif.items() if m["taken_at"].year == 2026]
    assert active and max(m["taken_at"].date() for m in active) <= config.DATA_END
    assert not (sources / "drive" / "projects" / "FVE-2026-02" / "grid_connection.pdf").exists()


def test_ten_percent_without_gps(photo_exif, planted):
    no_gps = {n for n, m in photo_exif.items() if m["lat"] is None}
    assert no_gps == set(_refs(planted, "NO_GPS"))
    assert abs(len(no_gps) / len(photo_exif) - 0.10) <= 0.02


def test_drawing_versions_present(run, projects):
    root = run[0] / "drive" / "projects"
    assert sorted(d.name for d in root.iterdir()) == sorted(c for c, p in projects.items() if p.is_signed)
    for code, p in projects.items():
        if not p.is_signed:
            continue
        for version in ("v1", "v2", "final"):
            data = (root / code / f"site_layout_{version}.dwg").read_bytes()
            assert data.startswith(b"AC1032")
            assert f"{code} {version} ".encode() in data[:80]
        names = {f.name for f in (root / code).iterdir() if f.is_file()}
        expected = {"contract.docx", "building_permit.pdf"}
        if p.status == "COMPLETED":
            expected |= {"grid_connection.pdf", "handover_protocol.pdf"}
        assert expected <= names
        assert (root / code / "contract.docx").read_bytes()[:2] == b"PK"


def test_final_newer_than_v2_except_planted(run, projects, planted):
    root = run[0] / "drive" / "projects"
    wrong = set(_refs(planted, "WRONG_VERSION"))
    for code, p in projects.items():
        if not p.is_signed or code in wrong:
            continue
        v1, v2, final = (_mtime(root / code / f"site_layout_{v}.dwg") for v in ("v1", "v2", "final"))
        assert v1 < v2 < final <= _midday(p.construction_start)


def test_one_wrong_version_project(run, projects, planted):
    wrong = _refs(planted, "WRONG_VERSION")
    assert len(wrong) == 1
    (code,) = wrong
    assert wrong[code]["project_code"] == code and projects[code].status == "COMPLETED"
    folder = run[0] / "drive" / "projects" / code
    v1, v2, final = (_mtime(folder / f"site_layout_{v}.dwg") for v in ("v1", "v2", "final"))
    assert v1 < final < v2


def test_videos_unique_bytes(run):
    sample = SAMPLE.read_bytes()
    videos = sorted((run[0] / "drive" / "projects").glob("*/videos/*.mp4"))
    assert videos
    hashes = set()
    for path in videos:
        data = path.read_bytes()
        name = path.name.encode()
        assert data == sample + struct.pack(">I", 8 + len(name)) + b"free" + name
        hashes.add(hashlib.sha256(data).hexdigest())
    assert len(hashes) == len(videos)


def test_names_unique(run):
    photo_names = [p.name for p in (run[0] / "mailbox" / "photos").iterdir()]
    assert photo_names and all(PHOTO_NAME.match(n) for n in photo_names)
    assert len(set(photo_names)) == len(photo_names)
    video_names = [p.name for p in (run[0] / "drive" / "projects").glob("*/videos/*")]
    assert all(VIDEO_NAME.match(n) for n in video_names)
    assert len(set(video_names)) == len(video_names)


def test_same_seed_same_files(run, tmp_path):
    again, _, _ = _run(tmp_path)

    def tree(root):
        return {
            p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime)
            for p in root.rglob("*")
            if p.is_file()
        }

    assert tree(again) == tree(run[0])
    assert (tmp_path / "ledger" / "planted_media.csv").read_bytes() == (
        run[1] / "planted_media.csv"
    ).read_bytes()
    shutil.rmtree(tmp_path / "sources")


def test_other_seed_other_files():
    a = photos.plan(load_projects(PROJECTS_CSV), random.Random(1))
    b = photos.plan(load_projects(PROJECTS_CSV), random.Random(2))
    assert [s.name for s in a] != [s.name for s in b]


def test_mtime_is_business_date(run, photo_exif, projects):
    sources = run[0]
    for name, meta in photo_exif.items():
        assert meta["taken_at"].strftime("%Y%m%d_%H%M%S") == name[4:19]
        assert _mtime(sources / "mailbox" / "photos" / name) == _midday(meta["taken_at"].date())
    for path in (sources / "drive" / "projects").glob("*/videos/*.mp4"):
        day = datetime.strptime(path.name[4:12], "%Y%m%d").date()
        assert _mtime(path) == _midday(day)
    for code, p in projects.items():
        if not p.is_signed:
            continue
        assert _mtime(sources / "drive" / "projects" / code / "contract.docx") == _midday(p.signed_date)
        if p.status == "COMPLETED":
            handover = sources / "drive" / "projects" / code / "handover_protocol.pdf"
            assert _mtime(handover) == _midday(p.construction_end)


def test_exif_round_trip():
    jpeg = photos.render(
        photos.PhotoSpec(
            "IMG_20260520_101500_00001.jpg", _midday(date(2026, 5, 20)), 0, 0, ("A", "B"), "", None
        ),
        random.Random(0),
    )
    taken = datetime(2026, 5, 20, 10, 15, 7, tzinfo=timezone.utc)
    meta = exif.read(exif.add(jpeg, taken, 49.331000, 14.165000, ("Samsung", "Galaxy A54")))
    assert meta["taken_at"] == taken and meta["device"] == ("Samsung", "Galaxy A54")
    assert abs(meta["lat"] - 49.331) < 1e-6 and abs(meta["lon"] - 14.165) < 1e-6
    assert exif.read(exif.add(jpeg, taken, None, None, ("A", "B")))["lat"] is None
    assert exif.to_dms(49.9999999999) == ((50, 1), (0, 1), (0, 10_000))


def test_cli_prints_summary(tmp_path, capsys):
    from generators.media import __main__ as cli

    sources = tmp_path / "sources"
    (sources / "master").mkdir(parents=True)
    shutil.copy(PROJECTS_CSV, sources / "master" / "projects.csv")
    cli.main(["--out", str(sources), "--ledger", str(tmp_path / "ledger")])
    out = capsys.readouterr().out
    for word in (
        "photos:",
        "with GPS:",
        "wrong site: 5",
        "without GPS:",
        "videos:",
        "documents:",
        "drawings:",
    ):
        assert word in out
