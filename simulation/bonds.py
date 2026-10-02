"""Bonds and Government bills (design document, section 11).

A bond is a loan that can be bought and sold. Whoever holds it is paid the
interest (the "coupon") each quarter and the face value (₦1,000 a bond) at the end.

The range:

  bill              a three-month loan to the Government. It pays no coupon: it is
                    sold for a little less than ₦1,000 and repaid at ₦1,000. This is
                    how idle cash earns interest.
  fixed             the same coupon every quarter. A company's is "high-yield" if
                    its credit rating was below BBB when it was issued.
  floating          the coupon moves with the Central Bank's rate.
  inflation_linked  the face value, and so the coupon, rises with prices.
  convertible       a company's bond that its holder can swap for shares.
  project           a company's bond raised for one named project; "green" if the
                    project is one.

  A bond of a company that is behind with its debts, or rated D, is "distressed":
  investors no longer count on being repaid in full, and it trades far below
  its face value.

Two prices, always. The fair value is worked out in the open: every payment
still to come, counted for less the further off it is (the same sum as for a
company's shares), at the yearly return investors want for that length of loan
and that borrower. The prices you can actually trade at are the bond desk's:
a little above fair value to buy, a little below to sell, and moved by how much
has been bought or sold lately. The Government sells its own bills and bonds
itself, as many as are asked for. A company's bonds are bought from the pension
funds, who hold them. Everything is sold back to the pension funds.

Every naira and every bond moves through the ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import clock, ledger
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, MAX_AMOUNT

FACE = data.BOND_FACE_NAIRA * 100                 # kobo repaid for each bond
DEALER = ledger.INVESTORS_INSTITUTIONS            # the pension funds make the market in bonds
HELD = "exchange:offers"                          # held for swaps, share offers and takeover offers
RATING_ORDER = list(data.LOAN_SPREAD_BPS)         # AAA first, D last

KIND_WORDS = {
    "bill": "Government bill", "fixed": "Fixed-rate bond", "floating": "Floating-rate bond",
    "inflation_linked": "Inflation-linked bond", "convertible": "Convertible bond", "project": "Project bond",
}


class BondError(Exception):
    """The bond desk refused something. The message is written for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _percent(bps: int) -> str:
    return f"{bps / 100:.2f}".rstrip("0").rstrip(".") + "%"


def held_account(conn: Connection) -> UUID:
    found = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (HELD,))
    if found:
        return found["id"]
    return ledger.create_account(conn, kind="exchange", name="Broad Street Exchange: held for offers", code=HELD)


# ---------------------------------------------------------------------------
# What investors want: the yield curve and the extra for risk
# ---------------------------------------------------------------------------

def government_yield_bps(policy_rate_bps: int, quarters: int) -> int:
    """The yearly return wanted for lending to the Government for this long. Longer loans
    pay more: the lender waits longer and more can change."""
    points = data.YIELD_CURVE_BPS
    quarters = max(quarters, points[0][0])
    for (near, low), (far, high) in zip(points, points[1:]):
        if quarters <= far:
            return max(policy_rate_bps + low + (high - low) * (quarters - near) // (far - near), 100)
    return max(policy_rate_bps + points[-1][1], 100)


def credit_spread_bps(rating: str) -> int:
    """The extra yearly return wanted for lending to a company with this credit rating."""
    return max(data.LOAN_SPREAD_BPS.get(rating, data.LOAN_SPREAD_BPS["BBB"]) - data.BOND_DISCOUNT_BPS, 50)


def curve(conn: Connection) -> dict:
    """The published yield curve and credit spreads."""
    policy = _policy(conn)
    return {
        "policy_rate_bps": policy,
        "points": [{"label": label, "quarters": q, "yield_bps": government_yield_bps(policy, q)}
                   for label, q in (("3 months", 1), ("2 years", 8), ("5 years", 20), ("10 years", 40))],
        "spreads": [{"rating": rating, "spread_bps": credit_spread_bps(rating)} for rating in RATING_ORDER],
    }


def _policy(conn: Connection) -> int:
    row = _one(conn, "SELECT next_policy_rate_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["next_policy_rate_bps"] if row else data.OPENING_RATE_BPS


def market(conn: Connection, now: datetime) -> dict:
    """What every bond's value depends on, read once: the quarter, the Central Bank's rate,
    prices, each company's credit rating, and how much of the running quarter is left."""
    world = _one(conn, "SELECT world_start, weeks_ahead, last_closed_period FROM world_state")
    economy = _one(conn, "SELECT next_policy_rate_bps, policy_rate_bps, price_index_bps, inflation_bps FROM economy_results"
                         " ORDER BY period DESC LIMIT 1")
    left = 1.0
    if world:
        start = clock.effective_start(world["world_start"], world["weeks_ahead"])
        if now >= start:
            ends = clock.next_quarter_end(now, start)
            left = min(max((ends - now) / timedelta(days=clock.REAL_DAYS_PER_QUARTER), 0.0), 1.0)
    companies = {r["company_id"]: r for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) company_id, credit_rating,"
              " coalesce((figures->'notes'->>'principal_overdue')::bigint, 0) AS overdue"
              " FROM company_reports ORDER BY company_id, period DESC, version DESC")}
    return {
        "period": world["last_closed_period"] if world else 0,
        "policy": economy["next_policy_rate_bps"] if economy else data.OPENING_RATE_BPS,
        "index": economy["price_index_bps"] if economy else BPS,
        "left": left, "companies": companies,
    }


def _claim(bond: dict) -> int:
    """What each bond is owed at the end. For a company's bond it is its share of what the company
    still owes on that debt, so a part-payment is never counted twice."""
    if bond.get("principal") is not None and bond.get("units"):
        return bond["principal"] // bond["units"]
    return bond["face"]


