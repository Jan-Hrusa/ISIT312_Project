"""ISDOC 6.0.2 invoice (XML)."""

from lxml import etree

from generators.finance_docs.util import money

NS = "http://isdoc.cz/namespace/2013"
CUSTOMER_NAME = "Stavitel FVE s.r.o."  # synthetic buyer, not the real company
CUSTOMER_ICO = "27000009"


def _add(parent, tag, text=None, **attrib):
    el = etree.SubElement(parent, f"{{{NS}}}{tag}", **attrib)
    if text is not None:
        el.text = str(text)
    return el


def _qty(q) -> str:
    return format(q.normalize(), "f")


def to_xml(inv) -> bytes:
    root = etree.Element(f"{{{NS}}}Invoice", nsmap={None: NS}, version="6.0.2")
    _add(root, "DocumentType", 1)
    _add(root, "ID", inv.number)
    _add(root, "UUID", inv.uuid)
    _add(root, "IssuingSystem", "Synthetic finance generator")
    _add(root, "IssueDate", inv.issue_date.isoformat())
    _add(root, "TaxPointDate", inv.issue_date.isoformat())
    _add(root, "VATApplicable", "true")
    _add(root, "LocalCurrencyCode", "CZK")
    _add(root, "CurrRate", 1)
    _add(root, "RefCurrRate", 1)

    sup = _add(_add(root, "AccountingSupplierParty"), "Party")
    _add(_add(sup, "PartyIdentification"), "ID", inv.supplier["ico"])
    _add(_add(sup, "PartyName"), "Name", inv.supplier["name"])
    cus = _add(_add(root, "AccountingCustomerParty"), "Party")
    _add(_add(cus, "PartyIdentification"), "ID", CUSTOMER_ICO)
    _add(_add(cus, "PartyName"), "Name", CUSTOMER_NAME)

    lines = _add(root, "InvoiceLines")
    for i, ln in enumerate(inv.lines, start=1):
        el = _add(lines, "InvoiceLine")
        _add(el, "ID", i)
        _add(el, "InvoicedQuantity", _qty(ln.quantity), unitCode="C62")
        _add(el, "LineExtensionAmount", money(ln.net))
        _add(el, "LineExtensionAmountTax", money(ln.vat))
        _add(el, "LineExtensionAmountTaxInclusive", money(ln.net + ln.vat))
        _add(el, "UnitPrice", money(ln.unit_price))
        cat = _add(el, "ClassifiedTaxCategory")
        _add(cat, "Percent", _qty(ln.vat_rate))
        _add(cat, "VATCalculationMethod", 0)
        _add(_add(el, "Item"), "Description", ln.description)

    tax = _add(root, "TaxTotal")
    sub = _add(tax, "TaxSubTotal")
    _add(sub, "TaxableAmount", money(inv.net))
    _add(sub, "TaxAmount", money(inv.vat))
    _add(sub, "TaxInclusiveAmount", money(inv.gross))
    _add(_add(sub, "TaxCategory"), "Percent", 21)
    _add(tax, "TaxAmount", money(inv.vat))

    tot = _add(root, "LegalMonetaryTotal")
    _add(tot, "TaxExclusiveAmount", money(inv.net))
    _add(tot, "TaxInclusiveAmount", money(inv.gross))
    _add(tot, "PayableAmount", money(inv.gross))

    pay = _add(_add(root, "PaymentMeans"), "Payment")
    _add(pay, "PaidAmount", money(inv.gross))
    _add(pay, "PaymentMeansCode", 42)
    det = _add(pay, "Details")
    _add(det, "PaymentDueDate", inv.due_date.isoformat())
    _add(det, "ID", inv.supplier["bank_account"])
    _add(det, "BankCode", inv.supplier["bank_code"])
    if inv.vs:  # MISSING_VS (Task 17.1): the element is left out
        _add(det, "VariableSymbol", inv.vs)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
