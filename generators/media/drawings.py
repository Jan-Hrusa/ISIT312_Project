"""A project's site layout drawings: site_layout_v1.dwg, site_layout_v2.dwg, site_layout_final.dwg.

The three dates are distinct days between the signing date and the day before construction starts (cut at
DATA_END), in the order v1 < v2 < final. A planted WRONG_VERSION project swaps the last two: its final drawing
is older than v2, which the "latest drawing" search must warn about. The bytes are dummy DWG: the AutoCAD 2018
magic `AC1032`, a readable line naming the drawing, then seeded filler, so every file has its own file_id.
"""

from datetime import date
from pathlib import Path

from common import config
from common.projects import Project
from generators.media.documents import pre_construction_days
from generators.media.util import set_business_mtime

VERSIONS = ("v1", "v2", "final")
DWG_MAGIC = b"AC1032"
FILLER_BYTES = (4_000, 12_000)


def drawing_name(version: str) -> str:
    return f"site_layout_{version}.dwg"


def plan(
    project: Project, rng, wrong_version: bool = False, data_end: date = config.DATA_END
) -> dict[str, date]:
    """Version -> drawing date for a signed project ({} if no three distinct days fit before construction)."""
    if not project.is_signed:
        return {}
    window = pre_construction_days(project, data_end)
    if len(window) < 3:
        return {}
    first, second, third = sorted(rng.sample(window, 3))
    if wrong_version:
        return {"v1": first, "v2": third, "final": second}
    return {"v1": first, "v2": second, "final": third}


def write(
    project: Project, folder: Path, rng, wrong_version: bool = False, data_end: date = config.DATA_END
) -> dict[str, date]:
    """Write the three drawings into folder (mtime = drawing date); return version -> date."""
    dated = plan(project, rng, wrong_version, data_end)
    folder.mkdir(parents=True, exist_ok=True)
    for version, day in dated.items():
        write_file(project, folder / drawing_name(version), version, day, rng)
    return dated


def write_file(project: Project, path: Path, version: str, day: date, rng) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"\x00SYNTHETIC SITE LAYOUT {project.project_code} {version} {day.isoformat()}\n".encode("ascii")
    path.write_bytes(DWG_MAGIC + header + rng.randbytes(rng.randint(*FILLER_BYTES)))
    set_business_mtime(path, day)