def yield_bps(bond: dict, state: dict) -> int:
    quarters = max(bond["maturity_period"] - state["period"], 1)
    base = government_yield_bps(state["policy"], quarters)
    if bond["issuer"] == "company":
        rating = state["companies"].get(bond["company_id"], {}).get("credit_rating", "BBB")
        return base + credit_spread_bps(rating)
    return base


def distressed(bond: dict, state: dict) -> bool:
    if bond["issuer"] != "company":
        return False
    company = state["companies"].get(bond["company_id"], {})
    return company.get("credit_rating") in ("CCC", "D") or company.get("overdue", 0) > 0 \
        or bond["maturity_period"] <= state["period"]


def payments(bond: dict, state: dict) -> list[tuple[float, float]]:
    """Every payment still to come on one bond: (years from now, kobo)."""
    remaining = bond["maturity_period"] - state["period"]            # quarter closes still to come
    claim = _claim(bond)
    out = []
    for k in range(max(remaining, 1)):
        years = (state["left"] + k) / 4
        last = k == max(remaining, 1) - 1
        if bond["kind"] == "bill":
            coupon, face = 0.0, float(claim)
        elif bond["kind"] == "floating":
            coupon, face = claim * (state["policy"] + bond["coupon_bps"]) / BPS / 4, float(claim)
        elif bond["kind"] == "inflation_linked":
            # The face value has risen with prices since issue, and is expected to keep rising at the target rate.
            face = claim * state["index"] / (bond["issue_index_bps"] or BPS) * (1 + data.INFLATION_TARGET_BPS / BPS) ** years
            coupon = face * bond["coupon_bps"] / BPS / 4
        else:
            coupon, face = claim * bond["coupon_bps"] / BPS / 4, float(claim)
        out.append((years, coupon + (face if last else 0.0)))
    return out


def fair_value(bond: dict, state: dict) -> int:
    """What one bond is worth today, in kobo: every payment still to come, counted for less
    the further off it is."""
    if bond["redeemed_period"] is not None:
        return 0
    wanted = yield_bps(bond, state) / BPS
    value = sum(amount / (1 + wanted) ** years for years, amount in payments(bond, state))
    if distressed(bond, state):
        # Lenders to a company in trouble expect to recover only part of what they are owed.
        value = min(value, _claim(bond) * data.DISTRESSED_RECOVERY_BPS / BPS)
    return max(int(value), 1)


def _half_spread(bond: dict, state: dict) -> int:
    if bond["kind"] == "bill":
        return data.BOND_HALF_SPREAD_BPS["bill"]
    if distressed(bond, state):
        return data.BOND_HALF_SPREAD_BPS["distressed"]
    return data.BOND_HALF_SPREAD_BPS[bond["issuer"]]


# ---------------------------------------------------------------------------
# Creating bonds
# ---------------------------------------------------------------------------

def _load(conn: Connection, where: str = "true", params=(), *, lock: bool = False) -> list[dict]:
    """Bonds with how many exist and, for a company's, what is still owed on the debt behind them."""
    return _rows(
        conn,
        "SELECT b.*, c.ticker, c.name AS company_name, d.principal_outstanding AS principal,"
        "   coalesce(-i.balance, 0)::bigint AS units"
        " FROM bonds b LEFT JOIN companies c ON c.id = b.company_id LEFT JOIN company_debts d ON d.id = b.debt_id"
        " JOIN assets a ON a.code = b.asset"
        " LEFT JOIN ledger_balances i ON i.account_id = a.issuer_account_id AND i.asset = b.asset"
        f" WHERE {where} ORDER BY b.issuer DESC, b.maturity_period, b.asset" + (" FOR UPDATE OF b" if lock else ""), params)


def find(conn: Connection, code: str, *, lock: bool = False) -> dict | None:
    found = _load(conn, "b.asset = %s", (f"BND-{code}",), lock=lock)
    return found[0] if found else None


def _create(conn: Connection, *, prefix: str, name: str, issuer: str, issuer_account, kind: str, coupon_bps: int,
            issued: int, maturity: int, company_id=None, debt_id=None, **extra) -> dict:
    number = _one(conn, "SELECT count(*) AS n FROM bonds WHERE asset LIKE %s", (f"BND-{prefix}%",))["n"] + 1
    code = f"BND-{prefix}{number:04d}"
    ledger.create_asset(conn, code=code, kind="bond", name=name, unit="bond", issuer_account_id=issuer_account)
    columns = {"asset": code, "name": name, "issuer": issuer, "company_id": company_id, "debt_id": debt_id, "kind": kind,
               "face": FACE, "coupon_bps": coupon_bps, "issued_period": issued, "maturity_period": maturity, **extra}
    conn.execute(f"INSERT INTO bonds ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})", list(columns.values()))
    return _load(conn, "b.asset = %s", (code,))[0]


def maturity_words(period: int) -> str:
    return "the end of " + clock.period_label(period)


