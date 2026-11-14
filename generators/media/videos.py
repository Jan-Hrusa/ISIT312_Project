"""Short site videos: unique copies of one synthetic clip (tests/fixtures/media/sample.mp4).

Each copy gets a top-level MP4 `free` box holding its own file name appended at the end. Players skip `free`
boxes, so every copy still plays, but every copy has different bytes (and so its own file_id).
"""

import struct
from datetime import date
from pathlib import Path

from common import config
from common.projects import Project
from generators.media.util import workdays

VIDEOS_PER_PROJECT = 4
SAMPLE_MP4 = config.REPO_ROOT / "tests" / "fixtures" / "media" / "sample.mp4"


def video_name(day: date, n: int) -> str:
    """VID_<yyyyMMdd>_<nnnnn>.mp4; n counts the videos of one day over all projects."""
    return f"VID_{day:%Y%m%d}_{n:05d}.mp4"


def free_box(payload: bytes) -> bytes:
    """An MP4 `free` box: 4-byte big-endian size (header included), the type, the payload."""
    return struct.pack(">I", 8 + len(payload)) + b"free" + payload


def plan_days(project: Project, rng, period: tuple[date, date] | None) -> list[date]:
    """VIDEOS_PER_PROJECT distinct weekdays of the photo period (fewer if it is shorter), sorted."""
    if period is None:
        return []
    work = workdays(*period)
    return sorted(rng.sample(work, min(VIDEOS_PER_PROJECT, len(work))))


def make(project_dir: Path, day: date, n: int, sample: bytes) -> Path:
    """Write <project_dir>/videos/VID_<yyyyMMdd>_<nnnnn>.mp4 (sample + free box with the name); return it."""
    name = video_name(day, n)
    path = Path(project_dir) / "videos" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sample + free_box(name.encode("ascii")))
    return path
