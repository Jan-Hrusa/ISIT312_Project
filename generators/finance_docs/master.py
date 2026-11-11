"""Projects and suppliers (master data)."""

import csv
import math
from datetime import date, timedelta
from decimal import Decimal

from generators.finance_docs.util import (
    CATEGORIES,
    DATA_END,
    DATA_START,
    money,
)

# (town, kraj, lat, lon) - fixed list of real Czech towns (approximate centres)
TOWNS = [
    ("Kladno", "Středočeský", 50.147, 14.103),
    ("Mladá Boleslav", "Středočeský", 50.412, 14.906),
    ("Kolín", "Středočeský", 50.028, 15.200),
    ("Kutná Hora", "Středočeský", 49.949, 15.268),
    ("Beroun", "Středočeský", 49.964, 14.072),
    ("Příbram", "Středočeský", 49.690, 14.010),
    ("Benešov", "Středočeský", 49.782, 14.687),
    ("Mělník", "Středočeský", 50.350, 14.474),
    ("Nymburk", "Středočeský", 50.186, 15.042),
    ("Rakovník", "Středočeský", 50.103, 13.733),
    ("České Budějovice", "Jihočeský", 48.975, 14.474),
    ("Tábor", "Jihočeský", 49.414, 14.658),
    ("Písek", "Jihočeský", 49.309, 14.147),
    ("Strakonice", "Jihočeský", 49.261, 13.902),
    ("Jindřichův Hradec", "Jihočeský", 49.144, 15.003),
    ("Prachatice", "Jihočeský", 49.012, 13.999),
    ("Český Krumlov", "Jihočeský", 48.811, 14.317),
    ("Třeboň", "Jihočeský", 49.004, 14.771),
    ("Plzeň", "Plzeňský", 49.747, 13.378),
    ("Klatovy", "Plzeňský", 49.396, 13.295),
    ("Rokycany", "Plzeňský", 49.743, 13.594),
    ("Domažlice", "Plzeňský", 49.440, 12.929),
    ("Tachov", "Plzeňský", 49.795, 12.633),
    ("Karlovy Vary", "Karlovarský", 50.232, 12.872),
    ("Cheb", "Karlovarský", 50.080, 12.374),
    ("Sokolov", "Karlovarský", 50.181, 12.640),
    ("Ostrov", "Karlovarský", 50.306, 12.940),
    ("Ústí nad Labem", "Ústecký", 50.661, 14.042),
    ("Most", "Ústecký", 50.503, 13.636),
    ("Teplice", "Ústecký", 50.640, 13.824),
    ("Chomutov", "Ústecký", 50.460, 13.418),
    ("Děčín", "Ústecký", 50.772, 14.215),
    ("Litoměřice", "Ústecký", 50.533, 14.131),
    ("Louny", "Ústecký", 50.357, 13.797),
    ("Žatec", "Ústecký", 50.327, 13.545),
    ("Liberec", "Liberecký", 50.771, 15.058),
    ("Jablonec nad Nisou", "Liberecký", 50.724, 15.171),
    ("Česká Lípa", "Liberecký", 50.686, 14.538),
    ("Turnov", "Liberecký", 50.587, 15.157),
    ("Semily", "Liberecký", 50.603, 15.335),
    ("Hradec Králové", "Královéhradecký", 50.209, 15.832),
    ("Trutnov", "Královéhradecký", 50.561, 15.912),
    ("Náchod", "Královéhradecký", 50.416, 16.163),
    ("Jičín", "Královéhradecký", 50.437, 15.351),
    ("Rychnov nad Kněžnou", "Královéhradecký", 50.163, 16.275),
    ("Pardubice", "Pardubický", 50.038, 15.776),
    ("Chrudim", "Pardubický", 49.951, 15.795),
    ("Svitavy", "Pardubický", 49.756, 16.469),
    ("Ústí nad Orlicí", "Pardubický", 49.974, 16.393),
    ("Litomyšl", "Pardubický", 49.868, 16.314),
    ("Jihlava", "Vysočina", 49.396, 15.591),
    ("Třebíč", "Vysočina", 49.215, 15.882),
    ("Žďár nad Sázavou", "Vysočina", 49.564, 15.939),
    ("Havlíčkův Brod", "Vysočina", 49.607, 15.581),
    ("Pelhřimov", "Vysočina", 49.431, 15.223),
    ("Brno", "Jihomoravský", 49.195, 16.608),
    ("Znojmo", "Jihomoravský", 48.856, 16.049),
    ("Břeclav", "Jihomoravský", 48.759, 16.882),
    ("Hodonín", "Jihomoravský", 48.849, 17.126),
    ("Vyškov", "Jihomoravský", 49.277, 16.999),
    ("Blansko", "Jihomoravský", 49.342, 16.646),
    ("Olomouc", "Olomoucký", 49.594, 17.251),
    ("Prostějov", "Olomoucký", 49.472, 17.111),
    ("Přerov", "Olomoucký", 49.455, 17.451),
    ("Šumperk", "Olomoucký", 49.965, 16.971),
    ("Jeseník", "Olomoucký", 50.229, 17.205),
    ("Zlín", "Zlínský", 49.226, 17.666),
    ("Kroměříž", "Zlínský", 49.298, 17.393),
    ("Uherské Hradiště", "Zlínský", 49.070, 17.460),
    ("Vsetín", "Zlínský", 49.339, 17.996),
    ("Valašské Meziříčí", "Zlínský", 49.472, 17.971),
    ("Ostrava", "Moravskoslezský", 49.835, 18.292),
    ("Opava", "Moravskoslezský", 49.938, 17.904),
    ("Karviná", "Moravskoslezský", 49.854, 18.542),
    ("Frýdek-Místek", "Moravskoslezský", 49.685, 18.348),
    ("Nový Jičín", "Moravskoslezský", 49.594, 18.010),
    ("Třinec", "Moravskoslezský", 49.678, 18.670),
    ("Bruntál", "Moravskoslezský", 49.988, 17.464),
]
TOWN_BY_NAME = {t[0]: t for t in TOWNS}

