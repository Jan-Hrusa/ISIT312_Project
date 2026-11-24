"""Project, type and version of project documents and videos from their path (Task 19 filing rules).

Documents sit in `drive/projects/<project_code>/`, videos in `drive/projects/<project_code>/videos/`; the
project comes from that folder, the type and version from the file name. Paths may be `original_path` values
(relative to `sources/`) or full local paths of test fixtures: only their last parts are used.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import PurePosixPath

from common import config

DOC_TYPES = {
    "contract": "CONTRACT",
    "building_permit": "PERMIT",
    "grid_connection": "GRID",
    "handover_protocol": "HANDOVER",
}
DRAWING = "DRAWING"
DRAWING_STEM = "site_layout"
DRAWING_RE = re.compile(rf"^{DRAWING_STEM}_(v\d+|final)$")
FINAL = "final"
VIDEO_NAME_RE = re.compile(r"^VID_(\d{8})_\d+$")


def project_from_folder(path: str, videos: bool = False) -> str:
    """The project code of the folder a document (or, with `videos`, a video) sits in; ValueError if none."""
    p = PurePosixPath(path.replace("\\", "/"))
    folder = p.parent
    if videos:
        if folder.name != "videos":
            raise ValueError(f"a video must sit in a videos/ folder: {path}")
        folder = folder.parent
    if not config.is_project_code(folder.name):
        raise ValueError(f"no project folder in {path}")
    return folder.name


def video_date(path: str) -> date:
    """The date in a video's name `VID_<yyyyMMdd>_<nnnnn>.mp4`; ValueError for any other name."""
    stem = PurePosixPath(path.replace("\\", "/")).stem
    match = VIDEO_NAME_RE.match(stem)
    if not match:
        raise ValueError(f"not a video name VID_<yyyyMMdd>_<n>: {path}")
    return datetime.strptime(match.group(1), "%Y%m%d").date()


def describe(original_path: str, business_date: date, size: int) -> dict:
    """The `documents` columns that come from a project file's path, date and size (no file_id, raw_path).

    `doc_type` CONTRACT / PERMIT / GRID / HANDOVER / DRAWING from the name; drawings `site_layout_<v>` also
    get `version` (`v1`, `v2`, `final`) and `is_final`. A name outside these keeps doc_type None.
    """
    p = PurePosixPath(original_path.replace("\\", "/"))
    stem = p.stem
    doc_type, version, is_final = DOC_TYPES.get(stem), None, None
    drawing = DRAWING_RE.match(stem)
    if drawing:
        doc_type, version = DRAWING, drawing.group(1)
        is_final = version == FINAL
    return {
        "project_code": project_from_folder(original_path),
        "doc_type": doc_type,
        "title": stem.replace("_", " ").capitalize(),
        "version": version,
        "is_final": is_final,
        "file_date": business_date,
        "ext": p.suffix.lstrip(".").lower(),
        "size_bytes": size,
    }


def wrong_versions(docs: list[dict]) -> list[tuple[str, str]]:
    """(project_code, detail) for every project whose final drawing is older than a numbered one.

    `docs` are `describe` results; dates are compared by `file_date`.
    """
    by_project: dict[str, dict[str, date]] = {}
    for d in docs:
        if d["doc_type"] == DRAWING and d["version"] is not None:
            versions = by_project.setdefault(d["project_code"], {})
            day = d["file_date"]
            versions[d["version"]] = max(day, versions.get(d["version"], day))
    found = []
    for project in sorted(by_project):
        versions = by_project[project]
        final_day = versions.get(FINAL)
        if final_day is None:
            continue
        newer = sorted((day, v) for v, day in versions.items() if v != FINAL and day > final_day)
        if newer:
            day, version = newer[-1]
            found.append(
                (
                    project,
                    f"{DRAWING_STEM}_{FINAL} dated {final_day} is older than {DRAWING_STEM}_{version} "
                    f"dated {day}",
                )
            )
    return found
