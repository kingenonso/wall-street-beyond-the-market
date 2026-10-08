"""Private equity stage, part 2B: the deal-making between empires.

  takeover offers   an empire's Investment Banker drafts an offer for a listed company's shares and the head
                    signs it. The cash is held from the moment it is announced. Any other empire may top it
                    (by at least 5%); owners who accepted the lower offer are counted for the higher one.
  defences          the Investment Banker of an empire holding 5% or more of the target writes the board's
                    defence: what the company is worth. If it holds up and the offer is below it, the board
                    rejects the offer, the founders will not sell, and small investors are slower to.
  stake building    the Asset Manager buys a listed company's shares a little at each bell, up to a target
                    below 30% (at 30% an empire must make an offer for the company)
  disclosure        every 5% step held in a listed company is made public, by anybody's route to it
  block trades      a block of listed shares sold by one empire to another, off the order book, within a
                    tenth of the market price
  portfolio         the empire's private-equity holdings: cost, value, the multiple of money
  truces            a pact: no poaching each other's people, no offers or stake-building against each
                    other's companies
  mergers and spin-offs, voted by the members of every empire concerned
  the shadow side   a member of the empire that controls a private company may pay themselves fees out of
                    it. It is written in the empire's books as a cost; audits (the empire's own, or an audit
                    firm's) can find it, and the usual consequences follow.

Players may commit crimes against each other's empires, never against the game: every naira and every
share moves through the ledger, nothing is created, and nobody acts for an empire that is not theirs.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from simulation import (bonds, careers, clock, corporate, empires, exchange, firm, firm_deals, firm_money, firm_practice, leagues, ledger,
                        news, private)
from simulation import firm_duties as fd
from simulation import world_data as data
from simulation.empires import EmpireError, _log, _money, _one, _open, _rows, _text
from simulation.ledger import Leg
from simulation.money import BPS, apply_bps

TOP_BY_BPS = 500                    # a rival offer must beat the one on the table by 5%
OFFER_MOST_BPS = 15_000             # no offer above half as much again as the higher of the market price and the company's worth
DEFEND_FROM_BPS = 500               # an empire holding 5% of the target may defend it
DISCLOSE_STEP_BPS = 500             # every 5% held in a listed company is made public
MUST_OFFER_BPS = 3000               # at 30% an empire must make an offer: nobody builds a stake (or buys a block) to it
STAKE_BELL_BPS = 50                 # a stake is built at most half a percent of the shares at each bell
BLOCK_BAND_BPS = 1000               # a block changes hands within a tenth of the market price
TRUCE_HOLDS_BPS = 2000              # a truce protects the companies an empire holds a fifth of, or controls
DEFENCE_HOURS = 24                  # a defence not handed in within a day may be taken over by another holder's adviser
TAKE_MOST_BPS = 500                 # the shadow side: at most a twentieth of the company's cash at a time
TRUCE_KIND = "truce"


def _whole(value, least: int = 1, most: int = 10**17) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and least <= value <= most


def _listed(conn: Connection, company_id) -> dict:
    company = _one(conn, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.id = %s", (company_id,))
    if company is None or not company["listed"] or company["status"] != "trading" or corporate._market_price(conn, company_id) is None:
        raise EmpireError("That is not a company whose shares trade on the exchange.")
    return company


def _in_issue(conn: Connection, company: dict) -> int:
    return ledger.amount_in_existence(conn, company["share_asset"])


def holding(conn: Connection, account, company_id, share_asset: str) -> int:
    """Every share an account owns of a company: those it holds, those offered to a takeover, and those in its sell orders."""
    return ledger.balance(conn, account, share_asset) + _one(
        conn, "SELECT (SELECT coalesce(sum(d.shares), 0) FROM takeover_tenders d JOIN takeovers t ON t.id = d.takeover_id"
              " WHERE d.account_id = %s AND t.target_company_id = %s AND t.status = 'open')"
              " + (SELECT coalesce(sum(remaining), 0) FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'sell'"
              " AND status = 'open') AS n", (account, company_id, account, company_id))["n"]


def _held_bps(conn: Connection, account, company: dict) -> int:
    issued = _in_issue(conn, company)
    return holding(conn, account, company["id"], company["share_asset"]) * BPS // issued if issued else 0


def buying_guard(conn: Connection, empire_id, company_id, quantity: int) -> None:
    """Before an empire buys a listed company's shares on the exchange: no creeping to 30% without an offer, and no
    buying into a company held by an empire it has a truce with."""
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (company_id,))
    empire = empires._empire(conn, empire_id)
    if company is None or not company["listed"] or empire["kind"] != "player":
        return
    _truce_guards(conn, empire_id, company)
    issued = _in_issue(conn, company)
    have = holding(conn, empire["account_id"], company_id, company["share_asset"])
    buying = _one(conn, "SELECT coalesce(sum(remaining), 0) AS n FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy'"
                        " AND status = 'open'", (empire["account_id"], company_id))["n"]
    if have * 2 <= issued and (have + buying + quantity) * BPS >= issued * MUST_OFFER_BPS:
        raise EmpireError("With this the empire would hold 30% or more: at that point an empire must make an offer to every owner instead.")


def _worth_per_share(conn: Connection, company_id) -> int | None:
    row = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1", (company_id,))
    return row["value_per_share"] if row else None


def _truce_guards(conn: Connection, empire_id, company: dict) -> None:
    """An empire may not move against a company held (a fifth or more) or controlled by an empire it has a truce with."""
    for other in _rows(conn, "SELECT e.* FROM empire_pacts p JOIN empires e ON e.id = CASE WHEN p.from_empire = %s THEN p.to_empire ELSE p.from_empire END"
                             " WHERE p.kind = 'truce' AND p.status = 'signed' AND %s IN (p.from_empire, p.to_empire)", (empire_id, empire_id)):
        if _held_bps(conn, other["account_id"], company) >= TRUCE_HOLDS_BPS or _one(
                conn, "SELECT 1 FROM owned_companies WHERE company_id = %s AND empire_id = %s", (company["id"], other["id"])):
            raise EmpireError(f"Your empire has a truce with {other['name']}, which holds a large part of {company['name']}. "
                              "Break the truce first, and pay for it in trust.")


def _player_empire(conn: Connection, player_id, build: str | None = None) -> tuple[dict, dict]:
    seat, empire = firm._active(conn, player_id)
    if not firm.player_run(empire) or empire["kind"] != "player":
        raise EmpireError("An empire run by the computer keeps to its own rules.")
    if build and not firm_deals._desk_ok(conn, empire, seat, build):
        raise EmpireError(f"That is the work of the {firm.DESK_NAMES[build]}'s desk.")
    return seat, empire


# ---------------------------------------------------------------------------
# Takeover offers by empires
# ---------------------------------------------------------------------------

def _offer_terms(conn: Connection, empire: dict, company_id, price: int, shares: int) -> dict:
    """Check an offer as it would be announced. Returns what is needed to announce it."""
    company = _listed(conn, company_id)
    if not _whole(price) or not _whole(shares):
        raise EmpireError("Name a price for each share and how many shares the empire wants.")
    if company["sector"] in corporate.FINANCIAL:
        raise EmpireError("Banks and insurers are not taken over by an empire: the Central Bank would not allow it.")
    market = corporate._market_price(conn, company_id)
    worth = _worth_per_share(conn, company_id) or market
    if price < market:
        raise EmpireError(f"An offer below the market price ({_money(market)}) would be accepted by nobody.")
    if price * BPS > max(market, worth) * OFFER_MOST_BPS:
        raise EmpireError("No board would let an offer that far above what the company is worth: it would be moving the members' money out.")
    issued = _in_issue(conn, company)
    have = ledger.balance(conn, empire["account_id"], company["share_asset"])
    if shares > issued - have:
        raise EmpireError(f"There are only {issued - have:,} shares the empire does not already hold.")
    if (have + shares) * 2 <= issued:
        raise EmpireError("An offer is for control: with what it holds, the empire must be asking for more than half the shares.")
    if _one(conn, "SELECT 1 FROM owned_companies WHERE company_id = %s", (company_id,)):
        raise EmpireError("That company is controlled by an empire already.")
    _truce_guards(conn, empire["id"], company)
    standing = corporate.bid_for(conn, company_id)
    if standing:
        if standing.get("bidder_empire_id") == empire["id"]:
            raise EmpireError("Your empire's offer for it is already on the table.")
        if price * BPS < standing["price"] * (BPS + TOP_BY_BPS):
            raise EmpireError(f"There is an offer of {_money(standing['price'])} a share on the table. A rival offer must beat it by at least 5%.")
    elif _one(conn, "SELECT 1 FROM share_offers WHERE company_id = %s AND status = 'open' UNION SELECT 1 FROM company_votes"
                    " WHERE company_id = %s AND status = 'open'", (company_id, company_id)):
        raise EmpireError("That company has a share sale or a vote under way. Wait for it to finish.")
    cost = price * shares
    if cost > ledger.balance(conn, empire["account_id"]):
        raise EmpireError(f"The offer needs {_money(cost)} held from the moment it is announced. The empire has not that much cash.")
    premium = (price - market) * BPS // market
    return {"company": company, "market": market, "premium": premium, "cost": cost, "standing": standing, "issued": issued, "have": have}


def draft_offer(conn: Connection, player_id, company_id, price: int, shares: int, now: datetime) -> dict:
    """The Investment Banker drafts a takeover offer. It goes to the head to sign."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _player_empire(conn, player_id, "investment_banker")
        t = _offer_terms(conn, empire, company_id, price, shares)
        payload = {"company_id": str(company_id), "price": price, "share_count": shares}
        if empire["head_player_id"] == player_id:
            # The head drafted it at the banker's desk: their signature is the head's.
            _announce(conn, {"empire_id": empire["id"], "payload": payload}, now)
            return {"announced": True, "cost": t["cost"], "premium_bps": t["premium"]}
        approval = firm.ask(conn, empire, kind="takeover_offer", desk="head", asked_by=player_id,
                            title=f"A takeover offer for {t['company']['name']}: {_money(price)} a share for {shares:,} shares",
                            amount=t["cost"], payload=payload, period=state["period"], now=now)
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} drafted a takeover offer for {t['company']['name']} for the head to sign.", now)
        return {"approval_id": approval["id"], "cost": t["cost"], "premium_bps": t["premium"]}


