"""Invoice plan: who invoices which project, when, for how much."""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from generators.finance_docs import budgets as budgets_mod
from generators.finance_docs import master
from generators.finance_docs.util import CATEGORIES, DATA_END, q2

VAT_RATE = Decimal(21)
TARGET_INVOICES = 60  # per signed project
PDF_ONLY_SHARE = 0.10
AMBER_PROJECT_SHARE = 0.15  # projects with one category at 106-112%

# part of the construction period in which a category is invoiced (from, to)
WINDOWS = {
    "DESIGN": (0.00, 0.25),
    "SURVEY": (0.00, 0.20),
    "EARTHWORKS": (0.05, 0.50),
    "STRUCTURES": (0.15, 0.65),
    "PANELS": (0.20, 0.70),
    "INVERTERS": (0.30, 0.75),
    "BATTERIES": (0.40, 0.80),
    "CABLES": (0.30, 0.85),
    "GRID": (0.60, 1.00),
    "OTHER": (0.00, 1.00),
}

DESCRIPTIONS = {
    "PANELS": ["Fotovoltaicky panel 545 Wp mono", "Fotovoltaicky panel 600 Wp bifacial",
               "Doprava fotovoltaickych panelu", "Panel 450 Wp black frame"],
    "INVERTERS": ["Stridac 100 kW trifazovy", "Stridac 50 kW string", "Komunikacni modul invertoru",
                  "Uvedeni stridace do provozu"],
    "BATTERIES": ["Bateriovy modul 100 kWh", "Rizeni baterioveho systemu", "Kontejner pro baterie",
                  "Pozarni ochrana baterioveho uloziste"],
    "STRUCTURES": ["Hlinikova konstrukce pro panely", "Zemni sroub 1500 mm", "Montazni sada ocelova",
                   "Nosna konstrukce stolu"],
    "CABLES": ["Solarni kabel 6 mm2", "Kabel AYKY 4x240", "Trubky a kabelove zlaby",
               "Konektory MC4"],
    "EARTHWORKS": ["Terenni upravy a skrabani", "Vykop kabelovych rysu", "Oploceni areálu",
                   "Zpevnene plochy a cesty"],
    "GRID": ["Pripojeni k distribucni siti", "Trafostanice 22 kV", "Rozvadec VN",
             "Mereni a ochrany"],
    "DESIGN": ["Projektova dokumentace", "Stavebni povoleni - podklady", "Dokumentace skutecneho provedeni"],
    "SURVEY": ["Geodeticke zamereni pozemku", "Vytycovani stavby", "Geometricky plan"],
    "OTHER": ["Pronajem jerabu", "Ostraha staveniste", "Doprava materialu", "Pojisteni stavby"],
}  # fmt: skip


@dataclass
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal
    net: Decimal
    vat_rate: Decimal
    vat: Decimal


@dataclass
class Invoice:
    supplier: dict
    number: str  # YYYYNNNNN per supplier
    project_code: str  # the TRUE project (truth, ledger)
    category: str
    lines: list[Line]
    issue_date: date
    due_date: date
    booking_date: date
    vs: str | None
    pdf_only: bool
    uuid: str
    # what the accountant booked; Task 17.1 sets None for NO_PROJECT
    booked_project_code: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def invoice_id(self) -> str:
        return f"{self.supplier['ico']}-{self.number}"

    @property
    def net(self) -> Decimal:
        return sum((ln.net for ln in self.lines), Decimal("0.00"))

    @property
    def vat(self) -> Decimal:
        return sum((ln.vat for ln in self.lines), Decimal("0.00"))

    @property
    def gross(self) -> Decimal:
        return self.net + self.vat


def _spend_fractions(budget: dict[str, Decimal], rng) -> dict[str, float]:
    """Share of each category's budget that gets invoiced (before DATA_END clipping)."""
    fr = {c: rng.uniform(0.86, 0.99) for c in CATEGORIES}
    amber = rng.random() < AMBER_PROJECT_SHARE
    pick = rng.choice([c for c in CATEGORIES if budget[c] > 0])
    if amber:
        fr[pick] = rng.uniform(1.06, 1.115)
    return fr


