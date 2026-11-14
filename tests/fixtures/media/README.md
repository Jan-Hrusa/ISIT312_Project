# Media fixtures (Task 7.1)

Paths below are relative to `tests/fixtures/sources/` unless they start with `tests/`. All data is synthetic.
The projects are the three of Task 5.1 in `master/projects.csv`:

| Project | Site (lat, lon) | Radius | Construction | Status |
|---|---|---:|---|---|
| `FVE-2026-02` | 49.331000, 14.165000 | 500 m | 2026-03-02 → 2027-01-29 | ACTIVE |
| `FVE-2019-02` | 49.434000, 14.690000 | 400 m | 2019-05-06 → 2020-03-27 | COMPLETED |
| `FVE-2025-04` | 49.282300, 13.926400 | 600 m | – | NOT_SIGNED |

The files were made with the Task 7 generator's own functions (`generators.media.photos.render`,
`exif.add`, `documents.write_file`, `drawings.write_file`, `videos.make`), so they have exactly the
generator's formats. Business dates (mtimes) are in `tests/fixtures/mtimes_media.csv`; `file_id` is the first
16 hex characters of the file's SHA-256.

## Photos

`mailbox/photos/`, 320×240 JPEG, quality 70. EXIF: `DateTimeOriginal` = `taken_at` in UTC (also in
`GPSDateStamp` / `GPSTimeStamp` when there is GPS), `Make` / `Model` = device, GPS as degrees / minutes /
seconds rationals (seconds in 1/10000). Each photo's business date is its `taken_at` date. Distances are
haversine (Earth radius 6,371,000 m) to the nearest project site. "Filed to" is what Task 19 must give:
the signed project whose site (radius included) contains the position and whose construction period contains
the date, otherwise `UNASSIGNED` with the issue named.

| File | taken_at (UTC) | GPS lat | GPS lon | Device | Distance | Filed to | Issue |
|---|---|---|---|---|---:|---|---|
| IMG_20260415_093000_00001.jpg | 2026-04-15 09:30:00 | 49.332078 | 14.165000 | Samsung Galaxy A54 | 120 m to FVE-2026-02 | FVE-2026-02 | – |
| IMG_20260520_101500_00001.jpg | 2026-05-20 10:15:00 | 49.331000 | 14.171203 | Apple iPhone 13 | 449 m to FVE-2026-02 | FVE-2026-02 | – |
| IMG_20260520_101800_00002.jpg | 2026-05-20 10:18:00 | none | none | Apple iPhone 13 | – | UNASSIGNED | NO_GPS |
| IMG_20260520_143000_00003.jpg | 2026-05-20 14:30:00 | 49.331000 | 14.156040 | Xiaomi Redmi Note 12 | 649 m to FVE-2026-02 | UNASSIGNED | UNASSIGNED_PHOTO |
| IMG_20260610_110000_00001.jpg | 2026-06-10 11:00:00 | 49.700000 | 16.200000 | Google Pixel 7a | 112.8 km to FVE-2019-02 | UNASSIGNED | UNASSIGNED_PHOTO |
| IMG_20190715_083000_00001.jpg | 2019-07-15 08:30:00 | 49.434898 | 14.690000 | Samsung Galaxy A54 | 100 m to FVE-2019-02 | FVE-2019-02 | – |
| IMG_20260705_120000_00001.jpg | 2026-07-05 12:00:00 | 49.434000 | 14.690000 | Xiaomi Redmi Note 12 | 0 m to FVE-2019-02 | UNASSIGNED | UNASSIGNED_PHOTO |

What each one tests:
1. inside the site, well within the radius;
2. inside, near the edge (449 of 500 m);
3. no GPS position (the generator's `NO_GPS`);
4. just outside the radius (649 of 500 m) on a construction day of `FVE-2026-02`;
5. far from every site (the generator's `WRONG_SITE`);
6. the older project: inside the `FVE-2019-02` site during its construction;
7. right place, wrong date: the centre of the `FVE-2019-02` site six years after its construction ended.

| File | file_id | Bytes |
|---|---|---:|
| IMG_20260415_093000_00001.jpg | 00c7ce529644981b | 7124 |
| IMG_20260520_101500_00001.jpg | d30b6758675e92c2 | 8633 |
| IMG_20260520_101800_00002.jpg | a8f6f5932d61ea52 | 6665 |
| IMG_20260520_143000_00003.jpg | dce58c271b59a3ec | 8353 |
| IMG_20260610_110000_00001.jpg | e5250eb4246ce822 | 8648 |
| IMG_20190715_083000_00001.jpg | 81996a8f1af54d0c | 7584 |
| IMG_20260705_120000_00001.jpg | 6898b9ec0d8ca655 | 7110 |

## Project folder `drive/projects/FVE-2026-02/`

| File | Business date | doc_type / version | file_id | Bytes |
|---|---|---|---|---:|
| contract.docx | 2026-01-20 (signing) | contract | 5f0db876d7038852 | 36725 |
| building_permit.pdf | 2026-02-16 | building_permit | eaaef1eb0371160e | 1909 |
| site_layout_v1.dwg | 2026-01-26 | site_layout v1 | 3d08eaf0d12ec377 | 6416 |
| site_layout_v2.dwg | 2026-02-09 | site_layout v2 | 6f81cbdf10d57d51 | 7943 |
| site_layout_final.dwg | 2026-02-23 | site_layout final | 1b2b07da9d2f6e4d | 10495 |
| videos/VID_20260520_00001.mp4 | 2026-05-20 | video | 5c3286dcd620f43c | 24588 |

- The project is ACTIVE and its construction ends after `DATA_END`, so it has no `grid_connection.pdf`
  (dated 14-45 days before construction ends) and no `handover_protocol.pdf` (COMPLETED only), exactly as the
  generator would write it.
- Drawings are in order v1 < v2 < final: the latest drawing is `site_layout_final.dwg` and there is **no**
  `WRONG_VERSION` here (the generator plants that on one COMPLETED project).
- DWG files are dummy bytes: they start with `AC1032`, then a NUL and the ASCII line
  `SYNTHETIC SITE LAYOUT FVE-2026-02 <version> <date>`.
- `contract.docx` and the PDF carry the project code, name, site, power and date as text.

## Video

`tests/fixtures/media/sample.mp4` (24558 bytes, file_id 99481b41bea5c7d3) is the one synthetic clip every
generated video copies: 2 s, 320×240, 10 fps, H.264, no audio, an ffmpeg test pattern (`testsrc2`). Made with

    ffmpeg -f lavfi -i "testsrc2=size=320x240:rate=10:duration=2" -c:v libx264 -preset veryfast -crf 32 \
      -pix_fmt yuv420p -movflags +faststart -map_metadata -1 -fflags +bitexact -flags:v +bitexact -an sample.mp4

`videos/VID_20260520_00001.mp4` is `sample.mp4` followed by one MP4 `free` box (4-byte size 30, type `free`,
payload = the 22-byte file name in ASCII). Players skip the box, so the copy plays like the sample, but every
copy has different bytes.