def _announce(conn: Connection, approval: dict, now: datetime) -> None:
    """The head signed: the offer is announced and its cash held. A higher offer replaces the one on the table."""
    empire = empires._empire(conn, approval["empire_id"], lock=True)
    p = approval["payload"]
    state = careers.world_now(conn, now)
    period = state["period"]
    t = _offer_terms(conn, empire, p["company_id"], p["price"], p["share_count"])
    company, price, shares = t["company"], p["price"], p["share_count"]
    held = bonds.held_account(conn)
    ledger.transfer(conn, payer=empire["account_id"], receiver=held, amount=t["cost"], kind="takeover_reserve",
                    memo=f"{empire['name']}: cash set aside for its offer for {company['name']}", period=period)
    old = t["standing"]
    if old:
        beaten = corporate._bidder(conn, old)
        if old["reserved"] > 0:
            ledger.transfer(conn, payer=held, receiver=beaten["account_id"], amount=old["reserved"], kind="takeover_refund",
                            memo=f"{beaten['name']}: cash set aside for its offer for {company['name']}, handed back: a higher offer was made",
                            period=period, reference=f"takeover:{old['id']}")
        conn.execute("UPDATE takeovers SET status = 'failed', reserved = 0, outcome = %s, closed_at = %s WHERE id = %s",
                     (f"Beaten by a higher offer of {_money(price)} a share from {empire['name']}. Shares offered were counted for the higher offer.",
                      now, old["id"]))
        if old.get("bidder_empire_id"):
            _log(conn, old["bidder_empire_id"], f"{empire['name']} topped the empire's offer for {company['name']} with {_money(price)} a share. "
                                                "The cash held for the offer was handed back.", now)
    hostile = t["premium"] < data.BOARD_ACCEPTS_PREMIUM_BPS
    bid = _one(conn, "INSERT INTO takeovers (bidder_empire_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved, opens_period,"
                     " closes_period, topped) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
               (empire["id"], company["id"], price, shares, hostile, t["premium"], t["cost"], period, period + 1, old["id"] if old else None))
    if old:
        # Owners who accepted the lower offer are counted for the higher one; the new bidder's own shares come back to it.
        mine = _one(conn, "SELECT shares FROM takeover_tenders WHERE takeover_id = %s AND account_id = %s", (old["id"], empire["account_id"]))
        if mine and mine["shares"] > 0:
            ledger.transfer(conn, payer=held, receiver=empire["account_id"], amount=mine["shares"], asset=company["share_asset"], kind="tender_release",
                            memo=f"{company['name']} shares handed back: the empire now makes its own offer", reference=f"takeover:{old['id']}")
        conn.execute("DELETE FROM takeover_tenders WHERE takeover_id = %s AND account_id = %s", (old["id"], empire["account_id"]))
        conn.execute("UPDATE takeover_tenders SET takeover_id = %s WHERE takeover_id = %s", (bid["id"], old["id"]))
        news.publish(conn, period=period, day=1, kind="offer_topped", story=f"takeover:{bid['id']}",
                     facts={"rival": empire["name"], "bidder": beaten["name"], "target": company["name"], "ticker": company["ticker"],
                            "price": corporate._naira(price)}, tickers=[company["ticker"]])
    stake = (t["have"] + shares) * BPS // t["issued"]
    words = (f"{empire['name']} offers {corporate._naira(price)} for each share of {company['name']}, {corporate._percent(t['premium'])} above the "
             f"market price, for {shares:,} shares ({corporate._big(t['cost'])} in all, held from today). "
             + (f"The board of {company['name']} rejects it as too low: the offer goes straight to the owners. " if hostile else
                f"The board of {company['name']} recommends that owners accept. ")
             + f"It closes when {clock.period_label(period + 1)} closes, and succeeds only if owners of more than half the shares accept. "
             "Another empire may top it by at least 5%.")
    corporate.notice(conn, period, company["id"], "takeover_bid", f"{empire['name']} makes an offer for {company['name']}", words, now)
    if not old:
        news.publish(conn, period=period, day=1, kind="empire_offer", story=f"takeover:{bid['id']}",
                     facts={"bidder": empire["name"], "target": company["name"], "ticker": company["ticker"], "price": corporate._naira(price),
                            "premium": corporate._percent(t["premium"]), "stake": corporate._percent(stake), "value": corporate._big(t["cost"]),
                            "board": "has rejected the offer" if hostile else "recommends the offer"},
                     tickers=[company["ticker"]], sectors=[company["sector"]])
    _reprice(conn, bid, company, t["market"], now)
    _log(conn, empire["id"], f"The empire offered {_money(price)} a share for {shares:,} shares of {company['name']}; {_money(t['cost'])} is held "
                             "until the offer closes.", now)


def _reprice(conn: Connection, bid: dict, company: dict, market: int, now: datetime) -> None:
    """Trading in the target starts again from what a share is worth with the offer on the table."""
    worth = _worth_per_share(conn, company["id"]) or market
    expected = corporate.expected_value(conn, bid, worth)
    if expected and expected != market:
        exchange.cancel_all_in(conn, company["id"], now, "Handed back: a takeover offer for the company changed what its shares are worth.")
        exchange.reprice(conn, company["id"], expected, now,
                         f"An offer of {corporate._naira(bid['price'])} a share is on the table. The price was adjusted from {corporate._naira(market)} "
                         f"to {corporate._naira(expected)}: what a share is worth if the offer succeeds, part bought at the offer price and the rest kept.")


def tender(conn: Connection, head_id, takeover_id: int, shares: int, now: datetime) -> dict:
    """The head offers the empire's shares of the target to a bidder (0 takes them back)."""
    with conn.transaction():
        _open(conn, now)
        empire = empires._head(conn, head_id)
        bid = _one(conn, "SELECT * FROM takeovers WHERE id = %s", (takeover_id,))
        if bid is None or bid["status"] != "open":
            raise EmpireError("That offer is not open.")
        if bid["bidder_empire_id"] == empire["id"]:
            raise EmpireError("An empire does not sell to its own offer.")
        try:
            done = corporate.tender(conn, account=empire["account_id"], takeover_id=takeover_id, shares=shares, now=now, empire_ok=True)
        except corporate.CorporateError as refused:
            raise EmpireError(str(refused)) from None
        _log(conn, empire["id"], f"The head offered {shares:,} shares to the takeover offer." if shares else "The head took the empire's shares back "
                                 "from the takeover offer.", now)
        return done


def _defence_terms(conn: Connection, bid: dict, company: dict) -> dict:
    rows = _rows(conn, "SELECT net_profit FROM company_results WHERE company_id = %s AND period >= 1 ORDER BY period DESC LIMIT 4", (company["id"],))
    profit = sum(r["net_profit"] for r in rows) * 4 // max(len(rows), 1)
    multiple = firm_practice.industry_multiple(conn, company["sector"], company["id"])
    issued = _in_issue(conn, company)
    value = max(profit, 0) * multiple // 100 // max(issued, 1)
    return fd.terms(
        f"Write the board's defence of {company['name']}: what each share is worth on the measure the market uses for its industry. "
        "If it holds up and the offer is below it, the board rejects the offer and tells the owners why.",
        [fd.fact("Profit a year, from its filed results", profit), fd.fact("Shares in issue", f"{issued:,}", "text"),
         fd.fact("Listed rivals are worth, for each naira of yearly profit", f"{multiple / 100:.2f} times", "text"),
         fd.fact("The offer, a share", bid["price"]), fd.fact("The market price", corporate._market_price(conn, company["id"]))],
        [fd.q_number("value", "What one share is worth on that measure (₦)")], {"value": value},
        method="yearly profit × the industry's multiple ÷ shares in issue")


