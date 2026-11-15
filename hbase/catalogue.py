"""The HBase photo and document catalogue `media_catalog` (design in hbase/schema.md, contract section 8).

Row key `<project_code>#<KIND>#<yyyyMMddHHmmss>#<file_id>`, timestamp in UTC. Because the project and kind
come first and the timestamp is fixed-width, "all photos of a project between two dates" is one range scan
(`scan_bounds`) and "the drawings of a project" is one prefix scan (`prefix`).

Used by the catalogue load (Task 19) and the search notebook and experiment E3 (Task 32.1).
"""

from __future__ import annotations

import io
from datetime import date, datetime, time, timedelta, timezone

from PIL import Image, ImageOps

from common import config

KINDS = ("PHOTO", "VIDEO", "DOC", "DRAWING")
FAMILIES = ("meta", "loc", "doc", "thumb")
SEP = "#"
KEY_TIME_FORMAT = "%Y%m%d%H%M%S"
FILE_ID_LENGTH = 16
THUMB_SIZE = (96, 72)
THUMB_COLUMN = b"thumb:jpg"


def connect():
    """A happybase connection to the stack's HBase Thrift server (`config.HBASE_HOST:HBASE_PORT`)."""
    import happybase

    return happybase.Connection(host=config.HBASE_HOST, port=config.HBASE_PORT, timeout=30_000)


def create_table(conn, drop: bool = False) -> bool:
    """Create `config.HBASE_TABLE` with the four families, one version each; return True if it was created.

    An existing table is kept as it is (False), unless `drop` is set: then it is disabled, deleted and created
    again, empty.
    """
    name = config.HBASE_TABLE.encode()
    if name in conn.tables():
        if not drop:
            return False
        conn.delete_table(config.HBASE_TABLE, disable=True)
    conn.create_table(config.HBASE_TABLE, {family: {"max_versions": 1} for family in FAMILIES})
    return True


def row_key(project_code: str, kind: str, ts: datetime, file_id: str) -> bytes:
    """`<project_code>#<KIND>#<yyyyMMddHHmmss>#<file_id>` as UTF-8 bytes.

    `ts` is converted to UTC; a naive datetime is taken as UTC already (every contract timestamp is UTC).
    The project is a project code or `UNASSIGNED`, the kind one of KINDS, the file_id 16 lower-case hex
    characters; anything else is a ValueError, because a malformed key would sort outside every scan.
    """
    _check_project(project_code)
    _check_kind(kind)
    if len(file_id) != FILE_ID_LENGTH or any(c not in "0123456789abcdef" for c in file_id):
        raise ValueError(f"file_id must be {FILE_ID_LENGTH} lower-case hex characters, got {file_id!r}")
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc)
    return SEP.join((project_code, kind, ts.strftime(KEY_TIME_FORMAT), file_id)).encode()


def scan_bounds(project_code: str, kind: str, start: date, end: date) -> tuple[bytes, bytes]:
    """(row_start, row_stop) for every row of one project and kind from `start` to `end`, both days included.

    row_stop is exclusive in HBase, so it is midnight of the day after `end`: 1 Jun - 1 Sep 2026 gives
    `FVE-2026-02#PHOTO#20260601000000` and `FVE-2026-02#PHOTO#20260902000000`.
    """
    _check_project(project_code)
    _check_kind(kind)
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    first = datetime.combine(start, time.min)
    after_last = datetime.combine(end + timedelta(days=1), time.min)
    base = f"{project_code}{SEP}{kind}{SEP}"
    return (base + first.strftime(KEY_TIME_FORMAT)).encode(), (
        base + after_last.strftime(KEY_TIME_FORMAT)
    ).encode()


def prefix(project_code: str, kind: str | None = None) -> bytes:
    """The key prefix of a project (`FVE-2026-02#`) or of one kind in it (`FVE-2026-02#DRAWING#`).

    The trailing separator keeps `PHOTO` rows out of a prefix of another kind and one project out of another.
    """
    _check_project(project_code)
    if kind is None:
        return f"{project_code}{SEP}".encode()
    _check_kind(kind)
    return f"{project_code}{SEP}{kind}{SEP}".encode()


def cells(families: dict[str, dict[str, object]]) -> dict[bytes, bytes]:
    """`{"meta": {"lat": 49.33, ...}, ...}` -> `{b"meta:lat": b"49.33", ...}` for `Table.put`.

    Every value is stored as a UTF-8 string except `thumb:jpg`, which is the JPEG bytes. None values are left
    out (HBase stores no empty cells): a photo without GPS simply has no `meta:lat`.
    """
    out: dict[bytes, bytes] = {}
    for family, columns in families.items():
        if family not in FAMILIES:
            raise ValueError(f"unknown column family {family!r}")
        for column, value in columns.items():
            if value is None:
                continue
            name = f"{family}:{column}".encode()
            if name == THUMB_COLUMN:
                if not isinstance(value, bytes):
                    raise ValueError("thumb:jpg must be bytes")
                out[name] = value
            elif isinstance(value, bytes):
                raise ValueError(f"{family}:{column} must be a string value, not bytes")
            else:
                out[name] = _text(value).encode()
    return out


def thumbnail(jpeg: bytes) -> bytes:
    """A 96x72 JPEG of the photo (cropped to 4:3 around the centre if needed), without EXIF."""
    with Image.open(io.BytesIO(jpeg)) as image:
        small = ImageOps.fit(image.convert("RGB"), THUMB_SIZE, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _check_project(project_code: str) -> None:
    if project_code != config.UNASSIGNED and not config.is_project_code(project_code):
        raise ValueError(
            f"project must be a project code FVE-YYYY-NN or {config.UNASSIGNED}, got {project_code!r}"
        )


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, got {kind!r}")
