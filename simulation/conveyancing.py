"""The gap stage, Part 2: buying property outside the Auction House (the twelve-step purchase), the Land Registry, and
claims on a property besides a flawed title.

The twelve steps of a private purchase:
   1. confirm who the seller is (the Land Registry's record of owners)
   2. the title search (does the seller own all of it?)
   3. the claims search (old loans, rights of way, disputes)
   4. the zoning check (what may stand on it)
   5. the valuation (comparable sales, income, cost)
   6. the money (cash, or a mortgage from a bank)
   7. the terms (the seller agrees the price)
   8. asking for the Governor's consent (a fee to the Government)
   9. consent granted (about two real days later)
  10. the contract (the buyer's money is held)
  11. registration at the Land Registry (a fee to the Government)
  12. handover: the seller is paid and the buyer owns it
Steps 1 to 5 are checks: skipping one never blocks the purchase, but what it would have found shows up later.

Claims: about one property in twenty has an old loan secured on it, which the owner must pay off when it comes to light;
about one in twenty-five has a right of way across it, which takes a tenth off its value; about one in thirty-odd has
a family or community dispute, which freezes the property (nothing may be built, sold, leased or rezoned, and its rent
is not paid out) until it is settled with the claimants. A claim is secret until a claims search finds it or it comes to
light at the first quarter's close after the property passes to somebody other than a property company. Courts come
in Stage 11; until then a dispute nobody settles fades after eight quarters.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, ledger
from simulation import world_data as data
from simulation.money import BPS, naira

SALE_HELD = "property:sales"        # the buyer's money, held from the contract until the handover


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('property_sales') IS NOT NULL AS ok")["ok"] is True


def _held(conn: Connection):
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (SALE_HELD,))
    if row:
        return row["id"]
    return ledger.create_account(conn, kind="escrow", name="Land Registry: money held for private property sales", code=SALE_HELD)


def _err(words: str):
    from simulation.property import PropertyError
    return PropertyError(words)


# ---------------------------------------------------------------------------
# The Land Registry
# ---------------------------------------------------------------------------

def register(conn: Connection, property_id: int, how: str, price: int, period: int, now: datetime, *, payer=None) -> int:
    """Record a change of hands. A sale pays the registration fee (from the buyer, as far as it can)."""
    if not ready(conn):
        return 0
    fee = 0
    if payer is not None and price > 0:
        wanted = price * data.REGISTRATION_FEE_BPS // BPS
        fee = ledger.pay_up_to(conn, payer=payer, receiver=ledger.account_id(conn, ledger.TREASURY), wanted=wanted, kind="land_registration",
                               memo=f"Land Registry: registering the transfer of property {property_id}", period=period)
    conn.execute("INSERT INTO land_register (property_id, how, price, fee, period, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (property_id, how, price, fee, period, now))
    return fee


def register_of(conn: Connection, property_id: int) -> list[dict]:
    """The public record: when it changed hands and how (never who, for a player)."""
    if not ready(conn):
        return []
    return [{"label": clock.period_label(r["period"]) if r["period"] else "Start", "how": r["how"], "price": r["price"]}
            for r in _rows(conn, "SELECT * FROM land_register WHERE property_id = %s ORDER BY id DESC LIMIT 10", (property_id,))]


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

def first_claims(conn: Connection) -> None:
    """A new world: the claims hidden on some property, drawn from each property's number (as the migration did)."""
    conn.execute("INSERT INTO property_claims (property_id, kind, cut_bps, status, at) SELECT id, 'old_loan', 0, 'hidden', now() FROM properties"
                 " WHERE (id::bigint * 7919 + 13) %% 10000 < %s", (data.CLAIM_OLD_LOAN_BPS,))
    conn.execute("INSERT INTO property_claims (property_id, kind, cut_bps, status, at) SELECT id, 'right_of_way', %s, 'hidden', now() FROM properties"
                 " WHERE (id::bigint * 104729 + 71) %% 10000 < %s", (data.CLAIM_RIGHT_OF_WAY_CUT_BPS, data.CLAIM_RIGHT_OF_WAY_BPS))
    conn.execute("INSERT INTO property_claims (property_id, kind, cut_bps, status, at) SELECT id, 'dispute', 0, 'hidden', now() FROM properties"
                 " WHERE (id::bigint * 15485863 + 211) %% 10000 < %s", (data.CLAIM_DISPUTE_BPS,))


