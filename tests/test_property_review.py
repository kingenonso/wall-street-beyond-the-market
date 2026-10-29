"""Stage 8: the independent reviewer's twelve findings, each fixed and tested."""

from __future__ import annotations

import uuid
from datetime import timedelta

import psycopg
import pytest

from simulation import auctions, headquarters, ledger, marketview, quarters
from simulation import objectives as o
from simulation import objectives_property as op
from simulation import property as prop
from simulation.money import BPS
from tests.conftest import TEST_DATABASE_URL, after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_firm import firm_of
from tests.test_property import LATER, _one, a_bank, a_unit, end, hand_over, lot

pytestmark = pytest.mark.world("eight")


def _held(db):
    return ledger.balance(db, ledger.account_id(db, prop.HELD))


def test_1_a_price_at_the_limit_with_a_mortgage_settles_to_the_kobo(db):
    a = lot(db, a_unit(db, "Lagos")["id"])
    player, account = pro(db, "accountant", "exact", level=20, cash_naira=900_000_000)
    bank = a_bank(db)
    # Odd figures, so the hold (worked out on the limit) and the price's parts round differently.
    auctions.place_bid(db, account, a["id"], a["start_price"] + 7, LATER, player_id=player, mortgage_bank=bank["id"], mortgage_bps=7900)
    db.execute("UPDATE auctions SET price = %s WHERE id = %s", (a["start_price"] + 7, a["id"]))
    end(db, a)
    assert auctions._auction(db, a["id"])["status"] == "sold"
    assert _held(db) == 0
    sound(db)


def test_1_sellers_sharing_a_property_are_paid_every_kobo_and_a_bad_lot_never_stops_the_rest(db, monkeypatch):
    p = a_unit(db, "Abuja")
    owners = [pro(db, "accountant", f"own{n}", cash_naira=0)[1] for n in range(3)]
    db.execute("DELETE FROM property_holdings WHERE property_id = %s", (p["id"],))
    for account, share in zip(owners, (3333, 3333, 3334)):
        db.execute("INSERT INTO property_holdings (property_id, account_id, share_bps, since_period) VALUES (%s, %s, %s, 8)", (p["id"], account, share))
    seller = owners[2]
    with db.transaction():
        auction = auctions._open_auction(db, p["id"], seller, "owner", 0, 1001, 5000, NOW9, 9)
    buyer, buyer_account = pro(db, "lawyer", "buyer", cash_naira=900_000_000)
    auctions.place_bid(db, buyer_account, auction, 1001, LATER, player_id=buyer)
    # Another lot whose settling fails is ended unsold instead of stopping the run.
    other = lot(db, a_unit(db, "Kano")["id"])
    real = auctions._settle
    monkeypatch.setattr(auctions, "_settle", lambda conn, a, now: (_ for _ in ()).throw(RuntimeError("boom")) if a["id"] == other["id"] else real(conn, a, now))
    auctions.run(db, max(auctions._auction(db, auction)["ends_at"], other["ends_at"]) + timedelta(seconds=1))
    assert auctions._auction(db, auction)["status"] == "sold" and auctions._auction(db, other["id"])["status"] == "unsold"
    assert _held(db) == 0
    sound(db)


def test_2_a_partner_cannot_agree_once_the_auction_has_ended_and_waiting_asks_are_released(db):
    a = lot(db, a_unit(db, "Aba")["id"])
    lead, lead_account = pro(db, "accountant", "lead", cash_naira=900_000_000)
    friend, friend_account = pro(db, "lawyer", "friend", cash_naira=900_000_000)
    ask = auctions.ask_partner(db, lead_account, a["id"], friend_account, 3000, LATER)
    auctions.place_bid(db, lead_account, a["id"], a["start_price"], LATER, player_id=lead)
    with pytest.raises(prop.PropertyError, match="not taking bids"):
        auctions.answer_partner(db, friend_account, ask, True, a["start_price"] * 4, a["ends_at"] + timedelta(seconds=1))
    end(db, a)
    assert _one(db, "SELECT status FROM auction_partners WHERE id = %s", (ask,))["status"] == "released"
    with pytest.raises(prop.PropertyError):
        auctions.answer_partner(db, friend_account, ask, True, a["start_price"] * 4, LATER)
    assert _held(db) == 0
    sound(db)


