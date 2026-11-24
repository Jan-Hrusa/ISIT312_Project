"""Search over the HBase catalogue `media_catalog`: the questions the office asks of photos and drawings.

Each search is one scan made possible by the row key `<project_code>#<KIND>#<yyyyMMddHHmmss>#<file_id>`
(hbase/schema.md): a project's photos between two dates are one range scan (`catalogue.scan_bounds`), a
project's drawings and the unassigned items are prefix scans (`catalogue.prefix`). Used by the Zeppelin note
"search" (the repo is on its PYTHONPATH) and by experiment E3 (benchmarks/e3).

Rows come back as dicts of typed values: the row key's `project_code`, `kind` and `file_id`, then every cell
under its column name without the family (`taken_at` datetime in UTC, `lat`/`lon` float, `size_bytes` int,
`is_final` bool, `file_date` date, `thumb` the thumbnail JPEG bytes, every other column a string). A
cell that was never written (a photo without GPS has no `lat`) is None.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from common import config
from hbase import catalogue

FINAL = "final"
UNASSIGNED = config.UNASSIGNED
WARNING = (
    "⚠️ {version} je novější než final – ověřte, kterou verzi stavba používá "
    "({version} is newer than final – check which one the site uses)"
)

# Columns read per search: the photo table shows thumbnails, the drawing and unassigned lists don't.
_PHOTO_COLUMNS = [b"meta", b"loc", b"thumb"]
_LIST_COLUMNS = [b"meta", b"loc", b"doc"]
_TEXT_COLUMNS = (
    "taken_at",
    "lat",
    "lon",
    "size_bytes",
    "device",
    "original_name",
    "ext",
    "filing_rule",
    "raw_path",
    "seq_key",
    "doc_type",
    "version",
    "is_final",
    "title",
    "file_date",
)


def photos(project: str, start: date, end: date, conn=None) -> list[dict]:
    """Every photo of `project` taken from `start` to `end` (UTC days, both included), oldest first.

    One range scan between `catalogue.scan_bounds` keys; each row has its thumbnail under `thumb`.
    """
    row_start, row_stop = catalogue.scan_bounds(project, "PHOTO", start, end)
    with _table(conn) as table:
        return [
            _row(k, d) for k, d in table.scan(row_start=row_start, row_stop=row_stop, columns=_PHOTO_COLUMNS)
        ]


def latest_drawing(project: str, conn=None) -> tuple[dict | None, str | None]:
    """The project's final drawing and a warning when a numbered version is dated after it.

    One prefix scan over `<project>#DRAWING#`. A project without a final drawing gives (None, None). The
    warning is the planted WRONG_VERSION case of Task 19: `site_layout_final` older than `site_layout_v2`;
    the newest such version is named. Dates compare by `file_date`, as in the media job.
    """
    with _table(conn) as table:
        drawings = [_row(k, d) for k, d in table.scan(row_prefix=catalogue.prefix(project, "DRAWING"))]
    finals = [d for d in drawings if d["is_final"]]
    if not finals:
        return None, None
    final = max(finals, key=lambda d: d["file_date"])
    newer = [d for d in drawings if not d["is_final"] and d["file_date"] > final["file_date"]]
    if not newer:
        return final, None
    newest = max(newer, key=lambda d: d["file_date"])
    return final, WARNING.format(version=newest["version"])


def unassigned(kind: str | None = None, limit: int | None = 50, conn=None) -> list[dict]:
    """Items filed to no project (`UNASSIGNED#`, or `UNASSIGNED#<kind>#`), newest first; `limit` None = all.

    Rows of one kind are read with a reversed scan, so the newest come first and only `limit` rows are read;
    without a kind the kinds are read that way one by one and merged by their key time.
    """
    kinds = catalogue.KINDS if kind is None else (kind,)
    found: list[dict] = []
    with _table(conn) as table:
        for k in kinds:
            row_prefix = catalogue.prefix(UNASSIGNED, k)
            # A reversed scan starts at the largest key: every key of the prefix sorts below prefix + 0xff.
            scan = table.scan(
                row_start=row_prefix + b"\xff",
                row_stop=row_prefix,
                columns=_LIST_COLUMNS,
                reverse=True,
                limit=limit,
            )
            found.extend(_row(key, data) for key, data in scan)
    found.sort(key=lambda r: r["key_time"], reverse=True)
    return found if limit is None else found[:limit]


class _table:
    """`with _table(conn) as table:` the catalogue table, on `conn` or on a connection opened here."""

    def __init__(self, conn):
        self.conn, self.own = (conn, False) if conn is not None else (catalogue.connect(), True)

    def __enter__(self):
        return self.conn.table(config.HBASE_TABLE)

    def __exit__(self, *exc):
        if self.own:
            self.conn.close()


def _row(key: bytes, data: dict[bytes, bytes]) -> dict:
    project_code, kind, key_time, file_id = key.decode().split(catalogue.SEP)
    row = {
        "project_code": project_code,
        "kind": kind,
        "key_time": key_time,
        "file_id": file_id,
    }
    cells = {name.split(b":", 1)[1].decode(): value for name, value in data.items()}
    for column in _TEXT_COLUMNS:
        text = cells[column].decode() if column in cells else None
        row[column] = None if text is None else _parse(column, text)
    row["thumb"] = cells.get("jpg")
    return row


def _parse(column: str, text: str):
    if column == "taken_at":
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if column in ("lat", "lon"):
        return float(text)
    if column == "size_bytes":
        return int(text)
    if column == "is_final":
        return text == "true"
    if column == "file_date":
        return date.fromisoformat(text)
    return text