def _draw(conn: Connection, claim: dict, worth: int) -> dict:
    """An old loan's size and its bank, or a dispute's settlement, fixed when it is first found (from its number)."""
    if claim["amount"] or claim["kind"] == "right_of_way":
        return claim
    if claim["kind"] == "old_loan":
        low, high = data.CLAIM_OLD_LOAN_SIZE_BPS
        share = low + (claim["property_id"] * 7 + claim["id"] * 13) % max(high - low, 1)
        banks = _rows(conn, "SELECT id FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY ticker")
        bank = banks[claim["property_id"] % len(banks)]["id"] if banks else None
        amount = max(worth * share // BPS, naira(100_000))
        conn.execute("UPDATE property_claims SET amount = %s, lender = %s WHERE id = %s", (amount, bank, claim["id"]))
        return {**claim, "amount": amount, "lender": bank}
    amount = max(worth * data.CLAIM_DISPUTE_SETTLE_BPS // BPS, naira(100_000))
    conn.execute("UPDATE property_claims SET amount = %s WHERE id = %s", (amount, claim["id"]))
    return {**claim, "amount": amount}


def _worth(conn: Connection, property_id: int) -> int:
    from simulation import property as prop
    p = prop._property(conn, property_id)
    return prop.value(p, prop.districts(conn)[p["district_id"]], prop.policy_rate(conn))


def _describe(c: dict) -> str:
    from simulation.property import money
    if c["kind"] == "old_loan":
        return f"An old loan of {money(c['amount'])} is secured on it: whoever owns it must pay it off."
    if c["kind"] == "right_of_way":
        return f"A right of way crosses it: it is worth {c['cut_bps'] / 100:.0f}% less."
    return f"A family dispute over it: nothing may be done with it until it is settled (for {money(c['amount'])})."


def claims_search(conn: Connection, account, property_id: int, now: datetime) -> dict:
    """The Land Registry's search for claims besides the title: a fee to the Government."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        prop._property(conn, property_id)
        fee = naira(data.CLAIMS_SEARCH_FEE_NAIRA)
        try:
            ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="property_tax",
                            memo=f"Claims search at the Land Registry: property {property_id}", period=state["period"])
        except ledger.InsufficientFunds:
            raise _err(f"A claims search costs {prop.money(fee)}.") from None
        worth = _worth(conn, property_id)
        found = [_draw(conn, c, worth) for c in _rows(conn, "SELECT * FROM property_claims WHERE property_id = %s AND status IN ('hidden', 'found', 'known')"
                                                            " ORDER BY id", (property_id,))]
        # A claim the registry has found is on its record from now on: it comes to bear at the next close on whoever owns
        # the property then (so it cannot be dodged by selling quickly to somebody who did not search).
        conn.execute("UPDATE property_claims SET status = 'found' WHERE property_id = %s AND status = 'hidden'", (property_id,))
        return {"fee": fee, "clean": not found, "claims": [{"kind": c["kind"], "words": _describe(c)} for c in found],
                "words": "The registry shows no claims on it." if not found else " ".join(_describe(c) for c in found)}


def known_claims(conn: Connection, property_id: int) -> list[dict]:
    if not ready(conn):
        return []
    return [{"id": c["id"], "kind": c["kind"], "words": _describe(c), "amount": c["amount"]}
            for c in _rows(conn, "SELECT * FROM property_claims WHERE property_id = %s AND status IN ('found', 'known') ORDER BY id", (property_id,))]


def _come_to_light(conn: Connection, c: dict, period: int, now: datetime) -> None:
    from simulation import headquarters, lending, news
    p = _one(conn, "SELECT p.*, d.city FROM properties p JOIN districts d ON d.id = p.district_id WHERE p.id = %s", (c["property_id"],))
    c = _draw(conn, c, _worth(conn, c["property_id"]))
    conn.execute("UPDATE property_claims SET status = 'known', known_period = %s WHERE id = %s", (period, c["id"]))
    owners = _rows(conn, "SELECT * FROM property_holdings WHERE property_id = %s", (c["property_id"],))
    if c["kind"] == "right_of_way":
        conn.execute("UPDATE properties SET value_cut_bps = value_cut_bps + %s WHERE id = %s", (c["cut_bps"], c["property_id"]))
    elif c["kind"] == "dispute":
        conn.execute("UPDATE properties SET frozen = true WHERE id = %s", (c["property_id"],))
    else:
        # The old loan: the owners pay it off now, each for their share; what they cannot pay they owe the bank.
        bank = _one(conn, "SELECT account_id FROM companies WHERE id = %s", (c["lender"],))
        for h in owners:
            part = c["amount"] * h["share_bps"] // BPS
            if part <= 0 or bank is None:
                continue
            got = ledger.pay_up_to(conn, payer=h["account_id"], receiver=bank["account_id"], wanted=part, kind="shortfall_repayment",
                                   memo=f"An old loan secured on {p['name']}, paid off", period=period)
            if got < part:
                lending.record_shortfall(conn, h["account_id"], bank["account_id"], part - got, f"The old loan secured on {p['name']}", period, now)
        conn.execute("UPDATE property_claims SET status = 'settled' WHERE id = %s", (c["id"],))
    words = {"old_loan": "an old loan secured on it", "right_of_way": "a right of way across it", "dispute": "a family dispute over it"}[c["kind"]]
    news.publish(conn, period=period + 1, day=4, kind="property_claim", story=f"claim:{c['id']}",
                 facts={"property": p["name"], "claim": words}, locations=[p["city"]], sectors=["real_estate"])
    _ = headquarters


def settle_dispute(conn: Connection, account, property_id: int, now: datetime) -> dict:
    """An owner settles a known dispute with the claimants: the property is free again."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, account) <= 0:
            raise _err("Only an owner settles a dispute over it.")
        c = _one(conn, "SELECT * FROM property_claims WHERE property_id = %s AND kind = 'dispute' AND status = 'known' FOR UPDATE", (property_id,))
        if c is None:
            raise _err("There is no dispute over it to settle.")
        try:
            ledger.transfer(conn, payer=account, receiver=ledger.account_id(conn, ledger.INVESTORS_FOUNDERS), amount=c["amount"],
                            kind="dispute_settlement", memo=f"Settling the dispute over property {property_id}", period=state["period"])
        except ledger.InsufficientFunds:
            raise _err(f"Settling it costs {prop.money(c['amount'])}.") from None
        conn.execute("UPDATE property_claims SET status = 'settled' WHERE id = %s", (c["id"],))
        conn.execute("UPDATE properties SET frozen = false WHERE id = %s", (property_id,))
        return {"paid": c["amount"]}


def close_claims(conn: Connection, period: int, now: datetime) -> None:
    """Hidden claims on property owned outside the property companies come to light at the first close after it changed
    hands; disputes nobody settled fade after eight quarters."""
    if not ready(conn):
        return
    for c in _rows(conn, """
            SELECT c.* FROM property_claims c
            WHERE c.status = 'found'
               OR (c.status = 'hidden'
                   AND EXISTS (SELECT 1 FROM property_holdings h WHERE h.property_id = c.property_id AND h.since_period < %s
                               AND NOT EXISTS (SELECT 1 FROM companies co WHERE co.account_id = h.account_id)))
            ORDER BY c.id FOR UPDATE OF c""", (period,)):
        _come_to_light(conn, c, period, now)
    for c in _rows(conn, "SELECT * FROM property_claims WHERE kind = 'dispute' AND status = 'known' AND known_period <= %s",
                   (period - data.CLAIM_DISPUTE_FADES_QUARTERS,)):
        conn.execute("UPDATE property_claims SET status = 'faded' WHERE id = %s", (c["id"],))
        conn.execute("UPDATE properties SET frozen = false WHERE id = %s", (c["property_id"],))


def not_frozen(p: dict) -> None:
    if p.get("frozen"):
        raise _err("A family dispute over it freezes it: nothing may be done with it until the owner settles it.")


# ---------------------------------------------------------------------------
# The twelve-step purchase
# ---------------------------------------------------------------------------

def _counterparty(conn: Connection, who: dict):
    if who.get("player"):
        row = _one(conn, "SELECT a.id FROM players p JOIN ledger_accounts a ON a.player_id = p.id WHERE lower(p.display_name) = lower(%s)",
                   (who["player"],))
        if row is None:
            raise _err("There is no player of that name.")
        return row["id"]
    if who.get("empire"):
        row = _one(conn, "SELECT account_id FROM empires WHERE lower(name) = lower(%s) AND status = 'active' AND kind <> 'pension'",
                   (str(who["empire"]),))
        if row is None:
            raise _err("There is no open empire of that name.")
        return row["account_id"]
    raise _err("Name the buyer: a player or an empire.")


def _same_side(conn: Connection, a, b) -> bool:
    """Is one of them an empire the other sits in (a member selling to their own empire, or the reverse)?"""
    if a == b:
        return True
    row = _one(conn, """
        SELECT 1 FROM empire_seats s JOIN empires e ON e.id = s.empire_id JOIN ledger_accounts pa ON pa.player_id = s.player_id
        WHERE (e.account_id = %s AND pa.id = %s) OR (e.account_id = %s AND pa.id = %s)""", (a, b, b, a))
    return row is not None


def offer(conn: Connection, seller, property_id: int, buyer_who: dict, price: int, now: datetime, *, offered_by=None) -> dict:
    """The owner of the whole of a property offers it to a named buyer at a price."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        p = prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, seller) < BPS:
            raise _err("Only the owner of the whole of a property sells it this way. (Part-owners sell at the Auction House.)")
        not_frozen(p)
        if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
            raise _err("Name a price.")
        buyer = _counterparty(conn, buyer_who)
        if _same_side(conn, seller, buyer):
            raise _err("A sale needs a buyer who is not the seller, nor the seller's own empire or member.")
        if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
            raise _err("It is up for auction.")
        if _one(conn, "SELECT 1 FROM property_leases WHERE property_id = %s AND status = 'running'", (property_id,)):
            raise _err("It is leased.")
        if _one(conn, "SELECT 1 FROM developments WHERE property_id = %s AND status IN ('permit', 'building')", (property_id,)):
            raise _err("It is being developed.")
        if _one(conn, "SELECT 1 FROM property_sales WHERE property_id = %s AND status IN ('offered', 'agreed', 'consent', 'contracted')",
                (property_id,)):
            raise _err("A sale of it is already under way.")
        row = _one(conn, "INSERT INTO property_sales (property_id, seller, buyer, price, offered_by, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                         " RETURNING id", (property_id, seller, buyer, price, offered_by, state["period"], now))
        return {"sale_id": row["id"], "status": "offered"}


def _sale(conn: Connection, sale_id: int, account, *, as_buyer: bool) -> dict:
    sale = _one(conn, "SELECT s.*, p.name, p.title_flaw_bps, p.zone, p.frozen FROM property_sales s JOIN properties p ON p.id = s.property_id"
                      " WHERE s.id = %s AND s." + ("buyer" if as_buyer else "seller") + " = %s FOR UPDATE OF s", (sale_id, account))
    if sale is None:
        raise _err("There is no such sale of yours.")
    return sale


def _mark(conn: Connection, sale: dict, step: str, result: dict | None = None) -> dict:
    steps = dict(sale["steps"] or {})
    steps[step] = result or {"done": True}
    conn.execute("UPDATE property_sales SET steps = %s WHERE id = %s", (Jsonb(steps), sale["id"]))
    return steps


def check(conn: Connection, buyer, sale_id: int, step: str, now: datetime) -> dict:
    """One of the buyer's checks (steps 1 to 5). Each finds what it finds; none is required."""
    from simulation import careers, propvalue
    from simulation import property as prop
    if step not in data.SALE_CHECK_STEPS:
        raise _err("Name a check: seller, title, claims, zoning or valuation.")
    with conn.transaction():
        careers.world_now(conn, now)
        sale = _sale(conn, sale_id, buyer, as_buyer=True)
        if sale["status"] not in ("offered", "agreed"):
            raise _err("The checks come before the contract.")
        if step == "seller":
            owns = prop.share_of(conn, sale["property_id"], sale["seller"]) >= BPS
            result = {"words": "The Land Registry's record shows the seller as the owner of all of it." if owns
                      else "The registry does not show the seller as its owner."}
        elif step == "title":
            result = prop.title_search(conn, buyer, sale["property_id"], now)
        elif step == "claims":
            result = claims_search(conn, buyer, sale["property_id"], now)
        elif step == "zoning":
            p = prop._property(conn, sale["property_id"])
            allowed = ", ".join(data.PROPERTY_KIND_NAMES[k].lower() for k in data.ZONE_ALLOWS[p["zone"]])
            result = {"words": f"Zoned {data.ZONE_NAMES[p['zone']].lower()}: {allowed} may be built.",
                      "fits": p["kind"] == "land" or p["kind"] in data.ZONE_ALLOWS[p["zone"]]}
        else:
            v = propvalue.three_ways(conn, sale["property_id"])
            result = {"words": f"Comparable sales {prop.money(v['comparables'])}; income {prop.money(v['income'])}; cost {prop.money(v['cost'])}.",
                      **{k: v[k] for k in ("comparables", "income", "cost")}}
        _mark(conn, sale, step, {k: v for k, v in result.items() if k in ("words", "clean", "fits", "comparables", "income", "cost")})
        return result


def accept(conn: Connection, buyer, sale_id: int, now: datetime, *, mortgage_bank=None, mortgage: int = 0) -> dict:
    """Steps 6 and 7: the buyer says how it will pay and agrees the terms. A mortgage is the bank's promise, paid at the
    handover."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        sale = _sale(conn, sale_id, buyer, as_buyer=True)
        if sale["status"] != "offered":
            raise _err("That offer is not open.")
        if not isinstance(mortgage, int) or isinstance(mortgage, bool) or mortgage < 0:
            raise _err("A mortgage is a sum in kobo.")
        if mortgage:
            if mortgage_bank is None or not _one(conn, "SELECT 1 FROM companies WHERE id = %s AND sector = 'banking' AND status = 'trading'",
                                                 (mortgage_bank,)):
                raise _err("Choose a bank for the mortgage.")
            most = prop.mortgage_limit(conn, buyer, sale["price"], now, except_sale=sale["id"])
            if mortgage > most:
                raise _err(f"A bank lends you at most {prop.money(most)} against it.")
        if ledger.balance(conn, buyer) < sale["price"] - mortgage:
            raise _err(f"You need {prop.money(sale['price'] - mortgage)} of your own for it.")
        conn.execute("UPDATE property_sales SET status = 'agreed', mortgage = %s, mortgage_bank = %s WHERE id = %s",
                     (mortgage, mortgage_bank if mortgage else None, sale["id"]))
        _mark(conn, sale, "money", {"words": f"{prop.money(sale['price'] - mortgage)} in cash" + (f", {prop.money(mortgage)} from a bank" if mortgage else "")})
        sale = _sale(conn, sale_id, buyer, as_buyer=True)
        _mark(conn, sale, "terms", {"words": f"The price is agreed at {prop.money(sale['price'])}."})
        return {"status": "agreed", "period": state["period"]}


def ask_consent(conn: Connection, buyer, sale_id: int, now: datetime) -> dict:
    """Step 8: ask the Governor's consent, with its fee. It comes about two real days later."""
    from simulation import careers
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        sale = _sale(conn, sale_id, buyer, as_buyer=True)
        if sale["status"] != "agreed":
            raise _err("Agree the terms first.")
        fee = sale["price"] * data.CONSENT_FEE_BPS // BPS
        try:
            ledger.transfer(conn, payer=buyer, receiver=ledger.account_id(conn, ledger.TREASURY), amount=fee, kind="property_tax",
                            memo=f"The Governor's consent to buy {sale['name']}", period=state["period"])
        except ledger.InsufficientFunds:
            raise _err(f"The consent fee is {prop.money(fee)}.") from None
        due = now + timedelta(days=data.CONSENT_DAYS)
        conn.execute("UPDATE property_sales SET status = 'consent', consent_due = %s WHERE id = %s", (due, sale["id"]))
        _mark(conn, sale, "consent_asked", {"words": f"Asked, with a fee of {prop.money(fee)}."})
        return {"status": "consent", "due": due.isoformat(), "fee": fee}


def sign(conn: Connection, buyer, sale_id: int, now: datetime) -> dict:
    """Steps 9 to 12, once consent has come: the contract (the buyer's money is held), registration at the Land
    Registry, and the handover."""
    from simulation import careers, headquarters
    from simulation import property as prop
    with conn.transaction():
        state = careers.world_now(conn, now)
        period = state["period"]
        sale = _sale(conn, sale_id, buyer, as_buyer=True)
        if sale["status"] != "consent":
            raise _err("Ask for the Governor's consent first.")
        if sale["consent_due"] > now:
            raise _err(f"The consent has not come yet: it is due {sale['consent_due']:%d %b, %H:%M}.")
        p = prop._property(conn, sale["property_id"], lock=True)
        if prop.share_of(conn, sale["property_id"], sale["seller"]) < BPS or p["frozen"]:
            conn.execute("UPDATE property_sales SET status = 'failed' WHERE id = %s", (sale["id"],))
            return {"status": "failed", "words": "The seller no longer owns all of it free to sell: the sale fails."}
        _mark(conn, sale, "consent", {"words": "The Governor's consent was granted."})
        held = _held(conn)
        own = sale["price"] - sale["mortgage"]
        # (The seller's own mortgage, read before the buyer's new one exists, and by who owes it.)
        sellers_mortgage = _one(conn, "SELECT * FROM mortgages WHERE property_id = %s AND borrower = %s AND status = 'open' FOR UPDATE",
                                (sale["property_id"], sale["seller"]))
        try:
            ledger.transfer(conn, payer=buyer, receiver=held, amount=own, kind="auction_hold", memo=f"Contract to buy {sale['name']}", period=period)
        except ledger.InsufficientFunds:
            raise _err(f"The contract needs your {prop.money(own)}.") from None
        if sale["mortgage"]:
            if sale["mortgage"] > prop.mortgage_limit(conn, buyer, sale["price"], now, except_sale=sale["id"]):
                ledger.transfer(conn, payer=held, receiver=buyer, amount=own, kind="auction_release", memo="The bank would not lend", period=period)
                conn.execute("UPDATE property_sales SET status = 'failed' WHERE id = %s", (sale["id"],))
                return {"status": "failed", "words": "The bank will no longer lend that much to you: your other borrowing has used it. "
                                                     "The sale fails and your money is back."}
            bank = _one(conn, "SELECT account_id FROM companies WHERE id = %s", (sale["mortgage_bank"],))
            if ledger.balance(conn, bank["account_id"]) < sale["mortgage"]:
                ledger.transfer(conn, payer=held, receiver=buyer, amount=own, kind="auction_release", memo="The bank could not lend", period=period)
                conn.execute("UPDATE property_sales SET status = 'failed' WHERE id = %s", (sale["id"],))
                return {"status": "failed", "words": "The bank could not pay out the mortgage. The sale fails and your money is back."}
            prop.take_mortgage(conn, buyer, sale["mortgage_bank"], sale["property_id"], sale["mortgage"], period, now)
            ledger.transfer(conn, payer=buyer, receiver=held, amount=sale["mortgage"], kind="auction_hold", memo=f"The mortgage paid in: {sale['name']}",
                            period=period)
        _mark(conn, {**sale, "steps": _one(conn, "SELECT steps FROM property_sales WHERE id = %s", (sale["id"],))["steps"]}, "contract",
              {"words": "Signed: the price is held by the Land Registry."})
        # The seller's own mortgage and unpaid tax come out of the price.
        ledger.transfer(conn, payer=held, receiver=sale["seller"], amount=sale["price"], kind="property_sale", memo=f"Sold: {sale['name']}",
                        period=period)
        if p["tax_owed"]:
            ledger.pay_up_to(conn, payer=sale["seller"], receiver=ledger.account_id(conn, ledger.TREASURY), wanted=p["tax_owed"],
                             kind="property_tax", memo=f"Unpaid tax on {sale['name']}, from its sale", period=period)
        if sellers_mortgage is not None:
            bank = _one(conn, "SELECT account_id FROM companies WHERE id = %s", (sellers_mortgage["bank_company_id"],))
            got = ledger.pay_up_to(conn, payer=sale["seller"], receiver=bank["account_id"], wanted=sellers_mortgage["outstanding"],
                                   kind="mortgage_repayment", memo=f"The mortgage on {sale['name']} repaid from its sale", period=period)
            left = sellers_mortgage["outstanding"] - got
            conn.execute("UPDATE mortgages SET outstanding = %s, status = %s WHERE id = %s",
                         (left, "repaid" if left == 0 else "shortfall", sellers_mortgage["id"]))
        fee = register(conn, sale["property_id"], "private", sale["price"], period, now, payer=buyer)
        conn.execute("DELETE FROM property_holdings WHERE property_id = %s", (sale["property_id"],))
        conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, 10000, %s, %s)",
                     (sale["property_id"], buyer, period, sale["price"]))
        conn.execute("UPDATE properties SET tax_owed = 0, book_value = 0 WHERE id = %s", (sale["property_id"],))
        steps = _one(conn, "SELECT steps FROM property_sales WHERE id = %s", (sale["id"],))["steps"]
        steps["registered"] = {"words": f"Registered at the Land Registry (fee {prop.money(fee)})."}
        steps["handover"] = {"words": "Handed over: it is yours."}
        conn.execute("UPDATE property_sales SET status = 'done', steps = %s, done_at = %s WHERE id = %s", (Jsonb(steps), now, sale["id"]))
        headquarters.lost_building(conn, sale["property_id"], buyer, period, now, why=f"The empire sold {sale['name']}, its headquarters' building.")
        return {"status": "done", "fee": fee}


