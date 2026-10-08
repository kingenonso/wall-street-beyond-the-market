"""Companies using the market (design document, section 11).

  share offers   a company sells new shares: its first sale to the public (an IPO),
                 a later sale to anybody, or a rights issue (offered to existing
                 owners first, in proportion to what they hold)
  share splits   each share becomes several, each worth less; nobody gains or loses
  votes          owners decide large matters; votes follow shares held
  takeovers      one company offers to buy another's shares from their owners,
                 with the target board's blessing (agreed) or over its head (hostile)
  integration    after a takeover the two businesses are joined; the planned
                 savings can succeed or fail

Everything is announced as one quarter closes and settled as the next one
closes. In between, players decide: apply for shares, vote, accept or refuse a
bid. Settling at the close matters: it is the one moment when the computer-run
investors have no orders on the exchange and every company's worth is about to
be worked out afresh, so nobody can trade against a stale price.

Every naira and every share moves through the ledger. Cash and shares a player
commits are held by the exchange until the matter is settled.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import bonds, clock, events, exchange, ledger, news
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS

FINANCIAL = ("banking", "insurance")
GOOD_RATINGS = ("AAA", "AA", "A", "BBB")
PROJECTS = {
    "power": ("a solar plant", True), "agriculture": ("an irrigation scheme", True), "oil_gas": ("a gas processing plant", False),
    "cement": ("a new kiln line", False), "telecoms": ("a fibre network", False), "transport": ("a rail freight terminal", True),
    "real_estate": ("a housing estate", False), "manufacturing": ("a new factory", False), "consumer": ("a new bottling plant", False),
    "media": ("a broadcast centre", False),
}


class CorporateError(Exception):
    """Something a player asked for was refused. The message is written for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchone()


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def notice(conn: Connection, period: int, company_id, kind: str, title: str, body: str, now: datetime) -> None:
    conn.execute("INSERT INTO market_notices (period, company_id, kind, title, body, posted_at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (period, company_id, kind, title, body, now))


def _open(conn: Connection, now: datetime) -> None:
    """Nothing can be changed in the moments after a quarter has ended and before its books are closed."""
    if not bonds.books_open(conn, now):
        raise CorporateError(bonds.CLOSING)


def _player(conn: Connection, account) -> None:
    owner = _one(conn, "SELECT kind FROM ledger_accounts WHERE id = %s", (account,))
    if owner is None or owner["kind"] != "player":
        raise CorporateError("That account cannot take part.")


def _owners(conn: Connection, company_id) -> dict:
    return {r["account_id"]: r["shares"] for r in _rows(
        conn, "SELECT account_id, shares FROM share_owners WHERE company_id = %s ORDER BY account_id", (company_id,))}


def _investors(conn: Connection) -> dict:
    return {r["code"]: r["id"] for r in _rows(
        conn, "SELECT code, id FROM ledger_accounts WHERE code = ANY(%s)",
        ([ledger.INVESTORS_FOUNDERS, ledger.INVESTORS_INSTITUTIONS, ledger.INVESTORS_PUBLIC],))}


def _company(conn: Connection, company_id) -> dict:
    return _one(conn, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.id = %s", (company_id,))


def _market_price(conn: Connection, company_id) -> int | None:
    row = _one(conn, "SELECT coalesce(last_price, reference_price) AS price FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["price"] if row else None


def _after_trade(conn: Connection) -> int:
    return _one(conn, "SELECT coalesce(max(id), 0) AS id FROM market_trades")["id"]


def _words(count: int) -> str:
    for size, word in ((10**9, "billion"), (10**6, "million")):
        if count >= size:
            return f"{count / size:.1f} {word}".replace(".0 ", " ")
    return f"{count:,}"


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------

def open_vote(conn: Connection, company_id, *, subject: str, question: str, explanation: str, board: str, period: int,
              detail: dict) -> int:
    return _one(
        conn, "INSERT INTO company_votes (company_id, subject, question, explanation, board, detail, opens_period, closes_period)"
              " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (company_id, subject, question, explanation, board, Jsonb(detail), period, period + 1))["id"]


def cast_vote(conn: Connection, *, account: UUID | str, vote_id: int, choice: str, now: datetime) -> None:
    """Vote for or against. It can be changed until the vote is counted. It counts for as many
    shares as the voter holds at the moment of counting."""
    if choice not in ("for", "against"):
        raise CorporateError("A vote is for or against.")
    with conn.transaction():
        _open(conn, now)
        _player(conn, account)
        vote = _one(conn, "SELECT * FROM company_votes WHERE id = %s FOR UPDATE", (vote_id,))
        if vote is None or vote["status"] != "open":
            raise CorporateError("That vote is not open.")
        if not _owners(conn, vote["company_id"]).get(UUID(str(account)), 0):
            raise CorporateError("You hold no shares in this company, so you have no vote.")
        conn.execute("INSERT INTO vote_ballots (vote_id, account_id, choice, cast_at) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (vote_id, account_id) DO UPDATE SET choice = EXCLUDED.choice, cast_at = EXCLUDED.cast_at",
                     (vote_id, account, choice, now))


def _tally(conn: Connection, vote: dict, who: dict) -> dict:
    """How a vote stands: each kind of owner's shares for and against, by the shares held now."""
    owners = _owners(conn, vote["company_id"])
    ballots = {r["account_id"]: r["choice"] for r in _rows(conn, "SELECT account_id, choice FROM vote_ballots WHERE vote_id = %s", (vote["id"],))}
    kinds = {r["id"]: r["kind"] for r in _rows(conn, "SELECT id, kind FROM ledger_accounts WHERE id = ANY(%s)", (list(owners),))}
    tally = {"Founders": [0, 0], "Pension funds": [0, 0], "Small investors": [0, 0], "Players": [0, 0], "Other companies": [0, 0]}
    with_board = 0 if vote["board"] == "for" else 1
    for account, shares in owners.items():
        if account == who[ledger.INVESTORS_FOUNDERS]:
            tally["Founders"][with_board] += shares                       # founders sit on the board
        elif account == who[ledger.INVESTORS_INSTITUTIONS]:
            tally["Pension funds"][0 if vote["detail"].get("institutions", "for") == "for" else 1] += shares
        elif account == who[ledger.INVESTORS_PUBLIC]:
            follow = shares * data.SMALL_INVESTORS_WITH_BOARD_BPS // BPS   # most small investors follow the board
            tally["Small investors"][with_board] += follow
            tally["Small investors"][1 - with_board] += shares - follow
        elif kinds.get(account) == "company":
            tally["Other companies"][with_board] += shares
        elif account in ballots:
            tally["Players"][0 if ballots[account] == "for" else 1] += shares
    return tally


def _count_votes(conn: Connection, period: int, now: datetime) -> None:
    who = _investors(conn)
    for vote in _rows(conn, "SELECT * FROM company_votes WHERE status = 'open' AND closes_period <= %s ORDER BY id FOR UPDATE", (period,)):
        tally = _tally(conn, vote, who)
        votes_for, votes_against = sum(t[0] for t in tally.values()), sum(t[1] for t in tally.values())
        passed = votes_for > votes_against
        # What players hold between them is not shown on its own while they are few.
        if _one(conn, "SELECT count(*) AS n FROM players")["n"] < 20:
            players = tally.pop("Players")
            tally["Small investors"] = [tally["Small investors"][0] + players[0], tally["Small investors"][1] + players[1]]
        conn.execute("UPDATE company_votes SET status = %s, votes_for = %s, votes_against = %s, tally = %s, closed_at = %s WHERE id = %s",
                     ("passed" if passed else "failed", votes_for, votes_against,
                      Jsonb({k: {"for": v[0], "against": v[1]} for k, v in tally.items() if v[0] or v[1]}), now, vote["id"]))
        company = _company(conn, vote["company_id"])
        support = votes_for * BPS // (votes_for + votes_against) if votes_for + votes_against else 0
        outcome = "approved" if passed else "rejected"
        notice(conn, period, company["id"], "vote_result", f"{company['name']}: shareholders' vote {outcome}",
               f"{vote['question']} {outcome.capitalize()}: {_percent(support)} of the votes cast were in favour.", now)
        news.publish(conn, period=period + 1, day=2, kind="vote_result", story=f"vote:{vote['id']}",
                     facts={"company": company["name"], "ticker": company["ticker"], "matter": vote["detail"].get("matter", "its board's proposal"),
                            "outcome": outcome, "support": _percent(support)}, tickers=[company["ticker"]])


def _vote_passed(conn: Connection, vote_id) -> bool:
    return vote_id is None or _one(conn, "SELECT status FROM company_votes WHERE id = %s", (vote_id,))["status"] == "passed"


# ---------------------------------------------------------------------------
# Share offers
# ---------------------------------------------------------------------------

def announce_offer(conn: Connection, company: dict, *, kind: str, price: int, shares: int, period: int, reason: str,
                   now: datetime, rights: tuple[int, int] | None = None, institutions: str = "for") -> int:
    """Announce a sale of new shares. It closes, and the shares are issued, when the next quarter closes."""
    in_issue = ledger.amount_in_existence(conn, company["share_asset"])
    vote_id = None
    amount = _big(price * shares)
    if kind == "rights":
        terms = f"{news.number_word(rights[0])} new share{'s' if rights[0] != 1 else ''} for every {news.number_word(rights[1])} held"
        what = (f"{company['name']} is asking its owners for {amount}: {terms}, at {_naira(price)} a share. Whoever holds the "
                f"shares when {clock.period_label(period + 1)} closes may buy in proportion. Owners who do not take part end up "
                "with a smaller slice of the company.")
    elif kind == "ipo":
        what = (f"{company['name']} is selling shares to the public for the first time: {shares:,} new shares at {_naira(price)} "
                f"each, to raise {amount}. Afterwards its shares trade on the exchange.")
    else:
        what = (f"{company['name']} is selling {shares:,} new shares to anybody at {_naira(price)} each, to raise {amount}. "
                "Each existing share becomes a slightly smaller slice of the company.")
    if kind != "ipo" and shares * BPS // in_issue > data.VOTE_ABOVE_BPS:
        vote_id = open_vote(
            conn, company["id"], subject="rights_issue" if kind == "rights" else "share_offer", period=period, board="for",
            question=f"Should {company['name']} issue {shares:,} new shares at {_naira(price)} each?",
            explanation=what + " " + reason, detail={"institutions": institutions, "matter": f"its plan to raise {amount} by selling new shares"})
    offer_id = _one(
        conn, "INSERT INTO share_offers (company_id, kind, price, shares, rights_new, rights_held, reason, opens_period, closes_period, vote_id)"
              " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (company["id"], kind, price, shares, rights[0] if rights else None, rights[1] if rights else None, reason, period,
         period + 1, vote_id))["id"]
    notice(conn, period, company["id"], f"{kind}_offer", f"{company['name']}: " + {
        "rights": "rights issue", "ipo": "first sale of shares to the public", "public": "sale of new shares"}[kind],
        what + " " + reason + (" It goes ahead only if shareholders vote for it." if vote_id else ""), now)
    return offer_id


def _big(kobo: int) -> str:
    return news.money_words(kobo)


def apply_for_shares(conn: Connection, *, account: UUID | str, offer_id: int, shares: int, now: datetime) -> dict:
    """Ask for `shares` new shares in an offer (0 withdraws the request). The cash is held at once
    and whatever is not used is handed back when the offer closes."""
    if not _whole(shares) or shares < 0:
        raise CorporateError("The number of shares must be a whole number, zero or more.")
    with conn.transaction():
        _open(conn, now)
        _player(conn, account)
        offer = _one(conn, "SELECT * FROM share_offers WHERE id = %s FOR UPDATE", (offer_id,))
        if offer is None or offer["status"] != "open":
            raise CorporateError("That offer is not open.")
        if shares > offer["shares"]:
            raise CorporateError(f"Only {offer['shares']:,} shares are on offer.")
        held = bonds.held_account(conn)
        mine = _one(conn, "SELECT * FROM offer_subscriptions WHERE offer_id = %s AND account_id = %s FOR UPDATE", (offer_id, account))
        before = mine["held"] if mine else 0
        cost = shares * offer["price"]
        try:
            if cost > before:
                ledger.transfer(conn, payer=account, receiver=held, amount=cost - before, kind="offer_hold",
                                memo="Cash held for an application for new shares", reference=f"offer:{offer_id}")
            elif cost < before:
                ledger.transfer(conn, payer=held, receiver=account, amount=before - cost, kind="offer_release",
                                memo="Cash handed back: application for new shares reduced", reference=f"offer:{offer_id}")
        except ledger.InsufficientFunds:
            raise CorporateError(f"You do not have enough cash. That application needs {_naira(cost)}.") from None
        conn.execute("INSERT INTO offer_subscriptions (offer_id, account_id, shares, held, updated_at) VALUES (%s, %s, %s, %s, %s)"
                     " ON CONFLICT (offer_id, account_id) DO UPDATE SET shares = EXCLUDED.shares, held = EXCLUDED.held,"
                     " updated_at = EXCLUDED.updated_at", (offer_id, account, shares, cost, now))
        return {"shares": shares, "held": cost}


def _refund(conn: Connection, offer_id: int, account, amount: int, memo: str, held) -> None:
    if amount > 0:
        ledger.transfer(conn, payer=held, receiver=account, amount=amount, kind="offer_release", memo=memo, reference=f"offer:{offer_id}")


def _complete_offers(conn: Connection, period: int, now: datetime) -> None:
    held = bonds.held_account(conn)
    who = _investors(conn)
    founders, funds, public = who[ledger.INVESTORS_FOUNDERS], who[ledger.INVESTORS_INSTITUTIONS], who[ledger.INVESTORS_PUBLIC]
    for offer in _rows(conn, "SELECT * FROM share_offers WHERE status = 'open' AND closes_period <= %s ORDER BY id FOR UPDATE", (period,)):
        company = _company(conn, offer["company_id"])
        asked = {r["account_id"]: r for r in _rows(conn, "SELECT * FROM offer_subscriptions WHERE offer_id = %s ORDER BY account_id FOR UPDATE", (offer["id"],))}
        if not _vote_passed(conn, offer["vote_id"]):
            for account, sub in asked.items():
                _refund(conn, offer["id"], account, sub["held"], "Cash handed back: the share offer did not go ahead", held)
            conn.execute("UPDATE offer_subscriptions SET allotted = 0, held = 0 WHERE offer_id = %s", (offer["id"],))
            conn.execute("UPDATE share_offers SET status = 'withdrawn', shares_sold = 0, raised = 0, outcome = %s, closed_at = %s WHERE id = %s",
                         ("Shareholders voted against it. No shares were issued and all cash was handed back.", now, offer["id"]))
            notice(conn, period, company["id"], "offer_withdrawn", f"{company['name']}: share offer withdrawn",
                   "Shareholders voted against it. No shares were issued and all cash held was handed back.", now)
            continue

        price, wanted = offer["price"], {account: sub["shares"] for account, sub in asked.items() if sub["shares"] > 0}
        valued = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company["id"],))
        worth = valued["value_per_share"] if valued else price
        cash = {account: max(ledger.balance(conn, account), 0) for account in (founders, funds, public)}
        afford = lambda account, share_of_cash: cash[account] * share_of_cash // BPS // price            # noqa: E731
        allot: dict = {}
        if offer["kind"] == "rights":
            owners = _owners(conn, company["id"])
            entitled = {account: shares * offer["rights_new"] // offer["rights_held"] for account, shares in owners.items()}
            total = sum(entitled.values())
            # The computer-run owners: founders and pension funds take up their rights if the company's
            # debts are not larger than everything it owns; small investors take up most of theirs.
            sound = _one(conn, "SELECT total_equity FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                         (company["id"],))["total_equity"] > 0 and price <= worth
            if sound:
                wanted[founders] = min(entitled.get(founders, 0), afford(founders, data.OFFER_CASH_BPS))
                wanted[funds] = min(entitled.get(funds, 0), afford(funds, data.OFFER_CASH_BPS))
                wanted[public] = min(entitled.get(public, 0) * data.SMALL_INVESTORS_TAKE_UP_BPS // BPS, afford(public, data.OFFER_CASH_BPS))
            for account, amount in wanted.items():
                allot[account] = min(amount, entitled.get(account, 0))
            # Rights nobody took are bought by the pension funds, who stand behind the issue, if the
            # company is sound and they have the cash. (Nobody else may have more than their own rights:
            # shares below the market price handed to whoever asked would be money for nothing.)
            left = total - sum(allot.values())
            if left > 0 and sound:
                spare = max(afford(funds, data.OFFER_CASH_BPS) - allot.get(funds, 0), 0)
                allot[funds] = allot.get(funds, 0) + min(left, spare)
        else:
            total = offer["shares"]
            if price <= worth * 105 // 100:                    # they do not pay much more than the shares are worth
                wanted[funds] = min(total * data.OFFER_FUNDS_SHARE_BPS // BPS, afford(funds, data.OFFER_CASH_BPS))
                wanted[public] = min(total * data.OFFER_PUBLIC_SHARE_BPS // BPS, afford(public, data.OFFER_CASH_BPS))
            demand = sum(wanted.values())
            for account, amount in wanted.items():
                allot[account] = amount if demand <= total else amount * total // demand
        allot = {account: amount for account, amount in allot.items() if amount > 0}
        sold = sum(allot.values())
        raised = sold * price
        listed = _market_price(conn, company["id"])
        in_issue = ledger.amount_in_existence(conn, company["share_asset"])
        if sold:
            if listed is not None:
                exchange.cancel_all_in(conn, company["id"], now, "Handed back: the company issued new shares, which changes what each share is worth.")
                exchange.allow_index_for(conn, raised)
            from_players = sum(amount * price for account, amount in allot.items() if account in asked)
            legs = [Leg(company["account_id"], -sold, company["share_asset"]), Leg(company["account_id"], raised)]
            legs += [Leg(account, amount, company["share_asset"]) for account, amount in allot.items()]
            legs += [Leg(account, -amount * price) for account, amount in allot.items() if account not in asked]
            if from_players:
                legs.append(Leg(held, -from_players))
            ledger.post(conn, kind="share_issue", memo=f"{company['name']}: {sold:,} new shares issued at {_naira(price)}",
                        period=period, reference=f"offer:{offer['id']}", legs=legs)
            after = _after_trade(conn)
            for account, amount in allot.items():
                conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id)"
                             " VALUES (%s, %s, 'offer', %s, %s, %s)", (account, company["id"], amount, amount * price, after))
        for account, sub in asked.items():
            got = allot.get(account, 0)
            _refund(conn, offer["id"], account, sub["held"] - got * price, "Cash handed back: not all the shares applied for were allotted", held)
            conn.execute("UPDATE offer_subscriptions SET allotted = %s, held = 0 WHERE offer_id = %s AND account_id = %s",
                         (got, offer["id"], account))
        taken = sold * BPS // total if total else 0
        outcome = f"{sold:,} new shares were issued at {_naira(price)}, raising {_big(raised)}. {_percent(taken)} of the shares on offer found buyers."
        if sold and offer["kind"] == "ipo":
            exchange.list_company(conn, company["id"], price, now)
            outcome += " The shares now trade on the Broad Street Exchange."
        elif sold and listed is not None:
            # More shares, sold below the market price: each share is now a smaller slice.
            new_price = (in_issue * listed + raised) // (in_issue + sold)
            exchange.reprice(conn, company["id"], new_price, now,
                             f"{sold:,} new shares were issued at {_naira(price)}. The same company is now divided into more "
                             f"shares, so each is worth less: the price was adjusted from {_naira(listed)} to {_naira(new_price)}.")
            outcome += f" The share price was adjusted from {_naira(listed)} to {_naira(new_price)} to allow for the new shares."
        conn.execute("UPDATE share_offers SET status = 'done', shares_sold = %s, raised = %s, outcome = %s, closed_at = %s WHERE id = %s",
                     (sold, raised, outcome, now, offer["id"]))
        notice(conn, period, company["id"], "offer_result", f"{company['name']}: share offer completed", outcome, now)
        if sold:
            news.publish(conn, period=period + 1, day=2, kind="offer_result", story=f"offer:{offer['id']}",
                         facts={"company": company["name"], "ticker": company["ticker"], "amount": _big(raised), "taken": _percent(taken)},
                         tickers=[company["ticker"]])


# ---------------------------------------------------------------------------
# Share splits
# ---------------------------------------------------------------------------

def _complete_splits(conn: Connection, period: int, now: datetime) -> None:
    day, _ = exchange.session_of(now)
    for vote in _rows(conn, "SELECT * FROM company_votes WHERE subject = 'share_split' AND status = 'passed' AND closes_period = %s"
                            " AND NOT EXISTS (SELECT 1 FROM share_splits s WHERE s.company_id = company_votes.company_id AND s.period = %s)"
                            " ORDER BY id", (period, period)):
        company = _company(conn, vote["company_id"])
        ratio = int(vote["detail"]["ratio"])
        exchange.cancel_all_in(conn, company["id"], now, "Handed back: the company split its shares.")
        exchange.allow_index_for(conn, 0)                  # pin the index's base before the listing price changes
        every = _rows(conn, "SELECT b.account_id, b.balance::bigint AS shares FROM ledger_balances b WHERE b.asset = %s AND b.balance > 0"
                            " ORDER BY b.account_id", (company["share_asset"],))
        extra = sum(o["shares"] for o in every) * (ratio - 1)
        ledger.post(conn, kind="share_split", memo=f"{company['name']}: {ratio} shares for each one held", period=period,
                    reference=f"split:{company['ticker']}:{period}",
                    legs=[Leg(company["account_id"], -extra, company["share_asset"]),
                          *[Leg(o["account_id"], o["shares"] * (ratio - 1), company["share_asset"]) for o in every]])
        before = _market_price(conn, company["id"])
        conn.execute("UPDATE market_instruments SET listing_price = greatest(listing_price / %s, 1), reference_price = greatest(reference_price / %s, 1),"
                     " last_price = CASE WHEN last_price IS NULL THEN NULL ELSE greatest(last_price / %s, 1) END, updated_at = %s"
                     " WHERE company_id = %s", (ratio, ratio, ratio, now, company["id"]))
        conn.execute("UPDATE bonds SET conversion_shares = conversion_shares * %s WHERE company_id = %s AND kind = 'convertible'"
                     " AND redeemed_period IS NULL", (ratio, company["id"]))
        conn.execute("UPDATE takeover_tenders d SET shares = shares * %s FROM takeovers t WHERE t.id = d.takeover_id AND t.status = 'open'"
                     " AND t.target_company_id = %s", (ratio, company["id"]))
        conn.execute("UPDATE watchlist SET alert_above = alert_above / %s, alert_below = greatest(alert_below / %s, 1) WHERE company_id = %s",
                     (ratio, ratio, company["id"]))
        conn.execute("UPDATE investor_books SET centre = greatest(centre / %s, 1) WHERE company_id = %s", (ratio, company["id"]))
        conn.execute("INSERT INTO share_splits (company_id, period, ratio, after_trade_id, session_date) VALUES (%s, %s, %s, %s, %s)",
                     (company["id"], period, ratio, _after_trade(conn), day))
        after = _market_price(conn, company["id"])
        text = (f"Every share of {company['name']} became {ratio}. The price was adjusted from {_naira(before)} to {_naira(after)}. "
                "Nobody is richer or poorer: each owner holds more shares, each worth less.")
        conn.execute("INSERT INTO market_reasons (company_id, session_date, happened_at, reason) VALUES (%s, %s, %s, %s)",
                     (company["id"], day, now, text))
        notice(conn, period, company["id"], "share_split", f"{company['name']}: shares split {ratio} for 1", text, now)


# ---------------------------------------------------------------------------
# Takeovers
# ---------------------------------------------------------------------------

def tender(conn: Connection, *, account: UUID | str, takeover_id: int, shares: int, now: datetime) -> dict:
    """Offer `shares` of the target to the bidder (0 withdraws them). They are held until the
    offer closes. If the offer fails, or more are offered than the bidder wants, they come back."""
    if not _whole(shares) or shares < 0:
        raise CorporateError("The number of shares must be a whole number, zero or more.")
    with conn.transaction():
        _open(conn, now)
        _player(conn, account)
        bid = _one(conn, "SELECT t.*, c.share_asset, c.name FROM takeovers t JOIN companies c ON c.id = t.target_company_id"
                         " WHERE t.id = %s FOR UPDATE OF t", (takeover_id,))
        if bid is None or bid["status"] != "open":
            raise CorporateError("That offer is not open.")
        held = bonds.held_account(conn)
        mine = _one(conn, "SELECT * FROM takeover_tenders WHERE takeover_id = %s AND account_id = %s FOR UPDATE", (takeover_id, account))
        before = mine["shares"] if mine else 0
        if mine is None and shares == 0:
            return {"shares": 0, "value": 0}
        try:
            if shares > before:
                ledger.transfer(conn, payer=account, receiver=held, amount=shares - before, asset=bid["share_asset"],
                                kind="tender_hold", memo=f"{bid['name']} shares offered to the bidder", reference=f"takeover:{takeover_id}")
            elif shares < before:
                ledger.transfer(conn, payer=held, receiver=account, amount=before - shares, asset=bid["share_asset"],
                                kind="tender_release", memo=f"{bid['name']} shares taken back from the bidder's offer",
                                reference=f"takeover:{takeover_id}")
        except ledger.InsufficientFunds:
            raise CorporateError("You do not hold that many shares free to offer. Shares in a sell order must be freed first.") from None
        conn.execute("INSERT INTO takeover_tenders (takeover_id, account_id, shares, updated_at) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (takeover_id, account_id) DO UPDATE SET shares = EXCLUDED.shares, updated_at = EXCLUDED.updated_at",
                     (takeover_id, account, shares, now))
        return {"shares": shares, "value": shares * bid["price"]}


def _computer_run_acceptances(conn: Connection, bid: dict, who: dict) -> dict:
    """What the computer-run owners do about an offer, by rules anybody can read. Founders follow
    the target's board. Pension funds accept a price well above the market. Of the small
    investors, more accept the higher the price."""
    founders, funds, public = who[ledger.INVESTORS_FOUNDERS], who[ledger.INVESTORS_INSTITUTIONS], who[ledger.INVESTORS_PUBLIC]
    owned = _owners(conn, bid["target_company_id"])
    offered = {}
    if not bid["hostile"]:
        offered[founders] = owned.get(founders, 0)
    valued = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                  (bid["target_company_id"],))
    if bid["premium_bps"] >= data.FUNDS_ACCEPT_PREMIUM_BPS and (valued is None or bid["price"] >= valued["value_per_share"]):
        offered[funds] = owned.get(funds, 0)                # ...and never below what the company is worth
    offered[public] = owned.get(public, 0) * min(max(bid["premium_bps"] * 2, 2000), 9000) // BPS
    return {account: shares for account, shares in offered.items() if shares > 0}


def expected_value(conn: Connection, bid: dict, worth_per_share: int) -> int | None:
    """What a share of the target is worth while an offer is open, as far as anybody can tell
    today: if the offer looks like succeeding, the part of each share the bidder would buy at
    its price, and the rest at what the company is worth. None if it looks like failing."""
    who = _investors(conn)
    if bid["vote_id"]:
        vote = _one(conn, "SELECT * FROM company_votes WHERE id = %s", (bid["vote_id"],))
        tally = _tally(conn, vote, who)
        if sum(t[0] for t in tally.values()) <= sum(t[1] for t in tally.values()):
            return None
    target = _company(conn, bid["target_company_id"])
    bidder = _company(conn, bid["bidder_company_id"])
    # Only what the computer-run owners will do by their public rules is counted. What players have
    # offered so far can be taken back, so it is left out: nobody can move this figure and then withdraw.
    offered = _computer_run_acceptances(conn, bid, who)
    total = sum(offered.values())
    in_issue = ledger.amount_in_existence(conn, target["share_asset"])
    already = ledger.balance(conn, bidder["account_id"], target["share_asset"])
    if total <= 0 or (total + already) * 2 <= in_issue:
        return None
    buy = min(bid["shares_sought"], total)
    return (bid["price"] * buy + worth_per_share * (total - buy)) // total


def _complete_takeovers(conn: Connection, period: int, now: datetime) -> None:
    held = bonds.held_account(conn)
    who = _investors(conn)
    for bid in _rows(conn, "SELECT * FROM takeovers WHERE status = 'open' AND closes_period <= %s ORDER BY id FOR UPDATE", (period,)):
        bidder, target = _company(conn, bid["bidder_company_id"]), _company(conn, bid["target_company_id"])
        asset = target["share_asset"]
        offered = {r["account_id"]: r["shares"] for r in _rows(
            conn, "SELECT account_id, shares FROM takeover_tenders WHERE takeover_id = %s AND shares > 0 ORDER BY account_id FOR UPDATE", (bid["id"],))}
        players_offered = dict(offered)
        in_issue = ledger.amount_in_existence(conn, asset)
        already = ledger.balance(conn, bidder["account_id"], asset)
        blocked = not _vote_passed(conn, bid["vote_id"])
        if not blocked:
            offered.update(_computer_run_acceptances(conn, bid, who))
        total = sum(offered.values())
        accepted_bps = (total + already) * BPS // in_issue if in_issue else 0
        won = not blocked and (total + already) * 2 > in_issue and total > 0

        if won:
            exchange.cancel_all_in(conn, target["id"], now, "Handed back: the company has a new controlling owner.")
            buy = min(bid["shares_sought"], total)
            bought = {account: shares if buy == total else shares * buy // total for account, shares in offered.items()}
            bought = {account: shares for account, shares in bought.items() if shares > 0}
            buy = sum(bought.values())
            paid = buy * bid["price"]
            from_held = sum(shares for account, shares in bought.items() if account in players_offered)
            legs = [Leg(held, -paid), *[Leg(account, shares * bid["price"]) for account, shares in bought.items()],
                    Leg(bidder["account_id"], buy, asset),
                    *[Leg(account, -shares, asset) for account, shares in bought.items() if account not in players_offered]]
            if from_held:
                legs.append(Leg(held, -from_held, asset))
            ledger.post(conn, kind="takeover_payment", memo=f"{bidder['name']} buys {buy:,} {target['name']} shares at {_naira(bid['price'])}",
                        period=period, reference=f"takeover:{bid['id']}", legs=legs)
            after = _after_trade(conn)
            for account, shares in bought.items():
                conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id)"
                             " VALUES (%s, %s, 'takeover', %s, %s, %s)", (account, target["id"], -shares, shares * bid["price"], after))
        else:
            bought, buy, paid = {}, 0, 0
        # Shares offered but not bought go back to their owners; cash not used goes back to the bidder.
        for account, shares in players_offered.items():
            back = shares - bought.get(account, 0)
            if back > 0:
                ledger.transfer(conn, payer=held, receiver=account, amount=back, asset=asset, kind="tender_release",
                                memo=f"{target['name']} shares handed back: the bidder did not buy them", reference=f"takeover:{bid['id']}")
        conn.execute("UPDATE takeover_tenders SET shares = 0 WHERE takeover_id = %s", (bid["id"],))
        if bid["reserved"] - paid > 0:
            ledger.transfer(conn, payer=held, receiver=bidder["account_id"], amount=bid["reserved"] - paid, kind="takeover_refund",
                            memo=f"{bidder['name']}: cash set aside for its offer for {target['name']}, not used", period=period,
                            reference=f"takeover:{bid['id']}")
        stake = (already + buy) * BPS // in_issue if in_issue else 0
        if won:
            outcome = (f"Owners of {_percent(accepted_bps)} of the shares accepted. {bidder['name']} bought {buy:,} shares at "
                       f"{_naira(bid['price'])} for {_big(paid)} and now owns {_percent(stake)} of {target['name']}."
                       + (" More shares were offered than it wanted, so each seller sold the same proportion." if buy < total else ""))
            conn.execute("INSERT INTO integrations (takeover_id, bidder_company_id, target_company_id, start_period, quarters, planned_saving_bps)"
                         " VALUES (%s, %s, %s, %s, %s, %s)", (bid["id"], bidder["id"], target["id"], period + 1,
                                                              data.INTEGRATION_QUARTERS, data.INTEGRATION_SAVING_BPS))
            news.publish(conn, period=period + 1, day=1, kind="takeover_won", story=f"takeover:{bid['id']}",
                         facts={"bidder": bidder["name"], "target": target["name"], "ticker": target["ticker"],
                                "price": _naira(bid["price"]), "stake": _percent(stake), "value": _big(paid)},
                         tickers=[target["ticker"], bidder["ticker"]])
        else:
            outcome = ("The bidder's own shareholders voted against the purchase, so the offer was withdrawn." if blocked else
                       f"Owners of only {_percent(accepted_bps)} of the shares accepted; more than half was needed. The offer lapsed.") \
                + " Everybody keeps their shares."
            news.publish(conn, period=period + 1, day=1, kind="takeover_failed", story=f"takeover:{bid['id']}",
                         facts={"bidder": bidder["name"], "target": target["name"], "ticker": target["ticker"],
                                "price": _naira(bid["price"]), "accepted": _percent(accepted_bps)},
                         tickers=[target["ticker"], bidder["ticker"]])
        conn.execute("UPDATE takeovers SET status = %s, accepted = %s, bought = %s, paid = %s, reserved = 0, outcome = %s, closed_at = %s"
                     " WHERE id = %s", ("won" if won else "failed", total, buy, paid, outcome, now, bid["id"]))
        notice(conn, period, target["id"], "takeover_result",
               f"{bidder['name']}'s offer for {target['name']}: {'succeeded' if won else 'failed'}", outcome, now)


# ---------------------------------------------------------------------------
# After a takeover: joining the two businesses
# ---------------------------------------------------------------------------

def integration_effects(conn: Connection, period: int, seed: str, ratings: dict) -> dict:
    """What being joined to its new owner does to each target this quarter: company id ->
    {"cost_bps", "pull_bps", "notes"}. Worked out once for each quarter and written down."""
    effects: dict = {}
    for plan in _rows(conn, "SELECT i.*, b.name AS bidder, t.name AS target, t.ticker FROM integrations i"
                            " JOIN companies b ON b.id = i.bidder_company_id JOIN companies t ON t.id = i.target_company_id"
                            " WHERE i.start_period <= %s AND i.start_period + i.quarters > %s ORDER BY i.takeover_id", (period, period)):
        done = _one(conn, "SELECT * FROM integration_results WHERE takeover_id = %s AND period = %s", (plan["takeover_id"], period))
        if done is None:
            quarter = period - plan["start_period"] + 1
            key = f"integration:{plan['takeover_id']}"
            planned = plan["planned_saving_bps"] * min(quarter, 4) // 4            # the savings come in over the first year
            carried_out = 2000 + int(events._unit(seed, key, period, "execution") * 10_000)      # 20% to 120% of the plan
            saving = planned * carried_out // BPS
            cost, pull, notes = 0, 0, []
            if events._unit(seed, key, period, "clash") < 0.20:
                saving //= 2
                notes.append("The two companies' ways of working clashed, and half of this quarter's planned savings were lost.")
            if ratings.get(plan["bidder_company_id"]) in ("BB", "B", "CCC", "D"):
                saving = saving * 2 // 3
                notes.append(f"{plan['bidder']} is stretched by what it borrowed, and has slowed the work of joining the two.")
            if events._unit(seed, key, period, "staff") < 0.25:
                cost += 150
                notes.append("Experienced staff left after the takeover. Replacing them cost about 1.5% of sales.")
            if events._unit(seed, key, period, "rules") < 0.10:
                cost += 100
                notes.append("The competition regulator asked for changes. Meeting them cost about 1% of sales.")
            if events._unit(seed, key, period, "customers") < 0.20:
                pull = -150
                notes.append("Some customers went elsewhere during the change of owner: about 1.5% of its hold on its market.")
            net = cost - saving
            notes.insert(0, f"Being joined with {plan['bidder']} "
                            + (f"lowered its costs by about {_percent(-net)} of sales this quarter." if net < 0 else
                               f"added about {_percent(net)} of sales to its costs this quarter." if net > 0 else
                               "made no difference to its costs this quarter."))
            conn.execute("INSERT INTO integration_results (takeover_id, period, cost_bps, pull_bps, notes) VALUES (%s, %s, %s, %s, %s)",
                         (plan["takeover_id"], period, net, pull, Jsonb(notes)))
            done = {"cost_bps": net, "pull_bps": pull, "notes": notes}
            if quarter in (1, 4, plan["quarters"]):
                good = net < 0 and pull == 0
                detail = (f"Costs at {plan['target']} came in about {_percent(net)} of sales lower this quarter." if good else
                          notes[-1] if len(notes) > 1 else f"Costs at {plan['target']} were about {_percent(net)} of sales higher this quarter.")
                news.publish(conn, period=period + 1, day=3, kind="integration_good" if good else "integration_bad",
                             story=f"takeover:{plan['takeover_id']}",
                             facts={"bidder": plan["bidder"], "target": plan["target"], "ticker": plan["ticker"], "detail": detail},
                             tickers=[plan["ticker"]])
            if quarter == plan["quarters"]:
                # What was achieved over the last year of the work stays for good.
                kept = _one(conn, "SELECT coalesce(avg(cost_bps), 0)::int AS bps FROM (SELECT cost_bps FROM integration_results"
                                  " WHERE takeover_id = %s ORDER BY period DESC LIMIT 4) x", (plan["takeover_id"],))["bps"]
                conn.execute("UPDATE companies SET labour_bps = least(greatest(labour_bps + %s, 0), 10000) WHERE id = %s",
                             (kept, plan["target_company_id"]))
        effects[plan["target_company_id"]] = {"cost_bps": done["cost_bps"], "pull_bps": done["pull_bps"], "notes": list(done["notes"])}
    return effects


# ---------------------------------------------------------------------------
# Settling, as a quarter closes
# ---------------------------------------------------------------------------

def settle(conn: Connection, period: int, now: datetime) -> None:
    """Settle everything that was announced when the quarter before closed. Run at the very start
    of a quarter's close, before any company's accounts are drawn up."""
    _convert(conn, period, now)
    _count_votes(conn, period, now)
    _complete_splits(conn, period, now)
    _complete_offers(conn, period, now)
    _complete_takeovers(conn, period, now)


def _convert(conn: Connection, period: int, now: datetime) -> None:
    """Swap the convertible bonds whose holders asked. New shares at the market price would not
    move the index, so the base is raised by what they are worth."""
    waiting = _rows(conn, "SELECT DISTINCT b.company_id FROM bond_conversions v JOIN bonds b ON b.id = v.bond_id WHERE v.status = 'waiting'")
    for row in waiting:
        price = _market_price(conn, row["company_id"]) or 0
        pending = _one(conn, "SELECT coalesce(sum(v.units * b.conversion_shares), 0)::bigint AS shares FROM bond_conversions v"
                             " JOIN bonds b ON b.id = v.bond_id WHERE v.status = 'waiting' AND b.company_id = %s AND b.redeemed_period IS NULL",
                       (row["company_id"],))["shares"]
        if pending and price:
            exchange.allow_index_for(conn, pending * price)
    done = bonds.convert_waiting(conn, period)
    for company_id, (debt, shares) in done.items():
        company = _company(conn, company_id)
        notice(conn, period, company_id, "conversion", f"{company['name']}: bonds swapped for shares",
               f"Holders swapped {_big(debt)} of convertible bonds for {shares:,} new shares. The company owes that much less, "
               "and each existing share is a slightly smaller slice.", now)


def check_books(conn: Connection) -> list[str]:
    """What the exchange holds for offers must be exactly what the records say. An empty list means it is."""
    problems = []
    held = bonds.held_account(conn)
    cash = ledger.balance(conn, held)
    owed = _one(conn, "SELECT (SELECT coalesce(sum(s.held), 0) FROM offer_subscriptions s JOIN share_offers o ON o.id = s.offer_id"
                      " WHERE o.status = 'open') + (SELECT coalesce(sum(reserved), 0) FROM takeovers WHERE status = 'open') AS total")["total"]
    if cash != owed:
        problems.append(f"The exchange holds {cash} kobo for offers but the records account for {owed}.")
    for row in _rows(
        conn,
        "SELECT b.asset, b.balance::bigint AS held, coalesce(w.owed, 0)::bigint AS owed FROM ledger_balances b LEFT JOIN ("
        "   SELECT c.share_asset AS asset, sum(d.shares) AS owed FROM takeover_tenders d JOIN takeovers t ON t.id = d.takeover_id"
        "     JOIN companies c ON c.id = t.target_company_id WHERE t.status = 'open' GROUP BY c.share_asset"
        "   UNION ALL SELECT x.asset, sum(v.units) FROM bond_conversions v JOIN bonds x ON x.id = v.bond_id WHERE v.status = 'waiting'"
        "     GROUP BY x.asset) w ON w.asset = b.asset WHERE b.account_id = %s AND b.asset <> 'NGN'", (held,)):
        if row["held"] != row["owed"]:
            problems.append(f"The exchange holds {row['held']} of {row['asset']} for offers but the records account for {row['owed']}.")
    return problems


# ---------------------------------------------------------------------------
# What companies decide, once a quarter's results are in
# ---------------------------------------------------------------------------

def _busy(conn: Connection) -> set:
    """Companies with something already under way: an open offer, vote or bid, or a takeover behind them."""
    rows = _rows(conn, "SELECT company_id FROM share_offers WHERE status = 'open' UNION SELECT company_id FROM company_votes WHERE status = 'open'"
                       " UNION SELECT bidder_company_id FROM takeovers WHERE status IN ('open', 'won')"
                       " UNION SELECT target_company_id FROM takeovers WHERE status IN ('open', 'won')")
    return {r["company_id"] for r in rows}


def propose(conn: Connection, period: int, seed: str, now: datetime, results: list[tuple[dict, dict]], banks: dict,
            policy_rate_bps: int) -> None:
    """After a quarter's reports are filed: companies that need money, or have a use for the
    market, announce what they will do. Everything announced is settled when the next quarter closes."""
    ratings = {r["company_id"]: r["credit_rating"] for r in _rows(
        conn, "SELECT DISTINCT ON (company_id) company_id, credit_rating FROM company_reports ORDER BY company_id, period DESC, version DESC")}
    worth = {r["company_id"]: r for r in _rows(conn, "SELECT DISTINCT ON (company_id) * FROM company_valuations ORDER BY company_id, period DESC")}
    # The market price; for a share that has never traded, what it is worth (it will be listed there).
    prices = {r["company_id"]: r["last_price"] or (worth[r["company_id"]]["value_per_share"] if r["company_id"] in worth else r["reference_price"])
              for r in _rows(conn, "SELECT company_id, last_price, reference_price FROM market_instruments")}
    busy = _busy(conn)
    recent_offer = {r["company_id"] for r in _rows(conn, "SELECT company_id FROM share_offers WHERE opens_period > %s", (period - data.OFFER_GAP_QUARTERS,))}
    recent_bond = {r["company_id"] for r in _rows(conn, "SELECT company_id FROM bonds WHERE issuer = 'company' AND issued_period > %s"
                                                        " AND issued_period > 0", (period - data.BOND_ISSUE_GAP_QUARTERS,))}
    # New shares are priced from the lower of the market price and what the company is worth, so that a
    # price nobody will pay cannot make an offer that nobody will take up.
    basis = {c: min(p, worth[c]["value_per_share"]) if c in worth else p for c, p in prices.items()}
    order = lambda company, what: events._unit(seed, company["ticker"], period, what)          # noqa: E731
    listed = [(c, r) for c, r in results if c["id"] in prices and c["id"] not in busy]

    # 1. A share costing ₦100 or more is split.
    for company, _ in listed:
        price = prices[company["id"]]
        if price >= data.SPLIT_ABOVE_KOBO:
            ratio = min(max(price // (data.SPLIT_ABOVE_KOBO // 2), 2), 10)
            terms = f"{news.number_word(ratio)} new shares for each one held"
            open_vote(conn, company["id"], subject="share_split", period=period, board="for",
                      question=f"Should {company['name']} split its shares, {terms}?",
                      explanation=(f"A share of {company['name']} costs {_naira(price)}. The board proposes to split each into {ratio}, "
                                   f"so that one costs about {_naira(price // ratio)}. Nobody gains or loses: every owner holds "
                                   f"{ratio} times as many shares, each worth a {ratio}th as much. A lower price lets smaller investors buy."),
                      detail={"ratio": ratio, "matter": f"its plan to split each share into {news.number_word(ratio)}"})
            notice(conn, period, company["id"], "split_proposed", f"{company['name']}: proposes to split its shares",
                   f"{terms.capitalize()}. Shareholders vote; if they approve, the split takes effect when {clock.period_label(period + 1)} closes.", now)
            news.publish(conn, period=period + 1, day=4, kind="share_split", story=f"split:{company['ticker']}:{period}",
                         facts={"company": company["name"], "ticker": company["ticker"], "terms": terms, "old_price": _naira(price),
                                "new_price": _naira(price // ratio)}, tickers=[company["ticker"]])
            busy.add(company["id"])

    # 2. Companies short of money ask their owners for more: a rights issue.
    needy = []
    for company, result in listed:
        if company["id"] in busy or company["id"] in recent_offer or prices[company["id"]] < 200:
            continue
        owed = result["principal_overdue"] + result["payables"]
        rating = ratings.get(company["id"])
        if result["total_equity"] > 0 and (rating in ("B", "CCC") or (rating in ("BBB", "BB") and (owed > 0 or result["net_profit"] < 0))):
            needy.append((-(owed or 1), company, result))
    for _, company, result in sorted(needy, key=lambda item: (item[0], item[1]["ticker"]))[:data.MOST_RIGHTS_ISSUES_A_QUARTER]:
        price = max(basis[company["id"]] * (BPS - data.RIGHTS_DISCOUNT_BPS) // BPS, 1)
        new, per = data.RIGHTS_TERMS
        shares = result["shares_in_issue"] * new // per
        owed = result["principal_overdue"] + result["payables"]
        reason = (f"It owes {_big(owed)} that is overdue or unpaid, and needs the money to pay it." if owed else
                  f"Its credit rating is {ratings.get(company['id'])}, and it wants more of its owners' money behind it and less borrowed.")
        announce_offer(conn, company, kind="rights", price=price, shares=shares, period=period, reason=reason, now=now,
                       rights=(new, per), institutions="for" if result["total_equity"] > 0 else "against")
        news.publish(conn, period=period + 1, day=4, kind="rights_issue", story=f"offer:{company['ticker']}:{period}",
                     facts={"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                            "sector": news.SECTOR_WORDS[company["sector"]], "amount": _big(price * shares), "price": _naira(price),
                            "discount": _percent(data.RIGHTS_DISCOUNT_BPS),
                            "terms": f"{news.number_word(new)} new share for every {news.number_word(per)} held"},
                     tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
        busy.add(company["id"])

    # 3. One strong company whose shares are not cheap sells new ones to anybody.
    if period % clock.QUARTERS_PER_YEAR == 2:
        strong = [(order(c, "offer"), c, r) for c, r in listed
                  if c["id"] not in busy and c["id"] not in recent_offer and c["sector"] not in FINANCIAL
                  and ratings.get(c["id"]) in GOOD_RATINGS and r["net_profit"] > 0 and c["id"] in worth
                  and prices[c["id"]] * BPS >= worth[c["id"]]["value_per_share"] * data.OFFER_WHEN_DEAR_BPS]
        if strong:
            _, company, result = min(strong, key=lambda item: (item[0], item[1]["ticker"]))
            price = basis[company["id"]] * (BPS - data.OFFER_DISCOUNT_BPS) // BPS
            shares = result["shares_in_issue"] * data.OFFER_SIZE_BPS // BPS
            announce_offer(conn, company, kind="public", price=price, shares=shares, period=period, now=now,
                           reason="It will use the money to expand and to borrow less.")
            news.publish(conn, period=period + 1, day=4, kind="share_offer", story=f"offer:{company['ticker']}:{period}",
                         facts={"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                                "sector": news.SECTOR_WORDS[company["sector"]], "amount": _big(price * shares), "price": _naira(price),
                                "shares": _words(shares)},
                         tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
            busy.add(company["id"])

    # 4. Companies in good standing borrow from investors instead of their bank: new bonds.
    borrowers = sorted(
        ((order(c, "bond"), c, r) for c, r in listed
         if c["id"] not in recent_bond and c["sector"] not in FINANCIAL and ratings.get(c["id"]) in (*GOOD_RATINGS, "BB", "B")
         and r["payables"] == 0 and r["principal_overdue"] == 0 and r["net_profit"] > 0), key=lambda item: (item[0], item[1]["ticker"]))
    issued = 0
    for chance, company, result in borrowers:
        if issued >= data.MOST_BOND_ISSUES_A_QUARTER or chance > 0.15:
            break
        dearer = {c: max(p, worth[c]["value_per_share"]) if c in worth else p for c, p in prices.items()}
        if _issue_bond(conn, company, result, period, ratings[company["id"]], policy_rate_bps, order(company, "bond kind"), dearer):
            issued += 1

    # 5. Now and then one company makes an offer for another.
    if period >= 2 and not _rows(conn, "SELECT 1 FROM takeovers WHERE status = 'open'") \
            and int(events._unit(seed, "takeover", period) * data.TAKEOVER_ONE_IN) == 0:
        _propose_takeover(conn, period, seed, now, listed, ratings, prices, busy, banks, policy_rate_bps)


def _issue_bond(conn: Connection, company: dict, result: dict, period: int, rating: str, policy_rate_bps: int, draw: float,
                prices: dict) -> bool:
    loan = _one(conn, "SELECT * FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0"
                      " AND name NOT LIKE 'overdue%%' ORDER BY principal_outstanding DESC LIMIT 1 FOR UPDATE", (company["id"],))
    if loan is None:
        return False
    kind, project, green, conversion = "fixed", None, False, None
    amount = loan["principal_outstanding"] * data.BOND_SHARE_OF_LOAN_BPS // BPS
    if rating in GOOD_RATINGS and draw < 0.35 and company["sector"] in PROJECTS:
        kind = "project"
        project, green = PROJECTS[company["sector"]]
        amount = result["fixed_assets"] * data.PROJECT_BOND_ASSETS_BPS // BPS
    elif rating in GOOD_RATINGS and draw < 0.65:
        kind = "convertible"
        conversion = max(bonds.FACE * BPS // (prices[company["id"]] * (BPS + data.CONVERSION_PREMIUM_BPS)), 1)
    bond = bonds.issue_for_company(conn, company, period=period, amount=amount, kind=kind, rating=rating,
                                   policy_rate_bps=policy_rate_bps, quarters=data.COMPANY_BOND_QUARTERS,
                                   conversion_shares=conversion, project=project, green=green)
    if bond is None:
        return False
    raised = bond["units"] * bonds.FACE
    if kind != "project":
        # The money pays down what it owes its bank.
        ledger.transfer(conn, payer=company["account_id"], receiver=loan["lender_account_id"], amount=raised, kind="debt_repayment",
                        memo=f"{company['name']}: part of its bank loan repaid from a bond issue", period=period + 1,
                        reference=f"debt:{loan['id']}")
        conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding - %s WHERE id = %s", (raised, loan["id"]))
    words = {"project": f"a {'green ' if green else ''}bond to pay for {project}", "convertible": "a bond that can be swapped for shares"}.get(
        kind, "a high-interest bond" if bond["high_yield"] else "a five-year bond")
    news.publish(conn, period=period + 1, day=5, kind="bond_issue", story=f"bond:{bond['asset']}",
                 facts={"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                        "sector": news.SECTOR_WORDS[company["sector"]], "amount": _big(raised), "rate": bonds._percent(bond["rate"]),
                        "bond": words},
                 tickers=[company["ticker"]], sectors=[company["sector"]], locations=[company["headquarters"]])
    return True


def _propose_takeover(conn: Connection, period: int, seed: str, now: datetime, listed: list, ratings: dict, prices: dict,
                      busy: set, banks: dict, policy_rate_bps: int) -> None:
    value = {c["id"]: prices[c["id"]] * r["shares_in_issue"] for c, r in listed}
    owned_by_company = {r["company_id"] for r in _rows(
        conn, "SELECT o.company_id FROM share_owners o JOIN ledger_accounts a ON a.id = o.account_id WHERE a.kind = 'company'")}
    bidders = [(c, r) for c, r in listed if c["id"] not in busy and c["sector"] not in FINANCIAL
               and ratings.get(c["id"]) in ("AAA", "AA", "A") and r["net_profit"] > 0 and r["payables"] == 0]
    pairs = []
    for bidder, result in bidders:
        for target, target_result in listed:
            if (target["id"] == bidder["id"] or target["id"] in busy or target["id"] in owned_by_company
                    or target["sector"] != bidder["sector"] or prices[target["id"]] < 200
                    or value[target["id"]] * BPS > value[bidder["id"]] * data.TAKEOVER_TARGET_SIZE_BPS):
                continue
            pairs.append((events._unit(seed, "pair", period, bidder["ticker"], target["ticker"]), bidder, result, target, target_result))
    for _, bidder, result, target, target_result in sorted(pairs, key=lambda item: (item[0], item[1]["ticker"], item[3]["ticker"])):
        low, high = data.TAKEOVER_PREMIUM_BPS
        premium = low + int(events._unit(seed, "premium", period, target["ticker"]) * (high - low))
        price = prices[target["id"]] * (BPS + premium) // BPS
        sought = target_result["shares_in_issue"] * data.TAKEOVER_STAKE_BPS // BPS
        cost = sought * price
        # It pays from cash it does not need, and borrows the rest from its bank if the bank has room.
        spare = max(ledger.balance(conn, bidder["account_id"]) - 2 * result["operating_expenses"], 0)
        loan = _one(conn, "SELECT * FROM company_debts WHERE company_id = %s AND kind = 'bank_loan' AND principal_outstanding > 0"
                          " AND name NOT LIKE 'overdue%%' ORDER BY principal_outstanding DESC LIMIT 1 FOR UPDATE", (bidder["id"],))
        bank = banks.get(loan["lender_account_id"]) if loan else None
        borrow = max(cost - spare, 0)
        if borrow and (bank is None or borrow > min(bank.get("room", 0), max(ledger.balance(conn, bank["account_id"]), 0) // 2)):
            continue
        if borrow:
            ledger.transfer(conn, payer=bank["account_id"], receiver=bidder["account_id"], amount=borrow, kind="new_loan",
                            memo=f"{bank['name']} lends {bidder['name']} money for its offer for {target['name']}",
                            period=period + 1, reference=f"debt:{loan['id']}")
            conn.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding + %s,"
                         " original_principal = original_principal + %s WHERE id = %s", (borrow, borrow, loan["id"]))
        held = bonds.held_account(conn)
        ledger.transfer(conn, payer=bidder["account_id"], receiver=held, amount=cost, kind="takeover_reserve",
                        memo=f"{bidder['name']}: cash set aside for its offer for {target['name']}", period=period + 1)
        hostile = premium < data.BOARD_ACCEPTS_PREMIUM_BPS
        vote_id = None
        if cost * BPS > value[bidder["id"]] * data.TAKEOVER_VOTE_ABOVE_BPS:
            vote_id = open_vote(
                conn, bidder["id"], subject="takeover", period=period, board="for",
                question=f"Should {bidder['name']} buy {_percent(data.TAKEOVER_STAKE_BPS)} of {target['name']} for {_big(cost)}?",
                explanation=(f"The purchase costs more than a quarter of what {bidder['name']} itself is worth, so its owners decide. "
                             f"It would pay {_naira(price)} a share, {_percent(premium)} above the market price."
                             + (f" It would borrow {_big(borrow)} of that from its bank." if borrow else "")),
                detail={"institutions": "for" if premium <= 3500 else "against",
                        "matter": f"its plan to buy most of {target['name']} for {_big(cost)}"})
        bid_id = _one(
            conn, "INSERT INTO takeovers (bidder_company_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved,"
                  " opens_period, closes_period, vote_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (bidder["id"], target["id"], price, sought, hostile, premium, cost, period, period + 1, vote_id))["id"]
        stance = (f"The board of {target['name']} has REJECTED the offer as too low, so {bidder['name']} is going straight to the "
                  "shareholders over the board's head (a hostile bid)." if hostile else
                  f"The board of {target['name']} recommends that shareholders accept.")
        body = (f"{bidder['name']} offers {_naira(price)} for each share of {target['name']}, {_percent(premium)} above the market "
                f"price, for up to {_percent(data.TAKEOVER_STAKE_BPS)} of the shares ({_big(cost)} in all). {stance} The offer closes when "
                f"{clock.period_label(period + 1)} closes. It succeeds only if owners of more than half the shares accept; if it "
                "fails, everybody keeps their shares."
                + (" It also needs the approval of the bidder's own shareholders." if vote_id else ""))
        notice(conn, period, target["id"], "takeover_bid", f"{bidder['name']} makes an offer for {target['name']}", body, now)
        # Trading in the target starts again from what its shares are now worth with the offer on the table.
        bid = _one(conn, "SELECT * FROM takeovers WHERE id = %s", (bid_id,))
        npv = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1", (target["id"],))
        expected = expected_value(conn, bid, npv["value_per_share"] if npv else prices[target["id"]])
        if expected and expected != prices[target["id"]]:
            exchange.cancel_all_in(conn, target["id"], now, "Handed back: a takeover offer was announced for the company.")
            exchange.reprice(conn, target["id"], expected, now,
                             f"{bidder['name']} offered {_naira(price)} a share for up to {_percent(data.TAKEOVER_STAKE_BPS)} of the company. "
                             f"The price was adjusted from {_naira(prices[target['id']])} to {_naira(expected)}: what a share is worth if "
                             "the offer succeeds, part bought at the offer price and the rest kept.")
        news.publish(conn, period=period + 1, day=1, kind="takeover_hostile" if hostile else "takeover_bid", story=f"takeover:{bid_id}",
                     facts={"bidder": bidder["name"], "target": target["name"], "ticker": target["ticker"], "price": _naira(price),
                            "premium": _percent(premium), "stake": _percent(data.TAKEOVER_STAKE_BPS), "value": _big(cost)},
                     tickers=[target["ticker"], bidder["ticker"]], sectors=[target["sector"]])
        return


def bid_for(conn: Connection, company_id) -> dict | None:
    """The open takeover offer for a company, if there is one."""
    return _one(conn, "SELECT * FROM takeovers WHERE target_company_id = %s AND status = 'open'", (company_id,))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def control(conn: Connection, company_id) -> dict:
    """Who controls a company: whoever holds more than half its shares, if anybody does."""
    owners = _rows(conn, "SELECT a.kind, a.code, a.name, o.shares FROM share_owners o JOIN ledger_accounts a ON a.id = o.account_id"
                         " WHERE o.company_id = %s", (company_id,))
    total = sum(o["shares"] for o in owners)
    groups: dict = {}
    for owner in owners:
        name = {"investors:founders": "its founders", "investors:institutions": "pension funds",
                "investors:public": "small investors"}.get(owner["code"]) or (owner["name"] if owner["kind"] == "company" else "small investors")
        groups[name] = groups.get(name, 0) + owner["shares"]
    if not total:
        return {"controller": None, "share_bps": 0, "summary": "It has no shares in issue."}
    name, shares = max(groups.items(), key=lambda item: item[1])
    part = shares * BPS // total
    if part > 5000:
        return {"controller": name, "share_bps": part,
                "summary": f"Controlled by {name}, who hold{'s' if name[0].isupper() else ''} {_percent(part)} of the shares: enough to win any vote."}
    return {"controller": None, "share_bps": part,
            "summary": f"Nobody holds more than half. The largest group is {name}, with {_percent(part)}."}


def board(conn: Connection, account: UUID | str | None, period: int) -> dict:
    """Everything open that a shareholder can act on, and what was lately settled."""
    offers = _rows(conn, "SELECT o.*, c.ticker, c.name, s.shares AS asked, s.held, s.allotted FROM share_offers o"
                         " JOIN companies c ON c.id = o.company_id LEFT JOIN offer_subscriptions s ON s.offer_id = o.id AND s.account_id = %s"
                         " WHERE o.status = 'open' OR o.closes_period >= %s ORDER BY (o.status = 'open') DESC, o.id DESC LIMIT 30",
                   (account, period - 3))
    votes = _rows(conn, "SELECT v.*, c.ticker, c.name, b.choice, coalesce(o.shares, 0)::bigint AS my_shares FROM company_votes v"
                        " JOIN companies c ON c.id = v.company_id LEFT JOIN vote_ballots b ON b.vote_id = v.id AND b.account_id = %s"
                        " LEFT JOIN share_owners o ON o.company_id = v.company_id AND o.account_id = %s"
                        " WHERE v.status = 'open' OR v.closes_period >= %s ORDER BY (v.status = 'open') DESC, v.id DESC LIMIT 30",
                  (account, account, period - 3))
    bids = _rows(conn, "SELECT t.*, b.name AS bidder, b.ticker AS bidder_ticker, c.name AS target, c.ticker, d.shares AS offered,"
                       " coalesce(m.last_price, m.reference_price) AS market_price,"
                       " coalesce((SELECT h.balance FROM ledger_balances h WHERE h.account_id = %s AND h.asset = c.share_asset), 0)::bigint AS free"
                       " FROM takeovers t JOIN companies b ON b.id = t.bidder_company_id JOIN companies c ON c.id = t.target_company_id"
                       " LEFT JOIN market_instruments m ON m.company_id = c.id"
                       " LEFT JOIN takeover_tenders d ON d.takeover_id = t.id AND d.account_id = %s"
                       " WHERE t.status = 'open' OR t.closes_period >= %s ORDER BY (t.status = 'open') DESC, t.id DESC LIMIT 20",
                 (account, account, period - 3))
    joins = _rows(conn, "SELECT i.*, b.name AS bidder, c.name AS target, c.ticker,"
                        " (SELECT jsonb_agg(jsonb_build_object('period', r.period, 'cost_bps', r.cost_bps, 'notes', r.notes) ORDER BY r.period)"
                        "    FROM integration_results r WHERE r.takeover_id = i.takeover_id) AS quarters_done"
                        " FROM integrations i JOIN companies b ON b.id = i.bidder_company_id JOIN companies c ON c.id = i.target_company_id"
                        " ORDER BY i.takeover_id DESC LIMIT 10")
    notices = _rows(conn, "SELECT n.*, c.ticker FROM market_notices n LEFT JOIN companies c ON c.id = n.company_id ORDER BY n.id DESC LIMIT 40")
    return {"offers": offers, "votes": votes, "takeovers": bids, "integrations": joins, "notices": notices}


def ownership(conn: Connection) -> list[dict]:
    """Who owns what: every company, who controls it, and the companies that own shares in others."""
    out = []
    for company in _rows(conn, "SELECT id, ticker, name FROM companies WHERE listed ORDER BY name"):
        out.append({"ticker": company["ticker"], "name": company["name"], **control(conn, company["id"])})
    return out


def held_by_account(conn: Connection) -> dict:
    """Cash and shares the exchange is holding for each player's applications and takeover acceptances:
    account -> (cash, investments at present prices)."""
    worth: dict = {}
    for row in _rows(conn, "SELECT s.account_id, sum(s.held)::bigint AS cash FROM offer_subscriptions s JOIN share_offers o ON o.id = s.offer_id"
                           " WHERE o.status = 'open' GROUP BY s.account_id"):
        worth[row["account_id"]] = (row["cash"], 0)
    for row in _rows(conn, "SELECT d.account_id, sum(d.shares * coalesce(m.last_price, m.reference_price))::bigint AS value"
                           " FROM takeover_tenders d JOIN takeovers t ON t.id = d.takeover_id"
                           " JOIN market_instruments m ON m.company_id = t.target_company_id WHERE t.status = 'open' GROUP BY d.account_id"):
        was = worth.get(row["account_id"], (0, 0))
        worth[row["account_id"]] = (was[0], was[1] + row["value"])
    return worth
