"""Planted finance problems (Task 17.1).

apply() runs inside the Task 5 generator after plan.make_invoices and before any file is written.
It changes the planned Invoice objects in memory (so the ISDOC, PDF, Money export and invoice
ledger all agree) and returns one truth row per planted problem. All randomness comes from the
generator's one rng, so the seed still decides everything.

Problem      Count (x scale)  What is changed
OVERRUN      6 projects       invoices are added until one category has spent 118-130% of its budget
NO_PROJECT   25 invoices      booked_project_code = None (blank project_code in the Money export row)
DUPLICATE    5 invoices       the ISDOC and PDF are sent again as <ico>_<number>_resent.* 1-5 days later
MISSING_VS   10 invoices      vs = None (no VariableSymbol in ISDOC, PDF and Money export)
PARSE_ERROR  2 invoices       the ISDOC is cut off right after <InvoiceLines>

Flags that the file writers read are kept in Invoice.extra: "resent_date", "resent_uuid", "truncated".
"""

import csv
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from generators.finance_docs import plan
from generators.finance_docs.util import DATA_END, q2

PROBLEMS = ("OVERRUN", "NO_PROJECT", "DUPLICATE", "MISSING_VS", "PARSE_ERROR")
COUNTS = {"OVERRUN": 6, "NO_PROJECT": 25, "DUPLICATE": 5, "MISSING_VS": 10, "PARSE_ERROR": 2}
OVERRUN_CATEGORIES = (("EARTHWORKS", 3), ("CABLES", 2), ("GRID", 1))
TRUTH_COLUMNS = ["problem", "ref", "project_code", "detail"]

OVERRUN_TARGET = (1.19, 1.29)  # share of the category budget that is drawn as the goal
OVERRUN_ALLOWED = (1.18, 1.30)  # what the finished plan must satisfy (task: 118-130%)
MIN_CONSTRUCTION_DAYS = 183  # "at least 6 months of construction data"
NO_PROJECT_WINDOW_DAYS = 90  # the window of Task 20.1's SINGLE_ACTIVE rule
MAX_RESEND_DAYS = 5
# Task 6 pays a MISSING_VS invoice with an empty VS, and Task 25 reports it as OVERDUE with an unmatched
# payment on DATA_END (its as_of). That needs a due date on or before DATA_END - 6 days, the margin Task 6
# keeps for its own planted cases (an uncleared order is reported only after its due date + 5 days).
PAYABLE_MARGIN_DAYS = 6


def apply(invoices, projects, rng, *, budgets, suppliers, scale=1) -> list[dict]:
    """Plant the problems in `invoices` (in place) and return the truth rows.

    budgets and suppliers (both from plan.build_plan) are needed to add the overrun invoices.
    """
    by_code = {p["project_code"]: p for p in projects}
    used: set[str] = set()  # invoice_ids that already carry a planted problem
    overrun_pairs: set[tuple[str, str]] = set()
    truth: list[dict] = []
    truth += _plant_overruns(invoices, by_code, budgets, suppliers, rng, scale, used, overrun_pairs)
    truth += _plant_no_project(invoices, by_code, rng, scale, used, overrun_pairs)
    truth += _plant_duplicates(invoices, rng, scale, used)
    truth += _plant_missing_vs(invoices, rng, scale, used)
    truth += _plant_parse_errors(invoices, rng, scale, used)
    invoices.sort(key=_sort_key)
    order = {name: i for i, name in enumerate(PROBLEMS)}
    truth.sort(key=lambda r: (order[r["problem"]], r["ref"]))
    return truth


def write(rows, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(TRUTH_COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in TRUTH_COLUMNS])


def _sort_key(inv):
    return (inv.issue_date, inv.supplier["ico"], inv.project_code, inv.category, inv.number)


def _take(pool, n, rng, what):
    if len(pool) < n:
        raise ValueError(f"not enough candidates for {what}: need {n}, have {len(pool)}")
    return rng.sample(pool, n)


