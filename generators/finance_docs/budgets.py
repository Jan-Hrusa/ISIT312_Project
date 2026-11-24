"""Budget per signed project (XLSX, sheet Budget)."""

import io
import re
import zipfile
from datetime import datetime, timezone
from decimal import Decimal

from openpyxl import Workbook

from generators.finance_docs.util import CATEGORIES, set_business_mtime

# share of the budget per category (before jitter)
BASE_SHARES = {
    "PANELS": 0.27,
    "INVERTERS": 0.10,
    "BATTERIES": 0.14,
    "STRUCTURES": 0.10,
    "CABLES": 0.05,
    "EARTHWORKS": 0.07,
    "GRID": 0.10,
    "DESIGN": 0.04,
    "SURVEY": 0.02,
    "OTHER": 0.03,
}


def make_budget(project: dict, rng) -> dict[str, Decimal]:
    """One amount per category; total = 85-92% of the contract value."""
    total = round(float(project["contract_value"]) * rng.uniform(0.85, 0.92))
    shares = {}
    for cat in CATEGORIES:
        if cat == "BATTERIES" and not project["has_battery"]:
            shares[cat] = 0.0
        else:
            shares[cat] = BASE_SHARES[cat] * rng.uniform(0.85, 1.15)
    s = sum(shares.values())
    amounts = {cat: int(total * shares[cat] / s) for cat in CATEGORIES}
    amounts["PANELS"] += total - sum(amounts.values())  # rounding remainder
    return {cat: Decimal(amounts[cat]).quantize(Decimal("0.01")) for cat in CATEGORIES}


def _fixed_zip(data: bytes, stamp: str) -> bytes:
    """openpyxl stamps the current time into the zip and into docProps/core.xml
    (dcterms:modified); rewrite both with fixed values so runs are byte-identical."""
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            content = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                content = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>" + stamp.encode() + rb"\g<2>",
                    content,
                )
            dst.writestr(zi, content)
    return out.getvalue()


def write_xlsx(path, project_code: str, budget: dict[str, Decimal], signed_date) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["project_code", "category", "amount_czk"])
    for cat in CATEGORIES:
        ws.append([project_code, cat, float(budget[cat])])
    stamp = datetime(signed_date.year, signed_date.month, signed_date.day, 12, tzinfo=timezone.utc)
    wb.properties.creator = "generator"
    wb.properties.lastModifiedBy = "generator"
    wb.properties.created = stamp
    wb.properties.modified = stamp
    buf = io.BytesIO()
    wb.save(buf)
    with open(path, "wb") as f:
        f.write(_fixed_zip(buf.getvalue(), stamp.strftime("%Y-%m-%dT%H:%M:%SZ")))
    set_business_mtime(path, signed_date)
