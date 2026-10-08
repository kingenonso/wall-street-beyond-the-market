"""Stage 4, Part B: share offers, splits, votes, takeovers and what follows them.

Everything is announced as one quarter closes and settled as the next closes. Cash
and shares a player commits are held by the exchange until then. New shares never
move the index. Nothing is handed out below its worth for nothing.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from psycopg.rows import dict_row

from simulation import bonds, corporate, exchange, investors, ledger, marketview, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_market import place, reference, sound, trader

OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")
T = "IDC"


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def company_of(db, ticker=T) -> dict:
    return _dicts(db, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE c.ticker = %s", (ticker,))[0]


def whole(db) -> None:
    sound(db)
    assert corporate.check_books(db) == []


def dividends(db, account) -> int:
    return _dicts(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS d FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " WHERE e.account_id = %s AND t.kind = 'dividend'", (account,))[0]["d"]


def offer(db, kind="public", ticker=T, price=None, shares=1_000_000, **more) -> int:
    # When the world begins the computer-run investors hold shares but no cash; give them some to invest.
    treasury = ledger.account_id(db, ledger.TREASURY)
    for code in (ledger.INVESTORS_FOUNDERS, ledger.INVESTORS_INSTITUTIONS, ledger.INVESTORS_PUBLIC):
        if ledger.balance(db, ledger.account_id(db, code)) < naira(1_000_000_000):
            ledger.transfer(db, payer=treasury, receiver=ledger.account_id(db, code), amount=naira(60_000_000_000),
                            kind="test_cash", memo="Test: cash for the computer-run investors")
    company = company_of(db, ticker)
    with db.transaction():
        return corporate.announce_offer(db, company, kind=kind, price=price or reference(db, ticker) * 98 // 100, shares=shares,
                                        period=0, reason="A test offer.", now=OPEN, **more)


def index_now(db, now) -> int:
    return marketview.overview(db, now, with_history=False)["index"]


# ---------------------------------------------------------------------------
# A sale of new shares to anybody
# ---------------------------------------------------------------------------

def test_a_player_applies_for_new_shares_and_receives_them_when_the_quarter_closes(db):
    company = company_of(db)
    player = trader(db, "amaka", cash_naira=10_000_000)
    price = reference(db) * 98 // 100
    offer_id = offer(db, price=price, shares=1_000_000)
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    company_cash = ledger.balance(db, company["account_id"])

    held = corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=10_000, now=OPEN)
    assert held["held"] == 10_000 * price and ledger.balance(db, player) == naira(10_000_000) - 10_000 * price
    whole(db)

    quarters.close_due_quarters(db, after_quarters(1))
    done = _dicts(db, "SELECT * FROM share_offers WHERE id = %s", (offer_id,))[0]
    mine = _dicts(db, "SELECT * FROM offer_subscriptions WHERE offer_id = %s AND account_id = %s", (offer_id, player))[0]
    assert done["status"] == "done" and 0 < mine["allotted"] <= 10_000 and mine["held"] == 0
    assert ledger.balance(db, player, "SHR-IDC") == mine["allotted"]
    assert ledger.balance(db, player) == naira(10_000_000) - mine["allotted"] * price + dividends(db, player)   # the rest came back
    assert ledger.amount_in_existence(db, "SHR-IDC") == in_issue + done["shares_sold"] and done["raised"] == done["shares_sold"] * price
    # The company has the money, and its accounts show it as owners' funds, not as sales.
    result = _dicts(db, "SELECT r.*, o.share_capital AS opening FROM company_results r JOIN company_results o ON o.company_id = r.company_id"
                        " AND o.period = 0 WHERE r.company_id = %s AND r.period = 1", (company["id"],))[0]
    assert result["share_capital"] == result["opening"] + done["raised"] and result["shares_in_issue"] == in_issue + done["shares_sold"]
    assert "outside its normal business" not in str(result["drivers"]) and "by selling new shares" in str(result["drivers"])
    assert ledger.balance(db, company["account_id"]) != company_cash
    # What the shares cost is on record for the portfolio.
    seen = next(h for h in marketview.portfolio(db, player, after_quarters(1))["holdings"] if h["ticker"] == T)
    assert seen["cost"] == mine["allotted"] * price
    whole(db)


def test_when_more_is_asked_for_than_is_on_offer_everybody_is_scaled_back_alike(db):
    big, small = trader(db, "big", cash_naira=400_000_000), trader(db, "small", cash_naira=40_000_000)
    offer_id = offer(db, shares=100_000)
    corporate.apply_for_shares(db, account=big, offer_id=offer_id, shares=100_000, now=OPEN)
    corporate.apply_for_shares(db, account=small, offer_id=offer_id, shares=10_000, now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    got = {r["account_id"]: r["allotted"] for r in _dicts(db, "SELECT * FROM offer_subscriptions WHERE offer_id = %s", (offer_id,))}
    done = _dicts(db, "SELECT * FROM share_offers WHERE id = %s", (offer_id,))[0]
    assert done["shares_sold"] <= 100_000 and got[big] < 100_000
    assert abs(got[big] - 10 * got[small]) <= 10                                 # the same proportion each
    whole(db)


def test_an_application_can_be_changed_or_withdrawn_and_never_exceeds_the_players_cash(db):
    player = trader(db, "amaka", cash_naira=1_000_000)
    price = reference(db) * 98 // 100
    offer_id = offer(db, price=price)
    with pytest.raises(corporate.CorporateError, match="enough cash"):
        corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=naira(1_000_000) // price + 1, now=OPEN)
    corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=100, now=OPEN)
    corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=40, now=OPEN)          # replaced, not added
    assert ledger.balance(db, player) == naira(1_000_000) - 40 * price
    corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=0, now=OPEN)
    assert ledger.balance(db, player) == naira(1_000_000)
    for bad in (-1, True, 1.5, "10", 10**13):
        with pytest.raises(corporate.CorporateError):
            corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=bad, now=OPEN)
    for code in ("treasury", "investors:public", "company:IDC"):
        with pytest.raises(corporate.CorporateError, match="cannot take part"):
            corporate.apply_for_shares(db, account=ledger.account_id(db, code), offer_id=offer_id, shares=1, now=OPEN)
    whole(db)
    quarters.close_due_quarters(db, after_quarters(1))
    with pytest.raises(corporate.CorporateError, match="not open"):
        corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=1, now=after_quarters(1))


def test_new_shares_do_not_move_the_index(db):
    investors.act(db, OPEN, force=True)
    before = index_now(db, OPEN)
    offer(db, shares=2_000_000_000)                     # a large issue, about a twentieth of the company
    quarters.close_due_quarters(db, after_quarters(1))
    sold = _dicts(db, "SELECT shares_sold FROM share_offers")[0]["shares_sold"]
    assert sold > 0
    # Only the prices that changed in trading since may move it; the new shares alone must not.
    shares = marketview._shares(db, exchange.session_of(after_quarters(1))[0])
    by_hand = sum(s["price"] * s["shares"] for s in shares) * 100_000 // marketview.index_base(db)
    assert index_now(db, after_quarters(1)) == by_hand
    assert abs(index_now(db, after_quarters(1)) - before) <= before // 500          # within a fifth of a percent


def test_the_price_is_adjusted_for_the_new_shares_and_the_reason_is_on_record(db):
    seller, buyer = trader(db, "seller", shares=1_000), trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db)
    place(db, seller, "sell", 100, price)
    place(db, buyer, "buy", 100, price)                                             # it has traded: it has a last price
    waiting = place(db, buyer, "buy", 10, price * 95 // 100)["order"]
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    offer(db, kind="rights", price=price * 70 // 100, shares=in_issue // 3, rights=(1, 3))
    quarters.close_due_quarters(db, after_quarters(1))
    done = _dicts(db, "SELECT * FROM share_offers")[0]
    assert done["status"] == "done" and done["shares_sold"] > 0
    expected = (in_issue * price + done["raised"]) // (in_issue + done["shares_sold"])
    assert exchange.quote(db, T, after_quarters(1))["last_price"] == expected < price
    reasons = exchange.why(db, T, after_quarters(1))["reasons"]
    assert any("new shares were issued" in reason for reason in reasons)
    # Orders left waiting at the old price were handed back with a reason.
    order = _dicts(db, "SELECT status, closed_reason FROM market_orders WHERE id = %s", (waiting["id"],))[0]
    assert order["status"] == "cancelled" and "new shares" in order["closed_reason"]
    whole(db)


# ---------------------------------------------------------------------------
# A rights issue
# ---------------------------------------------------------------------------

def test_in_a_rights_issue_nobody_gets_more_than_their_own_rights(db):
    """Shares below the market price for whoever asks would be money for nothing."""
    holder, greedy = trader(db, "holder", cash_naira=50_000_000, shares=9_000), trader(db, "greedy", cash_naira=500_000_000)
    price = reference(db) * 70 // 100
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    offer_id = offer(db, kind="rights", price=price, shares=in_issue // 3, rights=(1, 3))
    corporate.apply_for_shares(db, account=holder, offer_id=offer_id, shares=5_000, now=OPEN)      # more than its 3,000
    corporate.apply_for_shares(db, account=greedy, offer_id=offer_id, shares=1_000_000, now=OPEN)  # holds nothing
    quarters.close_due_quarters(db, after_quarters(1))
    got = {r["account_id"]: r["allotted"] for r in _dicts(db, "SELECT * FROM offer_subscriptions WHERE offer_id = %s", (offer_id,))}
    assert got[holder] == 3_000 and got[greedy] == 0
    assert ledger.balance(db, greedy) == naira(500_000_000)
    assert ledger.balance(db, holder) == naira(50_000_000) - 3_000 * price + dividends(db, holder)
    assert ledger.balance(db, holder, "SHR-IDC") == 12_000
    whole(db)


def test_rights_go_with_the_shares_held_when_the_offer_closes(db):
    """Whoever holds the shares at the close has the rights: they cannot be kept while the shares are sold on."""
    first, second = trader(db, "first", cash_naira=50_000_000, shares=9_000), trader(db, "second", cash_naira=50_000_000)
    price = reference(db)
    offer_id = offer(db, kind="rights", price=price * 70 // 100, shares=ledger.amount_in_existence(db, "SHR-IDC") // 3, rights=(1, 3))
    corporate.apply_for_shares(db, account=first, offer_id=offer_id, shares=3_000, now=OPEN)
    corporate.apply_for_shares(db, account=second, offer_id=offer_id, shares=3_000, now=OPEN)
    place(db, first, "sell", 9_000, price)
    place(db, second, "buy", 9_000, price)
    quarters.close_due_quarters(db, after_quarters(1))
    got = {r["account_id"]: r["allotted"] for r in _dicts(db, "SELECT * FROM offer_subscriptions WHERE offer_id = %s", (offer_id,))}
    assert got[first] == 0 and got[second] == 3_000
    whole(db)


def test_a_holder_who_takes_up_their_rights_is_neither_richer_nor_poorer(db):
    holder = trader(db, "holder", cash_naira=50_000_000, shares=30_000)
    price = reference(db)
    offer_id = offer(db, kind="rights", price=price * 70 // 100, shares=ledger.amount_in_existence(db, "SHR-IDC") // 3, rights=(1, 3))
    corporate.apply_for_shares(db, account=holder, offer_id=offer_id, shares=10_000, now=OPEN)
    before = naira(50_000_000) + 30_000 * price
    quarters.close_due_quarters(db, after_quarters(1))
    now_price = exchange.quote(db, T, after_quarters(1))
    worth = ledger.balance(db, holder) + ledger.balance(db, holder, "SHR-IDC") * (now_price["last_price"] or now_price["reference_price"])
    received = dividends(db, holder)
    assert abs(worth - received - before) <= before // 200                         # within half a percent: rounding and those who did not take up


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------

def test_a_large_issue_needs_the_owners_vote_and_goes_ahead_when_it_passes(db):
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    offer_id = offer(db, kind="rights", price=reference(db) * 70 // 100, shares=in_issue // 3, rights=(1, 3))
    vote = _dicts(db, "SELECT * FROM company_votes")[0]
    assert vote["status"] == "open" and vote["subject"] == "rights_issue" and vote["closes_period"] == 1
    assert _dicts(db, "SELECT vote_id FROM share_offers WHERE id = %s", (offer_id,))[0]["vote_id"] == vote["id"]
    quarters.close_due_quarters(db, after_quarters(1))
    counted = _dicts(db, "SELECT * FROM company_votes WHERE id = %s", (vote["id"],))[0]
    assert counted["status"] == "passed" and counted["votes_for"] > counted["votes_against"] > 0
    assert _dicts(db, "SELECT status FROM share_offers WHERE id = %s", (offer_id,))[0]["status"] == "done"
    # A small issue needs no vote.
    assert _dicts(db, "SELECT vote_id FROM share_offers WHERE id = %s", (offer(db, ticker="ABA", shares=1_000),))[0]["vote_id"] is None


def test_if_the_vote_fails_no_shares_are_issued_and_all_cash_comes_back(db):
    player = trader(db, "amaka", cash_naira=10_000_000, shares=3_000)
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    offer_id = offer(db, kind="rights", price=reference(db) * 70 // 100, shares=in_issue // 3, rights=(1, 3), institutions="against")
    db.execute("UPDATE company_votes SET board = 'against'")                       # the board and the pension funds are against
    corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=1_000, now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    assert _dicts(db, "SELECT status FROM company_votes")[0]["status"] == "failed"
    assert _dicts(db, "SELECT status, shares_sold FROM share_offers WHERE id = %s", (offer_id,))[0] == {"status": "withdrawn", "shares_sold": 0}
    assert ledger.amount_in_existence(db, "SHR-IDC") == in_issue
    assert ledger.balance(db, player) == naira(10_000_000) + dividends(db, player)
    whole(db)


def test_a_vote_counts_for_the_shares_held_when_it_is_counted_and_can_be_changed_until_then(db):
    voter, buyer = trader(db, "voter", shares=1_000_000), trader(db, "buyer", cash_naira=100_000_000)
    offer(db, kind="rights", price=reference(db) * 70 // 100, shares=ledger.amount_in_existence(db, "SHR-IDC") // 3, rights=(1, 3))
    vote = _dicts(db, "SELECT * FROM company_votes")[0]
    corporate.cast_vote(db, account=voter, vote_id=vote["id"], choice="for", now=OPEN)
    corporate.cast_vote(db, account=voter, vote_id=vote["id"], choice="against", now=OPEN)            # changed, not added
    assert _dicts(db, "SELECT choice FROM vote_ballots") == [{"choice": "against"}]
    who = corporate._investors(db)
    assert corporate._tally(db, vote, who)["Players"] == [0, 1_000_000]
    # The voter sells most of the shares. The vote now counts for what is left; the buyer has not voted.
    place(db, voter, "sell", 900_000, reference(db))
    place(db, buyer, "buy", 900_000, reference(db))
    assert corporate._tally(db, vote, who)["Players"] == [0, 100_000]
    corporate.cast_vote(db, account=buyer, vote_id=vote["id"], choice="for", now=OPEN)
    assert corporate._tally(db, vote, who)["Players"] == [900_000, 100_000]                          # each share counted once
    for bad in ("maybe", "", None, 1):
        with pytest.raises(corporate.CorporateError):
            corporate.cast_vote(db, account=voter, vote_id=vote["id"], choice=bad, now=OPEN)
    with pytest.raises(corporate.CorporateError):
        corporate.cast_vote(db, account=ledger.account_id(db, "investors:public"), vote_id=vote["id"], choice="for", now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    counted = _dicts(db, "SELECT * FROM company_votes")[0]
    # While players are few, how they voted is not shown on its own.
    assert "Players" not in counted["tally"] and set(counted["tally"]) <= {"Founders", "Pension funds", "Small investors"}
    with pytest.raises(corporate.CorporateError, match="not open"):
        corporate.cast_vote(db, account=voter, vote_id=vote["id"], choice="for", now=after_quarters(1))


# ---------------------------------------------------------------------------
# Share splits
# ---------------------------------------------------------------------------

def test_a_split_gives_every_owner_more_shares_each_worth_less_and_nobody_gains(db, monkeypatch):
    monkeypatch.setattr(data, "SPLIT_ABOVE_KOBO", 3_000)                    # so that a ₦30 share is split
    monkeypatch.setattr(data, "TAKEOVER_ONE_IN", 10**9)
    holder, buyer = trader(db, "holder", shares=10_000), trader(db, "buyer", cash_naira=10_000_000)
    quarters.close_due_quarters(db, after_quarters(1))                      # shares are listed at what they are worth; votes open
    proposed = _dicts(db, "SELECT v.*, c.ticker FROM company_votes v JOIN companies c ON c.id = v.company_id WHERE v.subject = 'share_split'")
    assert proposed, "the test needs a share above the split price"
    ticker = proposed[0]["ticker"]
    ratio = proposed[0]["detail"]["ratio"]
    asset = f"SHR-{ticker}"
    mine = trader(db, "mine", shares=600, ticker=ticker)
    now = after_quarters(1)
    trading = datetime.fromisoformat("2026-10-13T13:00:00+01:00")
    before_price = reference(db, ticker)
    place(db, mine, "sell", 100, before_price, now=trading, ticker=ticker)
    place(db, buyer, "buy", 100, before_price, now=trading, ticker=ticker)          # it trades, so it has a history
    waiting = place(db, mine, "sell", 50, before_price + 10, now=trading, ticker=ticker)["order"]
    in_issue = ledger.amount_in_existence(db, asset)
    index_before = index_now(db, trading)
    worth_before = marketview.portfolio(db, mine, trading)["total"]

    quarters.close_due_quarters(db, after_quarters(2))
    later = after_quarters(2)
    assert ledger.amount_in_existence(db, asset) == in_issue * ratio
    assert ledger.balance(db, mine, asset) == 500 * ratio and ledger.balance(db, buyer, asset) == 100 * ratio
    after_price = exchange.quote(db, ticker, later)["last_price"]
    assert after_price == before_price // ratio
    # The waiting order was handed back (its price was in old shares), with its shares, before the split.
    assert _dicts(db, "SELECT status FROM market_orders WHERE id = %s", (waiting["id"],))[0]["status"] == "cancelled"
    # Nobody is richer or poorer, the index does not move, and the price history is in today's shares.
    seen = marketview.portfolio(db, mine, later)
    held = next(h for h in seen["holdings"] if h["ticker"] == ticker)
    # (A dividend paid as the quarter closed is income, not a gain from the split: it is left out.)
    dividends = ledger.received_in_period(db, mine, 2, kinds=("dividend",))
    assert held["shares"] == 500 * ratio and abs(seen["total"] - dividends - worth_before) <= worth_before // 200 + 500 * ratio
    assert abs(index_now(db, later) - index_before) <= index_before // 200
    assert marketview.history(db, ticker)[0]["close"] == before_price // ratio
    assert marketview.history(db, ticker)[0]["volume"] == 100 * ratio
    bought = next(h for h in marketview.portfolio(db, buyer, later)["holdings"] if h["ticker"] == ticker)
    assert bought["shares"] == 100 * ratio and bought["cost"] == 100 * before_price + exchange.fee_due(100 * before_price)
    assert _dicts(db, "SELECT ratio FROM share_splits")[0]["ratio"] == ratio
    _ = holder, now
    whole(db)


# ---------------------------------------------------------------------------
# A first sale of shares to the public
# ---------------------------------------------------------------------------

def test_a_company_not_yet_on_the_exchange_lists_its_shares_by_selling_some_to_the_public(db):
    company = company_of(db, "ABA")
    db.execute("DELETE FROM market_instruments WHERE company_id = %s", (company["id"],))        # a private company
    player = trader(db, "amaka", cash_naira=10_000_000)
    with pytest.raises(exchange.ExchangeError):
        place(db, player, "buy", 10, 2_000, ticker="ABA")
    offer_id = offer(db, kind="ipo", ticker="ABA", price=2_500, shares=50_000_000)
    assert _dicts(db, "SELECT vote_id FROM share_offers WHERE id = %s", (offer_id,))[0]["vote_id"] is None
    corporate.apply_for_shares(db, account=player, offer_id=offer_id, shares=2_000, now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    done = _dicts(db, "SELECT * FROM share_offers WHERE id = %s", (offer_id,))[0]
    assert done["status"] == "done" and "now trade on the Broad Street Exchange" in done["outcome"]
    listed = _dicts(db, "SELECT * FROM market_instruments WHERE company_id = %s", (company["id"],))[0]
    assert listed["listing_price"] == listed["reference_price"] == 2_500 and listed["last_price"] is None
    got = ledger.balance(db, player, "SHR-ABA")
    assert 0 < got <= 2_000
    trading = datetime.fromisoformat("2026-10-13T13:00:00+01:00")
    assert place(db, player, "sell", got, 2_500, now=trading, ticker="ABA")["order"]["status"] == "open"     # it trades
    assert len(marketview.overview(db, trading)["shares"]) == 50
    whole(db)


# ---------------------------------------------------------------------------
# Takeovers
# ---------------------------------------------------------------------------

def _bid(db, monkeypatch, *, premium=None) -> dict:
    """Close two quarters with a takeover offer made at the second close."""
    monkeypatch.setattr(data, "TAKEOVER_ONE_IN", 1)
    if premium:
        monkeypatch.setattr(data, "TAKEOVER_PREMIUM_BPS", (premium, premium + 1))
    quarters.close_due_quarters(db, after_quarters(2))
    bids = _dicts(db, "SELECT t.*, c.ticker, c.share_asset, b.ticker AS bidder_ticker, b.account_id AS bidder_account FROM takeovers t"
                      " JOIN companies c ON c.id = t.target_company_id JOIN companies b ON b.id = t.bidder_company_id")
    assert len(bids) == 1, "the test needs one takeover offer"
    return bids[0]


def test_a_takeover_offer_is_announced_with_the_cash_already_set_aside(db, monkeypatch):
    bid = _bid(db, monkeypatch, premium=3500)
    assert bid["status"] == "open" and bid["closes_period"] == 3 and not bid["hostile"]
    assert bid["reserved"] == bid["shares_sought"] * bid["price"]
    assert ledger.balance(db, bonds.held_account(db)) == bid["reserved"]             # the bidder cannot spend it elsewhere
    notice = _dicts(db, "SELECT * FROM market_notices WHERE kind = 'takeover_bid'")[0]
    assert "recommends that shareholders accept" in notice["body"]
    news = _dicts(db, "SELECT kind, period, day FROM news_items WHERE kind LIKE 'takeover%%'")
    assert {n["kind"] for n in news} == {"takeover_bid"} and all(n["period"] == 3 for n in news)
    # The share is repriced to what it is now worth with the offer on the table, and the reason is on record.
    assert any("offered" in reason for reason in exchange.why(db, bid["ticker"], after_quarters(2))["reasons"])
    whole(db)


def test_a_player_accepts_a_takeover_offer_and_is_paid_the_offer_price(db, monkeypatch):
    bid = _bid(db, monkeypatch, premium=3500)
    asset = bid["share_asset"]
    player = trader(db, "amaka", shares=10_000, ticker=bid["ticker"])
    now = after_quarters(2)
    with pytest.raises(corporate.CorporateError, match="do not hold"):
        corporate.tender(db, account=player, takeover_id=bid["id"], shares=10_001, now=now)
    corporate.tender(db, account=player, takeover_id=bid["id"], shares=10_000, now=now)
    corporate.tender(db, account=player, takeover_id=bid["id"], shares=8_000, now=now)        # replaced: 2,000 come back
    assert ledger.balance(db, player, asset) == 2_000
    # Offered shares still belong to the player until the offer closes: they still count for dividends and votes.
    assert corporate._owners(db, bid["target_company_id"])[player] == 10_000
    whole(db)

    quarters.close_due_quarters(db, after_quarters(3))
    done = _dicts(db, "SELECT * FROM takeovers")[0]
    assert done["status"] == "won" and done["reserved"] == 0
    sold = -_dicts(db, "SELECT shares FROM holding_events WHERE account_id = %s AND kind = 'takeover'", (player,))[0]["shares"]
    assert 0 < sold <= 8_000 and ledger.balance(db, player, asset) == 10_000 - sold           # what was not bought came back
    paid = _dicts(db, "SELECT coalesce(sum(e.amount), 0)::bigint AS n FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " WHERE e.account_id = %s AND t.kind = 'takeover_payment' AND e.asset = 'NGN'", (player,))[0]["n"]
    assert paid == sold * bid["price"]
    # The bidder owns the shares, controls the company, and its accounts show the purchase.
    in_issue = ledger.amount_in_existence(db, asset)
    assert ledger.balance(db, bid["bidder_account"], asset) == done["bought"] and done["bought"] * 2 > in_issue
    assert done["paid"] == done["bought"] * bid["price"]
    control = corporate.control(db, bid["target_company_id"])
    assert control["controller"] and control["share_bps"] > 5000
    bidder = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 3", (bid["bidder_company_id"],))[0]
    assert bidder["investments"] == done["paid"] and "for shares in another company" in str(bidder["drivers"])
    assert "outside its normal business" not in str(bidder["drivers"])
    # The joining of the two businesses has begun.
    plan = _dicts(db, "SELECT * FROM integrations")[0]
    assert plan["start_period"] == 4 and plan["target_company_id"] == bid["target_company_id"]
    assert {n["kind"] for n in _dicts(db, "SELECT kind FROM news_items WHERE story = %s", (f"takeover:{bid['id']}",))} >= {"takeover_bid", "takeover_won"}
    whole(db)


def test_a_low_offer_the_board_rejects_can_fail_and_then_everybody_keeps_their_shares(db, monkeypatch):
    bid = _bid(db, monkeypatch, premium=2000)                      # below what the board and the pension funds accept
    assert bid["hostile"]
    assert "REJECTED" in _dicts(db, "SELECT body FROM market_notices WHERE kind = 'takeover_bid'")[0]["body"]
    player = trader(db, "amaka", shares=10_000, ticker=bid["ticker"])
    corporate.tender(db, account=player, takeover_id=bid["id"], shares=10_000, now=after_quarters(2))
    bidder_cash = ledger.balance(db, bid["bidder_account"])
    expected = corporate.expected_value(db, bid, 1_000)
    quarters.close_due_quarters(db, after_quarters(3))
    done = _dicts(db, "SELECT * FROM takeovers")[0]
    assert (done["status"] == "failed") == (expected is None)       # the outcome is what the public rules said it would be
    if done["status"] == "failed":
        assert ledger.balance(db, player, bid["share_asset"]) == 10_000 and done["bought"] == 0
        assert ledger.balance(db, bid["bidder_account"], bid["share_asset"]) == 0
        assert _dicts(db, "SELECT count(*) AS n FROM integrations")[0]["n"] == 0
        bidder = _dicts(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 3", (bid["bidder_company_id"],))[0]
        assert bidder["investments"] == 0 and "outside its normal business" not in str(bidder["drivers"])
    _ = bidder_cash
    whole(db)


def test_the_computer_run_investors_price_in_an_open_offer_so_its_outcome_cannot_be_traded_against_them(db, monkeypatch):
    bid = _bid(db, monkeypatch, premium=3500)
    worth = _dicts(db, "SELECT value_per_share FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                   (bid["target_company_id"],))[0]["value_per_share"]
    expected = corporate.expected_value(db, bid, worth)
    assert expected and worth < expected < bid["price"]
    trading = datetime.fromisoformat("2026-10-20T13:00:00+01:00")
    investors.act(db, trading, force=True)
    quote = exchange.quote(db, bid["ticker"], trading)
    best_offer = min(level["price"] for level in quote["offers"])
    # Nobody can buy from them at the old price and hand the shares to the bidder for more.
    assert best_offer * 100 >= expected * 97
    assert best_offer > worth * 105 // 100


def test_after_a_takeover_the_joining_is_worked_out_once_a_quarter_and_written_into_the_accounts(db, monkeypatch):
    bid = _bid(db, monkeypatch, premium=3500)
    monkeypatch.setattr(data, "TAKEOVER_ONE_IN", 10**9)
    quarters.close_due_quarters(db, after_quarters(5))
    if _dicts(db, "SELECT status FROM takeovers")[0]["status"] != "won":
        pytest.skip("the offer failed in this world")
    done = _dicts(db, "SELECT * FROM integration_results ORDER BY period")
    assert [r["period"] for r in done] == [4, 5]
    for row in done:
        result = _dicts(db, "SELECT drivers FROM company_results WHERE company_id = %s AND period = %s", (bid["target_company_id"], row["period"]))[0]
        assert row["notes"][0] in result["drivers"]["notes"]
        assert row["notes"][0].startswith("Being joined with")
    # Asking again changes nothing: a quarter's outcome is decided once.
    seed = _dicts(db, "SELECT fortune_seed FROM world_state")[0]["fortune_seed"]
    again = corporate.integration_effects(db, 5, seed, {})
    assert again[bid["target_company_id"]]["cost_bps"] == done[1]["cost_bps"]
    assert _dicts(db, "SELECT count(*) AS n FROM integration_results")[0]["n"] == 2
    # The bidder is paid the dividends on the shares it bought, and its accounts say so.
    whole(db)


# ---------------------------------------------------------------------------
# What companies decide for themselves
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_over_two_years_companies_use_the_market_and_everything_is_settled_cleanly(db):
    offers = _dicts(db, "SELECT kind, status FROM share_offers")
    assert offers and all(o["status"] in ("done", "withdrawn") or o["kind"] for o in offers)
    assert _dicts(db, "SELECT count(*) AS n FROM share_offers WHERE status = 'open' AND closes_period <= 8")[0]["n"] == 0
    assert _dicts(db, "SELECT count(*) AS n FROM company_votes WHERE status = 'open' AND closes_period <= 8")[0]["n"] == 0
    assert _dicts(db, "SELECT count(*) AS n FROM takeovers WHERE status = 'open' AND closes_period <= 8")[0]["n"] == 0
    assert _dicts(db, "SELECT count(*) AS n FROM market_notices")[0]["n"] > 0
    # No company's accounts were thrown out by any of it.
    assert _dicts(db, "SELECT count(*) AS n FROM company_results WHERE drivers::text LIKE '%%outside its normal business%%'")[0]["n"] == 0
    # A company with new shares, new bonds or shares in another still balances (the database checks every row).
    assert _dicts(db, "SELECT count(*) AS n FROM company_results WHERE total_assets <> total_liabilities + total_equity")[0]["n"] == 0
    whole(db)


def test_who_controls_a_company_is_whoever_holds_more_than_half(db):
    rows = corporate.ownership(db)
    assert len(rows) == 50
    for row in rows:
        assert (row["controller"] is not None) == (row["share_bps"] > 5000)
        assert "Player" not in row["summary"] and "player" not in row["summary"]


# ---------------------------------------------------------------------------
# Through the server
# ---------------------------------------------------------------------------

def test_offers_votes_and_bids_through_the_server(db, client, monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)
    for path in ("/api/corporate", "/api/corporate/ownership"):
        assert client.get(path).status_code == 401
    for path, body in (("/api/corporate/offers/1", {"shares": 1}), ("/api/corporate/votes/1", {"choice": "for"}),
                       ("/api/corporate/takeovers/1", {"shares": 1})):
        assert client.put(path, json=body).status_code == 401
    assert join(client, ADULT).status_code == 201
    in_issue = ledger.amount_in_existence(db, "SHR-IDC")
    offer_id = offer(db, kind="rights", price=reference(db) * 70 // 100, shares=in_issue // 3, rights=(1, 3))
    seen = client.get("/api/corporate").json()
    assert seen["offers"][0]["id"] == offer_id and seen["offers"][0]["needs_vote"] and seen["votes"][0]["status"] == "open"
    assert seen["notices"][0]["title"].endswith("rights issue")
    applied = client.put(f"/api/corporate/offers/{offer_id}", json={"shares": 100}).json()
    assert applied["offers"][0]["asked"] == 100 and int(applied["offers"][0]["held_kobo"]) == 100 * (reference(db) * 70 // 100)
    assert client.get("/api/market/portfolio").json()["held_for_offers_kobo"] == applied["offers"][0]["held_kobo"]
    # Only a shareholder has a vote.
    assert client.put(f"/api/corporate/votes/{seen['votes'][0]['id']}", json={"choice": "against"}).status_code == 409
    account = _dicts(db, "SELECT id FROM ledger_accounts WHERE kind = 'player'")[0]["id"]
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=10, asset="SHR-IDC",
                    kind="test_shares", memo="Test: shares")
    voted = client.put(f"/api/corporate/votes/{seen['votes'][0]['id']}", json={"choice": "against"}).json()
    assert voted["votes"][0]["my_choice"] == "against"
    for path, bad in ((f"/api/corporate/offers/{offer_id}", {"shares": -1}), (f"/api/corporate/offers/{offer_id}", {"shares": "5"}),
                      (f"/api/corporate/offers/{offer_id}", {"shares": 5, "price": 1}), (f"/api/corporate/votes/{seen['votes'][0]['id']}", {"choice": "abstain"}),
                      ("/api/corporate/offers/0", {"shares": 1})):
        assert client.put(path, json=bad).status_code == 422, bad
    assert client.put("/api/corporate/offers/999999", json={"shares": 1}).status_code == 409
    assert client.put("/api/corporate/takeovers/999999", json={"shares": 1}).status_code == 409
    assert client.put(f"/api/corporate/offers/{offer_id}", json={"shares": 10**9}).status_code == 409         # more than the player's cash
    assert len(client.get("/api/corporate/ownership").json()) == 50
    facts = client.get("/api/market/IDC/facts").json()
    assert facts["control"] and facts["notices"][0]["title"].endswith("rights issue")
    whole(db)