PROJECT_COLUMNS = [
    "project_code",
    "name",
    "town",
    "region",
    "lat",
    "lon",
    "radius_m",
    "mwp",
    "has_battery",
    "contract_value",
    "offer_date",
    "signed_date",
    "construction_start",
    "construction_end",
    "status",
]
SUPPLIER_COLUMNS = ["ico", "name", "category", "bank_account", "bank_code"]
BANK_CODES = ["0100", "0300", "0800", "2010", "2700", "5500", "6210"]

MIN_SITE_DISTANCE_KM = 3.0
NOT_SIGNED_SHARE = 0.10
BATTERY_SHARE = 0.40


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _pick_site(rng, sites):
    """A town and a point 1-5 km from its centre, >= 3 km from every other site.

    If a very large dataset (scale 10) runs out of room, the offset limit grows
    slowly so that the 3 km separation always holds.
    """
    attempt = 0
    while True:
        max_off = 5.0 + max(0, attempt - 400) / 100.0
        town, region, tlat, tlon = rng.choice(TOWNS)
        bearing = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(1.0, max_off)
        lat = tlat + dist * math.cos(bearing) / 111.32
        lon = tlon + dist * math.sin(bearing) / (111.32 * math.cos(math.radians(tlat)))
        attempt += 1
        if all(haversine_km(lat, lon, s[0], s[1]) >= MIN_SITE_DISTANCE_KM for s in sites):
            return town, region, round(lat, 6), round(lon, 6)


def make_projects(rng, scale: int = 1) -> list[dict]:
    """8-9 offers a year x scale (at most 99), ~10% never signed."""
    projects: list[dict] = []
    sites: list[tuple[float, float]] = []
    town_counter: dict[str, int] = {}
    last_year = DATA_END.year
    for year in range(DATA_START.year, last_year + 1):
        n = min(99, rng.choice((8, 9)) * scale)
        last_offer = min(date(year, 10, 31), DATA_END - timedelta(days=61))
        first_offer = date(year, 1, 1)
        span = (last_offer - first_offer).days
        offsets = sorted(rng.randint(0, span) for _ in range(n))
        for i, off in enumerate(offsets, start=1):
            offer = first_offer + timedelta(days=off)
            signed_flag = rng.random() >= NOT_SIGNED_SHARE
            sign_gap = rng.randint(14, 60)
            start_gap = rng.randint(30, 90)
            duration = rng.randint(240, 425)
            mwp = Decimal(str(round(rng.uniform(1.0, 2.0), 2)))
            has_battery = rng.random() < BATTERY_SHARE
            per_mwp = rng.uniform(18_000_000, 30_000_000)
            value = Decimal(round(float(mwp) * per_mwp / 1000.0) * 1000)
            radius = rng.randint(300, 800)
            town, region, lat, lon = _pick_site(rng, sites)
            sites.append((lat, lon))
            town_counter[town] = town_counter.get(town, 0) + 1

            signed = start = end = None
            status = "NOT_SIGNED"
            if signed_flag:
                signed = min(offer + timedelta(days=sign_gap), date(year, 12, 31), DATA_END)
                start = signed + timedelta(days=start_gap)
                end = start + timedelta(days=duration)
                status = "COMPLETED" if end < DATA_END else "ACTIVE"
            projects.append(
                {
                    "project_code": f"FVE-{year}-{i:02d}",
                    "name": f"FVE {town} {town_counter[town]}",
                    "town": town,
                    "region": region,
                    "lat": lat,
                    "lon": lon,
                    "radius_m": radius,
                    "mwp": mwp,
                    "has_battery": has_battery,
                    "contract_value": value,
                    "offer_date": offer,
                    "signed_date": signed,
                    "construction_start": start,
                    "construction_end": end,
                    "status": status,
                }
            )
    return projects