def test_3_an_empire_shares_a_bid_only_after_its_checks_within_its_top_price_and_never_for_a_members_property(db):
    empire, team = firm_of(db)
    a = lot(db, a_unit(db, "Lagos")["id"])
    friend, friend_account = pro(db, "investment_banker", "outsider", cash_naira=900_000_000)
    ask = auctions.ask_partner(db, friend_account, a["id"], empire["account_id"], 9000, LATER)
    with pytest.raises(prop.PropertyError, match="Still to do"):
        auctions.answer_partner(db, empire["account_id"], ask, True, a["fair"], LATER)
    auctions.check(db, team["lawyer"], a["id"], "title", {}, LATER)
    auctions.check(db, team["accountant"], a["id"], "valuation", {"value": a["fair"]}, LATER)
    auctions.check(db, team["risk_manager"], a["id"], "limit", {"limit": a["fair"]}, LATER)
    auctions.check(db, team["investment_banker"], a["id"], "money", {"mortgage_bps": 0}, LATER)
    with pytest.raises(prop.PropertyError, match="top price"):
        auctions.answer_partner(db, empire["account_id"], ask, True, a["fair"] + 1, LATER)
    auctions.answer_partner(db, empire["account_id"], ask, True, a["fair"], LATER)
    # A member's property: refused even with every check done.
    p = a_unit(db, "Abuja")
    seller = ledger.player_account_id(db, team["accountant"])
    hand_over(db, p["id"], seller)
    member_lot = auctions.owner_list(db, seller, p["id"], 0, NOW9)
    for step, answer, who in (("title", {}, "lawyer"), ("valuation", {"value": 10**9}, "accountant"), ("limit", {"limit": 10**9}, "risk_manager"),
                              ("money", {"mortgage_bps": 0}, "investment_banker")):
        auctions.check(db, team[who], member_lot, step, answer, LATER)
    ask2 = auctions.ask_partner(db, friend_account, member_lot, empire["account_id"], 9000, LATER)
    with pytest.raises(prop.PropertyError, match="own members"):
        auctions.answer_partner(db, empire["account_id"], ask2, True, 10**9, LATER)
    sound(db)


def test_4_a_lone_top_price_at_or_above_the_reserve_buys_at_the_reserve(db):
    a = _one(db, "SELECT * FROM auctions WHERE status = 'open' AND property_id IS NOT NULL AND opens_at <= %s ORDER BY fair LIMIT 1", (NOW9,))
    player, account = pro(db, "accountant", "lone", cash_naira=900_000_000)
    seller_before = ledger.balance(db, a["seller"])
    done = auctions.place_bid(db, account, a["id"], a["fair"], LATER, player_id=player)
    assert done["price"] == a["start_price"]                      # the lowest price is never shown while it runs
    assert auctions._reserve_met(db, auctions._auction(db, a["id"]))
    end(db, a)
    assert auctions._auction(db, a["id"])["status"] == "sold" and prop.share_of(db, a["property_id"], account) == BPS
    assert ledger.balance(db, a["seller"]) == seller_before + a["reserve"]
    sound(db)


def test_5_property_and_bid_cash_count_in_the_closing_bells_net_worth():
    import server.main  # noqa: F401  (everything imported, in the server's order)
    from simulation import closingbell  # noqa: F401
    assert prop._players_property in marketview._OTHER_HOLDINGS
    # Each registered once: bonds, offer cash, property, and (Stage 9) loans and shorts, options and futures.
    from simulation import derivatives, lending
    assert lending._players_lending in marketview._OTHER_HOLDINGS and derivatives._players_derivatives in marketview._OTHER_HOLDINGS
    # (The gap stage adds swaps, preferred shares and warrants, and property-fund units.)
    from simulation import instruments, propfunds, swaps
    assert {swaps._players_swaps, instruments._players_instruments, propfunds._players_units} <= set(marketview._OTHER_HOLDINGS)
    # (The crises stage adds savings at the banks.)
    assert marketview._savings_held in marketview._OTHER_HOLDINGS
    # (The talent and funds stage, Part 2, adds units in investment funds.)
    from simulation import funds
    assert funds._players_holdings in marketview._OTHER_HOLDINGS
    assert len(marketview._OTHER_HOLDINGS) == len(set(marketview._OTHER_HOLDINGS)) == 10


def test_6_a_lot_is_searched_once_for_an_empire_and_the_fee_is_in_its_books(db):
    empire, team = firm_of(db)
    a = lot(db, a_unit(db, "Lagos")["id"])
    before = ledger.balance(db, empire["account_id"])
    first = auctions.check(db, team["lawyer"], a["id"], "title", {}, LATER)
    after_one = ledger.balance(db, empire["account_id"])
    assert after_one < before
    for _ in range(5):
        assert auctions.check(db, team["lawyer"], a["id"], "title", {}, LATER) == first
    assert ledger.balance(db, empire["account_id"]) == after_one
    assert _one(db, "SELECT count(*) AS n FROM empire_books WHERE empire_id = %s AND description LIKE 'Title search%%'", (empire["id"],))["n"] == 1


