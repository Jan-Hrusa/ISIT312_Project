"""Create the HBase table `media_catalog` (families meta, loc, doc, thumb; one version each).

Run in the client container with the hbase profile up:

    python -m hbase.create_table          # keeps an existing table
    python -m hbase.create_table --drop   # drops it first: every row is lost
"""

from __future__ import annotations

import argparse

from common import config
from hbase import catalogue


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drop", action="store_true", help="drop and recreate the table if it exists")
    args = ap.parse_args(argv)
    conn = catalogue.connect()
    try:
        created = catalogue.create_table(conn, drop=args.drop)
        families = sorted(
            f.decode() if isinstance(f, bytes) else f for f in conn.table(config.HBASE_TABLE).families()
        )
    finally:
        conn.close()
    state = "created" if created else "already exists, kept"
    print(f"{config.HBASE_TABLE}: {state}; families {', '.join(families)}")


if __name__ == "__main__":
    main()