def _split_lines(part_cents: int, category: str, rng) -> list[Line]:
    n = rng.randint(1, 5)
    n = min(n, max(1, part_cents // 100_000))  # no tiny lines
    weights = [rng.uniform(0.5, 1.5) for _ in range(n)]
    sw = sum(weights)
    lines = []
    for w in weights:
        target = Decimal(round(part_cents * w / sw)) / 100
        qty = Decimal(rng.randint(1, 200)) if category not in ("DESIGN", "SURVEY") else Decimal(1)
        unit = q2(target / qty)
        if unit <= 0:
            qty, unit = Decimal(1), q2(max(target, Decimal("0.01")))
        net = q2(qty * unit)
        vat = q2(net * VAT_RATE / 100)
        lines.append(Line(rng.choice(DESCRIPTIONS[category]), qty, unit, net, VAT_RATE, vat))
    return lines


def make_invoices(projects, suppliers, budgets, rng) -> list[Invoice]:
    by_cat = {c: [s for s in suppliers if s["category"] == c] for c in CATEGORIES}
    raw = []
    for p in sorted(projects, key=lambda x: x["project_code"]):
        if p["status"] == "NOT_SIGNED" or p["construction_start"] > DATA_END:
            continue
        budget = budgets[p["project_code"]]
        total_budget = sum(budget.values())
        fractions = _spend_fractions(budget, rng)
        start, end = p["construction_start"], p["construction_end"]
        dur = (end - start).days
        for cat in CATEGORIES:
            amount = budget[cat]
            if amount <= 0:
                continue
            target_cents = float(amount) * fractions[cat] * 100
            share = float(amount / total_budget)
            n = max(1, round(TARGET_INVOICES * share * rng.uniform(0.9, 1.1)))
            weights = [rng.uniform(0.5, 1.5) for _ in range(n)]
            sw = sum(weights)
            lo, hi = WINDOWS[cat]
            for w in weights:
                part = round(target_cents * w / sw)
                day = start + timedelta(days=int(dur * rng.uniform(lo, hi)))
                lines = _split_lines(part, cat, rng)  # always draw, then maybe drop
                supplier = rng.choice(by_cat[cat])
                if day > DATA_END:  # ACTIVE projects: nothing after DATA_END
                    continue
                raw.append((day, supplier, p["project_code"], cat, lines))
    raw.sort(key=lambda r: (r[0], r[1]["ico"], r[2], r[3]))

    invoices: list[Invoice] = []
    counters: dict[tuple[str, int], int] = {}
    for day, supplier, code, cat, lines in raw:
        key = (supplier["ico"], day.year)
        counters[key] = counters.get(key, 0) + 1
        number = f"{day.year}{counters[key]:05d}"
        invoices.append(
            Invoice(
                supplier=supplier,
                number=number,
                project_code=code,
                category=cat,
                lines=lines,
                issue_date=day,
                due_date=day + timedelta(days=rng.randint(14, 30)),
                booking_date=day + timedelta(days=rng.randint(2, 10)),
                vs=number,
                pdf_only=False,
                uuid=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                booked_project_code=code,
            )
        )
    k = round(PDF_ONLY_SHARE * len(invoices))
    for i in rng.sample(range(len(invoices)), k):
        invoices[i].pdf_only = True
    return invoices


def build_plan(rng, scale: int = 1):
    """projects, suppliers, budgets {code: {cat: amount}}, invoices - all from one rng."""
    projects = master.make_projects(rng, scale)
    suppliers = master.make_suppliers(rng)
    budgets = {}
    for p in projects:
        if p["status"] != "NOT_SIGNED":
            budgets[p["project_code"]] = budgets_mod.make_budget(p, rng)
    invoices = make_invoices(projects, suppliers, budgets, rng)
    return projects, suppliers, budgets, invoices
