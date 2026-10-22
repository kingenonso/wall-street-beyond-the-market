"""The Auction House (Stage 8; owner suggestion 1, 8 October 2026).

Live, timed auctions. Each runs for a day of real time; a bid in its last five minutes adds five
minutes, so nobody wins by sniping at the last second. Land, buildings and repossessed or seized
property are sold here first; companies, banks and media firms will use the same engine later.

  * A bid names the highest price the bidder will go to: its limit. Nobody else ever sees it. The
    Auction House bids on the bidder's behalf only as far as it needs to: the price shown is one
    step above the next-best limit. A bid at the same limit as another comes second to the earlier.
  * The bidder's own part of the limit is held in cash while the bid stands, and handed back at
    once when it is beaten. A bid can be shared with a partner, who agrees to it first, holds their
    own part and owns that part afterwards; or part can be borrowed from a bank as a mortgage.
  * The seller sets a lowest price (the reserve), which also nobody sees. Below it, nothing is sold.
  * The property companies bid for property sold by anybody else, up to what they think it is worth,
    so there is always a buyer at some price.
  * An empire bids only when its desks have done their checks: Legal Counsel the title, the
    Accountant a valuation, the Risk Manager the top price, the Investment Banker the money. Then the
    head decides, and may not go above the Risk Manager's top price.

Every naira moves through the ledger: held cash sits in the Auction House's own account.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.types.json import Jsonb

import logging

from simulation import clock, ledger, property as prop
from simulation import world_data as data
from simulation.money import BPS
from simulation.property import PropertyError, _one, _rows, _uniform, money

STEPS = {"title": ("lawyer", "Legal Counsel checks the title"), "valuation": ("accountant", "The Accountant values the lot"),
         "limit": ("risk_manager", "The Risk Manager sets the top price"), "money": ("investment_banker", "The Investment Banker arranges the money")}
log = logging.getLogger("wsbm.auctions")
STEPS_BUILDS = tuple(build for build, _ in STEPS.values())


def _state(conn: Connection, now: datetime) -> dict:
    from simulation import careers
    return careers.world_now(conn, now)


def _held() -> str:
    return prop.HELD


def _sale_kind(conn: Connection, account) -> str:
    return "asset_sale" if _one(conn, "SELECT 1 FROM companies WHERE account_id = %s", (account,)) else "property_sale"


def _event(conn: Connection, auction_id: int, now: datetime, price: int | None, words: str) -> None:
    conn.execute("INSERT INTO auction_events (auction_id, at, price, words) VALUES (%s, %s, %s, %s)", (auction_id, now, price, words))


def _open_auction(conn: Connection, property_id: int, seller, reason: str, reserve: int, start: int, fair: int, opens: datetime,
                  period: int) -> int:
    ends = opens + timedelta(hours=data.AUCTION_HOURS)
    row = _one(conn, "INSERT INTO auctions (property_id, seller, reason, opens_at, ends_at, reserve, start_price, fair, period)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (property_id, seller, reason, opens, ends, reserve, max(start, 100), max(fair, 100), period))
    _event(conn, row["id"], opens, None, f"Opens at {money(max(start, 100))}. It ends {clock.to_lagos(ends):%a %d %b, %H:%M} Lagos time,"
                                         f" later if bids come in its last five minutes.")
    return row["id"]


def open_title_auction(conn: Connection, title_id: int, seller, reason: str, reserve: int, start: int, fair: int, opens: datetime,
                       period: int) -> int:
    """A media title up for sale (Stage 10): the same engine, the same rules. The big media houses bid for one the Government sells."""
    ends = opens + timedelta(hours=data.AUCTION_HOURS)
    row = _one(conn, "INSERT INTO auctions (title_id, seller, reason, opens_at, ends_at, reserve, start_price, fair, period)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (title_id, seller, reason, opens, ends, reserve, max(start, 100), max(fair, 100), period))
    _event(conn, row["id"], opens, None, f"Opens at {money(max(start, 100))}. It ends {clock.to_lagos(ends):%a %d %b, %H:%M} Lagos time,"
                                         f" later if bids come in its last five minutes.")
    _computer_title_bids(conn, row["id"], opens)
    return row["id"]


def _computer_title_bids(conn: Connection, auction_id: int, now: datetime) -> None:
    a = _auction(conn, auction_id)
    if _one(conn, "SELECT 1 FROM companies WHERE account_id = %s", (a["seller"],)):
        return
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    buyers = _rows(conn, "SELECT id, account_id FROM companies WHERE sector = 'media' AND listed AND status = 'trading' ORDER BY ticker")
    low, high = data.MEDIA_COMPUTER_BID_BPS
    for b in buyers[:2]:
        limit = a["fair"] * int(low + (high - low) * _uniform(seed, f"title-limit:{auction_id}:{b['id']}", 0)) // BPS
        if limit < a["start_price"] or ledger.balance(conn, b["account_id"]) < limit * 3:
            continue
        conn.execute("INSERT INTO auction_bids (auction_id, bidder, limit_price, computer, at) VALUES (%s, %s, %s, true, %s)",
                     (auction_id, b["account_id"], limit, a["opens_at"]))
    _resolve(conn, _auction(conn, auction_id), now, _state(conn, now)["period"])


def _fair(conn: Connection, property_id: int) -> int:
    p = _one(conn, "SELECT * FROM properties WHERE id = %s", (property_id,))
    return prop.value(p, prop.districts(conn)[p["district_id"]], prop.policy_rate(conn))


# ---------------------------------------------------------------------------
# What goes up for sale
# ---------------------------------------------------------------------------

def list_for_quarter(conn: Connection, period: int, now: datetime, seed: str) -> list[int]:
    """The property companies put a few of their buildings and plots up for sale, spread over the coming week."""
    candidates = _rows(conn, """
        SELECT p.id, h.account_id FROM properties p JOIN property_holdings h ON h.property_id = p.id AND h.share_bps = 10000
        JOIN companies c ON c.account_id = h.account_id
        WHERE NOT EXISTS (SELECT 1 FROM auctions a WHERE a.property_id = p.id AND a.status = 'open')
          AND NOT EXISTS (SELECT 1 FROM headquarters q WHERE q.property_id = p.id)
        ORDER BY p.id""")
    if _one(conn, "SELECT to_regclass('property_leases') IS NOT NULL AS ok")["ok"]:
        leased = {r["property_id"] for r in _rows(conn, "SELECT property_id FROM property_leases WHERE status = 'running'")}
        candidates = [c for c in candidates if c["id"] not in leased]
    candidates.sort(key=lambda c: _uniform(seed, f"list:{c['id']}", period))
    opened = []
    week = timedelta(days=clock.REAL_DAYS_PER_QUARTER)
    count = min(data.AUCTION_LISTINGS_A_QUARTER, len(candidates))
    for n, c in enumerate(candidates[:count]):
        fair = _fair(conn, c["id"])
        low, high = data.AUCTION_RESERVE_BPS
        reserve = fair * int(low + (high - low) * _uniform(seed, f"reserve:{c['id']}", period)) // BPS
        # (Spread over the week, each ending before the next quarter's close.)
        opens = now + (week - timedelta(hours=data.AUCTION_HOURS + 1)) * n / max(count, 1)
        opened.append(_open_auction(conn, c["id"], c["account_id"], "listing", reserve, fair * 7 // 10, fair, opens, period - 1))
    return opened


def force_sale(conn: Connection, property_id: int, reason: str, period: int, now: datetime) -> int | None:
    """A property sold whatever the price: taken by a bank for a mortgage not paid, or by the Government for tax."""
    if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
        return None
    owners = prop.holdings(conn, property_id)
    if not owners:
        return None
    fair = _fair(conn, property_id)
    auction = _open_auction(conn, property_id, owners[0]["account_id"], reason, 0, fair // 2, fair, now, period)
    from simulation import news
    p = _one(conn, "SELECT name FROM properties WHERE id = %s", (property_id,))
    news.publish(conn, period=period + 1, day=6, kind="property_forced_sale", story=f"forced:{auction}",
                 facts={"property": p["name"], "why": "its mortgage was not paid" if reason == "repossession" else "its tax was not paid"})
    _computer_bids(conn, auction, now)
    return auction


def owner_list(conn: Connection, account, property_id: int, reserve: int, now: datetime) -> int:
    """The sole owner puts a property up for auction, with a lowest price nobody else sees."""
    with conn.transaction():
        state = _state(conn, now)
        prop._property(conn, property_id, lock=True)
        if prop.share_of(conn, property_id, account) < BPS:
            raise PropertyError("Only the sole owner of a property may put it up for auction.")
        if _one(conn, "SELECT 1 FROM auctions WHERE property_id = %s AND status = 'open'", (property_id,)):
            raise PropertyError("It is already up for auction.")
        if _one(conn, "SELECT 1 FROM headquarters WHERE property_id = %s", (property_id,)):
            raise PropertyError("This is an empire's headquarters. Move the headquarters first.")
        _free_to_sell(conn, property_id)
        if not isinstance(reserve, int) or reserve < 0:
            raise PropertyError("Name the lowest price you will take, in kobo (0 for none).")
        fair = _fair(conn, property_id)
        auction = _open_auction(conn, property_id, account, "owner", reserve, max(fair // 2, 100), fair, now, state["period"])
        _computer_bids(conn, auction, now)
        return auction


def _free_to_sell(conn: Connection, property_id: int) -> None:
    """(The gap stage.) Not while a dispute freezes it, a private sale of it is under way, it is being developed, or it
    is leased."""
    if _one(conn, "SELECT to_regclass('property_sales') IS NOT NULL AS ok")["ok"] is not True:
        return
    if _one(conn, "SELECT 1 FROM properties WHERE id = %s AND frozen", (property_id,)):
        raise PropertyError("A family dispute over it freezes it: nothing may be done with it until the owner settles it.")
    if _one(conn, "SELECT 1 FROM property_sales WHERE property_id = %s AND status IN ('offered', 'agreed', 'consent')", (property_id,)):
        raise PropertyError("A private sale of it is under way. Withdraw it first.")
    if _one(conn, "SELECT 1 FROM developments WHERE property_id = %s AND status IN ('permit', 'building')", (property_id,)):
        raise PropertyError("It is being developed.")
    if _one(conn, "SELECT 1 FROM property_leases WHERE property_id = %s AND status = 'running'", (property_id,)):
        raise PropertyError("It is leased.")


# ---------------------------------------------------------------------------
# Bidding
# ---------------------------------------------------------------------------

def _auction(conn: Connection, auction_id: int, *, lock: bool = False) -> dict:
    a = _one(conn, "SELECT * FROM auctions WHERE id = %s" + (" FOR UPDATE" if lock else ""), (auction_id,))
    if a is None:
        raise PropertyError("There is no such auction.")
    return a


def minimum(a: dict) -> int:
    if a["price"] is None:
        return a["start_price"]
    return a["price"] + max(a["price"] * data.AUCTION_STEP_BPS // BPS, 100)


def _release(conn: Connection, bid: dict, period: int, why: str) -> None:
    held = ledger.account_id(conn, _held())
    if bid["held"] > 0:
        ledger.transfer(conn, payer=held, receiver=bid["bidder"], amount=bid["held"], kind="auction_release", memo=why, period=period)
    conn.execute("UPDATE auction_bids SET held = 0 WHERE id = %s", (bid["id"],))


def _resolve(conn: Connection, a: dict, now: datetime, period: int) -> None:
    """Work out who leads and at what price, from the limits; hand back the cash behind beaten bids."""
    live = _rows(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND status = 'live' ORDER BY limit_price DESC, id", (a["id"],))
    if not live:
        conn.execute("UPDATE auctions SET leader = NULL, price = NULL WHERE id = %s", (a["id"],))
        return
    top = live[0]
    second = next((b for b in live[1:] if b["bidder"] != top["bidder"]), None)
    floor = a["start_price"] if a["price"] is None else a["price"]
    if second is None:
        price = floor
    else:
        step = max(second["limit_price"] * data.AUCTION_STEP_BPS // BPS, 100)
        price = max(min(top["limit_price"], second["limit_price"] + step), floor)
    price = min(price, top["limit_price"])
    for b in live[1:]:
        conn.execute("UPDATE auction_bids SET status = 'outbid' WHERE id = %s", (b["id"],))
        _release(conn, b, period, "A bid at the Auction House was beaten: its cash is handed back")
    changed = a["leader"] != top["id"] or a["price"] != price
    conn.execute("UPDATE auctions SET leader = %s, price = %s WHERE id = %s", (top["id"], price, a["id"]))
    if changed:
        number = _bidder_number(conn, a["id"], top["bidder"])
        _event(conn, a["id"], now, price, f"Bidder {number} leads at {money(price)}.")


def _bidder_number(conn: Connection, auction_id: int, bidder) -> int:
    """Bidders are shown by number, in the order they first bid: never by name, while the auction runs."""
    order = [r["bidder"] for r in _rows(conn, "SELECT bidder, min(id) AS first FROM auction_bids WHERE auction_id = %s GROUP BY bidder ORDER BY first",
                                        (auction_id,))]
    return order.index(bidder) + 1 if bidder in order else len(order) + 1


def _member_of_seller(conn: Connection, seller, player_id) -> bool:
    """Whether the seller is an empire in which this player holds a seat."""
    return bool(_one(conn, "SELECT 1 FROM empires e JOIN empire_seats s ON s.empire_id = e.id WHERE e.account_id = %s AND s.player_id = %s",
                     (seller, player_id)))


def _seller_is_member(conn: Connection, seller, empire_id: int) -> bool:
    return bool(_one(conn, "SELECT 1 FROM ledger_accounts a JOIN empire_seats s ON s.player_id = a.player_id WHERE a.id = %s AND s.empire_id = %s",
                     (seller, empire_id)))


def place_bid(conn: Connection, account, auction_id: int, limit: int, now: datetime, *, player_id=None, empire_id=None,
              partner=None, mortgage_bank=None, mortgage_bps: int = 0) -> dict:
    with conn.transaction():
        state = _state(conn, now)
        # One bidder's bids are placed one at a time, so two at once cannot each miss the other's mortgage.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('bidder:' || %s::text))", (str(account),))
        a = _auction(conn, auction_id, lock=True)
        if a["status"] != "open" or now < a["opens_at"] or now >= a["ends_at"]:
            raise PropertyError("This auction is not taking bids now.")
        if player_id is not None and empire_id is None and _member_of_seller(conn, a["seller"], player_id):
            raise PropertyError("This is your empire's property. A member does not buy the empire's property for themselves.")
        # (The gap stage.) A property fund's manager, and the manager's empire, never buy the fund's buildings.
        if _one(conn, "SELECT to_regclass('property_funds') IS NOT NULL AS ok")["ok"]:
            fund = _one(conn, "SELECT manager FROM property_funds WHERE account_id = %s", (a["seller"],))
            if fund and fund["manager"] is not None:
                sides = {ledger.player_account_id(conn, fund["manager"])}
                seat = _one(conn, "SELECT e.account_id FROM empire_seats s JOIN empires e ON e.id = s.empire_id WHERE s.player_id = %s",
                            (fund["manager"],))
                if seat:
                    sides.add(seat["account_id"])
                if account in sides or (player_id is not None and str(player_id) == str(fund["manager"])):
                    raise PropertyError("A property fund's manager never buys the fund's buildings, for themselves or their empire.")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise PropertyError("Name the highest price you will go to, in kobo.")
        if a["seller"] == account or (a["property_id"] and prop.share_of(conn, a["property_id"], account) > 0):
            raise PropertyError("You cannot bid for your own property.")
        if a["title_id"] and (partner is not None or mortgage_bps):
            raise PropertyError("A media title is bought outright: no partner, and no mortgage.")
        if a.get("bank_id") and (partner is not None or mortgage_bps):
            raise PropertyError("A bank is bought with your own money: no partner, and no mortgage.")
        if a.get("bank_id") and _one(conn, "SELECT 1 FROM companies WHERE id = %s AND account_id = %s", (a["bank_id"], account)):
            raise PropertyError("A bank does not bid for itself.")
        if limit < minimum(a):
            raise PropertyError(f"The lowest bid now is {money(minimum(a))}.")
        mine = _one(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND bidder = %s AND status = 'live'", (auction_id, account))
        if mine is not None and limit <= mine["limit_price"]:
            raise PropertyError("A new bid must go higher than your own standing bid.")
        partner_row = None
        partner_bps = 0
        if partner is not None:
            partner_row = _one(conn, "SELECT * FROM auction_partners WHERE id = %s AND auction_id = %s AND bidder = %s AND status = 'agreed'",
                               (partner, auction_id, account))
            if partner_row is None:
                raise PropertyError("That partner has not agreed to share this bid.")
            if limit > partner_row["most"]:
                raise PropertyError(f"Your partner agreed to go only as far as {money(partner_row['most'])}.")
            partner_bps = partner_row["partner_bps"]
        if not isinstance(mortgage_bps, int) or not 0 <= mortgage_bps <= 8000:
            raise PropertyError("A mortgage may pay at most 80% of the price.")
        if mortgage_bps and partner_row is not None:
            raise PropertyError("A bid shared with a partner cannot also be paid with a mortgage: the bank wants the whole property as security.")
        if mortgage_bps:
            bank = next((b for b in prop.lending_banks(conn, state["period"]) if str(b["id"]) == str(mortgage_bank)), None)
            if bank is None:
                raise PropertyError("Choose one of the banks.")
            need = limit * mortgage_bps // BPS
            most = prop.mortgage_limit(conn, account, limit, now, except_auction=auction_id)
            if need > most:
                raise PropertyError(f"The bank will lend you at most {money(most)} against a property at this price.")
            if need > bank["room"]:
                raise PropertyError(f"{bank['name']} has no room to lend that much now.")
        if empire_id is not None and a["property_id"]:
            _checks_allow(conn, empire_id, auction_id, limit, mortgage_bank, mortgage_bps)
        if empire_id is not None and (a["title_id"] or a.get("bank_id")):
            # A title has no desk checks; instead the head bids no more than twice what it is worth, and within what they may sign for.
            from simulation import empires
            if limit > a["fair"] * data.MEDIA_RESERVE_MOST_TIMES:
                raise PropertyError(f"For the empire, bid at most twice what the lot is worth: {money(a['fair'] * data.MEDIA_RESERVE_MOST_TIMES)}.")
            seat = empires.seat_of(conn, player_id)
            room = empires.signing_limit(conn, seat) - empires._spent(conn, empire_id, player_id, state["period"]) if seat else 0
            if limit > room:
                raise PropertyError(f"That is more of the empire's money than you may sign for this quarter ({money(max(room, 0))} left).")
        if empire_id is not None:
            # An empire does not buy from its own members: a price it set could carry its money out to one of them.
            if _seller_is_member(conn, a["seller"], empire_id):
                raise PropertyError("The seller is a member of the empire. An empire does not buy from its own members.")
        own = limit * (BPS - partner_bps - mortgage_bps) // BPS
        held = ledger.account_id(conn, _held())
        if mine is not None:
            conn.execute("UPDATE auction_bids SET status = 'withdrawn' WHERE id = %s", (mine["id"],))
            _release(conn, mine, state["period"], "Your standing bid is replaced by a higher one")
        try:
            ledger.transfer(conn, payer=account, receiver=held, amount=own, kind="auction_hold",
                            memo=f"Held for a bid at the Auction House (auction {auction_id})", period=state["period"])
        except ledger.InsufficientFunds:
            raise PropertyError(f"Your part of this bid is {money(own)}, held while it stands. You have not the cash.") from None
        bid = _one(conn, "INSERT INTO auction_bids (auction_id, bidder, player_id, empire_id, limit_price, partner, partner_bps, mortgage_bank,"
                         " mortgage_bps, held, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (auction_id, account, player_id, empire_id, limit, partner_row["partner"] if partner_row else None, partner_bps,
                    mortgage_bank if mortgage_bps else None, mortgage_bps, own, now))
        if a["ends_at"] - now <= timedelta(minutes=data.AUCTION_EXTEND_MINUTES):
            ends = a["ends_at"] + timedelta(minutes=data.AUCTION_EXTEND_MINUTES)
            conn.execute("UPDATE auctions SET ends_at = %s WHERE id = %s", (ends, auction_id))
            _event(conn, auction_id, now, None, f"A late bid: the auction now ends {clock.to_lagos(ends):%H:%M} Lagos time.")
        _resolve(conn, _auction(conn, auction_id), now, state["period"])
        a = _auction(conn, auction_id)
        return {"bid_id": bid["id"], "leading": a["leader"] == bid["id"], "price": a["price"], "ends_at": a["ends_at"]}


def withdraw(conn: Connection, account, bid_id: int, now: datetime) -> None:
    """A bidder may walk away, but not from a bid that leads: the seller is counting on it."""
    with conn.transaction():
        state = _state(conn, now)
        bid = _one(conn, "SELECT b.*, a.leader, a.status AS auction_status FROM auction_bids b JOIN auctions a ON a.id = b.auction_id"
                         " WHERE b.id = %s AND b.bidder = %s FOR UPDATE OF b", (bid_id, account))
        if bid is None or bid["status"] != "live":
            raise PropertyError("There is no standing bid of yours to withdraw.")
        if bid["leader"] == bid["id"]:
            raise PropertyError("Your bid leads. A leading bid cannot be withdrawn.")
        conn.execute("UPDATE auction_bids SET status = 'withdrawn' WHERE id = %s", (bid_id,))
        _release(conn, bid, state["period"], "A bid withdrawn: its cash is handed back")


def ask_partner(conn: Connection, account, auction_id: int, partner_account, partner_bps: int, now: datetime) -> int:
    with conn.transaction():
        a = _auction(conn, auction_id)
        if a["status"] != "open":
            raise PropertyError("This auction is not taking bids now.")
        if a["title_id"] or a.get("bank_id"):
            raise PropertyError("This lot is bought outright: no partner, and no mortgage.")
        if not isinstance(partner_bps, int) or not 500 <= partner_bps <= 9000:
            raise PropertyError("A partner takes between 5% and 90% of the property.")
        if partner_account == account:
            raise PropertyError("Ask somebody else.")
        if not _one(conn, "SELECT 1 FROM ledger_accounts WHERE id = %s AND kind IN ('player', 'empire')", (partner_account,)):
            raise PropertyError("A partner is a player or an empire.")
        row = _one(conn, "INSERT INTO auction_partners (auction_id, bidder, partner, partner_bps, most, at) VALUES (%s, %s, %s, %s, 1, %s)"
                         " ON CONFLICT (auction_id, bidder, partner) DO NOTHING RETURNING id", (auction_id, account, partner_account, partner_bps, now))
        if row is None:
            raise PropertyError("You have already asked them.")
        return row["id"]


def answer_partner(conn: Connection, partner_account, ask_id: int, agree: bool, most: int, now: datetime) -> None:
    """The partner agrees (holding their part of the price they will go to) or refuses."""
    with conn.transaction():
        state = _state(conn, now)
        ask = _one(conn, "SELECT * FROM auction_partners WHERE id = %s AND partner = %s AND status = 'asked' FOR UPDATE", (ask_id, partner_account))
        if ask is None:
            raise PropertyError("There is no such request waiting for you.")
        if not agree:
            conn.execute("UPDATE auction_partners SET status = 'refused' WHERE id = %s", (ask_id,))
            return
        if not isinstance(most, int) or most <= 0:
            raise PropertyError("Name the highest price you will share in.")
        a = _auction(conn, ask["auction_id"], lock=True)
        if a["status"] != "open" or now >= a["ends_at"]:
            raise PropertyError("That auction is not taking bids now.")
        empire = _one(conn, "SELECT id FROM empires WHERE account_id = %s", (partner_account,))
        if empire is not None:
            # An empire that shares a bid has made a bid: the same four checks, the same top price, and never a member's property.
            _checks_allow(conn, empire["id"], a["id"], most, None, 0)
            if _seller_is_member(conn, a["seller"], empire["id"]):
                raise PropertyError("The seller is a member of the empire. An empire does not buy from its own members.")
        held_part = most * ask["partner_bps"] // BPS
        try:
            ledger.transfer(conn, payer=partner_account, receiver=ledger.account_id(conn, _held()), amount=held_part, kind="auction_hold",
                            memo=f"Held as a partner in a bid at the Auction House (auction {ask['auction_id']})", period=state["period"])
        except ledger.InsufficientFunds:
            raise PropertyError(f"Your part is {money(held_part)}, held until the auction ends. You have not the cash.") from None
        conn.execute("UPDATE auction_partners SET status = 'agreed', most = %s, held = %s WHERE id = %s", (most, held_part, ask_id))


def _computer_bids(conn: Connection, auction_id: int, now: datetime) -> None:
    """The property companies bid for property sold by anybody else, up to what they think it is worth."""
    a = _auction(conn, auction_id)
    if _one(conn, "SELECT 1 FROM companies WHERE account_id = %s", (a["seller"],)):
        return                                            # property companies do not buy from each other here
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    owners = {h["account_id"] for h in prop.holdings(conn, a["property_id"])}
    buyers = _rows(conn, "SELECT id, account_id, name FROM companies WHERE sector = 'real_estate' AND status = 'trading' ORDER BY ticker")
    buyers = [b for b in buyers if b["account_id"] not in owners]
    buyers.sort(key=lambda b: _uniform(seed, f"bidder:{auction_id}:{b['id']}", 0))
    low, high = data.COMPUTER_BID_BPS
    for b in buyers[:2]:
        limit = a["fair"] * int(low + (high - low) * _uniform(seed, f"computer-limit:{auction_id}:{b['id']}", 0)) // BPS
        if limit < a["start_price"] or ledger.balance(conn, b["account_id"]) < limit * 3:
            continue
        conn.execute("INSERT INTO auction_bids (auction_id, bidder, limit_price, computer, at) VALUES (%s, %s, %s, true, %s)",
                     (auction_id, b["account_id"], limit, a["opens_at"]))
    _resolve(conn, _auction(conn, auction_id), now, _state(conn, now)["period"])


# ---------------------------------------------------------------------------
# An empire's checks before it bids
# ---------------------------------------------------------------------------

def check(conn: Connection, player_id, auction_id: int, step: str, answer: dict, now: datetime) -> dict:
    """A desk's check on a lot, for its empire. The title check is a search at the lands registry, paid by the empire."""
    from simulation import firm
    with conn.transaction():
        seat, empire = firm._active(conn, player_id)
        if step not in STEPS:
            raise PropertyError("Unknown check.")
        build = STEPS[step][0]
        if seat["build"] != build and not (empire["head_player_id"] == player_id and not firm.desk_members(conn, empire["id"], build)):
            raise PropertyError(f"{STEPS[step][1]}: it is that desk's check.")
        a = _auction(conn, auction_id)
        if a["status"] != "open":
            raise PropertyError("This auction is not taking bids now.")
        if a["title_id"] or a.get("bank_id"):
            raise PropertyError("This lot needs no checks at the lands registry: the head decides the bid.")
        if step == "title":
            before = checks_of(conn, empire["id"], auction_id).get("title")
            if before is not None:
                return before                     # searched once for this lot: no second fee
            found = prop.title_search(conn, empire["account_id"], a["property_id"], now)
            answer = {"clean": found["clean"], "words": found["words"]}
            from simulation import careers, empires
            empires._book(conn, empire["id"], careers.world_now(conn, now)["period"], "Property", "Title search at the lands registry",
                          found["fee"], True, now, kind="fee")
        elif step == "valuation":
            value = answer.get("value")
            if not isinstance(value, int) or value <= 0:
                raise PropertyError("Give the value, in kobo.")
            answer = {"value": value}
        elif step == "limit":
            limit = answer.get("limit")
            if not isinstance(limit, int) or limit <= 0:
                raise PropertyError("Give the top price, in kobo.")
            answer = {"limit": limit}
        else:
            bank, share = answer.get("bank"), answer.get("mortgage_bps", 0)
            if not isinstance(share, int) or not 0 <= share <= data.EMPIRE_MORTGAGE_MOST_BPS:
                raise PropertyError(f"An empire may borrow at most {data.EMPIRE_MORTGAGE_MOST_BPS // 100}% of the price.")
            if share and not _one(conn, "SELECT 1 FROM companies WHERE id::text = %s AND sector = 'banking'", (str(bank),)):
                raise PropertyError("Choose one of the banks.")
            answer = {"bank": str(bank) if share else None, "mortgage_bps": share}
        conn.execute("INSERT INTO property_checks (empire_id, auction_id, step, player_id, answer, at) VALUES (%s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (empire_id, auction_id, step) DO UPDATE SET player_id = EXCLUDED.player_id, answer = EXCLUDED.answer, at = EXCLUDED.at",
                     (empire["id"], auction_id, step, player_id, Jsonb(answer), now))
        return answer


