"""Stage 4: the attacks the independent reviewer made, each kept as a test.

A second reviewer, who did not write the code, was told to break Stage 4. Five serious holes,
one medium and four small ones were found. Each is fixed, and each attack is repeated here so
that it can never quietly come back.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import (
    bonds,
    corporate,
    exchange,
    grants,
    investors,
    ledger,
    quarters,
    valuation,
)
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, TEST_DATABASE_URL, after_quarters, join
from tests.test_bonds import _convertible, bond, corp, one, state
from tests.test_market import place, reference, sound, trader

OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")
EIGHT = datetime.fromisoformat("2026-12-01T13:00:00+01:00")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# 1. A bond that can be swapped for shares was sold at a plain bond's price however far the share had risen.

def test_the_desk_never_sells_the_right_to_swap_for_less_than_the_shares_are_worth(db):
    corp(db)
    company, made = _convertible(db, shares_each=80)             # 80 shares a bond: far more than ₦1,000 of shares
    code = made["asset"][4:]
    share = bonds.market(db, OPEN)["shares"][company["id"]]
    worth_of_swap = 80 * max(share["market"], share["worth"])
    assert worth_of_swap > bonds.FACE
    row = next(b for b in bonds.listing(db, OPEN) if b["code"] == code)
    assert row["ask"] >= worth_of_swap and row["fair"] >= 80 * min(share["market"], share["worth"])
    # Buying, swapping and selling the shares at what they are worth leaves nothing over.
    player = trader(db, "ngozi", cash_naira=10_000_000)
    bought = bonds.trade(db, account=player, code=code, side="buy", units=10, now=OPEN)
    assert bought["value"] >= 10 * worth_of_swap
    # A plain bond is unaffected, and a convertible is never worth less than the same bond without the right.
    plain = bond(issuer="company", company_id=company["id"], coupon_bps=1300)
    with_right = {**plain, "kind": "convertible", "conversion_shares": 1}
    st = bonds.market(db, OPEN)
    assert bonds.fair_value(with_right, st) >= bonds.fair_value(plain, st)


# 2. The computer-run investors priced in a takeover offer only for the first share in the alphabet.

@pytest.mark.world("eight")
def test_investors_price_in_a_takeover_offer_whichever_company_it_is_for(db):
    target = _dicts(db, "SELECT c.*, m.reference_price FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = 'TMB'")[0]
    bidder = _dicts(db, "SELECT * FROM companies WHERE ticker = 'GFM'")[0]
    worth = valuation.latest(db)[target["id"]]["value_per_share"]
    price = worth * 135 // 100
    in_issue = ledger.amount_in_existence(db, target["share_asset"])
    db.execute("INSERT INTO takeovers (bidder_company_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved,"
               " opens_period, closes_period) VALUES (%s, %s, %s, %s, false, 3500, 0, 8, 9)", (bidder["id"], target["id"], price, in_issue * 6 // 10))
    bid = _dicts(db, "SELECT * FROM takeovers WHERE status = 'open' ORDER BY id DESC")[0]
    expected = corporate.expected_value(db, bid, worth)
    assert expected and expected > worth * 110 // 100
    investors.act(db, EIGHT, force=True)
    offers = exchange.quote(db, "TMB", EIGHT)["offers"]
    assert offers and min(level["price"] for level in offers) * 100 >= expected * 97        # not the old price
    # A company with no offer is priced as before.
    other = exchange.quote(db, "ZRB", EIGHT)
    zrb = valuation.latest(db)[_dicts(db, "SELECT id FROM companies WHERE ticker = 'ZRB'")[0]["id"]]["value_per_share"]
    assert abs(min(level["price"] for level in other["offers"]) - zrb) < zrb // 10


@pytest.mark.world("eight")
def test_what_players_have_offered_a_bidder_does_not_move_what_investors_expect(db):
    target = _dicts(db, "SELECT * FROM companies WHERE ticker = 'TMB'")[0]
    bidder = _dicts(db, "SELECT * FROM companies WHERE ticker = 'GFM'")[0]
    worth = valuation.latest(db)[target["id"]]["value_per_share"]
    in_issue = ledger.amount_in_existence(db, target["share_asset"])
    # A low, rejected offer: by the public rules it fails.
    db.execute("INSERT INTO takeovers (bidder_company_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved,"
               " opens_period, closes_period) VALUES (%s, %s, %s, %s, true, 2000, 0, 8, 9)", (bidder["id"], target["id"], worth * 120 // 100, in_issue * 6 // 10))
    bid = _dicts(db, "SELECT * FROM takeovers WHERE status = 'open' ORDER BY id DESC")[0]
    before = corporate.expected_value(db, bid, worth)
    whale = trader(db, "whale", shares=0)
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    ledger.transfer(db, payer=founders, receiver=whale, amount=ledger.balance(db, founders, target["share_asset"]) // 2,
                    asset=target["share_asset"], kind="test_shares", memo="Test: a very large holding")
    corporate.tender(db, account=whale, takeover_id=bid["id"], shares=ledger.balance(db, whale, target["share_asset"]), now=EIGHT)
    assert corporate.expected_value(db, bid, worth) == before               # it can be taken back, so it is not counted


# 3 and 4. After a quarter had ended but before the server closed it, bills were priced a quarter cheap.

def test_nothing_is_sold_in_the_moments_after_a_quarter_ends_and_before_it_is_closed(db):
    player = trader(db, "ngozi", cash_naira=500_000, shares=100)
    bill = one(db, "bill")
    just_after = after_quarters(1) - timedelta(minutes=59, seconds=55)        # five seconds after the quarter's end; not yet closed
    for attempt in (lambda: bonds.trade(db, account=player, code=bill["code"], side="buy", units=10, now=just_after),
                    lambda: bonds.ask_to_convert(db, account=player, code=bill["code"], units=1, now=just_after)):
        with pytest.raises(bonds.BondError, match="books are being closed"):
            attempt()
    # What the page shows is not a bargain either: the bill is priced as due now.
    shown = next(b for b in bonds.listing(db, just_after) if b["code"] == bill["code"])
    assert shown["ask"] >= bonds.FACE
    assert ledger.balance(db, player) == naira(500_000)
    quarters.close_due_quarters(db, just_after)
    fresh = one(db, "bill", now=just_after)
    assert fresh["code"] != bill["code"] and bonds.trade(db, account=player, code=fresh["code"], side="buy", units=10, now=just_after)["price"] < bonds.FACE
    sound(db)


def test_a_purchase_waits_for_a_quarter_close_that_is_running_instead_of_colliding_with_it(db, connect):
    player = trader(db, "ngozi", cash_naira=500_000)
    bill = one(db, "bill")
    closing = connect()
    closing.execute("BEGIN")
    closing.execute("SELECT * FROM world_state FOR UPDATE")                    # what a quarter close holds from start to finish
    outcome = {}

    def buy():
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute("SET lock_timeout = '700ms'")
            try:
                bonds.trade(conn, account=player, code=bill["code"], side="buy", units=1, now=OPEN)
                outcome["done"] = True
            except errors.LockNotAvailable:
                outcome["waited"] = True

    thread = threading.Thread(target=buy)
    thread.start()
    thread.join()
    closing.execute("ROLLBACK")
    assert outcome == {"waited": True}                                         # it took nothing the close needs before waiting
    assert ledger.balance(db, player) == naira(500_000)
    bonds.trade(db, account=player, code=bill["code"], side="buy", units=1, now=OPEN)


# 5. One tiny trade froze a share's price for ever once its worth moved more than a tenth away.

@pytest.mark.world("eight")
def test_a_share_whose_worth_has_fallen_far_below_its_price_steps_down_a_tenth_a_day_and_trades_again(db, monkeypatch):
    investors.act(db, EIGHT, force=True)
    holder, buyer = trader(db, "holder", shares=1_000, ticker="AGA"), trader(db, "buyer", cash_naira=1_000_000)
    price = reference(db, "AGA")
    place(db, holder, "sell", 1, price, now=EIGHT, ticker="AGA")
    place(db, buyer, "buy", 1, price, now=EIGHT, ticker="AGA")                 # one share: the price is now "set by trading"
    company = _dicts(db, "SELECT id FROM companies WHERE ticker = 'AGA'")[0]["id"]
    real = valuation.latest

    def halved(conn):
        worth = real(conn)
        worth[company] = {**worth[company], "value_per_share": worth[company]["value_per_share"] // 2}
        return worth
    monkeypatch.setattr(valuation, "latest", halved)                           # its worth has halved

    seen = [price]
    for day in range(1, 8):
        now = EIGHT + timedelta(days=day)
        investors.act(db, now, force=True)
        investors.act(db, now + timedelta(minutes=10), force=True)             # looking again the same day moves nothing further
        quote = exchange.quote(db, "AGA", now + timedelta(minutes=10))
        seen.append(quote["last_price"])
        assert seen[-1] >= seen[-2] * 89 // 100                                # never more than a tenth in a day
    assert seen[-1] < price * 60 // 100                                        # it got there
    assert any("moved the price to that limit" in r["reason"] for r in _dicts(db, "SELECT reason FROM market_reasons"))
    # And once there, somebody will buy: a holder can sell.
    quote = exchange.quote(db, "AGA", EIGHT + timedelta(days=7, minutes=10))
    assert quote["bids"], "there must be buyers inside the limits again"
    sold = place(db, holder, "sell", 20, now=EIGHT + timedelta(days=7, minutes=20), ticker="AGA")
    assert sold["trades"]
    sound(db)


@pytest.mark.world("eight")
def test_the_exchange_does_not_move_a_price_that_trading_can_move(db):
    investors.act(db, EIGHT, force=True)
    before = {r["company_id"]: r["last_price"] for r in _dicts(db, "SELECT company_id, last_price FROM market_instruments")}
    for day in range(1, 4):
        investors.act(db, EIGHT + timedelta(days=day), force=True)
    assert _dicts(db, "SELECT count(*) AS n FROM market_instruments WHERE marked_session IS NOT NULL")[0]["n"] == 0
    assert not any("moved the price" in r["reason"] for r in _dicts(db, "SELECT reason FROM market_reasons"))
    _ = before


def test_new_shares_are_priced_from_the_lower_of_the_market_price_and_what_the_company_is_worth(db, monkeypatch):
    """A price nobody will pay must not make a rights issue that nobody takes up."""
    monkeypatch.setattr(data, "TAKEOVER_ONE_IN", 10**9)
    holder, buyer = trader(db, "holder", shares=10, ticker="OGA"), trader(db, "buyer", cash_naira=100_000)
    price = reference(db, "OGA")
    place(db, holder, "sell", 1, price, ticker="OGA")
    place(db, buyer, "buy", 1, price, ticker="OGA")                            # the attack: one share, to pin the price
    quarters.close_due_quarters(db, after_quarters(1))
    offers = _dicts(db, "SELECT o.*, c.ticker, v.value_per_share FROM share_offers o JOIN companies c ON c.id = o.company_id"
                        " JOIN company_valuations v ON v.company_id = o.company_id AND v.period = 1 WHERE o.kind = 'rights'")
    assert offers, "the test needs a rights issue announced at the first close"
    for offer in offers:
        assert offer["price"] <= offer["value_per_share"]                      # never dearer than the shares are worth


# 6. The inflation-linked bond sagged through the quarter and jumped back at the close.

def test_an_inflation_linked_bond_does_not_sag_through_the_quarter():
    linked = bond(kind="inflation_linked", coupon_bps=775, issue_index_bps=BPS, maturity_period=20)
    values = [bonds.fair_value(linked, state(left=left, index=10_300)) for left in (1.0, 0.75, 0.5, 0.25, 0.01)]
    assert values == sorted(values)                                            # it grows towards its next payment, like any bond
    # Across a close with prices up 1.5% in the quarter (the target's pace), there is no jump.
    before_close = bonds.fair_value(linked, state(left=0.0, index=10_300))
    coupon = bonds.FACE * 10_300 // BPS * 775 // BPS // 4
    after_close = bonds.fair_value(linked, state(period=1, left=1.0, index=10_300 * 10_147 // 10_000))
    assert abs(after_close + coupon - before_close) < before_close // 150


# 7. A part of the starting grant could be earned with no stake.

def test_only_a_shareholder_can_vote_and_an_empty_acceptance_leaves_no_trace(db, client):
    assert join(client, ADULT).status_code == 201
    row = _dicts(db, "SELECT a.id AS account, a.player_id FROM ledger_accounts a WHERE a.kind = 'player'")[0]
    company = _dicts(db, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE ticker = 'IDC'")[0]
    with db.transaction():
        corporate.announce_offer(db, company, kind="rights", price=reference(db) * 70 // 100,
                                 shares=ledger.amount_in_existence(db, "SHR-IDC") // 3, period=0, reason="A test.", now=OPEN, rights=(1, 3))
    vote = _dicts(db, "SELECT id FROM company_votes")[0]["id"]
    with pytest.raises(corporate.CorporateError, match="no shares"):
        corporate.cast_vote(db, account=row["account"], vote_id=vote, choice="for", now=OPEN)
    db.execute("INSERT INTO takeovers (bidder_company_id, target_company_id, price, shares_sought, hostile, premium_bps, reserved,"
               " opens_period, closes_period) SELECT b.id, %s, 3000, 1000, false, 3500, 0, 0, 1 FROM companies b WHERE b.ticker = 'KRC'", (company["id"],))
    corporate.tender(db, account=row["account"], takeover_id=_dicts(db, "SELECT id FROM takeovers WHERE status = 'open'")[0]["id"], shares=0, now=OPEN)
    assert _dicts(db, "SELECT count(*) AS n FROM takeover_tenders")[0]["n"] == 0 and _dicts(db, "SELECT count(*) AS n FROM vote_ballots")[0]["n"] == 0
    assert grants.review(db, row["player_id"], OPEN + timedelta(days=3))["steps"][3]["earned"] is False


# 8. Buying Government bonds from the Treasury lifted what the pension funds would pay for them.

def test_buying_from_the_treasury_does_not_move_what_the_pension_funds_pay(db):
    corp(db)
    player = trader(db, "ngozi", cash_naira=5_000_000_000)
    row = one(db, "fixed")
    before = next(b for b in bonds.listing(db, OPEN) if b["code"] == row["code"])
    bonds.trade(db, account=player, code=row["code"], side="buy", units=2_000_000, now=OPEN)
    after = next(b for b in bonds.listing(db, OPEN) if b["code"] == row["code"])
    assert after["bid"] <= before["bid"] and after["ask"] == before["ask"]
    assert after["bid"] <= after["fair"] * (BPS - 20) // BPS + 1


# 9. A bond's "outstanding" figure showed what players held between them while players were few.

def test_the_bond_page_does_not_show_what_a_few_players_hold_between_them(db, client, player, monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)
    other = trader(db, "other", cash_naira=5_000_000)
    bill = one(db, "bill")
    bonds.trade(db, account=other, code=bill["code"], side="buy", units=1_717, now=OPEN)
    seen = client.get("/api/bonds").json()
    assert "1717" not in str(seen)
    for row in seen["bonds"]:
        if row["issuer"] == "Federal Government":
            assert row["outstanding"] is None
        assert row["on_offer"] is None


# 10. Leads the reviewer could not prove; closed all the same.

def test_a_sale_of_new_shares_to_the_public_is_at_the_market_price(db):
    assert data.OFFER_DISCOUNT_BPS == 0


def test_a_bond_of_a_company_rated_ccc_or_d_is_not_replaced_at_its_full_value(db):
    """It trades at 40% of its face value; replacing it at 100% would be a sure gain for whoever bought it cheap."""
    import inspect

    from simulation import companies
    source = inspect.getsource(companies.close_company_quarter)
    assert 'net_profit + earlier_profit > 0 and rating not in ("CCC", "D")' in source