def _csv_value(key, value):
    if value is None:
        return ""
    if key in ("lat", "lon"):
        return f"{value:.6f}"
    if key == "mwp" or key == "contract_value":
        return money(value)
    if key == "has_battery":
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def write_projects_csv(path, projects: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(PROJECT_COLUMNS)
        for p in projects:
            w.writerow([_csv_value(k, p[k]) for k in PROJECT_COLUMNS])


# ---------------------------------------------------------------- suppliers

SUPPLIERS_PER_CATEGORY = {
    "PANELS": 4,
    "INVERTERS": 3,
    "BATTERIES": 3,
    "STRUCTURES": 4,
    "CABLES": 3,
    "EARTHWORKS": 4,
    "GRID": 2,
    "DESIGN": 3,
    "SURVEY": 3,
    "OTHER": 4,
}
EXTRA_SUPPLIERS = 2  # 33 + 2 = 35

_PREFIX = {
    "PANELS": ["Solar", "SunTech", "Fotovolt", "PV Trade"],
    "INVERTERS": ["Invertech", "Energo Menice", "Power Konverze", "Elektro Menic"],
    "BATTERIES": ["Akumulatory", "Battery Store", "Energo Sklad", "Li-Ion"],
    "STRUCTURES": ["Ocel", "Konstrukce", "Montaz Systemy", "Kovo"],
    "CABLES": ["Kabely", "Elektro Rozvody", "Kabel Trade", "Vodice"],
    "EARTHWORKS": ["Zemni Prace", "Stavby Zeme", "Bagry", "Terra"],
    "GRID": ["Energo Pripojky", "Sit Montaz", "Rozvodny", "Elektro Sit"],
    "DESIGN": ["Projekce", "Projekt Studio", "Atelier", "Inzenyring"],
    "SURVEY": ["Geodezie", "Zememerici", "Geo Mapy", "Mereni"],
    "OTHER": ["Servis", "Logistika", "Ostraha", "Pronajem Techniky"],
}
_SURNAMES = [
    "Novak", "Svoboda", "Dvorak", "Cerny", "Prochazka", "Kucera", "Vesely",
    "Horak", "Nemec", "Pokorny", "Marek", "Pospisil", "Hajek", "Jelinek", "Kral",
    "Ruzicka", "Benes", "Fiala", "Sedlacek", "Dolezal", "Zeman", "Kolar",
    "Navratil", "Cermak", "Vana",
]  # fmt: skip
_SUFFIX = ["s.r.o.", "a.s.", "spol. s r.o."]


def _fake_ico(rng) -> str:
    """8 digits with a deliberately WRONG check digit, so it is never a real IČO."""
    first7 = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(6)]
    total = sum(d * w for d, w in zip(first7, range(8, 1, -1), strict=True))
    check = (11 - total % 11) % 10
    wrong = (check + rng.randint(1, 9)) % 10
    return "".join(map(str, first7)) + str(wrong)


def make_suppliers(rng) -> list[dict]:
    plan = list(CATEGORIES)
    cats = []
    for c in plan:
        cats += [c] * SUPPLIERS_PER_CATEGORY[c]
    extra = [rng.choice(plan) for _ in range(EXTRA_SUPPLIERS)]
    cats += extra
    suppliers, used_ico, used_name = [], set(), set()
    for cat in cats:
        while True:
            name = f"{rng.choice(_PREFIX[cat])} {rng.choice(_SURNAMES)} {rng.choice(_SUFFIX)}"
            if name not in used_name:
                used_name.add(name)
                break
        while True:
            ico = _fake_ico(rng)
            if ico not in used_ico:
                used_ico.add(ico)
                break
        account = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(rng.randint(5, 9)))
        suppliers.append(
            {
                "ico": ico,
                "name": name,
                "category": cat,
                "bank_account": account,
                "bank_code": rng.choice(BANK_CODES),
            }
        )
    suppliers.sort(key=lambda s: s["ico"])
    return suppliers


def write_suppliers_csv(path, suppliers: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(SUPPLIER_COLUMNS)
        for s in suppliers:
            w.writerow([s[k] for k in SUPPLIER_COLUMNS])
