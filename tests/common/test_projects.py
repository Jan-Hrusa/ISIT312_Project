from datetime import date
from decimal import Decimal

import pytest

from common.projects import PROJECTS_CSV_COLUMNS, active_on, load_projects

ROWS = [
    "FVE-2025-04,Plant Kolín,Kolín,Středočeský,50.0281,15.2006,400,1.50,true,32000000.00,"
    "2025-02-10,2025-03-01,2025-04-15,2026-03-31,COMPLETED",
    "FVE-2026-02,Plant Tábor,Tábor,Jihočeský,49.4144,14.6578,350,1.20,false,24500000.00,"
    "2026-01-20,2026-02-05,2026-03-10,2027-02-28,ACTIVE",
    "FVE-2026-05,Plant Písek,Písek,Jihočeský,49.3088,14.1475,300,1.00,true,21000000.00,"
    "2026-05-04,,,,NOT_SIGNED",
]


def _csv(tmp_path, rows):
    path = tmp_path / "projects.csv"
    path.write_text("\n".join([",".join(PROJECTS_CSV_COLUMNS), *rows]) + "\n", encoding="utf-8")
    return path


def test_load_projects_from_csv(tmp_path):
    projects = load_projects(_csv(tmp_path, ROWS))
    assert [p.project_code for p in projects] == ["FVE-2025-04", "FVE-2026-02", "FVE-2026-05"]

    tabor = projects[1]
    assert tabor.town == "Tábor"
    assert (tabor.lat, tabor.radius_m) == (49.4144, 350)
    assert tabor.mwp == Decimal("1.20") and tabor.contract_value == Decimal("24500000.00")
    assert tabor.has_battery is False
    assert tabor.construction_start == date(2026, 3, 10)
    assert tabor.source_file is None

    offer = projects[2]
    assert not offer.is_signed
    assert (offer.signed_date, offer.construction_start, offer.construction_end) == (None, None, None)

    assert [p.project_code for p in active_on(projects, date(2026, 3, 31))] == ["FVE-2025-04", "FVE-2026-02"]
    assert [p.project_code for p in active_on(projects, date(2026, 4, 1))] == ["FVE-2026-02"]
    assert active_on(projects, date(2024, 1, 1)) == []


def test_load_projects_names_the_bad_line(tmp_path):
    bad = ROWS[1].replace("FVE-2026-02", "FVE-26-2")
    with pytest.raises(ValueError, match=r"line 3: bad project_code 'FVE-26-2'"):
        load_projects(_csv(tmp_path, [ROWS[0], bad]))