def decline(conn: Connection, account, sale_id: int, now: datetime) -> dict:
    """The buyer declines, or the seller withdraws, any time before the contract. A consent fee already paid is not refunded."""
    with conn.transaction():
        sale = _one(conn, "SELECT * FROM property_sales WHERE id = %s AND (buyer = %s OR seller = %s) FOR UPDATE", (sale_id, account, account))
        if sale is None or sale["status"] not in ("offered", "agreed", "consent"):
            raise _err("There is no such sale waiting.")
        status = "declined" if sale["buyer"] == account else "withdrawn"
        conn.execute("UPDATE property_sales SET status = %s WHERE id = %s", (status, sale["id"]))
        return {"status": status}


def view(conn: Connection, account, now: datetime) -> list[dict]:
    """The private sales this account is part of, as buyer or seller, with the steps done."""
    if not ready(conn):
        return []
    from simulation.property import money
    out = []
    for s in _rows(conn, "SELECT s.*, p.name FROM property_sales s JOIN properties p ON p.id = s.property_id WHERE (s.buyer = %s OR s.seller = %s)"
                         " AND (s.status IN ('offered', 'agreed', 'consent') OR s.done_at > %s) ORDER BY s.id DESC LIMIT 20",
                   (account, account, now - timedelta(days=7))):
        mine = "buyer" if s["buyer"] == account else "seller"
        steps = s["steps"] or {}
        out.append({"id": s["id"], "property_id": s["property_id"], "name": s["name"], "price": s["price"], "role": mine,
                    "status": s["status"], "mortgage": s["mortgage"],
                    "consent_due": s["consent_due"].isoformat() if s["consent_due"] else None,
                    "consent_ready": bool(s["consent_due"] and s["consent_due"] <= now),
                    "steps": [{"step": k, "done": k in steps, "words": steps.get(k, {}).get("words") if mine == "buyer" else None}
                              for k in data.SALE_STEPS if mine == "buyer" or k not in data.SALE_CHECK_STEPS],
                    "price_words": money(s["price"])})
    return out


def check_books(conn: Connection) -> list[str]:
    if not ready(conn):
        return []
    row = _one(conn, "SELECT id FROM ledger_accounts WHERE code = %s", (SALE_HELD,))
    if row and ledger.balance(conn, row["id"]) != 0:
        return [f"The Land Registry holds {ledger.balance(conn, row['id'])} kobo after every sale has finished."]
    return []
