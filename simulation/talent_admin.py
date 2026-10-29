"""Administrators' tools for Proven Talent. Run from the project root:

    python -m simulation.talent_admin firms                 every firm and its status
    python -m simulation.talent_admin approve "Firm name"   let a firm use the board and set challenges
    python -m simulation.talent_admin suspend "Firm name"   stop a firm (it is logged out; its open challenges are called off)
    python -m simulation.talent_admin flags                 the honesty checks waiting to be looked at
    python -m simulation.talent_admin clear 42 "why"        a check looked at and found to be nothing wrong
    python -m simulation.talent_admin refresh               work every record out afresh now

None of this is reachable from the website.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from simulation import firms, talent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m simulation.talent_admin")
    parser.add_argument("command", choices=("firms", "approve", "suspend", "flags", "clear", "refresh"))
    parser.add_argument("target", nargs="?")
    parser.add_argument("why", nargs="?", default="Looked at: nothing wrong.")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        if args.command == "firms":
            for f in conn.execute("SELECT name, contact_name, email, website, status, created_at, email_confirmed_at FROM talent_firms"
                                  " ORDER BY created_at").fetchall():
                confirmed = "email confirmed" if f["email_confirmed_at"] else "email NOT confirmed"
                print(f"{f['status']:10} {f['name']:30} {f['contact_name']:24} {f['email']:32} {confirmed:20} {f['website']}")
        elif args.command in ("approve", "suspend"):
            firm = conn.execute("SELECT id, name FROM talent_firms WHERE name_key = %s", (firms.name_key(args.target or ""),)).fetchone()
            if firm is None:
                raise SystemExit(f"No firm called {args.target!r}.")
            try:
                firms.approve(conn, firm["id"], now) if args.command == "approve" else firms.suspend(conn, firm["id"])
            except firms.FirmError as refused:
                raise SystemExit(f"{firm['name']}: {refused}") from None
            print(f"{firm['name']}: {args.command}d.")
        elif args.command == "flags":
            for f in conn.execute("SELECT f.id, f.kind, p.display_name AS who, q.display_name AS other, f.amount, f.session_date, f.detail"
                                  " FROM talent_flags f JOIN players p ON p.id = f.player_id LEFT JOIN players q ON q.id = f.other_id"
                                  " WHERE f.cleared_at IS NULL ORDER BY f.id").fetchall():
                print(f"#{f['id']:<6} {f['kind']:18} {f['who']:20} with {f['other'] or '-':20} {f['amount']:>16} {f['session_date']} {f['detail']}")
        elif args.command == "clear":
            talent.clear_flag(conn, int(args.target), args.why, now)
            print(f"Check #{args.target} cleared.")
        elif args.command == "refresh":
            for p in conn.execute("SELECT id FROM players").fetchall():
                talent.refresh(conn, p["id"], now)
            print("Every record worked out afresh.")
        conn.commit()


if __name__ == "__main__":
    main()
