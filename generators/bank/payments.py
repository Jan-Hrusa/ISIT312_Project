"""Plan synthetic orders, bank movements, and planted cases."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from common import config
from generators.bank.kpc import Order
from generators.bank.statements import DAY, Movement

BANK_WEIGHTS = {"RB": 70, "UCB": 10, "KB": 10, "CS": 10}


@dataclass(frozen=True)
class Planted:
    problem: str
    invoice_id: str
    record: Movement | Order | None
    detail: str


def _days(first: date, last: date):
    for offset in range((last - first).days + 1):
        yield first + timedelta(days=offset)


def _next_business_day(day: date) -> date:
    day += DAY
    while day.weekday() >= 5:
        day += DAY
    return day


def schedules(issue: date, first: date, last: date, *, late: bool = False):
    """Return (run, requested due, debit) triples in stable date order."""
    for due in _days(max(issue, first), min(last, config.DATA_END)):
        for debit in (due, _next_business_day(due)):
            if debit > config.DATA_END or (late and debit > last):
                continue
            for run in _days(max(issue, debit - timedelta(days=3)), due):
                if run.weekday() in (1, 4):
                    yield run, due, debit


def _cents(value: str) -> int:
    amount = Decimal(value) * 100
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValueError(f"Expected a positive CZK amount in whole haléře: {value}")
    return int(amount)


def _credits(projects, rng):
    credits = []
    for project in sorted(projects, key=lambda row: row["project_code"]):
        if not project["signed_date"]:
            continue
        signed = date.fromisoformat(project["signed_date"])
        start = max(signed, config.DATA_START)
        if start > config.DATA_END:
            continue
        # Spread milestone credits across the observable part of the project.
        end = min(date.fromisoformat(project["construction_end"]), config.DATA_END)
        count = rng.choice((3, 4))
        amount, remainder = divmod(_cents(project["contract_value"]), count)
        span = (max(start, end) - start).days
        for index in range(count):
            day = start + timedelta(days=span * index // (count - 1))
            credits.append(
                Movement(
                    "RB",
                    day,
                    amount + (index < remainder),
                    "7788990011",
                    "0800",
                    "",
                    f"Investor milestone {project['project_code']}",
                )
            )
    return credits


def _choose_cases(eligible, ordinary, late, rng):
    # Integer arithmetic implements nearest integer, with exact halves rounded up.
    size = len(eligible)
    counts = {
        "LATE": (3 * size + 50) // 100,
        "INSTALMENTS": (2 * size + 50) // 100,
        "PARTIAL": (size + 50) // 100,
        "NEVER": (size + 50) // 100,
        "WRONG_VS": 15,
        "ORDER_LOST": 10,
    }
    cases = {}
    for problem, count in counts.items():
        pool = []
        for invoice in eligible:
            key = invoice["invoice_id"]
            if key in cases or (problem == "LATE" and not late[key]):
                continue
            if problem == "INSTALMENTS" and len({entry[2] for entry in ordinary[key]}) < 2:
                continue
            pool.append(key)
        if len(pool) < count:
            raise ValueError(f"{problem}: need {count} eligible invoices, found {len(pool)}")
        cases.update(dict.fromkeys(rng.sample(pool, count), problem))
    return cases


def plan(ledger, suppliers, projects, rng):
    rows = sorted(ledger, key=lambda row: row["invoice_id"])
    names = {row["ico"]: row["name"] for row in suppliers}
    ordinary, late = {}, {}
    in_period = []
    planted = []
    for row in rows:
        key = row["invoice_id"]
        due = date.fromisoformat(row["due_date"])
        if not config.DATA_START <= due <= config.DATA_END:
            if not row["vs"]:
                planted.append(Planted("NO_VS", key, None, "Missing VS in input ledger"))
            continue
        issue = max(date.fromisoformat(row["issue_date"]), config.DATA_START)
        ordinary[key] = list(schedules(issue, due - timedelta(days=5), due))
        late[key] = list(schedules(issue, due + timedelta(days=5), due + timedelta(days=40), late=True))
        in_period.append(row)

    cases = _choose_cases([row for row in in_period if row["vs"]], ordinary, late, rng)
    used_vs = {row["vs"] for row in rows}
    debits, orders = [], []
    for row in in_period:
        key = row["invoice_id"]
        problem = cases.get(key, "" if row["vs"] else "NO_VS")
        bank = rng.choices(tuple(BANK_WEIGHTS), weights=tuple(BANK_WEIGHTS.values()))[0]
        if problem == "NEVER":
            planted.append(Planted(problem, key, None, "Invoice left unpaid"))
            continue
        options = late[key] if problem == "LATE" else ordinary[key]
        if not options:
            raise ValueError(f"{key}: no legal {problem or 'ordinary'} payment schedule")
        slots = [rng.choice(options)]
        cents = _cents(row["gross_amount"])
        amounts = [cents]
        if problem in ("PARTIAL", "INSTALMENTS"):
            first = (60 * cents + 50) // 100
            amounts = [first]
            if problem == "INSTALMENTS":
                slots.append(rng.choice([entry for entry in options if entry[2] != slots[0][2]]))
                slots.sort(key=lambda entry: entry[2])
                amounts.append(cents - first)
        vs = row["vs"]
        if problem == "WRONG_VS":
            while vs in used_vs:
                vs = str(rng.randrange(1_000_000_000, 10_000_000_000))
            used_vs.add(vs)
        for index, ((run, due, debit), amount) in enumerate(zip(slots, amounts, strict=True)):
            account, code = row["supplier_account"], row["supplier_bank_code"]
            order = Order(bank, run, due, amount, account, code, vs, key)
            orders.append(order)
            movement = None
            if problem != "ORDER_LOST":
                detail = f"{names[row['supplier_ico']]} invoice {key.rsplit('-', 1)[-1]}"
                movement = Movement(bank, debit, -amount, account, code, vs, detail, key, order.ks)
                debits.append(movement)
            if problem and index == 0:
                planted.append(Planted(problem, key, movement or order, "Planted payment case"))

    credits = _credits(projects, rng)
    occupied = {item.value_date for item in (*debits, *credits) if item.bank == "RB"}
    available = [day for day in _days(config.DATA_START, config.DATA_END) if day not in occupied]
    if not available:
        raise ValueError("BAD_FILE: no RB day without other movements")
    bad = Movement(
        "RB", rng.choice(available), 2500000, "7788990011", "0800", "", "Test credit", malformed=True
    )
    credits.append(bad)
    planted.append(Planted("BAD_FILE", "", bad, "Credit record shortened by two characters"))
    return debits, credits, orders, planted