def checks_of(conn: Connection, empire_id: int, auction_id: int) -> dict:
    return {r["step"]: r["answer"] for r in _rows(conn, "SELECT step, answer FROM property_checks WHERE empire_id = %s AND auction_id = %s",
                                                     (empire_id, auction_id))}


def _checks_allow(conn: Connection, empire_id: int, auction_id: int, limit: int, bank, mortgage_bps: int) -> None:
    done = checks_of(conn, empire_id, auction_id)
    missing = [STEPS[s][1] for s in STEPS if s not in done]
    if missing:
        raise PropertyError("Every desk checks a lot before the empire bids. Still to do: " + "; ".join(missing) + ".")
    if limit > done["limit"]["limit"]:
        raise PropertyError(f"The Risk Manager's top price is {money(done['limit']['limit'])}. The head may not go above it.")
    plan = done["money"]
    if (plan["mortgage_bps"] or 0) != mortgage_bps or (mortgage_bps and str(plan["bank"]) != str(bank)):
        raise PropertyError("The bid must be paid as the Investment Banker arranged.")


def empire_bid(conn: Connection, head_id, auction_id: int, limit: int, now: datetime, *, partner=None) -> dict:
    from simulation import firm
    seat, empire = firm._active(conn, head_id)
    if empire["head_player_id"] != head_id:
        raise PropertyError("The head decides the empire's bids.")
    plan = checks_of(conn, empire["id"], auction_id).get("money") or {"bank": None, "mortgage_bps": 0}
    return place_bid(conn, empire["account_id"], auction_id, limit, now, player_id=head_id, empire_id=empire["id"], partner=partner,
                     mortgage_bank=plan["bank"], mortgage_bps=plan["mortgage_bps"] or 0)


