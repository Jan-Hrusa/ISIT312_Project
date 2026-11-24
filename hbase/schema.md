# HBase catalogue `media_catalog` (Task 12)

One table for every photo, video, document and drawing of the company, built for the two questions people
ask in the search notebook (Task 32.1):

1. **"The photos of FVE-2026-02 between 1 Jun and 1 Sep 2026"**
2. **"The latest drawing of FVE-2026-02"**

Each one is a single scan over a contiguous run of rows. Names are those of `docs/contracts.md` section 8; the
code is `hbase/catalogue.py`.

## Table

`media_catalog` (`config.HBASE_TABLE`), reached through Thrift at `hbase:9090` with happybase. Four column
families, each keeping one version (`VERSIONS => 1`): a row is rewritten when the load runs again, and an old
thumbnail or path is of no use.

| Family | Columns | Filled for |
|---|---|---|
| `meta` | `taken_at`, `lat`, `lon`, `size_bytes`, `device`, `original_name`, `ext`, `filing_rule` | every row (`taken_at`, `lat`, `lon`, `device` for photos and videos only, as far as they have them) |
| `loc` | `raw_path`, `seq_key` | every row; `seq_key` only for photos, which live inside a daily SequenceFile |
| `doc` | `doc_type`, `version`, `is_final`, `title`, `file_date` | documents and drawings; `version` and `is_final` for drawings |
| `thumb` | `jpg` | photos: a 96×72 JPEG thumbnail |

Values are UTF-8 strings: timestamps `yyyy-MM-dd HH:mm:ss` in UTC, dates `yyyy-MM-dd`, booleans
`true`/`false`, coordinates with 6 decimals, sizes in bytes (`catalogue.cells` writes these formats). The only
binary value is `thumb:jpg`. An unknown value is not stored at all (HBase keeps no empty cells), so a photo
without GPS has no `meta:lat`.

Two columns hold codes, the same as in the clean tables (`docs/contracts.md` section 6, written by Task 19):

- `meta:filing_rule`: `GPS` (photo filed by position and date), `NONE` (photo left under `UNASSIGNED`),
  `FOLDER` (video, filed by its project folder). Documents and drawings have none.
- `doc:doc_type`: `CONTRACT`, `PERMIT`, `GRID`, `HANDOVER`, or `DRAWING` for every drawing; `doc:version` is
  `v1`, `v2` or `final`.

Create it with `python -m hbase.create_table` (`--drop` recreates it empty). In the HBase shell it is

    create 'media_catalog', {NAME => 'meta', VERSIONS => 1}, {NAME => 'loc', VERSIONS => 1},
                            {NAME => 'doc', VERSIONS => 1}, {NAME => 'thumb', VERSIONS => 1}

## Row key

    <project_code>#<KIND>#<yyyyMMddHHmmss>#<file_id>
    FVE-2026-02#PHOTO#20260520101500#d30b6758675e92c2

- `project_code`: `FVE-YYYY-NN`, or `UNASSIGNED` for photos that could not be filed (no GPS, or no site in
  reach on their date), so the "to fix" list can find them under one prefix too.
- `KIND`: `PHOTO`, `VIDEO`, `DOC` or `DRAWING`. Drawings are their own kind, not a `DOC` with a type, so
  that "the drawings of a project" is a prefix of their own.
- Timestamp: when the photo was taken (EXIF, UTC). Videos, documents and drawings only have a date (the
  date in the video's name, the document's file date): their key carries that date at 00:00:00. A photo
  whose EXIF has no capture time is keyed at `19700101000000` (1970-01-01 00:00:00), so it sorts before
  every dated photo of its project; it has no `meta:taken_at` cell.
- `file_id`: the first 16 hex characters of the file's SHA-256, as everywhere in the lake. It makes the key
  unique when two photos are taken in the same second.

### Why the key starts with the project