def open_defence(conn: Connection, player_id, takeover_id: int, now: datetime) -> dict:
    """The Investment Banker of an empire holding 5% or more of the target opens the board's defence. One defence an offer."""
    with conn.transaction():
        _open(conn, now)
        seat, empire = _player_empire(conn, player_id, "investment_banker")
        bid = _one(conn, "SELECT * FROM takeovers WHERE id = %s FOR UPDATE", (takeover_id,))
        if bid is None or bid["status"] != "open":
            raise EmpireError("That offer is not open.")
        if bid["bidder_empire_id"] == empire["id"]:
            raise EmpireError("An empire does not defend a company against its own offer.")
        company = _listed(conn, bid["target_company_id"])
        if _held_bps(conn, empire["account_id"], company) < DEFEND_FROM_BPS:
            raise EmpireError("The board takes advice from owners of 5% of the shares or more. Your empire holds less.")
        if bid["defence_value"] is not None or (bid["defence_terms"] or {}).get("done"):
            raise EmpireError("The board's defence has been handed in.")
        mine = bid["defence_terms"] is not None and bid["defence_by"] == player_id
        stale = bid["defence_terms"] is not None and not mine and firm._hours(datetime.fromisoformat(bid["defence_terms"]["opened_at"]), now) >= DEFENCE_HOURS
        if bid["defence_terms"] is not None and not mine and not stale:
            raise EmpireError("The board's defence is already being written by another adviser. If it is not handed in within a day, "
                              "the board will take another's.")
        if bid["defence_terms"] is None or stale:
            terms = {**_defence_terms(conn, bid, company), "opened_at": now.isoformat()}
            conn.execute("UPDATE takeovers SET defence_terms = %s, defence_by = %s, defence_empire_id = %s WHERE id = %s",
                         (Jsonb(terms), player_id, empire["id"], takeover_id))
            bid = {**bid, "defence_terms": terms}
        return {"takeover_id": takeover_id, "terms": firm._public_terms(bid["defence_terms"])}


def hand_in_defence(conn: Connection, player_id, takeover_id: int, answers: dict, now: datetime) -> dict:
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _player_empire(conn, player_id, "investment_banker")
        bid = _one(conn, "SELECT * FROM takeovers WHERE id = %s FOR UPDATE", (takeover_id,))
        if bid is None or bid["status"] != "open" or bid["defence_by"] != player_id or bid["defence_terms"] is None:
            raise EmpireError("Open the defence first.")
        if bid["defence_terms"].get("done"):
            raise EmpireError("The defence has been handed in.")
        if not isinstance(answers, dict):
            raise EmpireError("The answers did not arrive in a form that can be read.")
        terms = bid["defence_terms"]
        result = fd.mark({"conn": conn}, terms, answers)
        score = max(0, min(100, int(result["score"])))
        well = score >= firm.DUTY_PASS
        value = terms["_truth"]["value"]
        conn.execute("UPDATE takeovers SET defence_terms = defence_terms || '{\"done\": true}'::jsonb WHERE id = %s", (takeover_id,))
        company = _listed(conn, bid["target_company_id"])
        words = "The defence did not hold up: the board could not stand on it."
        if well:
            conn.execute("UPDATE takeovers SET defence_value = %s WHERE id = %s", (value, takeover_id))
            bidder = corporate._bidder(conn, bid)
            if bid["price"] < value:
                conn.execute("UPDATE takeovers SET hostile = true WHERE id = %s", (takeover_id,))
                words = (f"The board of {company['name']} published its defence: each share is worth {_money(value)}, above the offer of "
                         f"{_money(bid['price'])}. It rejects the offer.")
                news.publish(conn, period=state["period"], day=1, kind="defence_published", story=f"defence:{takeover_id}",
                             facts={"target": company["name"], "ticker": company["ticker"], "worth": corporate._naira(value),
                                    "price": corporate._naira(bid["price"]), "bidder": bidder["name"]}, tickers=[company["ticker"]])
            else:
                words = f"The defence holds up, but the offer is above what it shows each share is worth ({_money(value)}): the board cannot object."
            corporate.notice(conn, state["period"], company["id"], "takeover_defence", f"{company['name']}: the board's defence", words, now)
            fresh = _one(conn, "SELECT * FROM takeovers WHERE id = %s", (takeover_id,))
            _reprice(conn, fresh, company, corporate._market_price(conn, company["id"]), now)
        mine = careers.career(conn, player_id, seat["build"])
        gained = firm.DUTY_EXPERIENCE * score // 100 * (1 + (mine["rank"] if mine else 0))
        if gained and mine:
            careers.add_experience(conn, player_id, seat["build"], gained, now)
        _log(conn, empire["id"], f"{firm._name(conn, player_id)} handed in the board's defence of {company['name']} (marked {score} out of 100).", now)
        return {"score": score, "result": {**result, "lines": [{"label": x["label"], "right": x["right"]} for x in result["lines"]], "words": ""},
                "words": words}