def test_7_a_member_does_not_buy_the_empires_property_for_themselves(db):
    empire, team = firm_of(db)
    p = a_unit(db, "Lagos")
    hand_over(db, p["id"], empire["account_id"])
    auction = auctions.owner_list(db, empire["account_id"], p["id"], 0, NOW9)
    head_account = ledger.player_account_id(db, team["head"])
    give = 900_000_000_00
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=head_account, amount=give, kind="test_cash", memo="Test: cash")
    for who in ("head", "accountant"):
        with pytest.raises(prop.PropertyError, match="your empire's property"):
            auctions.place_bid(db, ledger.player_account_id(db, team[who]), auction, auctions.minimum(auctions._auction(db, auction)), LATER,
                               player_id=team[who])


def test_8_the_bankers_property_paper_sometimes_needs_a_partner_and_sometimes_not(db):
    seen = set()
    for n in range(40):
        ctx = {"conn": db, "player_id": uuid.UUID(int=n + 1), "period": 9, "now": NOW9}
        terms = op._funding_offer(ctx)
        verdict = op._funding_submit(ctx, {"terms": terms}, {})
        seen.add(verdict["answers"]["partner"])
    assert seen == {"yes", "no"}


def test_9_the_title_paper_says_the_claim_is_on_the_sellers_share_and_marks_it_so(db):
    for n in range(40):
        ctx = {"conn": db, "player_id": uuid.UUID(int=n + 1), "period": 9, "now": NOW9}
        terms = op._title_offer(ctx)
        if terms["claim_bps"]:
            assert any("of the seller's share" in g["text"] for g in terms["given"])
            right = op._title_submit(ctx, {"terms": terms}, {})["answers"]["share"]
            assert right == round(terms["seller_bps"] * (BPS - terms["claim_bps"]) / BPS / 100, 2)
            return
    pytest.fail("no case with a claim drawn")


def test_10_a_title_claim_on_the_headquarters_building_stops_its_benefits(db):
    empire, team = firm_of(db, n_cash=50_000_000_000)
    flawed = _one(db, "SELECT * FROM properties WHERE title_flaw_bps > 0 AND status = 'standing' AND kind <> 'land' ORDER BY size_m2 LIMIT 1")
    hand_over(db, flawed["id"], empire["account_id"])
    headquarters.establish(db, team["head"], flawed["id"], NOW9)
    headquarters.raise_level(db, team["head"], 10, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    hq = headquarters.of(db, empire["id"])
    assert hq["homeless"] and not headquarters.standing(hq) and headquarters.bonus_bps(db, empire["id"]) == 0
    assert all(s["hq_frozen"] for s in o._rows(db, "SELECT hq_frozen FROM empire_seats WHERE empire_id = %s AND slot >= 3", (empire["id"],)))
    sound(db)


def test_11_a_risk_manager_who_asked_for_the_upkeep_is_not_blamed_and_the_head_who_refused_is(db, monkeypatch):
    empire, team = firm_of(db, n_cash=50_000_000_000)
    p = a_unit(db, "Lagos")
    hand_over(db, p["id"], empire["account_id"])
    headquarters.establish(db, team["head"], p["id"], NOW9)
    headquarters.ask_upkeep(db, team["risk_manager"], NOW9)
    db.execute("UPDATE players SET reputation = 50 WHERE id = ANY(%s)", ([team["head"], team["risk_manager"]],))
    db.execute("UPDATE headquarters SET condition = 20 WHERE empire_id = %s", (empire["id"],))
    monkeypatch.setattr(headquarters, "_uniform", lambda *args: 0.0)
    quarters.close_due_quarters(db, after_quarters(9))
    rep = {r["id"]: r["reputation"] for r in o._rows(db, "SELECT id, reputation FROM players WHERE id = ANY(%s)", ([team["head"], team["risk_manager"]],))}
    assert headquarters.of(db, empire["id"])["collapsed_period"] == 9
    assert rep[team["head"]] == 45 and rep[team["risk_manager"]] == 50


def test_12_one_bidders_bids_are_placed_one_at_a_time(db):
    a = lot(db, a_unit(db, "Kano")["id"])
    player, account = pro(db, "accountant", "twice", cash_naira=900_000_000)
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as other:
        with other.transaction():
            other.execute("SELECT pg_advisory_xact_lock(hashtext('bidder:' || %s::text))", (str(account),))
            db.execute("SET lock_timeout = '300ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                auctions.place_bid(db, account, a["id"], a["start_price"], LATER, player_id=player)
            db.execute("SET lock_timeout = 0")
    auctions.place_bid(db, account, a["id"], a["start_price"], LATER, player_id=player)
