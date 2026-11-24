"""PDF copy of an invoice (same numbers as the ISDOC)."""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from generators.finance_docs.util import money_cz

CUSTOMER = "Stavitel FVE s.r.o."


def write(path, inv) -> None:
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1, pageCompression=0)
    c.setTitle(f"Faktura {inv.number}")
    c.setAuthor("")
    _, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"Faktura - danovy doklad c. {inv.number}")
    c.setFont("Helvetica", 10)
    y -= 30
    c.drawString(50, y, f"Dodavatel: {inv.supplier['name']}")
    y -= 14
    c.drawString(50, y, f"ICO: {inv.supplier['ico']}")
    y -= 14
    c.drawString(50, y, f"Odberatel: {CUSTOMER}")
    y -= 24
    c.drawString(50, y, f"Datum vystaveni: {inv.issue_date.isoformat()}")
    y -= 14
    c.drawString(50, y, f"Datum splatnosti: {inv.due_date.isoformat()}")
    y -= 14
    c.drawString(50, y, f"Ucet: {inv.supplier['bank_account']}/{inv.supplier['bank_code']}")
    if inv.vs:  # MISSING_VS: the PDF shows no variable symbol
        y -= 14
        c.drawString(50, y, f"Variabilni symbol: {inv.vs}")
    y -= 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Polozka")
    c.drawRightString(340, y, "Mnozstvi")
    c.drawRightString(420, y, "Cena/ks")
    c.drawRightString(500, y, "Bez DPH")
    c.drawRightString(560, y, "DPH 21%")
    c.setFont("Helvetica", 10)
    for ln in inv.lines:
        y -= 16
        c.drawString(50, y, ln.description[:48])
        c.drawRightString(340, y, f"{ln.quantity.normalize():f}")
        c.drawRightString(420, y, money_cz(ln.unit_price))
        c.drawRightString(500, y, money_cz(ln.net))
        c.drawRightString(560, y, money_cz(ln.vat))
    y -= 30
    c.drawString(50, y, f"Zaklad dane: {money_cz(inv.net)} CZK")
    y -= 14
    c.drawString(50, y, f"DPH 21 %: {money_cz(inv.vat)} CZK")
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Celkem k uhrade: {money_cz(inv.gross)} CZK")
    c.showPage()
    c.save()