def _new_uuid(rng) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _lines(part_cents: int, category: str, rng) -> list[plan.Line]:
    """1-5 invoice lines adding up to about part_cents (same rule as the Task 5 plan)."""
    n = min(rng.randint(1, 5), max(1, part_cents // 100_000))
    weights = [rng.uniform(0.5, 1.5) for _ in range(n)]
    total = sum(weights)
    lines = []
    for w in weights:
        target = Decimal(round(part_cents * w / total)) / 100
        qty = Decimal(rng.randint(1, 200)) if category not in ("DESIGN", "SURVEY") else Decimal(1)
        unit = q2(target / qty)
        if unit <= 0:
            qty, unit = Decimal(1), q2(max(target, Decimal("0.01")))
        net = q2(qty * unit)
        vat = q2(net * plan.VAT_RATE / 100)
        lines.append(plan.Line(rng.choice(plan.DESCRIPTIONS[category]), qty, unit, net, plan.VAT_RATE, vat))
    return lines


# ------------------------------------------------------------------ OVERRUN


def _plant_overruns(invoices, by_code, budgets, suppliers, rng, scale, used, overrun_pairs):
    eligible = sorted(
        code
        for code, p in by_code.items()
        if code in budgets
        and p["status"] != "NOT_SIGNED"
        and (min(p["construction_end"], DATA_END) - p["construction_start"]).days >= MIN_CONSTRUCTION_DAYS
    )
    wanted = [cat for cat, n in OVERRUN_CATEGORIES for _ in range(n * scale)]
    chosen = _take(eligible, len(wanted), rng, "OVERRUN")

    spent: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    seq: dict[tuple[str, int], int] = {}  # highest invoice number per (supplier, year)
    for inv in invoices:
        spent[(inv.project_code, inv.category)] += inv.net
        key = (inv.supplier["ico"], int(inv.number[:4]))
        seq[key] = max(seq.get(key, 0), int(inv.number[4:]))
    by_category = {
        cat: sorted((s for s in suppliers if s["category"] == cat), key=lambda s: s["ico"])
        for cat, _ in OVERRUN_CATEGORIES
    }

    rows, added = [], []
    for code, cat in zip(chosen, wanted, strict=True):
        p, budget = by_code[code], budgets[code][cat]
        start, end = p["construction_start"], min(p["construction_end"], DATA_END)
        dur = (p["construction_end"] - start).days
        lo_w, hi_w = plan.WINDOWS[cat]
        lo = start + timedelta(days=int(dur * lo_w))
        hi = min(start + timedelta(days=int(dur * hi_w)), end)
        if hi < lo:  # the category's usual window lies after DATA_END (ACTIVE project)
            lo, hi = start, end

        target = budget * Decimal(str(round(rng.uniform(*OVERRUN_TARGET), 4)))
        extra_cents = int((target - spent[(code, cat)]) * 100)
        n_new = max(2, round(float(Decimal(extra_cents) / 100 / budget) / 0.12))
        weights = [rng.uniform(0.6, 1.4) for _ in range(n_new)]
        parts = [round(extra_cents * w / sum(weights)) for w in weights]
        parts[-1] += extra_cents - sum(parts)

        for part in parts:
            day = lo + timedelta(days=rng.randint(0, (hi - lo).days))
            supplier = rng.choice(by_category[cat])
            lines = _lines(part, cat, rng)
            key = (supplier["ico"], day.year)
            seq[key] = seq.get(key, 0) + 1
            number = f"{day.year}{seq[key]:05d}"
            inv = plan.Invoice(
                supplier=supplier,
                number=number,
                project_code=code,
                category=cat,
                lines=lines,
                issue_date=day,
                due_date=day + timedelta(days=rng.randint(14, 30)),
                booking_date=day + timedelta(days=rng.randint(2, 10)),
                vs=number,
                pdf_only=rng.random() < plan.PDF_ONLY_SHARE,
                uuid=_new_uuid(rng),
                booked_project_code=code,
            )
            added.append(inv)
            used.add(inv.invoice_id)
            spent[(code, cat)] += inv.net

        ratio = spent[(code, cat)] / budget
        if not OVERRUN_ALLOWED[0] <= ratio <= OVERRUN_ALLOWED[1]:
            raise ValueError(f"overrun of {code}/{cat} is {ratio:.3f}, outside {OVERRUN_ALLOWED}")
        overrun_pairs.add((code, cat))
        rows.append(
            {
                "problem": "OVERRUN",
                "ref": f"{code}/{cat}",
                "project_code": code,
                "detail": f"{cat} spent {float(ratio):.1%} of its budget {budget:.2f} CZK "
                f"({n_new} invoices added)",
            }
        )
    invoices.extend(added)
    return rows


# --------------------------------------------------------------- NO_PROJECT


def _plant_no_project(invoices, by_code, rng, scale, used, overrun_pairs):
    by_supplier = defaultdict(list)
    for inv in invoices:
        by_supplier[inv.supplier["ico"]].append(inv)

    def deciding_projects(inv) -> set[str]:
        """Projects Task 20.1's SINGLE_ACTIVE rule would have to choose between for this invoice."""
        day, found = inv.issue_date, set()
        for other in by_supplier[inv.supplier["ico"]]:
            if other is inv or other.booked_project_code is None or other.booking_date > DATA_END:
                continue
            if abs((other.issue_date - day).days) > NO_PROJECT_WINDOW_DAYS:
                continue
            p = by_code[other.booked_project_code]
            if p["construction_start"] <= day <= p["construction_end"]:
                found.add(other.booked_project_code)
        return found

    pool = sorted(
        (
            inv
            for inv in invoices
            if inv.invoice_id not in used
            and inv.booked_project_code is not None
            and inv.booking_date <= DATA_END  # it must be a row of the Money export
            and (inv.project_code, inv.category) not in overrun_pairs  # keep the overrun spend visible
        ),
        key=lambda i: i.invoice_id,
    )
    want = COUNTS["NO_PROJECT"] * scale
    chosen: list = []
    chosen_by_supplier = defaultdict(list)
    for inv in rng.sample(pool, len(pool)):
        if len(chosen) == want:
            break
        if len(deciding_projects(inv)) < 2:
            continue
        inv.booked_project_code = None
        near = [
            c
            for c in chosen_by_supplier[inv.supplier["ico"]]
            if abs((c.issue_date - inv.issue_date).days) <= NO_PROJECT_WINDOW_DAYS
        ]
        if any(len(deciding_projects(c)) < 2 for c in near):  # this one would make an earlier pick decidable
            inv.booked_project_code = inv.project_code
            continue
        chosen.append(inv)
        chosen_by_supplier[inv.supplier["ico"]].append(inv)
    if len(chosen) < want:
        raise ValueError(f"not enough candidates for NO_PROJECT: need {want}, found {len(chosen)}")

    rows = []
    for inv in chosen:
        used.add(inv.invoice_id)
        rows.append(
            {
                "problem": "NO_PROJECT",
                "ref": inv.invoice_id,
                "project_code": inv.project_code,
                "detail": f"project_code blank in the Money export; {len(deciding_projects(inv))} projects "
                f"active on {inv.issue_date} had booked invoices from this supplier within "
                f"{NO_PROJECT_WINDOW_DAYS} days",
            }
        )
    return rows


# ------------------------------------------------- DUPLICATE, MISSING_VS, PARSE_ERROR


def _with_isdoc(invoices, used, latest_issue=None, latest_due=None):
    """Booked invoices that have an ISDOC and carry no planted problem yet, sorted for a fixed order."""
    return sorted(
        (
            inv
            for inv in invoices
            if inv.invoice_id not in used
            and not inv.pdf_only
            and inv.booking_date <= DATA_END
            and (latest_issue is None or inv.issue_date <= latest_issue)
            and (latest_due is None or inv.due_date <= latest_due)
        ),
        key=lambda i: i.invoice_id,
    )


def _plant_duplicates(invoices, rng, scale, used):
    pool = _with_isdoc(invoices, used, latest_issue=DATA_END - timedelta(days=MAX_RESEND_DAYS))
    rows = []
    for inv in _take(pool, COUNTS["DUPLICATE"] * scale, rng, "DUPLICATE"):
        resent = inv.issue_date + timedelta(days=rng.randint(1, MAX_RESEND_DAYS))
        inv.extra["resent_date"] = resent
        inv.extra["resent_uuid"] = _new_uuid(rng)
        used.add(inv.invoice_id)
        base = f"{inv.supplier['ico']}_{inv.number}"
        rows.append(
            {
                "problem": "DUPLICATE",
                "ref": inv.invoice_id,
                "project_code": inv.project_code,
                "detail": f"sent again as {base}_resent.isdoc on {resent}",
            }
        )
    return rows


def _plant_missing_vs(invoices, rng, scale, used):
    rows = []
    pool = _with_isdoc(invoices, used, latest_due=DATA_END - timedelta(days=PAYABLE_MARGIN_DAYS))
    for inv in _take(pool, COUNTS["MISSING_VS"] * scale, rng, "MISSING_VS"):
        old_vs, inv.vs = inv.vs, None
        used.add(inv.invoice_id)
        rows.append(
            {
                "problem": "MISSING_VS",
                "ref": inv.invoice_id,
                "project_code": inv.project_code,
                "detail": f"variable symbol {old_vs} left out of ISDOC, PDF and Money export",
            }
        )
    return rows


def _plant_parse_errors(invoices, rng, scale, used):
    rows = []
    for inv in _take(_with_isdoc(invoices, used), COUNTS["PARSE_ERROR"] * scale, rng, "PARSE_ERROR"):
        inv.extra["truncated"] = True
        used.add(inv.invoice_id)
        rows.append(
            {
                "problem": "PARSE_ERROR",
                "ref": inv.invoice_id,
                "project_code": inv.project_code,
                "detail": f"{inv.supplier['ico']}_{inv.number}.isdoc cut off right after <InvoiceLines>",
            }
        )
    return rows
