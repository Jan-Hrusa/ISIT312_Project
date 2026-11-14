"""A project's site layout drawings: site_layout_v1.dwg, site_layout_v2.dwg, site_layout_final.dwg.

Dates follow Task 7: v1 = signed + 10 days, v2 = signed + 25 days, final = the later of v2 + 10 days and
construction start - 5 days, so final is always the newest. A planted WRONG_VERSION project dates its final
20 days before v2, which the "latest drawing" search must warn about. A drawing dated after DATA_END doesn't
exist yet. The bytes are dummy DWG (20-60 KB): the AutoCAD 2018 magic `AC1032`, a readable line naming the
drawing, then seeded filler, so every file has its own file_id.
"""

from datetime import date, timedelta
from pathlib import Path

from common import config
from common.projects import Project
from generators.media.util import set_business_mtime

VERSIONS = ("v1", "v2", "final")
DWG_MAGIC = b"AC1032"
FILE_BYTES = (20_000, 60_000)
V1_AFTER_SIGNED_DAYS = 10
V2_AFTER_SIGNED_DAYS = 25
FINAL_AFTER_V2_DAYS = 10
FINAL_BEFORE_START_DAYS = 5
PLANTED_FINAL_BEFORE_V2_DAYS = 20


def drawing_name(version: str) -> str:
    return f"site_layout_{version}.dwg"


def plan(project: Project, wrong_version: bool = False, data_end: date = config.DATA_END) -> dict[str, date]:
    """Version -> drawing date for a signed project (only drawings dated on or before data_end)."""
    if not project.is_signed:
        return {}
    v1 = project.signed_date + timedelta(V1_AFTER_SIGNED_DAYS)
    v2 = project.signed_date + timedelta(V2_AFTER_SIGNED_DAYS)
    if wrong_version:
        final = v2 - timedelta(PLANTED_FINAL_BEFORE_V2_DAYS)
    else:
        final = max(
            v2 + timedelta(FINAL_AFTER_V2_DAYS),
            project.construction_start - timedelta(FINAL_BEFORE_START_DAYS),
        )
    dated = {"v1": v1, "v2": v2, "final": final}
    return {version: day for version, day in dated.items() if day <= data_end}


def write(
    project: Project, folder: Path, rng, wrong_version: bool = False, data_end: date = config.DATA_END
) -> dict[str, date]:
    """Write the project's drawings into folder (mtime = drawing date); return version -> date."""
    dated = plan(project, wrong_version, data_end)
    folder.mkdir(parents=True, exist_ok=True)
    for version, day in dated.items():
        write_file(project, folder / drawing_name(version), version, day, rng)
    return dated


def write_file(project: Project, path: Path, version: str, day: date, rng) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"\x00SYNTHETIC SITE LAYOUT {project.project_code} {version} {day.isoformat()}\n".encode("ascii")
    size = rng.randint(*FILE_BYTES)
    path.write_bytes(DWG_MAGIC + header + rng.randbytes(size - len(DWG_MAGIC) - len(header)))
    set_business_mtime(path, day)