def setup(conn: Connection, period: int, now: datetime | None = None) -> None:
    """Make every company's existing bond a bond that can be traded, open the Government's
    first bonds, and open the bill for the running quarter. Safe to run again."""
    held_account(conn)
    dealer = ledger.account_id(conn, DEALER)
    for debt in _rows(conn, "SELECT d.*, c.name AS company_name, c.account_id FROM company_debts d"
                            " JOIN companies c ON c.id = d.company_id WHERE d.kind = 'bond' AND d.principal_outstanding > 0"
                            " AND NOT EXISTS (SELECT 1 FROM bonds b WHERE b.debt_id = d.id) ORDER BY c.ticker, d.id"):
        units = debt["principal_outstanding"] // FACE
        if units <= 0:
            continue
        bond = _create(conn, prefix="C", name=f"{debt['company_name']} {_percent(debt['annual_rate_bps'])} bond",
                       issuer="company", issuer_account=debt["account_id"], company_id=debt["company_id"], debt_id=debt["id"],
                       kind="fixed", coupon_bps=debt["annual_rate_bps"], issued=max(debt["start_period"], 0),
                       maturity=max(debt["maturity_period"], max(debt["start_period"], 0) + 1))
        # The pension funds lent this money when the world began: the bonds are theirs.
        ledger.post(conn, kind="bond_issue", memo=f"{bond['name']}: bonds issued to the lenders who hold the debt",
                    legs=[Leg(debt["account_id"], -units, bond["asset"]), Leg(dealer, units, bond["asset"])], period=period)

    treasury = ledger.account_id(conn, ledger.TREASURY)
    if not _rows(conn, "SELECT 1 FROM bonds WHERE issuer = 'government' AND kind <> 'bill' LIMIT 1"):
        state = {"period": period, "policy": _policy(conn), "index": _index(conn), "left": 1.0, "companies": {}}
        cash = ledger.balance(conn, dealer)
        each = min(data.GOVERNMENT_FIRST_ISSUE_NAIRA * 100, cash * data.GOVERNMENT_BOND_APPETITE_BPS // BPS // 5)
        for bond in _new_government_lines(conn, period, state):
            units = each // FACE
            if units > 0:
                _sell_new(conn, bond, treasury, dealer, units, FACE, period)
    _open_bill(conn, period)


def _index(conn: Connection) -> int:
    row = _one(conn, "SELECT price_index_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    return row["price_index_bps"] if row else BPS


def _open_bill(conn: Connection, period: int) -> dict:
    """The bill for the quarter now running: it is repaid when that quarter closes."""
    found = _load(conn, "b.kind = 'bill' AND b.maturity_period = %s", (period + 1,))
    if found:
        return found[0]
    return _create(conn, prefix="T", name=f"Government bill repaid at {maturity_words(period + 1)}", issuer="government",
                   issuer_account=ledger.account_id(conn, ledger.TREASURY), kind="bill", coupon_bps=0, issued=period,
                   maturity=period + 1)


def _new_government_lines(conn: Connection, period: int, state: dict) -> list[dict]:
    """A new set of Government bonds, each paying today's going rate so that it starts at its face value."""
    treasury = ledger.account_id(conn, ledger.TREASURY)
    lines = []
    for kind, quarters, words in data.GOVERNMENT_BOND_LINES:
        going = government_yield_bps(state["policy"], quarters)
        if kind == "floating":
            coupon = going - state["policy"]                       # what it pays above the Central Bank's rate
            label = f"Government floating-rate bond, the Central Bank's rate {'+' if coupon >= 0 else '−'} {_percent(abs(coupon))}"
            coupon = max(coupon, 0)
        elif kind == "inflation_linked":
            coupon = max(going - data.INFLATION_TARGET_BPS, 100)   # the return above rising prices
            label = f"Government inflation-linked bond, {_percent(coupon)} above prices"
        else:
            coupon = going
            label = f"Government {words} bond, {_percent(coupon)}"
        extra = {"issue_index_bps": state["index"]} if kind == "inflation_linked" else {}
        lines.append(_create(conn, prefix="G", name=f"{label}, repaid at {maturity_words(period + quarters)}",
                             issuer="government", issuer_account=treasury, kind=kind, coupon_bps=coupon, issued=period,
                             maturity=period + quarters, **extra))
    return lines


def _sell_new(conn: Connection, bond: dict, issuer_account, buyer, units: int, price: int, period: int) -> int:
    """New bonds from the issuer to a buyer for cash, in one transaction. Returns the cash raised."""
    cash = units * price
    ledger.post(
        conn, kind="bond_issue", memo=f"{bond['name']}: {units:,} new bonds sold", period=period, reference=f"bond:{bond['id']}",
        legs=[Leg(issuer_account, -units, bond["asset"]), Leg(buyer, units, bond["asset"]),
              Leg(buyer, -cash), Leg(issuer_account, cash)])
    return cash


def holders(conn: Connection, asset: str) -> dict:
    """Who holds a bond: account -> how many. Bonds held for a swap still belong to whoever asked for it."""
    held = {r["account_id"]: r["units"] for r in _rows(
        conn, "SELECT b.account_id, b.balance::bigint AS units FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
              " WHERE b.asset = %s AND b.balance > 0 AND a.kind <> 'exchange' ORDER BY b.account_id", (asset,))}
    for row in _rows(conn, "SELECT v.account_id, sum(v.units)::bigint AS units FROM bond_conversions v JOIN bonds b ON b.id = v.bond_id"
                           " WHERE b.asset = %s AND v.status = 'waiting' GROUP BY v.account_id", (asset,)):
        held[row["account_id"]] = held.get(row["account_id"], 0) + row["units"]
    return held


# ---------------------------------------------------------------------------
# The Government's bonds at the close of a quarter
# ---------------------------------------------------------------------------

def government_service(conn: Connection, treasury, period: int, policy_rate_bps: int, index_bps: int) -> int:
    """Pay this quarter's interest on the Government's bonds and repay those that have reached
    their end. Returns what borrowing cost the Government this quarter: the interest, plus the
    difference between what a bill was sold for and what it is repaid at."""
    cost = 0
    held = held_account(conn)
    for bond in _load(conn, "b.issuer = 'government' AND b.redeemed_period IS NULL AND b.issued_period < %s", (period,), lock=True):
        owners = holders(conn, bond["asset"])
        if not owners:
            if period >= bond["maturity_period"]:
                conn.execute("UPDATE bonds SET redeemed_period = %s WHERE id = %s", (period, bond["id"]))
            continue
        face = bond["face"] * index_bps // bond["issue_index_bps"] if bond["kind"] == "inflation_linked" else bond["face"]
        rate = policy_rate_bps + bond["coupon_bps"] if bond["kind"] == "floating" else bond["coupon_bps"]
        coupon = 0 if bond["kind"] == "bill" else (face * rate + 2 * BPS) // (4 * BPS)
        ends = period >= bond["maturity_period"]
        each = coupon + (face if ends else 0)
        total = each * sum(owners.values())
        if total > max(ledger.balance(conn, treasury), 0):
            continue                                   # the Treasury is short: it pays when it can (never yet seen)
        if coupon:
            ledger.post(conn, kind="bond_coupon", memo=f"{bond['name']}: interest for {clock.period_label(period)}",
                        period=period, reference=f"bond:{bond['id']}",
                        legs=[Leg(treasury, -coupon * sum(owners.values())), *[Leg(a, coupon * n) for a, n in owners.items()]])
            cost += coupon * sum(owners.values())
        if ends:
            sold_for = _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                                  " ON t.id = e.transaction_id WHERE t.kind = 'bond_issue' AND t.reference = %s"
                                  " AND e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0",
                            (f"bond:{bond['id']}", treasury))["total"]
            repaid = face * sum(owners.values())
            # Bonds waiting to be swapped are in the exchange's hands: they are handed in from there.
            waiting = {r["account_id"]: r["units"] for r in _rows(
                conn, "SELECT account_id, sum(units)::bigint AS units FROM bond_conversions WHERE bond_id = %s"
                      " AND status = 'waiting' GROUP BY account_id", (bond["id"],))}
            legs = [Leg(treasury, -repaid), *[Leg(a, face * n) for a, n in owners.items()]]
            legs += [Leg(a, -(n - waiting.get(a, 0)), bond["asset"]) for a, n in owners.items() if n - waiting.get(a, 0) > 0]
            if waiting:
                legs.append(Leg(held, -sum(waiting.values()), bond["asset"]))
            legs.append(Leg(treasury, sum(owners.values()), bond["asset"]))
            ledger.post(conn, kind="bond_redemption", memo=f"{bond['name']}: repaid", period=period,
                        reference=f"bond:{bond['id']}", legs=legs)
            conn.execute("UPDATE bonds SET redeemed_period = %s WHERE id = %s", (period, bond["id"]))
            cost += max(repaid - sold_for, 0)
    return cost


def government_borrows(conn: Connection, treasury, period: int, collected: int) -> int:
    """After a quarter closes: open the next bill, and sell new bonds to the pension funds to
    cover a small planned shortfall. Returns what was raised to spend.

    The Government spends a little more than it collects, and borrows the difference from
    whoever will lend it (design document, section 10)."""
    _open_bill(conn, period)
    state = {"period": period, "policy": _policy(conn), "index": _index(conn), "left": 1.0, "companies": {}}
    dealer = ledger.account_id(conn, DEALER)
    newest: dict = {}
    for bond in _load(conn, "b.issuer = 'government' AND b.kind <> 'bill' AND b.redeemed_period IS NULL"):
        line = (bond["kind"], bond["maturity_period"] - bond["issued_period"])
        if line not in newest or bond["issued_period"] > newest[line]["issued_period"]:
            newest[line] = bond
    lines = list(newest.values())
    # A fresh set of bonds once a game year, so that there is always one of each length on sale.
    if not lines or period - max(b["issued_period"] for b in lines) >= clock.QUARTERS_PER_YEAR:
        lines = _new_government_lines(conn, period, state)
    wanted = collected * data.GOVERNMENT_DEFICIT_BPS // BPS
    room = max(ledger.balance(conn, dealer), 0) * data.GOVERNMENT_BOND_APPETITE_BPS // BPS
    budget = min(wanted, room)
    raised = 0
    for bond in lines:
        price = fair_value(bond, state)
        units = budget // len(lines) // price
        if units > 0:
            raised += _sell_new(conn, bond, treasury, dealer, units, price, period)
    return raised


def government_debt(conn: Connection) -> int:
    """What the Government owes on all its bonds and bills, at face value."""
    return sum(b["units"] * b["face"] for b in _load(conn, "b.issuer = 'government' AND b.redeemed_period IS NULL"))


# ---------------------------------------------------------------------------
# A company's bonds at the close of its quarter (called by the company engine)
# ---------------------------------------------------------------------------

def of_debt(conn: Connection, debt_id) -> dict | None:
    found = _load(conn, "b.debt_id = %s", (debt_id,))
    return found[0] if found else None


def share_out(conn: Connection, bond: dict, amount: int) -> dict:
    """An amount due to a bond's holders, divided by how many each holds: account -> kobo.
    It adds up exactly: the odd kobo left by rounding goes to the largest holder."""
    owners = holders(conn, bond["asset"])
    total = sum(owners.values())
    if not total or amount <= 0:
        return {}
    shares = {account: amount * units // total for account, units in owners.items()}
    largest = max(owners, key=lambda account: (owners[account], str(account)))
    shares[largest] += amount - sum(shares.values())
    return shares


def hand_in(conn: Connection, bond: dict, period: int) -> None:
    """A company's bond has been repaid in full: every bond goes back to the company and out of existence."""
    owners = _rows(conn, "SELECT account_id, balance::bigint AS units FROM ledger_balances WHERE asset = %s AND balance > 0", (bond["asset"],))
    issuer = _one(conn, "SELECT issuer_account_id FROM assets WHERE code = %s", (bond["asset"],))["issuer_account_id"]
    if owners:
        ledger.post(conn, kind="bond_redemption", memo=f"{bond['name']}: repaid", period=period, reference=f"bond:{bond['id']}",
                    legs=[*[Leg(o["account_id"], -o["units"], bond["asset"]) for o in owners],
                          Leg(issuer, sum(o["units"] for o in owners), bond["asset"])])
    conn.execute("UPDATE bond_conversions SET status = 'cancelled', closed_at = now() WHERE bond_id = %s AND status = 'waiting'",
                 (bond["id"],))
    conn.execute("UPDATE bonds SET redeemed_period = %s WHERE id = %s", (period, bond["id"]))


def refinance(conn: Connection, company: dict, debt: dict, period: int, rating: str, policy_rate_bps: int) -> bool:
    """A company's bond has reached its end and investors will lend again: a new bond replaces it.

    The pension funds take the new bonds. Whoever held the old ones is paid their face value,
    and the company's debt carries on at today's rate. Done as one transaction, so that it
    happens completely or not at all. Returns False if the pension funds cannot find the cash."""
    old = of_debt(conn, debt["id"])
    if old is None or old["units"] <= 0:
        return False
    dealer = ledger.account_id(conn, DEALER)
    principal = debt["principal_outstanding"]
    dues = share_out(conn, old, principal)
    to_others = sum(amount for account, amount in dues.items() if account != dealer)
    if to_others > max(ledger.balance(conn, dealer), 0):
        return False
    rate = government_yield_bps(policy_rate_bps, data.BOND_TERM_QUARTERS) + credit_spread_bps(rating)
    new_debt = _one(
        conn,
        "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal, principal_outstanding,"
        " annual_rate_bps, start_period, maturity_period, repayment) VALUES (%s, %s, 'bond', %s, %s, %s, %s, %s, %s, 'bullet')"
        " RETURNING id", (company["id"], dealer, f"{company['name']} bond", principal, principal, rate, period,
                          period + data.BOND_TERM_QUARTERS))["id"]
    new = _create(conn, prefix="C", name=f"{company['name']} {_percent(rate)} bond", issuer="company",
                  issuer_account=company["account_id"], company_id=company["id"], debt_id=new_debt, kind="fixed",
                  coupon_bps=rate, issued=period, maturity=period + data.BOND_TERM_QUARTERS,
                  high_yield=RATING_ORDER.index(rating) > RATING_ORDER.index("BBB"))
    units = max(principal // FACE, 1)
    legs = [Leg(company["account_id"], -units, new["asset"]), Leg(dealer, units, new["asset"])]
    old_owners = _rows(conn, "SELECT account_id, balance::bigint AS units FROM ledger_balances WHERE asset = %s AND balance > 0", (old["asset"],))
    legs += [Leg(o["account_id"], -o["units"], old["asset"]) for o in old_owners]
    legs.append(Leg(company["account_id"], sum(o["units"] for o in old_owners), old["asset"]))
    if to_others:
        legs.append(Leg(dealer, -to_others))
        legs += [Leg(account, amount) for account, amount in dues.items() if account != dealer and amount > 0]
    ledger.post(conn, kind="bond_issue", memo=f"{company['name']}: a new bond replaces the one that has reached its end",
                period=period, reference=f"bond:{new['id']}", legs=legs)
    conn.execute("UPDATE company_debts SET principal_outstanding = 0 WHERE id = %s", (debt["id"],))
    conn.execute("UPDATE bond_conversions SET status = 'cancelled', closed_at = now() WHERE bond_id = %s AND status = 'waiting'", (old["id"],))
    conn.execute("UPDATE bonds SET redeemed_period = %s WHERE id = %s", (period, old["id"]))
    return True


def issue_for_company(conn: Connection, company: dict, *, period: int, amount: int, kind: str, rating: str,
                      policy_rate_bps: int, quarters: int, conversion_shares: int | None = None, project: str | None = None,
                      green: bool = False) -> dict | None:
    """A company borrows by selling a new bond to the pension funds, at its face value.
    Returns the bond, or None if the pension funds will not put up the cash."""
    dealer = ledger.account_id(conn, DEALER)
    units = amount // FACE
    if units <= 0 or units * FACE > max(ledger.balance(conn, dealer), 0) * data.COMPANY_BOND_APPETITE_BPS // BPS:
        return None
    rate = government_yield_bps(policy_rate_bps, quarters) + credit_spread_bps(rating)
    if kind == "convertible":
        rate = max(rate - data.CONVERTIBLE_DISCOUNT_BPS, 200)      # the right to swap for shares is worth a lower coupon
    high_yield = RATING_ORDER.index(rating) > RATING_ORDER.index("BBB")
    words = {"convertible": "convertible bond", "project": ("green bond" if green else "project bond")}.get(
        kind, "high-yield bond" if high_yield else "bond")
    name = f"{company['name']} {_percent(rate)} {words}"
    debt_id = _one(
        conn,
        "INSERT INTO company_debts (company_id, lender_account_id, kind, name, original_principal, principal_outstanding,"
        " annual_rate_bps, start_period, maturity_period, repayment) VALUES (%s, %s, 'bond', %s, %s, %s, %s, %s, %s, 'bullet')"
        " RETURNING id", (company["id"], dealer, f"{company['name']} {words}", units * FACE, units * FACE, rate, period,
                          period + quarters))["id"]
    extra = {"high_yield": high_yield, "green": green}
    if conversion_shares:
        extra["conversion_shares"] = conversion_shares
    if project:
        extra["project"] = project
    bond = _create(conn, prefix="C", name=name, issuer="company", issuer_account=company["account_id"], company_id=company["id"],
                   debt_id=debt_id, kind=kind, coupon_bps=rate, issued=period, maturity=period + quarters, **extra)
    _sell_new(conn, bond, company["account_id"], dealer, units, FACE, period + 1)
    return {**bond, "units": units, "rate": rate, "words": words}


# ---------------------------------------------------------------------------
# The bond desk: buying and selling
# ---------------------------------------------------------------------------

def _pressure(conn: Connection, bond: dict, day, extra_units: int) -> int:
    """How far recent buying and selling has moved the desk's prices for this bond, in hundredths
    of a percent. Buying pushes them up, selling pushes them down; half fades each trading day."""
    if bond["kind"] == "bill" or bond["units"] <= 0 or (bond["issuer"] == "government" and extra_units > 0):
        return 0                     # the Treasury sells any number at the same price
    net = _one(
        conn,
        "SELECT coalesce(sum(CASE WHEN side = 'buy' THEN units ELSE -units END) FILTER (WHERE session_date = %s), 0)::bigint AS today,"
        "       coalesce(sum(CASE WHEN side = 'buy' THEN units ELSE -units END) FILTER (WHERE session_date = %s), 0)::bigint AS before"
        " FROM bond_trades WHERE bond_id = %s AND session_date >= %s", (day, day - timedelta(days=1), bond["id"], day - timedelta(days=1)))
    level = net["today"] + net["before"] // 2 + extra_units
    moved = level * data.BOND_IMPACT_BPS * 100 // bond["units"]          # so much for each 1% of the whole issue
    return min(max(moved, -data.MOST_BOND_IMPACT_BPS), data.MOST_BOND_IMPACT_BPS)


def prices(conn: Connection, bond: dict, state: dict, day, *, buying: int = 1, selling: int = 1) -> dict:
    """The fair value of one bond and the prices the desk will trade it at: what it asks from a
    buyer of `buying` bonds and what it pays a seller of `selling` bonds."""
    fair = fair_value(bond, state)
    half = _half_spread(bond, state)
    ask = -(-fair * (BPS + half + _pressure(conn, bond, day, buying)) // BPS)
    bid = fair * (BPS - half + _pressure(conn, bond, day, -selling)) // BPS
    return {"fair": fair, "ask": max(ask, 1), "bid": max(min(bid, ask - 1), 0)}


def trade(conn: Connection, *, account: UUID | str, code: str, side: str, units: int, now: datetime) -> dict:
    """Buy bonds from the desk, or sell them to it. Returns what was done.

    Raises BondError, with a message for the player, if it cannot be done. Nothing is left half-done."""
    from simulation import exchange

    if side not in ("buy", "sell"):
        raise BondError("You can buy bonds or sell them.")
    if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
        raise BondError("The number of bonds must be a whole number above zero.")
    with conn.transaction():
        owner = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))
        if owner is None or owner["kind"] != "player":
            raise BondError("That account cannot trade at the bond desk.")
        bond = find(conn, code, lock=True)
        if bond is None:
            raise BondError("There is no bond with that code.")
        state = market(conn, now)
        day, session = exchange.session_of(now)
        if bond["redeemed_period"] is not None or (bond["maturity_period"] <= state["period"] and bond["issuer"] == "government"):
            raise BondError("That bond has been repaid. It no longer trades.")
        # The Government sells its own bills and bonds itself: as many as are asked for. Everything
        # else is bought from the pension funds, and everything is sold to them.
        tap = bond["issuer"] == "government" and side == "buy"
        if not (tap and bond["kind"] == "bill") and session is not clock.MarketState.OPEN:
            raise BondError("The bond desk trades from 12:00 to 22:00 Lagos time. A Government bill can be bought at any hour.")
        dealer = ledger.account_id(conn, DEALER)
        quote = prices(conn, bond, state, day, buying=units, selling=units)
        price = quote["ask"] if side == "buy" else quote["bid"]
        if price <= 0:
            raise BondError("The desk is not buying that bond today.")
        value = price * units
        if value > MAX_AMOUNT:
            raise BondError("That is too many.")
        try:
            if tap:
                treasury = ledger.account_id(conn, ledger.TREASURY)
                transaction = ledger.post(
                    conn, kind="bond_issue", memo=f"{units:,} of {bond['name']} bought from the Treasury",
                    reference=f"bond:{bond['id']}", period=state["period"] + 1,
                    legs=[Leg(treasury, -units, bond["asset"]), Leg(account, units, bond["asset"]),
                          Leg(account, -value), Leg(treasury, value)])
                counterparty = treasury
            else:
                buyer, seller = (account, dealer) if side == "buy" else (dealer, account)
                if side == "buy" and ledger.balance(conn, dealer, bond["asset"]) < units:
                    on_offer = ledger.balance(conn, dealer, bond["asset"])
                    raise BondError(f"The pension funds have {on_offer:,} of that bond to sell today." if on_offer else
                                    "The pension funds have none of that bond to sell today.")
                if side == "sell" and ledger.balance(conn, account, bond["asset"]) < units:
                    raise BondError("You do not hold that many of that bond.")
                transaction = ledger.post(
                    conn, kind="bond_trade", memo=f"{units:,} of {bond['name']} at ₦{price / 100:,.2f}",
                    reference=f"bond:{bond['id']}", period=state["period"] + 1,
                    legs=[Leg(seller, -units, bond["asset"]), Leg(buyer, units, bond["asset"]),
                          Leg(buyer, -value), Leg(seller, value)])
                counterparty = dealer
        except ledger.InsufficientFunds:
            if side == "buy":
                raise BondError(f"You do not have enough cash. That costs ₦{value / 100:,.2f}.") from None
            raise BondError("The pension funds cannot pay for that many today. Try fewer.") from None
        conn.execute(
            "INSERT INTO bond_trades (bond_id, account_id, side, units, price, counterparty, session_date, ledger_transaction, traded_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (bond["id"], account, side, units, price, counterparty, day, transaction, now))
        return {"code": code, "name": bond["name"], "side": side, "units": units, "price": price, "value": value,
                "fair": quote["fair"]}


# ---------------------------------------------------------------------------
# Swapping a convertible bond for shares
# ---------------------------------------------------------------------------

def ask_to_convert(conn: Connection, *, account: UUID | str, code: str, units: int, now: datetime) -> dict:
    """Ask for convertible bonds to be swapped for shares. The bonds are held at once; the swap
    is made when the quarter closes."""
    if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
        raise BondError("The number of bonds must be a whole number above zero.")
    with conn.transaction():
        bond = find(conn, code, lock=True)
        if bond is None or bond["kind"] != "convertible":
            raise BondError("That is not a bond that can be swapped for shares.")
        if bond["redeemed_period"] is not None:
            raise BondError("That bond has been repaid.")
        try:
            ledger.transfer(conn, payer=account, receiver=held_account(conn), amount=units, asset=bond["asset"],
                            kind="conversion_hold", memo=f"{bond['name']}: held to be swapped for shares")
        except ledger.InsufficientFunds:
            raise BondError("You do not hold that many of that bond.") from None
        row = _one(conn, "INSERT INTO bond_conversions (bond_id, account_id, units, requested_at) VALUES (%s, %s, %s, %s)"
                         " RETURNING id", (bond["id"], account, units, now))
        return {"id": row["id"], "units": units, "shares": units * bond["conversion_shares"]}


def cancel_conversion(conn: Connection, *, account: UUID | str, request_id: int, now: datetime) -> None:
    with conn.transaction():
        row = _one(conn, "SELECT v.*, b.asset, b.name FROM bond_conversions v JOIN bonds b ON b.id = v.bond_id"
                         " WHERE v.id = %s AND v.account_id = %s FOR UPDATE OF v", (request_id, account))
        if row is None or row["status"] != "waiting":
            raise BondError("You have no swap waiting with that number.")
        ledger.transfer(conn, payer=held_account(conn), receiver=account, amount=row["units"], asset=row["asset"],
                        kind="conversion_release", memo=f"{row['name']}: handed back, swap cancelled")
        conn.execute("UPDATE bond_conversions SET status = 'cancelled', closed_at = %s WHERE id = %s", (now, request_id))


def convert_waiting(conn: Connection, period: int) -> dict:
    """Make every swap that is waiting. Returns, for each company, the debt that became shares
    and how many shares were issued: company id -> (kobo, shares)."""
    done: dict = {}
    held = held_account(conn)
    after = _one(conn, "SELECT coalesce(max(id), 0) AS id FROM market_trades")["id"]
    for row in _rows(conn, "SELECT v.* FROM bond_conversions v WHERE v.status = 'waiting' ORDER BY v.id FOR UPDATE"):
        bond = _load(conn, "b.id = %s", (row["bond_id"],))[0]
        if bond["redeemed_period"] is not None or bond["units"] <= 0:
            continue
        shares = row["units"] * bond["conversion_shares"]
        debt = row["units"] * (bond["principal"] // bond["units"])
        company = _one(conn, "SELECT id, account_id, share_asset, name FROM companies WHERE id = %s", (bond["company_id"],))
        ledger.post(
            conn, kind="share_issue", memo=f"{bond['name']}: {row['units']:,} bonds swapped for {shares:,} shares",
            period=period, reference=f"bond:{bond['id']}",
            legs=[Leg(company["account_id"], -shares, company["share_asset"]), Leg(row["account_id"], shares, company["share_asset"]),
                  Leg(held, -row["units"], bond["asset"]), Leg(company["account_id"], row["units"], bond["asset"])])
        conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding - %s WHERE id = %s", (debt, bond["debt_id"]))
        conn.execute("UPDATE bond_conversions SET status = 'done', period = %s, shares = %s, face_value = %s, closed_at = now()"
                     " WHERE id = %s", (period, shares, debt, row["id"]))
        conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id)"
                     " VALUES (%s, %s, 'conversion', %s, %s, %s)", (row["account_id"], company["id"], shares, debt, after))
        was = done.get(company["id"], (0, 0))
        done[company["id"]] = (was[0] + debt, was[1] + shares)
    return done


def converted_in(conn: Connection, company_id, period: int) -> int:
    """How much of a company's debt became shares as one quarter closed, in kobo."""
    return _one(conn, "SELECT coalesce(sum(v.face_value), 0)::bigint AS total FROM bond_conversions v JOIN bonds b ON b.id = v.bond_id"
                      " WHERE b.company_id = %s AND v.period = %s AND v.status = 'done'", (company_id, period))["total"]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def describe(bond: dict, state: dict) -> dict:
    """One bond as the page shows it, without prices."""
    kind = KIND_WORDS[bond["kind"]]
    if bond["issuer"] == "company":
        if distressed(bond, state):
            kind = "Distressed debt"
        elif bond["kind"] == "project" and bond["green"]:
            kind = "Green bond"
        elif bond["kind"] == "fixed" and bond["high_yield"]:
            kind = "High-yield bond"
        elif bond["kind"] == "fixed":
            kind = "Company bond"
    if bond["kind"] == "floating":
        pays = f"The Central Bank's rate plus {_percent(bond['coupon_bps'])} a year, now {_percent(state['policy'] + bond['coupon_bps'])}"
    elif bond["kind"] == "inflation_linked":
        pays = f"{_percent(bond['coupon_bps'])} a year on a face value that rises with prices"
    elif bond["kind"] == "bill":
        pays = "No interest: it is bought for less than its face value and repaid in full"
    else:
        pays = f"{_percent(bond['coupon_bps'])} a year, in four payments"
    return {
        "code": bond["asset"][4:], "name": bond["name"], "kind": bond["kind"], "kind_label": kind,
        "issuer": "Federal Government" if bond["issuer"] == "government" else bond["company_name"], "ticker": bond["ticker"],
        "rating": state["companies"].get(bond["company_id"], {}).get("credit_rating") if bond["company_id"] else None,
        "pays": pays, "coupon_bps": bond["coupon_bps"], "face": _claim(bond),
        "maturity_period": bond["maturity_period"], "maturity_label": clock.period_label(bond["maturity_period"]),
        "quarters_left": max(bond["maturity_period"] - state["period"], 0),
        "yield_bps": yield_bps(bond, state), "distressed": distressed(bond, state),
        "conversion_shares": bond["conversion_shares"], "project": bond["project"], "green": bond["green"],
        "outstanding": bond["units"],
    }


def listing(conn: Connection, now: datetime) -> list[dict]:
    """Every bond that can be traded, with its fair value and the desk's prices."""
    from simulation import exchange
    state = market(conn, now)
    day, _ = exchange.session_of(now)
    dealer = ledger.account_id(conn, DEALER)
    on_offer = {r["asset"]: r["balance"] for r in _rows(
        conn, "SELECT asset, balance::bigint AS balance FROM ledger_balances WHERE account_id = %s AND asset LIKE 'BND-%%'", (dealer,))}
    out = []
    for bond in _load(conn, "b.redeemed_period IS NULL"):
        if bond["issuer"] == "government" and bond["maturity_period"] <= state["period"]:
            continue
        if bond["issuer"] == "company" and bond["units"] <= 0:
            continue
        out.append({**describe(bond, state), **prices(conn, bond, state, day),
                    "on_offer": None if bond["issuer"] == "government" else on_offer.get(bond["asset"], 0)})
    return out


def holdings_of(conn: Connection, account: UUID | str, now: datetime) -> list[dict]:
    """The bonds an account holds, what they cost, what they are worth, and the interest received."""
    from simulation import exchange
    state = market(conn, now)
    day, _ = exchange.session_of(now)
    waiting = {r["bond_id"]: r["units"] for r in _rows(
        conn, "SELECT bond_id, sum(units)::bigint AS units FROM bond_conversions WHERE account_id = %s AND status = 'waiting'"
              " GROUP BY bond_id", (account,))}
    out = []
    for bond in _load(conn, "b.redeemed_period IS NULL AND (EXISTS (SELECT 1 FROM ledger_balances h WHERE h.asset = b.asset"
                            " AND h.account_id = %s AND h.balance > 0) OR b.id = ANY(%s))", (account, list(waiting))):
        units = ledger.balance(conn, account, bond["asset"]) + waiting.get(bond["id"], 0)
        # What the bonds still held cost, by the average-cost method.
        held, cost = 0, 0
        for t in _rows(conn, "SELECT side, units, price FROM bond_trades WHERE bond_id = %s AND account_id = %s ORDER BY id",
                       (bond["id"], account)):
            if t["side"] == "buy":
                held, cost = held + t["units"], cost + t["units"] * t["price"]
            else:
                sold = min(t["units"], held)
                cost -= cost * sold // held if held else 0
                held -= sold
        cost = cost * min(units, held) // held if held else 0
        quote = prices(conn, bond, state, day)
        out.append({**describe(bond, state), **quote, "units": units, "held_for_swap": waiting.get(bond["id"], 0),
                    "value": units * quote["fair"], "cost": cost, "gain": units * quote["fair"] - cost})
    return out


def income_of(conn: Connection, account: UUID | str) -> int:
    """All the bond interest an account has received, and the gain on bills repaid."""
    return _one(conn, "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                      " ON t.id = e.transaction_id WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0"
                      " AND (t.kind = 'bond_coupon' OR (t.kind = 'debt_interest' AND t.reference LIKE 'debt:%%'))", (account,))["total"]


def values_by_account(conn: Connection) -> dict:
    """For each player: the fair value of the bonds they hold: account -> (cash, investments)."""
    state = market(conn, datetime.now(clock.LAGOS))
    worth: dict = {}
    values: dict = {}
    for row in _rows(
        conn,
        "SELECT x.account_id, x.asset, sum(x.units)::bigint AS units FROM ("
        "   SELECT h.account_id, h.asset, h.balance AS units FROM ledger_balances h JOIN ledger_accounts a ON a.id = h.account_id"
        "    WHERE a.kind = 'player' AND h.asset LIKE 'BND-%%' AND h.balance > 0"
        "   UNION ALL SELECT v.account_id, b.asset, v.units FROM bond_conversions v JOIN bonds b ON b.id = v.bond_id"
        "    WHERE v.status = 'waiting') x GROUP BY x.account_id, x.asset"):
        if row["asset"] not in values:
            bond = _load(conn, "b.asset = %s", (row["asset"],))[0]
            values[row["asset"]] = fair_value(bond, state)
        was = worth.get(row["account_id"], (0, 0))
        worth[row["account_id"]] = (0, was[1] + row["units"] * values[row["asset"]])
    return worth