# ---------------------------------------------------------------------------
# The end of an auction
# ---------------------------------------------------------------------------

def run(conn: Connection, now: datetime) -> int:
    """Settle every auction whose time is up. Safe to call as often as you like."""
    done = 0
    for a in _rows(conn, "SELECT id FROM auctions WHERE status = 'open' AND ends_at <= %s ORDER BY ends_at", (now,)):
        try:
            with conn.transaction():
                row = _auction(conn, a["id"], lock=True)
                if row["status"] == "open" and row["ends_at"] <= now:
                    _settle(conn, row, now)
                    done += 1
        except Exception:                         # one lot that cannot settle must never stop the others, or the quarter's close
            log.exception("Auction %s could not be settled; it is ended unsold.", a["id"])
            with conn.transaction():
                row = _auction(conn, a["id"], lock=True)
                if row["status"] == "open":
                    _unsold(conn, row, now, _state(conn, now)["period"], "It could not be settled, and is not sold. Every bid's cash is handed back.")
    return done


def _release_partners(conn: Connection, auction_id: int, period: int, keep=None) -> None:
    held = ledger.account_id(conn, _held())
    conn.execute("UPDATE auction_partners SET status = 'released' WHERE auction_id = %s AND status = 'asked'", (auction_id,))
    for p in _rows(conn, "SELECT * FROM auction_partners WHERE auction_id = %s AND status = 'agreed'", (auction_id,)):
        if keep is not None and p["id"] == keep:
            continue
        if p["held"] > 0:
            ledger.transfer(conn, payer=held, receiver=p["partner"], amount=p["held"], kind="auction_release",
                            memo="A partner's share of a bid handed back", period=period)
        conn.execute("UPDATE auction_partners SET status = 'released', held = 0 WHERE id = %s", (p["id"],))


