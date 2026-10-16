"""The gap stage, Part 2: development projects.

The owner of the whole of an empty plot (or a fallen building) may develop it instead of paying a builder to put up a
building at once:

  1. A building permit, with a design (what kind of building, which the zone must allow) and a budget. The permit costs
     1% of the budget and comes about two real days later; one in five is held up a quarter.
  2. A construction loan, if wanted: a bank lends up to 70% of the budget, paid out phase by phase.
  3. The building goes up in four phases, one at each quarter's close: foundations, frame, building, fitting out. Each
     buys cement, steel and building work from the listed companies. A phase costs a quarter of the budget, moved by
     what building materials cost that quarter against when the budget was set.
  4. Risks: dearer materials, a strike that holds a phase up, a permit held up, and the owner (or the bank) failing to pay
     for a phase, which stops the work until paid.
  5. When finished, the building stands: it is let (rent comes like any other building's), or put up for auction. The
     construction loan becomes a mortgage.

Managing the work yourself is a tenth cheaper than a builder's turnkey price, but takes a year and carries the risks.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS

PHASE_NAMES = ("foundations", "frame", "building", "fitting out")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('developments') IS NOT NULL AS ok")["ok"] is True


def _err(words: str):
    from simulation.property import PropertyError
    return PropertyError(words)


def _chance(seed: str, subject: str) -> float:
    return int.from_bytes(hashlib.sha256(f"{seed}:{subject}:development".encode()).digest()[:8], "big") / 2**64


def materials_bps(conn: Connection) -> int:
    """What building materials cost now against the start (the index the futures desk uses)."""
    row = _one(conn, "SELECT materials_bps AS v FROM economy_results ORDER BY period DESC LIMIT 1")
    return max(row["v"], 1) if row and row["v"] else BPS


def budget_for(p: dict, kind: str) -> int:
    from simulation import property as prop
    return prop.build_cost(p) * (BPS - data.DEVELOPMENT_SAVING_BPS) // BPS


def start(conn: Connection, account, property_id: int, kind: str | None, now: datetime, *, loan_bank=None, loan: int = 0,
          then_what: str = "let") -> dict:
    """Ask for the permit, with the design and the budget (and the construction loan, if any)."""
    from simulation import careers, conveyancing, zoning
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        p = prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, account) < BPS:
            raise _err("Only the owner of the whole of a plot develops it.")
        if p["status"] == "standing" and p["kind"] != "land":
            raise _err("A building already stands here.")
        conveyancing.not_frozen(p)
        if then_what not in ("let", "sell"):
            raise _err("When it is done, it is let or sold.")
        kind = zoning.check_build(p, kind)
        if _one(conn, "SELECT 1 FROM developments WHERE property_id = %s AND status IN ('permit', 'building')", (property_id,)):
            raise _err("It is being developed already.")
        if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
            raise _err("It is up for auction.")
        budget = budget_for(p, kind)
        rate = None
        if not isinstance(loan, int) or isinstance(loan, bool) or loan < 0:
            raise _err("A loan is a sum in kobo.")
        if loan:
            if loan > budget * data.CONSTRUCTION_LOAN_MOST_BPS // BPS:
                raise _err(f"A bank lends at most {data.CONSTRUCTION_LOAN_MOST_BPS // 100}% of the budget: {prop.money(budget * data.CONSTRUCTION_LOAN_MOST_BPS // BPS)}.")
            if loan_bank is None or not _one(conn, "SELECT 1 FROM companies WHERE id = %s AND sector = 'banking' AND status = 'trading'", (loan_bank,)):
                raise _err("Choose a bank for the construction loan.")
            if prop.mortgage_on(conn, property_id):
                raise _err("Repay the mortgage on the plot first: the construction loan is secured on it.")
            rate = prop.policy_rate(conn) + data.CONSTRUCTION_LOAN_SPREAD_BPS
        fee = budget * data.PERMIT_FEE_BPS // BPS
        try:
            ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="property_tax",
                            memo=f"Building permit for {p['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise _err(f"The permit costs {prop.money(fee)}.") from None
        seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
        delayed = _chance(seed, f"permit:{property_id}:{state['period']}") < data.PERMIT_DELAY_CHANCE_BPS / BPS
        due = now + timedelta(days=data.PERMIT_DAYS)
        row = _one(conn, "INSERT INTO developments (property_id, owner, kind, budget, materials_bps, permit_due, permit_delayed, loan_bank, loan_most, loan_rate_bps,"
                         " then_what, log, started_period, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (property_id, account, kind, budget, materials_bps(conn), due, delayed, loan_bank if loan else None, loan, rate, then_what,
                    Jsonb([{"label": clock.period_label(state["period"]), "words": f"Permit asked for {data.PROPERTY_KIND_NAMES[kind].lower()}, budget {prop.money(budget)}."}]),
                    state["period"], now))
        return {"development_id": row["id"], "budget": budget, "permit_fee": fee, "permit_due": due.isoformat(), "kind": kind}


def _log(conn: Connection, dev: dict, period: int, words: str) -> None:
    log = list(dev["log"] or []) + [{"label": clock.period_label(period), "words": words}]
    conn.execute("UPDATE developments SET log = %s WHERE id = %s", (Jsonb(log[-12:]), dev["id"]))
    dev["log"] = log


def close(conn: Connection, period: int, now: datetime, seed: str) -> dict:
    """At each quarter's close: permits come (or are held up), and each development builds a phase if it can pay."""
    if not ready(conn):
        return {}
    from simulation import auctions, infrastructure
    from simulation import property as prop
    built = 0
    m_now = materials_bps(conn)
    for dev in _rows(conn, "SELECT v.*, p.name, p.size_m2, d.city, d.kind AS district_kind, p.district_id FROM developments v"
                           " JOIN properties p ON p.id = v.property_id JOIN districts d ON d.id = p.district_id"
                           " WHERE v.status IN ('permit', 'building') ORDER BY v.id FOR UPDATE OF v"):
        if dev["status"] == "permit":
            if dev["permit_due"] > now:
                continue
            if dev["permit_delayed"]:
                conn.execute("UPDATE developments SET permit_delayed = false WHERE id = %s", (dev["id"],))
                _log(conn, dev, period, "The permit was held up at the planning office: building starts a quarter later.")
                continue
            conn.execute("UPDATE developments SET status = 'building' WHERE id = %s", (dev["id"],))
            _log(conn, dev, period, "Permit granted.")
            dev["status"] = "building"
        if prop.share_of(conn, dev["property_id"], dev["owner"]) < BPS:
            conn.execute("UPDATE developments SET status = 'stopped' WHERE id = %s", (dev["id"],))
            _log(conn, dev, period, "The owner no longer owns all of the plot: the work stops.")
            continue
        if _chance(seed, f"strike:{dev['id']}:{period}") < data.STRIKE_CHANCE_BPS / BPS:
            _log(conn, dev, period, "A strike on site: no work this quarter.")
            continue
        # A phase costs its quarter of the budget, moved by what materials cost now against when the budget was set.
        phase_cost = max(dev["budget"] // data.DEVELOPMENT_PHASES * m_now // max(dev["materials_bps"], 1), 1)
        # The owner must be able to pay its own part of the phase; the bank pays the rest of it (a construction loan is a
        # mortgage on the plot from its first payment, so the bank's books show it and interest runs from then).
        bank_part = 0
        if dev["loan_bank"] and dev["loan_drawn"] < dev["loan_most"]:
            bank_part = min(phase_cost * data.CONSTRUCTION_LOAN_MOST_BPS // BPS, dev["loan_most"] - dev["loan_drawn"])
            bank = _one(conn, "SELECT account_id, name FROM companies WHERE id = %s", (dev["loan_bank"],))
            if ledger.balance(conn, bank["account_id"]) < bank_part:
                bank_part = 0
                _log(conn, dev, period, "The bank could not pay out this phase of the loan.")
        if ledger.balance(conn, dev["owner"]) < phase_cost - bank_part:
            _log(conn, dev, period, f"There was not the cash for the {PHASE_NAMES[dev['phase']]} ({prop.money(phase_cost - bank_part)} "
                                    f"of the owner's own): the work waits.")
            continue
        if bank_part:
            ledger.transfer(conn, payer=bank["account_id"], receiver=dev["owner"], amount=bank_part, kind="mortgage_loan",
                            memo=f"{bank['name']}: construction loan for {dev['name']}, phase {dev['phase'] + 1}", period=period)
            loan = _one(conn, "SELECT id FROM mortgages WHERE property_id = %s AND borrower = %s AND bank_company_id = %s AND status = 'open'",
                        (dev["property_id"], dev["owner"], dev["loan_bank"]))
            if loan:
                conn.execute("UPDATE mortgages SET principal = principal + %s, outstanding = outstanding + %s WHERE id = %s", (bank_part, bank_part, loan["id"]))
            else:
                conn.execute("INSERT INTO mortgages (property_id, borrower, bank_company_id, principal, outstanding, rate_bps, taken_period, term_quarters, at)"
                             " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                             (dev["property_id"], dev["owner"], dev["loan_bank"], bank_part, bank_part, dev["loan_rate_bps"], period,
                              data.MORTGAGE_TERM_QUARTERS, now))
            conn.execute("UPDATE developments SET loan_drawn = loan_drawn + %s WHERE id = %s", (bank_part, dev["id"]))
        label = clock.period_label(period)
        for part, sectors in ((data.DEVELOPMENT_SPLIT_BPS["cement"], ("cement",)), (data.DEVELOPMENT_SPLIT_BPS["steel"], (data.STEEL_SECTOR,)),
                              (data.DEVELOPMENT_SPLIT_BPS["works"], ("real_estate",))):
            infrastructure.buy_from(conn, dev["owner"], phase_cost * part // BPS, sectors, dev["city"],
                                    f"{dev['name']}: {PHASE_NAMES[dev['phase']]}, {label}", period, up_to=False)
        phase = dev["phase"] + 1
        conn.execute("UPDATE developments SET phase = %s, spent = spent + %s WHERE id = %s", (phase, phase_cost, dev["id"]))
        _log(conn, dev, period, f"The {PHASE_NAMES[dev['phase']]} done, for {prop.money(phase_cost)}"
                                + (f" ({prop.money(bank_part)} of it lent)." if bank_part else "."))
        built += 1
        if phase < data.DEVELOPMENT_PHASES:
            continue
        # Finished.
        conn.execute("UPDATE properties SET kind = %s, status = 'standing', condition = 100, base_rent = %s, built_period = %s WHERE id = %s",
                     (dev["kind"], prop.base_rent(dev["city"], dev["kind"], dev["size_m2"]), period, dev["property_id"]))
        conn.execute("UPDATE developments SET status = 'done' WHERE id = %s", (dev["id"],))
        drawn = dev["loan_drawn"] + bank_part
        _log(conn, dev, period, "Finished: the building stands." + (" The construction loan runs on as its mortgage." if drawn else ""))
        from simulation import news
        news.publish(conn, period=period + 1, day=3, kind="development_done", story=f"dev:{dev['id']}",
                     facts={"property": dev["name"], "city": dev["city"], "kind": data.PROPERTY_KIND_NAMES[dev["kind"]].lower()},
                     locations=[dev["city"]], sectors=["real_estate", "cement"])
        if dev["then_what"] == "sell":
            try:
                auctions.owner_list(conn, dev["owner"], dev["property_id"], 0, now)
            except Exception:  # noqa: BLE001 - it stays the owner's, let, if it cannot be listed now
                _log(conn, dev, period, "It could not be put up for auction this quarter: it is let meanwhile.")
    return {"phases": built}


def view(conn: Connection, account) -> list[dict]:
    if not ready(conn):
        return []
    return [{"id": v["id"], "property_id": v["property_id"], "name": v["name"], "kind": data.PROPERTY_KIND_NAMES.get(v["kind"], v["kind"]),
             "budget": v["budget"], "spent": v["spent"], "phase": v["phase"], "phases": data.DEVELOPMENT_PHASES, "status": v["status"],
             "loan_most": v["loan_most"], "loan_drawn": v["loan_drawn"], "then_what": v["then_what"], "log": v["log"]}
            for v in _rows(conn, "SELECT v.*, p.name FROM developments v JOIN properties p ON p.id = v.property_id WHERE v.owner = %s"
                                 " ORDER BY v.id DESC LIMIT 10", (account,))]


def check_books(conn: Connection) -> list[str]:
    if not ready(conn):
        return []
    bad = _one(conn, "SELECT count(*) AS n FROM developments WHERE loan_drawn > loan_most OR phase > %s", (data.DEVELOPMENT_PHASES,))["n"]
    return [f"{bad} developments have drawn more than their loan or built too many phases."] if bad else []