HBase stores rows sorted by key, and a scan reads a contiguous range of them. Every question in the search
is about one project, so putting the project first keeps all of a project's rows next to each other, and
the kind after it splits them into photos, videos, documents and drawings. One question is then one scan
over exactly the rows it needs, never a filter over the whole table.

### Why the timestamp is zero-padded

Keys are compared byte by byte, not as numbers or dates. `yyyyMMddHHmmss` always has 14 digits and goes from
the largest unit to the smallest, so byte order is the same as time order: `20260520101500` sorts after
`20260415093000`, and `20261001000000` after `20260930235959`. A key like `2026-5-20 9:30` would sort
`10:00` before `9:30`. Within a project and kind the rows therefore come back in time order, and a date range
is a key range.

### Why not start with the date

A key starting with the timestamp would also make date ranges easy, but it would cost twice:

- **Hot-spotting.** New photos always have the newest time, so every write would go to the last region
  of the table, held by one region server, while the others stay idle. With the project first, writes
  spread over the regions of the active projects.
- **Scattered reads.** "Photos of one project in a month" would become a scan over everyone's rows of that
  month, with a filter dropping the other projects' rows, instead of reading only that project's rows.

### Why four families

A family is stored in its own files, and a read fetches only the families it asks for. The families follow
how the data is used:

- `meta`: what the search shows in a result list and what experiment E3 counts (number and size of photos).
- `loc`: needed only when someone opens the original, to fetch it from HDFS.
- `doc`: only documents and drawings have it.
- `thumb`: kept apart from the small text columns. A thumbnail is a few kilobytes against about 200 bytes of
  metadata; in `meta` it would make every metadata scan read every image.

## The two questions as scans

**Photos of a project between two dates** (both days included). `scan_bounds` gives the range; the stop key is
exclusive, so it is midnight of the day after the end. The days are UTC days, like every time in the lake: a
photo taken at 00:30 Czech time belongs to the day before.

    start, stop = catalogue.scan_bounds("FVE-2026-02", "PHOTO", date(2026, 6, 1), date(2026, 9, 1))
    # b"FVE-2026-02#PHOTO#20260601000000", b"FVE-2026-02#PHOTO#20260902000000"
    table.scan(row_start=start, row_stop=stop, columns=[b"meta", b"thumb"])

HBase shell:

    scan 'media_catalog', {STARTROW => 'FVE-2026-02#PHOTO#20260601000000',
                           STOPROW => 'FVE-2026-02#PHOTO#20260902000000', COLUMNS => ['meta']}

**The latest drawing of a project.** One prefix scan returns the project's drawings oldest first; the last row is
the newest. A project has a handful of drawings, so reading all of them costs nothing:

    rows = list(table.scan(row_prefix=catalogue.prefix("FVE-2026-02", "DRAWING")))
    latest = rows[-1]          # doc:version, doc:is_final, loc:raw_path

    scan 'media_catalog', {ROWPREFIXFILTER => 'FVE-2026-02#DRAWING#'}

The newest drawing is normally `final`. When a `final` is older than a numbered version, the newest row is
that version, which is exactly the case the media job reports as `WRONG_VERSION` (Task 19).

## Test table

`python -m hbase.sample_rows` puts the Task 7.1 samples (`tests/fixtures/sources/`) into the table: 11 photos
(5 filed to their project, 6 under `UNASSIGNED`), 1 video, 3 documents and 3 drawings of `FVE-2026-02`, with
thumbnails. Each photo's project is the expected answer in `tests/fixtures/media/README.md`; the filing rule
itself is Task 19's. `meta:filing_rule` is `GPS` for the 5 filed photos, `NONE` for the 6 unassigned ones and
`FOLDER` for the video.

Check it in the HBase shell (`docker compose exec hbase hbase shell`):

    describe 'media_catalog'
    count 'media_catalog'
    scan 'media_catalog', {STARTROW => 'FVE-2026-02#PHOTO#20260415000000',
                           STOPROW => 'FVE-2026-02#PHOTO#20260521000000', COLUMNS => ['meta:original_name']}
