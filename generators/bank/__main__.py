"""Generate bank statements and payment orders from the finance generator's ledger."""

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

from common import config
from generators.bank import gpc, kpc, payments, sta, statements, txt
from generators.finance_docs.util import set_business_mtime


def _read(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Missing finance generator input: {path}") from error


def generate(seed: int) -> dict:
    ledger_dir = config.LEDGER_DIR
    sources = config.SOURCES_DIR
    ledger = _read(ledger_dir / "invoice_ledger.csv")
    suppliers = _read(sources / "master" / "suppliers.csv")
    projects = _read(sources / "master" / "projects.csv")
    debits, credits, orders, planted = payments.plan(ledger, suppliers, projects, random.Random(seed))
    # Check every order's VS before writing any file, so a bad ledger leaves no partial output.
    for order in orders:
        kpc.validate_vs(order)

    references = {}
    files = Counter()
    for st in statements.build(debits, credits, config.BANKS):
        directory = sources / "mailbox" / "bank" / st.bank
        directory.mkdir(parents=True, exist_ok=True)
        extension = config.BANKS[st.bank].format.lower()
        path = directory / f"{st.basename}.{extension}"
        companion = directory / f"{st.basename}.txt"
        writer = gpc if extension == "gpc" else sta
        writer.write(path, st)
        txt.write(companion, st)
        set_business_mtime(path, st.day)
        set_business_mtime(companion, st.day)
        files[st.bank] += 2
        for index, movement in enumerate(st.movements, start=1):
            references[id(movement)] = f"{st.bank}-{st.day:%Y%m%d}-{index:04d}"

    runs = defaultdict(list)
    for order in orders:
        runs[order.bank, order.run_date].append(order)
    if runs:
        directory = sources / "drive" / "payments"
        directory.mkdir(parents=True, exist_ok=True)
        for (bank, day), items in sorted(runs.items()):
            items.sort(key=lambda item: (item.due_date, item.invoice_id, item.cents))
            path = directory / f"PO_{day.isoformat()}_{bank}.kpc"
            kpc.write(path, items)
            set_business_mtime(path, day)
            files[bank] += 1
            for index, order in enumerate(items, start=1):
                references[id(order)] = f"{path.stem}-{index:03d}"

    truth = ledger_dir / "planted_payments.csv"
    with truth.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("problem", "invoice_id", "tx_or_order_ref", "detail"))
        for case in sorted(planted, key=lambda entry: (entry.problem, entry.invoice_id)):
            reference = "" if case.record is None else references[id(case.record)]
            writer.writerow((case.problem, case.invoice_id, reference, case.detail))
    set_business_mtime(truth, config.DATA_END)
    return {
        "files": dict(files),
        "transactions": len(debits) + len(credits),
        "orders": len(orders),
        "planted": dict(sorted(Counter(case.problem for case in planted).items())),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=config.SEED)
    parser.add_argument("--scale", type=int, default=1, help="scale of the upstream finance dataset")
    args = parser.parse_args(argv)
    if args.scale < 1:
        parser.error("--scale must be positive")
    stats = generate(args.seed)
    print(f"Finance input scale: {args.scale} ({config.DATASET})")
    print(f"Files per bank: {stats['files']}")
    print(f"Transactions: {stats['transactions']}")
    print(f"Orders: {stats['orders']}")
    print(f"Planted counts: {stats['planted']}")


if __name__ == "__main__":
    main()
