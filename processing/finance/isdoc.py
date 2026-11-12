"""Namespace aware parser for Czech ISDOC 6.0.2 XML invoices."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from lxml import etree

from common import config
from processing.finance.master import FinanceParseError

ISDOC_NS = "http://isdoc.cz/namespace/2013"
NS = {"i": ISDOC_NS}
ICO_RE = re.compile(r"^\d{8}$")


def _text(elem: etree._Element, xpath: str) -> str | None:
    val = elem.findtext(xpath, namespaces=NS)
    if val is None:
        return None
    stripped = val.strip()
    return stripped if stripped != "" else None


def _req_text(elem: etree._Element, xpath: str, source_file: str) -> str:
    val = _text(elem, xpath)
    if val is None:
        raise FinanceParseError(f"Missing required XML element {xpath}", source_file)
    return val


def _req_date(elem: etree._Element, xpath: str, source_file: str) -> date:
    raw = _req_text(elem, xpath, source_file)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise FinanceParseError(f"Invalid date {raw!r} at {xpath}", source_file) from exc


def _req_dec(
    elem: etree._Element, xpath: str, source_file: str, scale: str = "0.01"
) -> Decimal:
    raw = _req_text(elem, xpath, source_file)
    cleaned = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal(scale))
    except InvalidOperation as exc:
        raise FinanceParseError(f"Invalid decimal {raw!r} at {xpath}", source_file) from exc


def _normalize_vs(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip().lstrip("0")
    return stripped if stripped != "" else None


def parse(
    xml_bytes: bytes, source_file: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse an ISDOC XML byte stream into (invoice_dict, list_of_line_dicts)."""
    if not xml_bytes:
        raise FinanceParseError("Empty ISDOC XML file", source_file)

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise FinanceParseError(f"Invalid XML syntax: {exc}", source_file) from exc

    if root.tag != f"{{{ISDOC_NS}}}Invoice":
        raise FinanceParseError(f"Unexpected root element {root.tag!r}", source_file)

    number = _req_text(root, "i:ID", source_file)
    supplier_ico = _req_text(
        root,
        "i:AccountingSupplierParty/i:Party/i:PartyIdentification/i:ID",
        source_file,
    )
    if not ICO_RE.fullmatch(supplier_ico):
        raise FinanceParseError(f"Invalid supplier IČO {supplier_ico!r}", source_file)

    invoice_id = f"{supplier_ico}-{number}"
    issue_date = _req_date(root, "i:IssueDate", source_file)
    due_date = _req_date(
        root, "i:PaymentMeans/i:Payment/i:Details/i:PaymentDueDate", source_file
    )
    vs = _normalize_vs(
        _text(root, "i:PaymentMeans/i:Payment/i:Details/i:VariableSymbol")
    )
    currency = _text(root, "i:LocalCurrencyCode") or config.CURRENCY

    total_net = _req_dec(
        root, "i:LegalMonetaryTotal/i:TaxExclusiveAmount", source_file, "0.01"
    )
    total_gross = _req_dec(
        root, "i:LegalMonetaryTotal/i:TaxInclusiveAmount", source_file, "0.01"
    )
    total_vat = _req_dec(root, "i:TaxTotal/i:TaxAmount", source_file, "0.01")

    line_elems = root.findall("i:InvoiceLines/i:InvoiceLine", namespaces=NS)
    if not line_elems:
        raise FinanceParseError("ISDOC has no InvoiceLine elements", source_file)

    lines: list[dict[str, Any]] = []
    for line_el in line_elems:
        line_id_raw = _req_text(line_el, "i:ID", source_file)
        try:
            line_no = int(line_id_raw)
        except ValueError as exc:
            raise FinanceParseError(f"Invalid line ID {line_id_raw!r}", source_file) from exc

        description = _req_text(line_el, "i:Item/i:Description", source_file)
        quantity = _req_dec(line_el, "i:InvoicedQuantity", source_file, "0.001")
        unit_price = _req_dec(line_el, "i:UnitPrice", source_file, "0.01")
        amount_net = _req_dec(line_el, "i:LineExtensionAmount", source_file, "0.01")
        vat_rate = _req_dec(
            line_el, "i:ClassifiedTaxCategory/i:Percent", source_file, "0.01"
        )
        vat_amount = _req_dec(line_el, "i:LineExtensionTaxAmount", source_file, "0.01")

        lines.append(
            {
                "invoice_id": invoice_id,
                "line_no": line_no,
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "amount_net": amount_net,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "category": None,
                "project_code": None,
                "source_file": source_file,
            }
        )

    invoice = {
        "invoice_id": invoice_id,
        "supplier_ico": supplier_ico,
        "number": number,
        "vs": vs,
        "issue_date": issue_date,
        "due_date": due_date,
        "total_net": total_net,
        "total_vat": total_vat,
        "total_gross": total_gross,
        "currency": currency,
        "category": None,
        "project_code": None,
        "project_rule": None,
        "has_isdoc": True,
        "source_file": source_file,
    }
    return invoice, lines
