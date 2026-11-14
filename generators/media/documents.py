"""A project's documents in its Drive folder: contract.docx, building_permit.pdf, grid_connection.pdf and
(COMPLETED only) handover_protocol.pdf, each dated by a fixed rule (Task 7):

- contract: the signing date;
- building permit: 30 days before construction starts;
- grid connection: 60 days after construction starts;
- handover protocol: the day construction ends.

A document dated after DATA_END doesn't exist yet and isn't written. Both formats are byte-reproducible:
reportlab runs with invariant=1, and the DOCX zip gets fixed timestamps (python-docx stamps the current time).
"""

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from common import config
from common.projects import Project
from generators.media.util import set_business_mtime

PERMIT_BEFORE_START_DAYS = 30
GRID_AFTER_START_DAYS = 60

TITLES = {
    "contract.docx": "Contract for work: construction of a photovoltaic power plant",
    "building_permit.pdf": "Building permit",
    "grid_connection.pdf": "Grid connection agreement",
    "handover_protocol.pdf": "Handover protocol",
}


def plan(project: Project, data_end: date = config.DATA_END) -> dict[str, date]:
    """File name -> document date for a signed project (only documents dated on or before data_end)."""
    if not project.is_signed:
        return {}
    dated = {
        "contract.docx": project.signed_date,
        "building_permit.pdf": project.construction_start - timedelta(PERMIT_BEFORE_START_DAYS),
        "grid_connection.pdf": project.construction_start + timedelta(GRID_AFTER_START_DAYS),
    }
    if project.status == "COMPLETED":
        dated["handover_protocol.pdf"] = project.construction_end
    return {name: day for name, day in dated.items() if day <= data_end}


def write(project: Project, folder: Path, data_end: date = config.DATA_END) -> dict[str, date]:
    """Write the project's documents into folder (mtime = document date); return file name -> date."""
    dated = plan(project, data_end)
    folder.mkdir(parents=True, exist_ok=True)
    for name, day in dated.items():
        write_file(project, folder / name, day)
    return dated


def write_file(project: Project, path: Path, day: date) -> None:
    """One document: DOCX for .docx, PDF otherwise; mtime set to day."""
    path.parent.mkdir(parents=True, exist_ok=True)
    title = TITLES[path.name]
    lines = _lines(project, path.name, day)
    if path.suffix == ".docx":
        path.write_bytes(_docx(title, lines, day))
    else:
        _pdf(path, title, lines)
    set_business_mtime(path, day)


def _lines(project: Project, name: str, day: date) -> list[str]:
    lines = [
        f"Project: {project.project_code} - {project.name}",
        f"Site: {project.town}, {project.region} region ({project.lat:.6f} N, {project.lon:.6f} E)",
        f"Installed power: {project.mwp} MWp" + (", with battery storage" if project.has_battery else ""),
        f"Date: {day.isoformat()}",
    ]
    if name == "contract.docx":
        lines.append(f"Contract value: CZK {project.contract_value:,.2f} excl. VAT")
        lines.append(f"Construction: {project.construction_start} to {project.construction_end}")
    elif name == "handover_protocol.pdf":
        lines.append("The plant was handed over to the investor without defects preventing operation.")
    lines.append("Synthetic document generated for the ISIT312 project; not a real record.")
    return lines


def _pdf(path: Path, title: str, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(60, 780, title)
    c.setFont("Helvetica", 11)
    for i, line in enumerate(lines):
        c.drawString(60, 740 - 18 * i, line)
    c.showPage()
    c.save()


def _docx(title: str, lines: list[str], day: date) -> bytes:
    doc = Document()
    doc.core_properties.title = title
    doc.core_properties.author = "ISIT312 synthetic data"
    doc.core_properties.created = doc.core_properties.modified = _midday(day)
    doc.core_properties.last_modified_by = "ISIT312 synthetic data"
    doc.core_properties.revision = 1
    doc.add_heading(title, level=1)
    for line in lines:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return _fixed_zip_times(buf.getvalue(), day)


def _midday(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12)


def _fixed_zip_times(data: bytes, day: date) -> bytes:
    """The same zip with every entry stamped 12:00 of day, so the same seed gives the same bytes."""
    stamp = (day.year, day.month, day.day, 12, 0, 0)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=stamp)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = 0o644 << 16
            dst.writestr(fixed, src.read(info.filename))
    return out.getvalue()