def _takeover_closed(conn: Connection, bid: dict, target: dict, period: int, now: datetime) -> None:
    """An empire's offer has closed: the empire's records, and the news."""
    if not bid.get("bidder_empire_id"):
        return
    empire = empires._empire(conn, bid["bidder_empire_id"])
    issued = _in_issue(conn, target)
    stake = ledger.balance(conn, empire["account_id"], target["share_asset"]) * BPS // max(issued, 1)
    if bid["status"] == "won":
        news.publish(conn, period=period + 1, day=1, kind="empire_offer_won", story=f"takeover:{bid['id']}:won",
                     facts={"bidder": empire["name"], "target": target["name"], "ticker": target["ticker"], "price": corporate._naira(bid["price"]),
                            "stake": corporate._percent(stake), "value": corporate._big(bid["paid"])}, tickers=[target["ticker"]])
        _log(conn, empire["id"], f"The offer for {target['name']} succeeded: the empire bought {bid['bought']:,} shares for {_money(bid['paid'])} "
                                 f"and holds {corporate._percent(stake)}.", now)
        leagues.award(conn, empire["id"], 2, f"Took control of {target['name']}", period, now, reference=f"takeover:{bid['id']}")
        for member in empires.humans(conn, empire["id"]):
            careers._event(conn, member["player_id"], member["build"], "deal", f"{empire['name']} took control of {target['name']}.", now)
    else:
        accepted = _one(conn, "SELECT accepted FROM takeovers WHERE id = %s", (bid["id"],))["accepted"] or 0
        news.publish(conn, period=period + 1, day=1, kind="empire_offer_failed", story=f"takeover:{bid['id']}:failed",
                     facts={"bidder": empire["name"], "target": target["name"], "ticker": target["ticker"], "price": corporate._naira(bid["price"]),
                            "accepted": corporate._percent(accepted * BPS // max(issued, 1))}, tickers=[target["ticker"]])
        _log(conn, empire["id"], f"The offer for {target['name']} failed. The cash held for it was handed back.", now)


# ---------------------------------------------------------------------------
# Stake building, and disclosure
# ---------------------------------------------------------------------------

def start_stake(conn: Connection, player_id, company_id, target_bps: int, most_price: int, now: datetime) -> dict:
    """The Asset Manager asks to build a stake in a listed company, a little at each bell, up to a target below 30%."""
    with conn.transaction():
        state = _open(conn, now)
        seat, empire = _player_empire(conn, player_id, "asset_manager")
        company = _listed(conn, company_id)
        if not _whole(target_bps, 100, MUST_OFFER_BPS - 1):
            raise EmpireError("A target from 1% to just under 30%: at 30% an empire must make an offer for the whole company.")
        market = corporate._market_price(conn, company_id)
        if not _whole(most_price) or most_price * BPS > market * OFFER_MOST_BPS:
            raise EmpireError("Name the most the empire will pay for a share (no more than half as much again as the market price).")
        if _held_bps(conn, empire["account_id"], company) >= target_bps:
            raise EmpireError("The empire already holds that much.")
        _truce_guards(conn, empire["id"], company)
        if _one(conn, "SELECT 1 FROM stake_programmes WHERE empire_id = %s AND company_id = %s AND status = 'running'", (empire["id"], company_id)):
            raise EmpireError("The empire is already building a stake in it.")
        need = _in_issue(conn, company) * target_bps // BPS - ledger.balance(conn, empire["account_id"], company["share_asset"])
        payload = {"company_id": str(company_id), "target_bps": target_bps, "most_price": most_price}
        if empire["head_player_id"] == player_id:
            _start_programme(conn, {"empire_id": empire["id"], "payload": payload, "asked_by": player_id}, now)
            return {"started": True}
        approval = firm.ask(conn, empire, kind="stake_programme", desk="head", asked_by=player_id,
                            title=f"Build a stake of {corporate._percent(target_bps)} in {company['name']}, paying up to {_money(most_price)} a share",
                            amount=max(need, 0) * most_price, payload=payload, period=state["period"], now=now)
        return {"approval_id": approval["id"]}


def _start_programme(conn: Connection, approval: dict, now: datetime) -> None:
    p = approval["payload"]
    empire = empires._empire(conn, approval["empire_id"])
    company = _listed(conn, p["company_id"])
    _truce_guards(conn, empire["id"], company)
    if _one(conn, "SELECT 1 FROM stake_programmes WHERE empire_id = %s AND company_id = %s AND status = 'running'", (empire["id"], company["id"])):
        raise EmpireError("The empire is already building a stake in it.")
    conn.execute("INSERT INTO stake_programmes (empire_id, company_id, target_bps, most_price, set_by, at) VALUES (%s, %s, %s, %s, %s, %s)",
                 (empire["id"], company["id"], p["target_bps"], p["most_price"], approval["asked_by"], now))
    _log(conn, empire["id"], f"The empire began building a stake in {company['name']}, up to {corporate._percent(p['target_bps'])}.", now)


def stop_stake(conn: Connection, player_id, programme_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        seat, empire = _player_empire(conn, player_id, "asset_manager")
        done = conn.execute("UPDATE stake_programmes SET status = 'stopped' WHERE id = %s AND empire_id = %s AND status = 'running'",
                            (programme_id, empire["id"])).rowcount
        if not done:
            raise EmpireError("There is no such stake being built.")
        _cancel_buys(conn, empire, _one(conn, "SELECT company_id FROM stake_programmes WHERE id = %s", (programme_id,))["company_id"], now)


def _cancel_buys(conn: Connection, empire: dict, company_id, now: datetime) -> None:
    for order in _rows(conn, "SELECT id FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                       (empire["account_id"], company_id)):
        try:
            with conn.transaction():
                exchange.cancel_order(conn, account=empire["account_id"], order_id=order["id"], now=now)
        except exchange.ExchangeError:
            pass


def _build_stakes(conn: Connection, now: datetime) -> None:
    """At each bell: each stake being built buys a little more, patiently, never above its most."""
    for row in _rows(conn, "SELECT id FROM stake_programmes WHERE status = 'running' ORDER BY id"):
        with conn.transaction():
            prog = _one(conn, "SELECT * FROM stake_programmes WHERE id = %s AND status = 'running' FOR UPDATE", (row["id"],))
            if prog is None:
                continue
            empire = empires._empire(conn, prog["empire_id"])
            company = _one(conn, "SELECT * FROM companies WHERE id = %s", (prog["company_id"],))
            if empire["status"] != "active" or not company["listed"] or company["status"] != "trading" or corporate.bid_for(conn, company["id"]):
                conn.execute("UPDATE stake_programmes SET status = 'stopped' WHERE id = %s", (prog["id"],))
                _cancel_buys(conn, empire, company["id"], now)
                continue
            issued = _in_issue(conn, company)
            have = ledger.balance(conn, empire["account_id"], company["share_asset"])
            want = issued * prog["target_bps"] // BPS - have
            if want <= 0:
                conn.execute("UPDATE stake_programmes SET status = 'done' WHERE id = %s", (prog["id"],))
                _log(conn, empire["id"], f"The stake in {company['name']} reached its target of {corporate._percent(prog['target_bps'])}.", now)
                continue
            if _one(conn, "SELECT 1 FROM market_orders WHERE account_id = %s AND company_id = %s AND side = 'buy' AND status = 'open'",
                    (empire["account_id"], company["id"])):
                continue
            share = _one(conn, "SELECT c.ticker, m.reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE m.company_id = %s",
                         (company["id"],))
            low, high = exchange.price_limits(share["reference_price"])
            try:
                with conn.transaction():
                    # Never against the empire's own people's orders, and at the day's reference price (a member cannot push
                    # the price the programme pays by bidding it up first).
                    empires.no_dealing_with_yourself(conn, empire["account_id"], company["id"], "buy", empires._insiders(conn, empire["id"]), "the empire")
                    buying_guard(conn, empire["id"], company["id"], 0)
                    price = min(prog["most_price"], high, share["reference_price"])
                    if price < low:
                        continue
                    quantity = min(want, max(issued * STAKE_BELL_BPS // BPS, 1), ledger.balance(conn, empire["account_id"]) // max(price, 1))
                    if quantity > 0:
                        exchange.place_order(conn, account=empire["account_id"], ticker=share["ticker"], side="buy", kind="limit",
                                             quantity=quantity, limit_price=price, now=now)
            except (exchange.ExchangeError, ledger.LedgerError, EmpireError):
                pass


def disclose(conn: Connection, now: datetime) -> None:
    """Every 5% step an empire holds in a listed company is made public: crossing it up, or falling below it."""
    period = careers.world_now(conn, now)["period"]
    rows = _rows(conn, "SELECT e.id AS empire_id, e.name AS empire, e.account_id, c.id AS company_id, c.name AS company, c.ticker, c.share_asset,"
                       " d.bps AS disclosed FROM empires e CROSS JOIN companies c"
                       " LEFT JOIN ledger_balances b ON b.account_id = e.account_id AND b.asset = c.share_asset"
                       " LEFT JOIN stake_disclosures d ON d.empire_id = e.id AND d.company_id = c.id"
                       " WHERE e.kind IN ('player', 'computer') AND e.status IN ('active', 'merged') AND c.listed AND c.status = 'trading'"
                       " AND (coalesce(b.balance, 0) > 0 OR d.bps > 0 OR EXISTS (SELECT 1 FROM market_orders o WHERE o.account_id = e.account_id"
                       " AND o.company_id = c.id AND o.side = 'sell' AND o.status = 'open') OR EXISTS (SELECT 1 FROM takeover_tenders t"
                       " WHERE t.account_id = e.account_id AND t.shares > 0)) ORDER BY e.id, c.ticker")
    for r in rows:
        issued = ledger.amount_in_existence(conn, r["share_asset"])
        owned = holding(conn, r["account_id"], r["company_id"], r["share_asset"])
        step = owned * BPS // max(issued, 1) // DISCLOSE_STEP_BPS * DISCLOSE_STEP_BPS
        if step == (r["disclosed"] or 0):
            continue
        conn.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, %s, %s) ON CONFLICT (empire_id, company_id)"
                     " DO UPDATE SET bps = excluded.bps, at = excluded.at", (r["empire_id"], r["company_id"], step, now))
        conn.execute("UPDATE stake_programmes SET disclosed_bps = %s WHERE empire_id = %s AND company_id = %s AND status = 'running'",
                     (step, r["empire_id"], r["company_id"]))
        words = (f"{r['empire']} now holds {corporate._percent(step)} or more of {r['company']}." if step else
                 f"{r['empire']} now holds less than 5% of {r['company']}.")
        corporate.notice(conn, period, r["company_id"], "stake_disclosed", f"{r['company']}: {r['empire']} discloses its holding", words, now)
        if step >= (r["disclosed"] or 0) and step:
            news.publish(conn, period=period, day=1, kind="stake_disclosed", story=f"stake:{r['empire_id']}:{r['company_id']}:{step}",
                         facts={"empire": r["empire"], "company": r["company"], "ticker": r["ticker"], "stake": corporate._percent(step)},
                         tickers=[r["ticker"]])


# ---------------------------------------------------------------------------
# Block trades between empires
# ---------------------------------------------------------------------------

def _block_check(conn: Connection, seller: dict, buyer: dict, company: dict, shares: int, price: int) -> None:
    market = corporate._market_price(conn, company["id"])
    if not _whole(shares) or not _whole(price):
        raise EmpireError("Name how many shares and the price for each.")
    if abs(price - market) * BPS > market * BLOCK_BAND_BPS:
        raise EmpireError(f"A block changes hands within a tenth of the market price ({_money(market)}): otherwise it would be moving money, "
                          "not selling shares.")
    if corporate.bid_for(conn, company["id"]):
        raise EmpireError("While a takeover offer is open, shares change hands through the offer or the exchange.")
    if ledger.balance(conn, seller["account_id"], company["share_asset"]) < shares:
        raise EmpireError("The selling empire does not hold that many shares free to sell (shares in a sell order must be freed first).")
    issued = _in_issue(conn, company)
    after = (ledger.balance(conn, buyer["account_id"], company["share_asset"]) + shares) * BPS // max(issued, 1)
    if after >= MUST_OFFER_BPS and _held_bps(conn, buyer["account_id"], company) <= 5000:
        raise EmpireError("With the block the buyer would hold 30% or more: at that point an empire must make an offer to every owner instead.")


def offer_block(conn: Connection, head_id, buyer_empire_id: int, company_id, shares: int, price: int, now: datetime) -> dict:
    """The head offers a block of the empire's shares in a listed company to another empire."""
    with conn.transaction():
        _open(conn, now)
        seller = empires._head(conn, head_id)
        if seller["kind"] != "player" or seller["status"] != "active":
            raise EmpireError("Your empire is not open.")
        buyer = _one(conn, "SELECT * FROM empires WHERE id = %s AND kind = 'player' AND status = 'active' AND head_player_id IS NOT NULL", (buyer_empire_id,))
        if buyer is None or buyer["id"] == seller["id"]:
            raise EmpireError("A block is sold to another empire run by players.")
        company = _listed(conn, company_id)
        _block_check(conn, seller, buyer, company, shares, price)
        if _one(conn, "SELECT 1 FROM block_trades WHERE seller_empire_id = %s AND company_id = %s AND status = 'offered'", (seller["id"], company_id)):
            raise EmpireError("The empire already has a block of these shares on offer.")
        block = _one(conn, "INSERT INTO block_trades (seller_empire_id, buyer_empire_id, company_id, shares, price, offered_by, at)"
                           " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id", (seller["id"], buyer["id"], company_id, shares, price, head_id, now))
        _log(conn, seller["id"], f"The head offered {buyer['name']} a block of {shares:,} {company['name']} shares at {_money(price)} each.", now)
        _log(conn, buyer["id"], f"{seller['name']} offers the empire a block of {shares:,} {company['name']} shares at {_money(price)} each.", now)
        return {"block_id": block["id"]}


def answer_block(conn: Connection, head_id, block_id: int, accept: bool, now: datetime) -> dict:
    """The buying empire's head takes the block or turns it down. Shares and money move together, at once."""
    with conn.transaction():
        state = _open(conn, now)
        buyer = empires._head(conn, head_id)
        block = _one(conn, "SELECT * FROM block_trades WHERE id = %s AND buyer_empire_id = %s AND status = 'offered' FOR UPDATE", (block_id, buyer["id"]))
        if block is None:
            raise EmpireError("There is no such block on offer to your empire.")
        if not accept:
            conn.execute("UPDATE block_trades SET status = 'refused', answered_by = %s, done_at = %s WHERE id = %s", (head_id, now, block_id))
            _log(conn, block["seller_empire_id"], f"{buyer['name']} turned down the block of shares.", now)
            return {"accepted": False}
        seller = empires._empire(conn, block["seller_empire_id"], lock=True)
        company = _listed(conn, block["company_id"])
        _block_check(conn, seller, buyer, company, block["shares"], block["price"])
        cost = block["shares"] * block["price"]
        if ledger.balance(conn, buyer["account_id"]) < cost:
            raise EmpireError(f"The block costs {_money(cost)}. The empire has not that much cash.")
        ledger.post(conn, kind="block_trade", memo=f"{block['shares']:,} {company['name']} shares from {seller['name']} to {buyer['name']}",
                    period=state["period"], reference=f"block:{block_id}",
                    legs=[Leg(seller["account_id"], -block["shares"], company["share_asset"]), Leg(buyer["account_id"], block["shares"], company["share_asset"]),
                          Leg(buyer["account_id"], -cost), Leg(seller["account_id"], cost)])
        after = corporate._after_trade(conn)
        for account, shares, amount in ((seller["account_id"], -block["shares"], cost), (buyer["account_id"], block["shares"], cost)):
            conn.execute("INSERT INTO holding_events (account_id, company_id, kind, shares, amount, after_trade_id) VALUES (%s, %s, 'block', %s, %s, %s)",
                         (account, company["id"], shares, amount, after))
        conn.execute("UPDATE block_trades SET status = 'done', answered_by = %s, done_at = %s WHERE id = %s", (head_id, now, block_id))
        news.publish(conn, period=state["period"], day=1, kind="block_trade", story=f"block:{block_id}",
                     facts={"seller": seller["name"], "buyer": buyer["name"], "company": company["name"], "ticker": company["ticker"],
                            "shares": corporate._words(block["shares"]), "amount": corporate._big(cost)}, tickers=[company["ticker"]])
        for e, words in ((seller, f"sold a block of {block['shares']:,} {company['name']} shares to {buyer['name']} for {_money(cost)}"),
                         (buyer, f"bought a block of {block['shares']:,} {company['name']} shares from {seller['name']} for {_money(cost)}")):
            _log(conn, e["id"], f"The empire {words}.", now)
        disclose(conn, now)
        return {"accepted": True, "cost": cost}


def withdraw_block(conn: Connection, head_id, block_id: int, now: datetime) -> None:
    with conn.transaction():
        _open(conn, now)
        seller = empires._head(conn, head_id)
        if not conn.execute("UPDATE block_trades SET status = 'withdrawn', done_at = %s WHERE id = %s AND seller_empire_id = %s AND status = 'offered'",
                            (now, block_id, seller["id"])).rowcount:
            raise EmpireError("There is no such block of yours on offer.")


# ---------------------------------------------------------------------------
# The portfolio of private companies
# ---------------------------------------------------------------------------

def portfolio(conn: Connection, empire: dict, period: int) -> list[dict]:
    """The empire's private-equity holdings: what it paid, what its share is worth on the latest valuation, the multiple of money."""
    out = []
    for r in _rows(conn, "SELECT s.*, c.name, c.ticker, c.share_asset, c.status, sec.name AS sector, o.empire_id AS controller FROM company_stakes s"
                         " JOIN companies c ON c.id = s.company_id JOIN sectors sec ON sec.code = c.sector"
                         " LEFT JOIN owned_companies o ON o.company_id = c.id WHERE s.empire_id = %s ORDER BY s.cost DESC", (empire["id"],)):
        held = ledger.balance(conn, empire["account_id"], r["share_asset"])
        issued = max(ledger.amount_in_existence(conn, r["share_asset"]), 1)
        value = private.value_of(conn, r["company_id"]) * held // issued
        out.append({"company_id": r["company_id"], "name": r["name"], "sector": r["sector"], "cost": r["cost"], "value": value,
                    "share_bps": held * BPS // issued, "multiple_x100": value * 100 // r["cost"] if r["cost"] else None,
                    "quarters": max(period - r["since_period"], 0), "controls": r["controller"] == empire["id"], "status": r["status"]})
    return out


# ---------------------------------------------------------------------------
# Mergers and spin-offs
# ---------------------------------------------------------------------------

def _merge_blockers(conn: Connection, joining: dict) -> list[str]:
    """What must be settled before an empire can join another: nothing of its may be left half-done."""
    e, a = joining["id"], joining["account_id"]
    checks = (
        ("SELECT 1 FROM empire_debts WHERE empire_id = %s AND status IN ('open', 'called', 'defaulted')", (e,), "it still owes money: repay its debts first"),
        ("SELECT 1 FROM deal_bids WHERE empire_id = %s AND status IN ('pending', 'live')", (e,), "it has a bid for a company under way"),
        ("SELECT 1 FROM deal_partners WHERE empire_id = %s AND status IN ('invited', 'pledged')", (e,), "it has money pledged to another empire's bid"),
        ("SELECT 1 FROM sale_processes WHERE seller_empire_id = %s AND status = 'open'", (e,), "it has a company on sale"),
        ("SELECT 1 FROM deals WHERE seller_account = %s AND escrow > 0", (a,), "money from a company it sold is still held back against claims"),
        ("SELECT 1 FROM takeovers WHERE bidder_empire_id = %s AND status = 'open'", (e,), "it has a takeover offer open"),
        ("SELECT 1 FROM takeover_tenders d JOIN takeovers t ON t.id = d.takeover_id WHERE d.account_id = %s AND t.status = 'open' AND d.shares > 0",
         (a,), "it has shares offered to a takeover"),
        ("SELECT 1 FROM offer_subscriptions s JOIN share_offers o ON o.id = s.offer_id WHERE s.account_id = %s AND o.status = 'open' AND s.held > 0",
         (a,), "it has applied for new shares"),
        ("SELECT 1 FROM stake_programmes WHERE empire_id = %s AND status = 'running'", (e,), "it is building a stake"),
        ("SELECT 1 FROM block_trades WHERE %s IN (seller_empire_id, buyer_empire_id) AND status = 'offered'", (e,), "it has a block of shares on offer"),
        ("SELECT 1 FROM bank_loan_offers WHERE empire_id = %s AND status = 'offered'", (e,), "it has a bank's loan offer waiting"),
        ("SELECT 1 FROM share_offers o JOIN owned_companies c ON c.company_id = o.company_id WHERE c.empire_id = %s AND o.status = 'open'", (e,),
         "a company it owns is being listed"),
        ("SELECT 1 FROM empire_stake_offers WHERE empire_id = %s AND status = 'open'", (e,), "it is selling a stake in itself"),
        ("SELECT 1 FROM empire_cases WHERE empire_id = %s AND status = 'open'", (e,), "a case of money taken is waiting to be decided"),
        ("SELECT 1 FROM deal_files WHERE empire_id = %s AND status = 'open'", (e,), "it has a deal file open"),
        ("SELECT 1 FROM firm_jobs WHERE client_empire_id = %s AND status = 'open'", (e,), "a firm is doing work for it"),
        ("SELECT 1 FROM empire_resolutions WHERE empire_id = %s AND status = 'open' AND kind <> 'merger_join'", (e,), "its members have a vote open"),
    )
    return [why for sql, params, why in checks if _one(conn, sql, params)]


def _seats_fit(conn: Connection, continuing: dict, joining: dict) -> list[str]:
    short = []
    for build in data.EMPIRE_BUILDS:
        need = sum(1 for h in empires.humans(conn, joining["id"]) if h["build"] == build)
        have = _one(conn, "SELECT count(*) AS n FROM empire_seats WHERE empire_id = %s AND build = %s AND player_id IS NULL",
                    (continuing["id"], build))["n"]
        if need > have:
            short.append(firm.DESK_NAMES[build])
    return short


def _merger_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    other_id = payload.get("other_empire_id")
    if not _whole(other_id):
        raise EmpireError("Choose the empire to merge with.")
    other = _one(conn, "SELECT * FROM empires WHERE id = %s AND kind = 'player' AND status = 'active' AND head_player_id IS NOT NULL", (other_id,))
    if other is None or other["id"] == empire["id"]:
        raise EmpireError("An empire merges with another open empire run by players.")
    if _one(conn, "SELECT 1 FROM empire_combinations WHERE status = 'voting' AND (empire_id IN (%s, %s) OR other_empire_id IN (%s, %s))",
            (empire["id"], other["id"], empire["id"], other["id"])):
        raise EmpireError("One of the two empires already has a merger or a split being voted on.")
    blockers = _merge_blockers(conn, other)
    if blockers:
        raise EmpireError(f"{other['name']} cannot join yet: " + "; ".join(blockers) + ".")
    short = _seats_fit(conn, empire, other)
    if short:
        raise EmpireError("Not every member of the other empire would have a seat: there are too few free seats for " + ", ".join(short) + ".")
    return {"other_empire_id": other["id"], "other": other["name"]}


def _merger_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    p = resolution["payload"]
    _merger_check(conn, empire, {"other_empire_id": p["other_empire_id"]}, now)
    period = careers.world_now(conn, now)["period"]
    combo = _one(conn, "INSERT INTO empire_combinations (kind, empire_id, other_empire_id, status, resolution_ids, period, at)"
                       " VALUES ('merger', %s, %s, 'voting', %s, %s, %s) RETURNING id", (empire["id"], p["other_empire_id"], [resolution["id"]], period, now))
    _log(conn, p["other_empire_id"], f"{empire['name']}'s members voted to merge with this empire, which would join theirs. Its head may put the "
                                     "merger to this empire's members (Requests and votes).", now)
    return f"Now {p['other']}'s members must agree (merger {combo['id']})."


def _join_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    combo = _one(conn, "SELECT c.*, e.name FROM empire_combinations c JOIN empires e ON e.id = c.empire_id WHERE c.id = %s AND c.kind = 'merger'"
                       " AND c.other_empire_id = %s AND c.status = 'voting'", (payload.get("combination_id"), empire["id"]))
    if combo is None:
        raise EmpireError("No empire has voted to merge with yours.")
    return {"combination_id": combo["id"], "into": combo["name"]}


def _join_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    combo = _one(conn, "SELECT * FROM empire_combinations WHERE id = %s AND status = 'voting' FOR UPDATE", (resolution["payload"]["combination_id"],))
    if combo is None:
        raise EmpireError("The merger is no longer waiting.")
    return merge(conn, combo, resolution["id"], now)


def _join_failed(conn: Connection, resolution: dict, now: datetime) -> None:
    conn.execute("UPDATE empire_combinations SET status = 'refused' WHERE id = %s AND status = 'voting'", (resolution["payload"].get("combination_id"),))


def merge(conn: Connection, combo: dict, resolution_id: int, now: datetime) -> str:
    """Both empires' members agreed: the joining empire's money, shares and companies pass to the continuing one; its
    owners receive units in the continuing empire worth what theirs were; its members take seats there."""
    period = careers.world_now(conn, now)["period"]
    into = empires._empire(conn, combo["empire_id"], lock=True)
    joining = empires._empire(conn, combo["other_empire_id"], lock=True)
    if into["status"] != "active" or joining["status"] != "active":
        raise EmpireError("One of the empires has closed.")
    blockers = _merge_blockers(conn, joining)
    if blockers:
        raise EmpireError(f"{joining['name']} cannot join yet: " + "; ".join(blockers) + ".")
    if _seats_fit(conn, into, joining):
        raise EmpireError("Not every member would have a seat.")
    exchange.withdraw(conn, [joining["account_id"]], now, f"Handed back: {joining['name']} is merging into {into['name']}.")
    firm_money.ensure_units(conn, into)
    firm_money.ensure_units(conn, joining)
    worth_into, worth_joining = empires.worth(conn, into, now)["total"], empires.worth(conn, joining, now)["total"]
    units_into, units_joining = firm_money.units_total(conn, into["id"]), firm_money.units_total(conn, joining["id"])
    if worth_into <= 0 or worth_joining <= 0:
        raise EmpireError("An empire worth nothing or less cannot be merged: its owners' units could not be priced.")
    # Everything the joining empire holds moves, asset by asset.
    legs = []
    for b in _rows(conn, "SELECT asset, balance FROM ledger_balances WHERE account_id = %s AND balance > 0 ORDER BY asset", (joining["account_id"],)):
        legs += [Leg(joining["account_id"], -b["balance"], b["asset"]), Leg(into["account_id"], b["balance"], b["asset"])]
    if legs:
        ledger.post(conn, kind="empire_merger", memo=f"{joining['name']} merges into {into['name']}", period=period, reference=f"merger:{combo['id']}",
                    legs=legs)
    # Its stakes and deals pass on.
    for stake in _rows(conn, "SELECT * FROM company_stakes WHERE empire_id = %s", (joining["id"],)):
        conn.execute("INSERT INTO company_stakes (company_id, empire_id, cost, since_period) VALUES (%s, %s, %s, %s) ON CONFLICT (company_id, empire_id)"
                     " DO UPDATE SET cost = company_stakes.cost + excluded.cost, since_period = least(company_stakes.since_period, excluded.since_period)",
                     (stake["company_id"], into["id"], stake["cost"], stake["since_period"]))
        conn.execute("DELETE FROM company_stakes WHERE company_id = %s AND empire_id = %s", (stake["company_id"], joining["id"]))
        conn.execute("UPDATE deals SET empire_id = %s WHERE empire_id = %s AND company_id = %s AND status = 'held'", (into["id"], joining["id"], stake["company_id"]))
        firm_deals._take_control(conn, stake["company_id"], period, now)
    # Its owners' units become units of the continuing empire, worth the same.
    for u in _rows(conn, "SELECT * FROM empire_units WHERE empire_id = %s AND units > 0 FOR UPDATE", (joining["id"],)):
        new = u["units"] * worth_joining * units_into // (units_joining * worth_into)
        if new > 0:
            conn.execute("INSERT INTO empire_units (empire_id, holder_account, player_id, units) VALUES (%s, %s, %s, %s) ON CONFLICT (empire_id, holder_account)"
                         " DO UPDATE SET units = empire_units.units + excluded.units", (into["id"], u["holder_account"], u["player_id"], new))
        conn.execute("UPDATE empire_units SET units = 0 WHERE empire_id = %s AND holder_account = %s", (joining["id"], u["holder_account"]))
    # Its members take seats in the continuing empire.
    for member in empires.humans(conn, joining["id"]):
        seat = empires.seat_of(conn, member["player_id"], lock=True)
        empires._vacate(conn, seat, now, period, "merged")
        empires._take_seat(conn, into, member["player_id"], member["build"], now, period)
    # Thefts nobody has found yet go with it: the continuing empire's audits can still find them.
    conn.execute("UPDATE empire_books SET empire_id = %s WHERE empire_id = %s AND NOT genuine AND NOT found", (into["id"], joining["id"]))
    conn.execute("UPDATE empires SET status = 'merged', head_player_id = NULL WHERE id = %s", (joining["id"],))
    conn.execute("UPDATE empire_seats SET staffed = false WHERE empire_id = %s", (joining["id"],))
    conn.execute("UPDATE empire_pacts SET status = 'ended' WHERE status IN ('drafted', 'proposed', 'signed') AND %s IN (from_empire, to_empire)",
                 (joining["id"],))
    conn.execute("UPDATE empire_combinations SET status = 'done', worth_moved = %s, resolution_ids = resolution_ids || %s::bigint WHERE id = %s",
                 (worth_joining, resolution_id, combo["id"]))
    news.publish(conn, period=period, day=1, kind="empires_merge", story=f"merger:{combo['id']}", facts={"empire": into["name"], "other": joining["name"]})
    _log(conn, into["id"], f"{joining['name']} merged into the empire: its money, shares and companies are now the empire's, its owners hold units here, "
                           "and its members have taken seats.", now)
    _log(conn, joining["id"], f"The empire merged into {into['name']}.", now)
    return f"{joining['name']} has merged into {into['name']}."


def _spinoff_check(conn: Connection, empire: dict, payload: dict, now: datetime) -> dict:
    owned = _one(conn, "SELECT o.*, c.name, c.share_asset FROM owned_companies o JOIN companies c ON c.id = o.company_id WHERE o.company_id::text = %s"
                       " AND o.empire_id = %s AND NOT c.listed AND c.status = 'trading'", (str(payload.get("company_id")), empire["id"]))
    if owned is None:
        raise EmpireError("Choose a private company your empire controls.")
    if _one(conn, "SELECT 1 FROM empire_debts WHERE empire_id = %s AND company_id = %s AND status IN ('open', 'called', 'defaulted')",
            (empire["id"], owned["company_id"])):
        raise EmpireError("Its buyout loan is secured on it: repay the loan first.")
    if _one(conn, "SELECT 1 FROM sale_processes WHERE company_id = %s AND status = 'open' UNION SELECT 1 FROM share_offers WHERE company_id = %s"
                  " AND status = 'open'", (owned["company_id"], owned["company_id"])):
        raise EmpireError("It is on sale, or being listed.")
    name = _text(str(payload.get("new_name") or ""))
    if not 3 <= len(name) <= 40 or _one(conn, "SELECT 1 FROM empires WHERE lower(name) = lower(%s)", (name,)):
        raise EmpireError("Give the new empire a name of 3 to 40 letters that no other empire has.")
    head = str(payload.get("new_head") or "")
    member = next((h for h in empires.humans(conn, empire["id"]) if str(h["player_id"]) == head), None)
    if member is None or str(empire["head_player_id"]) == head:
        raise EmpireError("The new empire is led by one of your members (not the head).")
    cash = payload.get("cash", 0)
    if not _whole(cash, 0, ledger.balance(conn, empire["account_id"]) // 10):
        raise EmpireError("The new empire may take up to a tenth of the empire's cash with it.")
    return {"company_id": str(owned["company_id"]), "company": owned["name"], "new_name": name, "new_head": head, "subject_id": head, "cash": cash}


def _spinoff_carry(conn: Connection, empire: dict, resolution: dict, now: datetime) -> str:
    p = _spinoff_check(conn, empire, dict(resolution["payload"]), now)
    period = careers.world_now(conn, now)["period"]
    empire = empires._empire(conn, empire["id"], lock=True)
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (p["company_id"],))
    from simulation import world_data as wd
    fee = wd.EMPIRE_REGISTRATION_NAIRA * 100
    if ledger.balance(conn, empire["account_id"]) < fee + p["cash"]:
        raise EmpireError(f"A new empire pays the registration fee of {_money(fee)}; the empire has not the cash.")
    before = empires.worth(conn, empire, now)["total"]
    new = empires._create(conn, p["new_name"], "player", "active", p["new_head"], now, period)
    ledger.transfer(conn, payer=empire["account_id"], receiver=ledger.account_id(conn, ledger.PRIZE_POOL), amount=fee, kind="empire_registration",
                    memo=f"{new['name']}: registration fee", reference=f"empire:{new['id']}", period=period)
    leagues.place_new(conn, new["id"])
    shares = ledger.balance(conn, empire["account_id"], company["share_asset"])
    legs = [Leg(empire["account_id"], -shares, company["share_asset"]), Leg(new["account_id"], shares, company["share_asset"])]
    if p["cash"]:
        legs += [Leg(empire["account_id"], -p["cash"]), Leg(new["account_id"], p["cash"])]
    ledger.post(conn, kind="empire_spinoff", memo=f"{empire['name']} splits {company['name']} off into {new['name']}", period=period,
                reference=f"spinoff:{new['id']}", legs=legs)
    stake = _one(conn, "SELECT * FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company["id"], empire["id"]))
    if stake:
        conn.execute("INSERT INTO company_stakes (company_id, empire_id, cost, since_period) VALUES (%s, %s, %s, %s)",
                     (company["id"], new["id"], stake["cost"], stake["since_period"]))
        conn.execute("DELETE FROM company_stakes WHERE company_id = %s AND empire_id = %s", (company["id"], empire["id"]))
    conn.execute("UPDATE deals SET empire_id = %s WHERE empire_id = %s AND company_id = %s AND status = 'held'", (new["id"], empire["id"], company["id"]))
    firm_deals._take_control(conn, company["id"], period, now)
    # The same owners own the new empire, in the same proportions.
    firm_money.ensure_units(conn, empire)
    for u in _rows(conn, "SELECT * FROM empire_units WHERE empire_id = %s AND units > 0", (empire["id"],)):
        conn.execute("INSERT INTO empire_units (empire_id, holder_account, player_id, units) VALUES (%s, %s, %s, %s)",
                     (new["id"], u["holder_account"], u["player_id"], u["units"]))
    member = next(h for h in empires.humans(conn, empire["id"]) if str(h["player_id"]) == p["new_head"])
    seat = empires.seat_of(conn, member["player_id"], lock=True)
    empires._vacate(conn, seat, now, period, "spun_off")
    empires._take_seat(conn, new, member["player_id"], member["build"], now, period)
    moved = max(before - empires.worth(conn, empires._empire(conn, empire["id"]), now)["total"], 0)
    conn.execute("INSERT INTO empire_combinations (kind, empire_id, other_empire_id, company_id, new_name, new_head, status, resolution_ids, period, at,"
                 " worth_moved) VALUES ('spinoff', %s, %s, %s, %s, %s, 'done', %s, %s, %s, %s)",
                 (empire["id"], new["id"], company["id"], new["name"], member["player_id"], [resolution["id"]], period, now, moved))
    news.publish(conn, period=period, day=1, kind="spinoff", story=f"spinoff:{new['id']}",
                 facts={"empire": empire["name"], "company": company["name"], "new_empire": new["name"]})
    _log(conn, new["id"], f"{new['name']} was split off from {empire['name']}, with {company['name']}"
                          + (f" and {_money(p['cash'])} of cash" if p["cash"] else "") + ". Its owners are the owners of the empire it came from.", now)
    return f"{company['name']} was split off into a new empire, {new['name']}, led by {member['display_name']}."


# ---------------------------------------------------------------------------
# The shadow side: taking money out of a company the empire controls
# ---------------------------------------------------------------------------

def take_from_company(conn: Connection, player_id, company_id, amount: int, now: datetime) -> dict:
    """A member pays themselves "consulting fees" out of a private company their empire controls. The company pays;
    the empire's books carry it as a cost. It counts against the member's signing limit; audits can find it."""
    with conn.transaction():
        state = _open(conn, now)
        seat = empires.seat_of(conn, player_id, lock=True)
        if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] != "player":
            raise EmpireError("You hold no seat in an open empire run by players.")
        owned = _one(conn, "SELECT o.*, c.name, c.account_id FROM owned_companies o JOIN companies c ON c.id = o.company_id WHERE o.company_id = %s"
                           " AND o.empire_id = %s AND c.status = 'trading' FOR UPDATE OF o", (company_id, seat["empire_id"]))
        if owned is None:
            raise EmpireError("Your empire does not control that company.")
        if not _whole(amount):
            raise EmpireError("An amount above nought.")
        cash = ledger.balance(conn, owned["account_id"])
        if amount * BPS > max(cash, 0) * TAKE_MOST_BPS:
            raise EmpireError(f"Fees that large would be noticed at once: at most {_money(apply_bps(max(cash, 0), TAKE_MOST_BPS))} at a time.")
        limit = empires.signing_limit(conn, seat)
        used = empires._spent(conn, seat["empire_id"], player_id, state["period"])
        if used + amount > limit:
            raise EmpireError(f"Your signing limit for the quarter is {_money(limit)}, of which {_money(used)} is used.")
        ledger.transfer(conn, payer=owned["account_id"], receiver=ledger.player_account_id(conn, player_id), amount=amount, kind="professional_fee",
                        memo=f"{owned['name']}: consulting fees", period=state["period"], reference=f"consulting:{company_id}")
        mine = careers.career(conn, player_id, seat["build"])
        book = empires._book(conn, seat["empire_id"], state["period"], "Consulting fees", f"Consulting for {owned['name']}", amount, False, now,
                             entered_by=player_id, thief_level=mine["level"] if mine else 1,
                             desk="head" if seat["head_player_id"] == player_id else seat["build"], company_id=company_id)
        return {"book_id": book, "amount": amount, "limit": limit, "used": used + amount}


# ---------------------------------------------------------------------------
# What members see
# ---------------------------------------------------------------------------

def view(conn: Connection, seat: dict, empire: dict, state: dict, now: datetime) -> dict:
    me = seat["player_id"]
    is_head = empire["head_player_id"] == me
    banker = firm_deals._desk_ok(conn, empire, seat, "investment_banker")
    manager = firm_deals._desk_ok(conn, empire, seat, "asset_manager")
    offers = []
    for t in _rows(conn, "SELECT t.*, c.name AS target, c.ticker, c.share_asset, coalesce(b.name, e.name) AS bidder FROM takeovers t"
                         " JOIN companies c ON c.id = t.target_company_id LEFT JOIN companies b ON b.id = t.bidder_company_id"
                         " LEFT JOIN empires e ON e.id = t.bidder_empire_id WHERE t.status = 'open' OR (t.bidder_empire_id = %s AND t.closes_period >= %s)"
                         " ORDER BY (t.status = 'open') DESC, t.id DESC LIMIT 20", (empire["id"], state["period"] - 2)):
        held = ledger.balance(conn, empire["account_id"], t["share_asset"])
        tendered = _one(conn, "SELECT shares FROM takeover_tenders WHERE takeover_id = %s AND account_id = %s", (t["id"], empire["account_id"]))
        issued = max(ledger.amount_in_existence(conn, t["share_asset"]), 1)
        mine_bps = holding(conn, empire["account_id"], t["target_company_id"], t["share_asset"]) * BPS // issued
        defence = None
        if t["defence_terms"] is not None:
            defence = {"by_us": t["defence_empire_id"] == empire["id"], "done": bool(t["defence_terms"].get("done")), "value": t["defence_value"],
                       "terms": firm._public_terms(t["defence_terms"]) if t["defence_by"] == me and not t["defence_terms"].get("done") else None}
        offers.append({"id": t["id"], "target": t["target"], "ticker": t["ticker"], "company_id": t["target_company_id"], "bidder": t["bidder"],
                       "ours": t["bidder_empire_id"] == empire["id"], "price": t["price"], "premium_bps": t["premium_bps"], "shares_sought": t["shares_sought"],
                       "hostile": t["hostile"], "status": t["status"], "outcome": t["outcome"], "closes": clock.period_label(t["closes_period"]),
                       "held": held, "tendered": tendered["shares"] if tendered else 0, "our_bps": mine_bps, "defence": defence,
                       "defence_value": t["defence_value"],
                       "can_defend": banker and t["status"] == "open" and t["bidder_empire_id"] != empire["id"] and mine_bps >= DEFEND_FROM_BPS
                       and t["defence_value"] is None and (t["defence_terms"] is None or (not t["defence_terms"].get("done") and (
                           t["defence_by"] == me or firm._hours(datetime.fromisoformat(t["defence_terms"]["opened_at"]), now) >= DEFENCE_HOURS))),
                       "can_tender": is_head and t["status"] == "open" and t["bidder_empire_id"] != empire["id"] and (held or tendered)})
    holdings = []
    for h in _rows(conn, "SELECT c.id, c.name, c.ticker, c.share_asset, b.balance FROM ledger_balances b JOIN companies c ON c.share_asset = b.asset"
                         " WHERE b.account_id = %s AND b.balance > 0 AND c.listed ORDER BY c.name", (empire["account_id"],)):
        issued = max(ledger.amount_in_existence(conn, h["share_asset"]), 1)
        holdings.append({"company_id": h["id"], "name": h["name"], "ticker": h["ticker"], "shares": h["balance"], "share_bps": h["balance"] * BPS // issued,
                         "price": corporate._market_price(conn, h["id"])})
    programmes = [{"id": r["id"], "company": r["name"], "ticker": r["ticker"], "target_bps": r["target_bps"], "most_price": r["most_price"],
                   "status": r["status"], "disclosed_bps": r["disclosed_bps"]}
                  for r in _rows(conn, "SELECT p.*, c.name, c.ticker FROM stake_programmes p JOIN companies c ON c.id = p.company_id WHERE p.empire_id = %s"
                                       " ORDER BY (p.status = 'running') DESC, p.id DESC LIMIT 12", (empire["id"],))]
    blocks = [{"id": r["id"], "company": r["name"], "ticker": r["ticker"], "shares": r["shares"], "price": r["price"], "status": r["status"],
               "seller": r["seller"], "buyer": r["buyer"], "selling": r["seller_empire_id"] == empire["id"]}
              for r in _rows(conn, "SELECT k.*, c.name, c.ticker, s.name AS seller, b.name AS buyer FROM block_trades k JOIN companies c ON c.id = k.company_id"
                                   " JOIN empires s ON s.id = k.seller_empire_id JOIN empires b ON b.id = k.buyer_empire_id"
                                   " WHERE %s IN (k.seller_empire_id, k.buyer_empire_id) ORDER BY (k.status = 'offered') DESC, k.id DESC LIMIT 12",
                             (empire["id"],))] if is_head or manager else []
    combos = [{"id": c["id"], "kind": c["kind"], "with": c["name"], "status": c["status"], "joining_us": c["other_empire_id"] == empire["id"]}
              for c in _rows(conn, "SELECT c.*, e.name FROM empire_combinations c JOIN empires e ON e.id = CASE WHEN c.empire_id = %s THEN c.other_empire_id"
                                   " ELSE c.empire_id END WHERE %s IN (c.empire_id, c.other_empire_id) ORDER BY c.id DESC LIMIT 6",
                             (empire["id"], empire["id"]))]
    others = [{"id": e["id"], "name": e["name"], "truce": empires.in_truce(conn, empire["id"], e["id"])}
              for e in _rows(conn, "SELECT id, name FROM empires WHERE kind = 'player' AND status = 'active' AND head_player_id IS NOT NULL AND id <> %s"
                                   " ORDER BY name", (empire["id"],))]
    owned = [{"company_id": r["company_id"], "name": r["name"]} for r in _rows(
        conn, "SELECT o.company_id, c.name FROM owned_companies o JOIN companies c ON c.id = o.company_id WHERE o.empire_id = %s ORDER BY c.name",
        (empire["id"],))]
    listed = [{"company_id": r["id"], "name": r["name"], "ticker": r["ticker"], "price": r["price"]}
              for r in _rows(conn, "SELECT c.id, c.name, c.ticker, coalesce(m.last_price, m.reference_price) AS price FROM companies c"
                                   " JOIN market_instruments m ON m.company_id = c.id WHERE c.listed AND c.status = 'trading' ORDER BY c.name")]
    return {"offers": offers, "holdings": holdings, "listed": listed, "programmes": programmes, "blocks": blocks, "combinations": combos, "others": others,
            "portfolio": portfolio(conn, empire, state["period"]), "owned": owned,
            "members": [{"player_id": h["player_id"], "name": h["display_name"]} for h in empires.humans(conn, empire["id"])
                        if h["player_id"] != empire["head_player_id"]] if is_head else [],
            "may": {"offer": banker, "stake": manager, "head": is_head},
            "rules": {"top_by_bps": TOP_BY_BPS, "must_offer_bps": MUST_OFFER_BPS, "disclose_step_bps": DISCLOSE_STEP_BPS, "block_band_bps": BLOCK_BAND_BPS,
                      "defend_from_bps": DEFEND_FROM_BPS}}


def waiting(conn: Connection, seat: dict, empire: dict, now: datetime) -> int:
    n = 0
    if empire["head_player_id"] == seat["player_id"]:
        n += _one(conn, "SELECT count(*) AS n FROM block_trades WHERE buyer_empire_id = %s AND status = 'offered'", (empire["id"],))["n"]
        n += _one(conn, "SELECT count(*) AS n FROM empire_combinations c WHERE c.other_empire_id = %s AND c.kind = 'merger' AND c.status = 'voting'"
                        " AND NOT EXISTS (SELECT 1 FROM empire_resolutions r WHERE r.empire_id = %s AND r.kind = 'merger_join' AND r.status = 'open')",
                  (empire["id"], empire["id"]))["n"]
    return n


def _bell(conn: Connection, now: datetime) -> None:
    _build_stakes(conn, now)
    with conn.transaction():
        disclose(conn, now)


def _closed(conn: Connection, period: int, now: datetime) -> None:
    with conn.transaction():
        conn.execute("UPDATE block_trades SET status = 'lapsed', done_at = %s WHERE status = 'offered' AND at < %s", (now, now))
        conn.execute("UPDATE empire_combinations SET status = 'lapsed' WHERE status = 'voting' AND period < %s", (period - 1,))
        disclose(conn, now)


firm.EXECUTORS["takeover_offer"] = _announce
firm.EXECUTORS["stake_programme"] = _start_programme
corporate.TAKEOVER_CLOSED.append(_takeover_closed)
firm.RESOLUTIONS["merger"] = firm.Resolution("merger", "Merge another empire into ours", lambda seat, is_head: is_head, _merger_check, _merger_carry,
                                             lambda p: f"Merge {p['other']} into this empire", big=True)
firm.RESOLUTIONS["merger_join"] = firm.Resolution("merger_join", "Join another empire", lambda seat, is_head: is_head, _join_check, _join_carry,
                                                  lambda p: f"Join {p['into']}: this empire's money, companies and members pass to it", big=True)
firm.FAILED["merger_join"] = _join_failed
firm.RESOLUTIONS["spinoff"] = firm.Resolution("spinoff", "Split a company off into a new empire", lambda seat, is_head: is_head, _spinoff_check,
                                              _spinoff_carry, lambda p: f"Split {p['company']} off into a new empire, {p['new_name']}", big=True)
firm.BELL.append(_bell)
firm.CLOSED.append(_closed)
firm.VIEW["dealmaking"] = lambda conn, seat, empire, state, now: view(conn, seat, empire, state, now) if firm.player_run(empire) else None
firm.WAITING.append(lambda conn, seat, empire, now: waiting(conn, seat, empire, now) if firm.player_run(empire) else 0)