def _unsold(conn: Connection, a: dict, now: datetime, period: int, words: str) -> None:
    for b in _rows(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND status = 'live'", (a["id"],)):
        conn.execute("UPDATE auction_bids SET status = 'lost' WHERE id = %s", (b["id"],))
        _release(conn, b, period, "The auction ended unsold: the bid's cash is handed back")
    _release_partners(conn, a["id"], period)
    conn.execute("UPDATE auctions SET status = 'unsold', settled_at = %s, period = %s WHERE id = %s", (now, period, a["id"]))
    _event(conn, a["id"], now, a["price"], words)


def _settle(conn: Connection, a: dict, now: datetime) -> None:
    if a["title_id"]:
        return _settle_title(conn, a, now)
    if a.get("bank_id"):
        return _settle_bank(conn, a, now)
    state = _state(conn, now)
    period = state["period"]
    held = ledger.account_id(conn, _held())
    p = _one(conn, "SELECT * FROM properties WHERE id = %s FOR UPDATE", (a["property_id"],))
    win = _one(conn, "SELECT * FROM auction_bids WHERE id = %s", (a["leader"],)) if a["leader"] else None
    if win is not None and a["price"] is not None and a["price"] < a["reserve"] <= win["limit_price"]:
        # The leader's top price reaches the seller's lowest price: it is sold at that lowest price. (While the
        # auction runs the price shown never gives the lowest price away; only "lowest price met" shows.)
        a = {**a, "price": a["reserve"]}
    if win is None or a["price"] is None or a["price"] < a["reserve"]:
        _unsold(conn, a, now, period, "It did not reach the seller's lowest price, and is not sold.")
        return
    price = a["price"]
    if not win["computer"] and win["mortgage_bps"]:
        bank_account = _one(conn, "SELECT account_id FROM companies WHERE id = %s", (win["mortgage_bank"],))["account_id"]
        if ledger.balance(conn, bank_account) < price * win["mortgage_bps"] // BPS:
            # The bank cannot pay out the loan it promised: the sale fails, and everybody's cash goes back.
            _unsold(conn, a, now, period, "The winner's bank could not pay out the mortgage. It is not sold.")
            return
    buyer = win["bidder"]
    # (The seller's mortgage, read before the buyer's own new one is written.)
    sellers_mortgage = prop.mortgage_on(conn, p["id"])
    label = f"{p['name']} (auction {a['id']})"
    partner = _one(conn, "SELECT * FROM auction_partners WHERE auction_id = %s AND bidder = %s AND partner = %s AND status = 'agreed'",
                   (a["id"], buyer, win["partner"])) if win["partner"] else None
    partner_part = price * win["partner_bps"] // BPS if partner else 0
    mortgage_part = price * win["mortgage_bps"] // BPS
    own_part = price - partner_part - mortgage_part
    # 1. The money comes into the Auction House's account: the buyer's held cash, the partner's, the bank's loan.
    if win["computer"]:
        try:
            ledger.transfer(conn, payer=buyer, receiver=held, amount=price, kind="capital_spending", memo=f"Bought at auction: {label}", period=period)
        except ledger.InsufficientFunds:
            _unsold(conn, a, now, period, "The winner could not pay. It is not sold.")
            return
    else:
        if win["held"] < own_part:
            # (A kobo or two of rounding between the hold, worked out on the limit, and the price.)
            try:
                ledger.transfer(conn, payer=buyer, receiver=held, amount=own_part - win["held"], kind="auction_hold",
                                memo=f"The last of the price: {label}", period=period)
            except ledger.InsufficientFunds:
                _unsold(conn, a, now, period, "The winner could not pay the last of the price. It is not sold.")
                return
            win = {**win, "held": own_part}
        if win["held"] > own_part:
            ledger.transfer(conn, payer=held, receiver=buyer, amount=win["held"] - own_part, kind="auction_release",
                            memo=f"What was held above the winning price: {label}", period=period)
        if mortgage_part:
            prop.take_mortgage(conn, buyer, win["mortgage_bank"], p["id"], mortgage_part, period, now)
            ledger.transfer(conn, payer=buyer, receiver=held, amount=mortgage_part, kind="auction_hold",
                            memo=f"The mortgage paid in: {label}", period=period)
        if partner:
            if partner["held"] > partner_part:
                ledger.transfer(conn, payer=held, receiver=partner["partner"], amount=partner["held"] - partner_part, kind="auction_release",
                                memo=f"A partner's share held above the winning price: {label}", period=period)
            conn.execute("UPDATE auction_partners SET status = 'used', held = 0 WHERE id = %s", (partner["id"],))
    _release_partners(conn, a["id"], period, keep=partner["id"] if partner else None)
    conn.execute("UPDATE auction_bids SET status = 'won', held = 0 WHERE id = %s", (win["id"],))
    for b in _rows(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND status = 'live'", (a["id"],)):
        conn.execute("UPDATE auction_bids SET status = 'lost' WHERE id = %s", (b["id"],))
        _release(conn, b, period, "The auction ended: the bid's cash is handed back")
    # 2. The sellers are paid, each for their share, after what they owe on it: its mortgage and its unpaid tax.
    owners = prop.holdings(conn, p["id"])
    treasury = ledger.account_id(conn, ledger.TREASURY)
    tax_owed = p["tax_owed"]
    total_bps = sum(h["share_bps"] for h in owners) or BPS
    paid_out = 0
    for n, h in enumerate(owners):
        # The last owner takes what rounding leaves, so the Auction House keeps not a kobo.
        part = price * h["share_bps"] // total_bps if n < len(owners) - 1 else price - paid_out
        paid_out += part
        if part <= 0:
            continue
        kind = _sale_kind(conn, h["account_id"])
        ledger.transfer(conn, payer=held, receiver=h["account_id"], amount=part, kind=kind, memo=f"Sold at auction: {label}", period=period)
        if kind == "asset_sale":
            company = _one(conn, "SELECT id FROM companies WHERE account_id = %s", (h["account_id"],))
            # (Never more than what its buildings and machines stand at in its books.)
            fixed = _one(conn, "SELECT fixed_assets FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company["id"],))
            book = min(p["book_value"] * h["share_bps"] // BPS, max(fixed["fixed_assets"] * 9 // 10, 0) if fixed else 0)
            conn.execute("INSERT INTO company_asset_sales (company_id, asset_id, property_id, period, book, proceeds, at) VALUES (%s, NULL, %s, %s, %s, %s, %s)",
                         (company["id"], p["id"], period, book, part, now))
        tax_part = tax_owed * h["share_bps"] // BPS
        if tax_part:
            ledger.pay_up_to(conn, payer=h["account_id"], receiver=treasury, wanted=tax_part, kind="property_tax",
                             memo=f"Unpaid tax on {p['name']}, from its sale", period=period)
    m = sellers_mortgage
    if m is not None:
        bank = _one(conn, "SELECT account_id, name FROM companies WHERE id = %s", (m["bank_company_id"],))
        got = ledger.pay_up_to(conn, payer=m["borrower"], receiver=bank["account_id"], wanted=m["outstanding"], kind="mortgage_repayment",
                               memo=f"The mortgage on {p['name']} repaid from its sale", period=period)
        left = m["outstanding"] - got
        done = "repossessed" if a["reason"] == "repossession" else "repaid"
        conn.execute("UPDATE mortgages SET outstanding = %s, status = %s WHERE id = %s", (left, done if left == 0 else "shortfall", m["id"]))
    # 3. The property changes hands.
    conn.execute("DELETE FROM property_holdings WHERE property_id = %s", (p["id"],))
    winner_bps = BPS - (win["partner_bps"] if partner else 0)
    conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, %s, %s, %s)",
                 (p["id"], buyer, winner_bps, period, price * winner_bps // BPS))
    if partner:
        conn.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period, paid) VALUES (%s, %s, %s, %s, %s)",
                     (p["id"], partner["partner"], win["partner_bps"], period, partner_part))
    conn.execute("UPDATE properties SET tax_owed = 0, book_value = %s, upkeep = true WHERE id = %s",
                 (price if win["computer"] else 0, p["id"]))
    conn.execute("UPDATE auctions SET status = 'sold', settled_at = %s, period = %s, price = %s WHERE id = %s", (now, period, price, a["id"]))
    _event(conn, a["id"], now, price, f"Sold for {money(price)}.")
    # The Land Registry records the transfer; the buyer pays its fee.
    from simulation import conveyancing
    conveyancing.register(conn, p["id"], "auction", price, period, now, payer=buyer)
    # 4. A building sold from under an empire's headquarters (a forced sale): the headquarters must move.
    from simulation import headquarters
    headquarters.lost_building(conn, p["id"], buyer, period, now)


def _settle_title(conn: Connection, a: dict, now: datetime) -> None:
    """A media title's auction ends: the winner pays, the seller is paid, the title changes hands."""
    from simulation import media, news
    period = _state(conn, now)["period"]
    held = ledger.account_id(conn, _held())
    t = media.title(conn, a["title_id"], lock=True)
    win = _one(conn, "SELECT * FROM auction_bids WHERE id = %s", (a["leader"],)) if a["leader"] else None
    if win is not None and a["price"] is not None and a["price"] < a["reserve"] <= win["limit_price"]:
        a = {**a, "price": a["reserve"]}
    if win is None or a["price"] is None or a["price"] < a["reserve"] or t["owner_account"] != a["seller"]:
        _unsold(conn, a, now, period, "It did not reach the seller's lowest price, and is not sold.")
        return
    price, buyer, label = a["price"], win["bidder"], f"{t['name']} (auction {a['id']})"
    if win["computer"]:
        try:
            ledger.transfer(conn, payer=buyer, receiver=held, amount=price, kind="capital_spending", memo=f"Bought at auction: {label}", period=period)
        except ledger.InsufficientFunds:
            _unsold(conn, a, now, period, "The winner could not pay. It is not sold.")
            return
    else:
        if win["held"] < price:
            try:
                ledger.transfer(conn, payer=buyer, receiver=held, amount=price - win["held"], kind="auction_hold",
                                memo=f"The last of the price: {label}", period=period)
            except ledger.InsufficientFunds:
                _unsold(conn, a, now, period, "The winner could not pay the last of the price. It is not sold.")
                return
        elif win["held"] > price:
            ledger.transfer(conn, payer=held, receiver=buyer, amount=win["held"] - price, kind="auction_release",
                            memo=f"What was held above the winning price: {label}", period=period)
    conn.execute("UPDATE auction_bids SET status = 'won', held = 0 WHERE id = %s", (win["id"],))
    for b in _rows(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND status = 'live'", (a["id"],)):
        conn.execute("UPDATE auction_bids SET status = 'lost' WHERE id = %s", (b["id"],))
        _release(conn, b, period, "The auction ended: the bid's cash is handed back")
    ledger.transfer(conn, payer=held, receiver=a["seller"], amount=price, kind="title_sale",
                    memo=f"Sold at auction: {label}", period=period)
    media.sold(conn, t["id"], buyer, price, period)
    conn.execute("UPDATE auctions SET status = 'sold', settled_at = %s, period = %s, price = %s WHERE id = %s", (now, period, price, a["id"]))
    _event(conn, a["id"], now, price, f"Sold for {money(price)}.")
    w = _state(conn, now)
    news.publish(conn, period=w["period"], day=w["day"], kind="title_sold", story=f"title-sold:{a['id']}",
                 facts={"title": t["name"], "buyer": media.owner_name(conn, media.title(conn, t["id"])), "price": news.money_words(price)})


def title_view(conn: Connection, now: datetime, viewer=None) -> list[dict]:
    """Open and recent auctions of media titles. Never a reserve, a limit (except the viewer's own), or a bidder's name."""
    from simulation import media
    out = []
    for a in _rows(conn, "SELECT * FROM auctions WHERE title_id IS NOT NULL AND (status = 'open' OR settled_at > %s)"
                         " ORDER BY status = 'open' DESC, ends_at", (now - timedelta(days=2),)):
        t = media.title(conn, a["title_id"])
        mine = _one(conn, "SELECT id, limit_price, status FROM auction_bids WHERE auction_id = %s AND bidder = %s ORDER BY id DESC LIMIT 1",
                    (a["id"], viewer)) if viewer else None
        events = _rows(conn, "SELECT at, price, words FROM auction_events WHERE auction_id = %s AND at <= %s ORDER BY id DESC LIMIT 8", (a["id"], now))
        out.append({"id": a["id"], "title": {"id": t["id"], "name": t["name"], "city": t["city"], "kind": t["kind"], "audience": t["audience"]},
                    "opens_at": a["opens_at"], "ends_at": a["ends_at"],
                    "status": a["status"] if now >= a["opens_at"] or a["status"] != "open" else "coming",
                    "start_price": a["start_price"], "price": a["price"], "minimum": minimum(a), "fair": a["fair"],
                    "lowest_price_met": _reserve_met(conn, a),
                    "bidders": _one(conn, "SELECT count(DISTINCT bidder) AS n FROM auction_bids WHERE auction_id = %s", (a["id"],))["n"],
                    "you_lead": bool(mine and a["leader"] == mine["id"]), "your_limit": mine["limit_price"] if mine else None,
                    "your_status": mine["status"] if mine else None, "your_bid_id": mine["id"] if mine else None,
                    "events": [{"at": e["at"], "price": e["price"], "words": e["words"]} for e in events]})
    return out


# ---------------------------------------------------------------------------
# What players see
# ---------------------------------------------------------------------------

def _reserve_met(conn: Connection, a: dict) -> bool:
    """Whether the leading bid's top price reaches the seller's lowest price: a yes or no, never the price itself."""
    if not a["leader"]:
        return False
    top = _one(conn, "SELECT limit_price FROM auction_bids WHERE id = %s", (a["leader"],))
    return bool(top and top["limit_price"] >= a["reserve"])


def view(conn: Connection, now: datetime, viewer=None, empire_id=None) -> dict:
    """Open and recent auctions. Never a reserve, a limit (except the viewer's own), or a bidder's name."""
    rate = prop.policy_rate(conn)
    ds = prop.districts(conn)
    out = []
    for a in _rows(conn, "SELECT * FROM auctions WHERE property_id IS NOT NULL AND (status = 'open' OR settled_at > %s)"
                         " ORDER BY status = 'open' DESC, ends_at", (now - timedelta(days=2),)):
        p = _one(conn, "SELECT * FROM properties WHERE id = %s", (a["property_id"],))
        d = ds[p["district_id"]]
        mine = _one(conn, "SELECT id, limit_price, status, mortgage_bps, partner_bps FROM auction_bids WHERE auction_id = %s AND bidder = %s"
                          " ORDER BY id DESC LIMIT 1", (a["id"], viewer)) if viewer else None
        events = _rows(conn, "SELECT at, price, words FROM auction_events WHERE auction_id = %s AND at <= %s ORDER BY id DESC LIMIT 8", (a["id"], now))
        out.append({
            "id": a["id"], "property": prop.public_property(conn, p, d, rate, viewer=viewer), "reason": a["reason"],
            "opens_at": a["opens_at"], "ends_at": a["ends_at"], "status": a["status"] if now >= a["opens_at"] or a["status"] != "open" else "coming",
            "start_price": a["start_price"], "price": a["price"], "minimum": minimum(a), "fair": a["fair"],
            "lowest_price_met": _reserve_met(conn, a),
            "bidders": _one(conn, "SELECT count(DISTINCT bidder) AS n FROM auction_bids WHERE auction_id = %s", (a["id"],))["n"],
            "you_lead": bool(mine and a["leader"] == mine["id"]), "your_limit": mine["limit_price"] if mine else None,
            "your_status": mine["status"] if mine else None, "your_bid_id": mine["id"] if mine else None,
            "events": [{"at": e["at"], "price": e["price"], "words": e["words"]} for e in events],
            "checks": ({s: (s in checks_of(conn, empire_id, a["id"])) for s in STEPS} if empire_id else None),
        })
    return {"auctions": out, "now": now}


# ---------------------------------------------------------------------------
# Banks (the crises stage): a closed bank sold to whoever puts in the most new money; a bank in public hands sold again
# ---------------------------------------------------------------------------

def open_bank_auction(conn: Connection, resolution_id: int, now: datetime, period: int) -> int:
    """A bank the Central Bank closed goes to the Auction House. The price is the new money the buyer puts INTO the bank
    (never to anybody else); the buyer owns 95% of it afterwards. The lowest bid is the new money it needs."""
    from simulation import deposits
    r = _one(conn, "SELECT * FROM bank_resolutions WHERE id = %s", (resolution_id,))
    fund = ledger.account_id(conn, deposits.GUARANTEE_FUND)
    need = max(r["capital_needed"], 100)
    ends = now + timedelta(hours=data.AUCTION_HOURS)
    row = _one(conn, "INSERT INTO auctions (bank_id, seller, reason, opens_at, ends_at, reserve, start_price, fair, period)"
                     " VALUES (%s, %s, 'rescue', %s, %s, %s, %s, %s, %s) RETURNING id",
               (r["company_id"], fund, now, ends, need, need, need, period))
    conn.execute("UPDATE bank_resolutions SET auction_id = %s WHERE id = %s", (row["id"], resolution_id))
    _event(conn, row["id"], now, None, f"A closed bank for sale. The lowest bid is {money(need)} of new money, paid into the bank."
                                       f" It ends {clock.to_lagos(ends):%a %d %b, %H:%M} Lagos time, later if bids come in its last five minutes.")
    _computer_bank_bids(conn, row["id"], now)
    return row["id"]


def open_bank_resale(conn: Connection, resolution_id: int, now: datetime, period: int) -> int:
    """A bank a year in public hands: the Deposit Guarantee Fund sells its shares. Whatever it fetches repays the Treasury."""
    from simulation import deposits
    r = _one(conn, "SELECT * FROM bank_resolutions WHERE id = %s", (resolution_id,))
    fund = ledger.account_id(conn, deposits.GUARANTEE_FUND)
    filed = _one(conn, "SELECT total_equity FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (r["company_id"],))
    asset = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (r["company_id"],))["share_asset"]
    held = ledger.balance(conn, fund, asset)
    total = ledger.amount_in_existence(conn, asset)
    book = max((filed["total_equity"] if filed else 0) * held // max(total, 1), 100)
    reserve = book * 7 // 10
    ends = now + timedelta(hours=data.AUCTION_HOURS)
    row = _one(conn, "INSERT INTO auctions (bank_id, seller, reason, opens_at, ends_at, reserve, start_price, fair, period)"
                     " VALUES (%s, %s, 'public_sale', %s, %s, %s, %s, %s, %s) RETURNING id",
               (r["company_id"], fund, now, ends, reserve, max(reserve // 2, 100), book, period))
    _event(conn, row["id"], now, None, f"The Deposit Guarantee Fund sells its shares in a bank it rescued. Bids open at {money(max(reserve // 2, 100))}.")
    _computer_bank_bids(conn, row["id"], now)
    return row["id"]


def _computer_bank_bids(conn: Connection, auction_id: int, now: datetime) -> None:
    """Sound banks bid for a closed one: up to 100%-130% of the new money it needs (of its worth, when the fund sells)."""
    from simulation import crisis
    a = _auction(conn, auction_id)
    seed = _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]
    trust = crisis.trust_now(conn)
    low, high = data.RESCUE_COMPUTER_BID_BPS
    base = a["reserve"] if a["reason"] == "rescue" else a["fair"]
    bidders = []
    for b in _rows(conn, "SELECT c.id, c.account_id, c.ticker, r.total_equity FROM companies c JOIN bank_deposits d ON d.company_id = c.id"
                         " JOIN LATERAL (SELECT total_equity FROM company_results WHERE company_id = c.id ORDER BY period DESC LIMIT 1) r ON true"
                         " WHERE c.id <> %s AND c.status = 'trading' ORDER BY r.total_equity DESC", (a["bank_id"],)):
        t = trust.get(b["id"], {})
        if t.get("state", "calm") != "calm" or (t.get("score") or 0) < data.CONFIDENCE_WARNING:
            continue
        limit = base * int(low + (high - low) * _uniform(seed, f"bank-limit:{auction_id}:{b['id']}", 0)) // BPS
        if b["total_equity"] < limit * 2 or ledger.balance(conn, b["account_id"]) < limit * 2:
            continue
        bidders.append((b, limit))
    for b, limit in bidders[:2]:
        conn.execute("INSERT INTO auction_bids (auction_id, bidder, limit_price, computer, at) VALUES (%s, %s, %s, true, %s)",
                     (auction_id, b["account_id"], limit, a["opens_at"]))
    _resolve(conn, _auction(conn, auction_id), now, _state(conn, now)["period"])


def _settle_bank(conn: Connection, a: dict, now: datetime) -> None:
    from simulation import crisis, deposits
    period = _state(conn, now)["period"]
    held = ledger.account_id(conn, _held())
    r = _one(conn, "SELECT * FROM bank_resolutions WHERE company_id = %s AND status IN ('open', 'public') ORDER BY id DESC LIMIT 1",
             (a["bank_id"],))
    win = _one(conn, "SELECT * FROM auction_bids WHERE id = %s", (a["leader"],)) if a["leader"] else None
    if win is not None and a["price"] is not None and a["price"] < a["reserve"] <= win["limit_price"]:
        a = {**a, "price": a["reserve"]}
    sold = win is not None and a["price"] is not None and a["price"] >= a["reserve"] and r is not None
    paid = False
    if sold:
        price, buyer = a["price"], win["bidder"]
        try:
            if win["computer"]:
                # A bank buying another pays from its cash: it is an investment in another company's shares.
                ledger.transfer(conn, payer=buyer, receiver=held, amount=price, kind="takeover_reserve", period=period,
                                memo=f"Bought at auction: a bank (auction {a['id']})")
            elif win["held"] < price:
                ledger.transfer(conn, payer=buyer, receiver=held, amount=price - win["held"], kind="auction_hold", period=period,
                                memo=f"The last of the price: a bank (auction {a['id']})")
            elif win["held"] > price:
                ledger.transfer(conn, payer=held, receiver=buyer, amount=win["held"] - price, kind="auction_release", period=period,
                                memo=f"What was held above the winning price: a bank (auction {a['id']})")
            paid = True
        except ledger.InsufficientFunds:
            paid = False
    if not (sold and paid):
        _unsold(conn, a, now, period, "It did not reach the lowest price, and is not sold.")
        if r is not None and a["reason"] == "rescue" and r["status"] == "open":
            crisis.public_hands(conn, r["id"], period, now)
        elif r is not None and a["reason"] == "public_sale":
            conn.execute("UPDATE bank_resolutions SET resale_period = %s WHERE id = %s", (period + data.PUBLIC_RESALE_QUARTERS, r["id"]))
        return
    conn.execute("UPDATE auction_bids SET status = 'won', held = 0 WHERE id = %s", (win["id"],))
    for b in _rows(conn, "SELECT * FROM auction_bids WHERE auction_id = %s AND status = 'live'", (a["id"],)):
        conn.execute("UPDATE auction_bids SET status = 'lost' WHERE id = %s", (b["id"],))
        _release(conn, b, period, "The auction ended: the bid's cash is handed back")
    bank = _one(conn, "SELECT * FROM companies WHERE id = %s", (a["bank_id"],))
    if a["reason"] == "rescue":
        # The new money goes into the bank itself, for new shares.
        ledger.transfer(conn, payer=held, receiver=bank["account_id"], amount=price, kind="share_issue", period=period,
                        memo=f"{bank['name']}: new money from its new owner, for new shares")
        crisis.resolved(conn, r["id"], buyer=buyer, paid=price, how="sold", period=period, now=now)
    else:
        fund = ledger.account_id(conn, deposits.GUARANTEE_FUND)
        shares = ledger.balance(conn, fund, bank["share_asset"])
        ledger.post(conn, kind="share_sale", period=period, memo=f"{bank['name']}: the Deposit Guarantee Fund's shares, sold at auction",
                    legs=[ledger.Leg(held, -price), ledger.Leg(fund, price),
                          ledger.Leg(fund, -shares, bank["share_asset"]), ledger.Leg(buyer, shares, bank["share_asset"])])
        crisis.resold(conn, r["id"], buyer, price, period, now)
    conn.execute("UPDATE auctions SET status = 'sold', settled_at = %s, period = %s, price = %s WHERE id = %s", (now, period, price, a["id"]))
    _event(conn, a["id"], now, price, f"Sold for {money(price)}.")


def bank_view(conn: Connection, now: datetime, viewer=None) -> list[dict]:
    """Open and recent auctions of banks. Never a reserve, a limit (except the viewer's own), or a bidder's name."""
    if not _one(conn, "SELECT to_regclass('bank_resolutions') IS NOT NULL AS ok")["ok"]:
        return []
    out = []
    for a in _rows(conn, "SELECT a.*, c.name, c.ticker FROM auctions a JOIN companies c ON c.id = a.bank_id WHERE a.bank_id IS NOT NULL"
                         " AND (a.status = 'open' OR a.settled_at > %s) ORDER BY a.status = 'open' DESC, a.ends_at", (now - timedelta(days=2),)):
        mine = _one(conn, "SELECT id, limit_price, status FROM auction_bids WHERE auction_id = %s AND bidder = %s ORDER BY id DESC LIMIT 1",
                    (a["id"], viewer)) if viewer else None
        events = _rows(conn, "SELECT at, price, words FROM auction_events WHERE auction_id = %s AND at <= %s ORDER BY id DESC LIMIT 8", (a["id"], now))
        out.append({"id": a["id"], "bank": {"name": a["name"], "ticker": a["ticker"]}, "kind": a["reason"],
                    "opens_at": a["opens_at"], "ends_at": a["ends_at"], "status": a["status"],
                    "start_price": a["start_price"], "price": a["price"], "minimum": minimum(a),
                    "lowest_price_met": _reserve_met(conn, a),
                    "bidders": _one(conn, "SELECT count(DISTINCT bidder) AS n FROM auction_bids WHERE auction_id = %s", (a["id"],))["n"],
                    "you_lead": bool(mine and a["leader"] == mine["id"]), "your_limit": mine["limit_price"] if mine else None,
                    "your_status": mine["status"] if mine else None, "your_bid_id": mine["id"] if mine else None,
                    "events": [{"at": e["at"], "price": e["price"], "words": e["words"]} for e in events]})
    return out
