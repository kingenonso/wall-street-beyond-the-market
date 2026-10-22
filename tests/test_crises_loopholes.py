"""The crises stage, Part 1: ten questions a player might ask to get round the rules, each answered by a test."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import auctions, crisis, deposits, intel, ledger, lending, quarters
from simulation.money import naira
from simulation.property import PropertyError
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_crises import P, days, weaken
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def test_l1_savings_put_in_for_a_moment_before_the_close_earn_nothing(db):
    """'I'll move my cash into savings just before the quarter closes, and take it out after.'"""
    p, account = pro(db, "accountant", "kiter", cash_naira=50_000_000)
    deposits.put_in(db, p, "IKB", naira(40_000_000), after_quarters(9) - timedelta(minutes=30))
    quarters.close_due_quarters(db, after_quarters(9))
    paid = _one(db, "SELECT amount FROM savings_interest WHERE account_id = %s AND period = %s", (account, P))
    assert paid["amount"] == 0
    # Moving the money from bank to bank does not help either: each bank pays on the least kept with it all quarter.
    deposits.take_out(db, p, "IKB", naira(40_000_000), after_quarters(9) + timedelta(hours=2))
    deposits.put_in(db, p, "HMB", naira(40_000_000), after_quarters(10) - timedelta(minutes=30))
    quarters.close_due_quarters(db, after_quarters(10))
    assert _one(db, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM savings_interest WHERE account_id = %s", (account,))["t"] == 0


def test_l2_savings_cannot_be_written_into_the_ledger_a_second_time(db):
    """'Can a bank's savers be written in again, to make savings out of nothing?'"""
    b = deposits.bank(db, "IKB")
    p, account = pro(db, "accountant", "minter")
    with pytest.raises(errors.RestrictViolation):
        ledger.post(db, kind="deposit_record", memo="again", period=P,
                    legs=[ledger.Leg(b["account_id"], -naira(1_000_000), b["asset"]), ledger.Leg(account, naira(1_000_000), b["asset"])])
    assert deposits.saved(db, account, b["asset"]) == 0
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_l3_only_the_head_moves_the_empires_money_into_savings_and_only_within_what_they_may_sign(db):
    """'I'm a member: I'll park the empire's cash at a shaky bank.' / 'I'm the head: I'll move it all.'"""
    empire, team = firm_of(db, n_cash=2_000_000_000)
    with pytest.raises(deposits.SavingsError, match="head"):
        deposits.put_in(db, team["accountant"], "IKB", naira(1_000_000), NOW9, for_empire=True)
    with pytest.raises(deposits.SavingsError, match="sign"):
        deposits.put_in(db, team["head"], "IKB", naira(1_900_000_000), NOW9, for_empire=True)
    deposits.put_in(db, team["head"], "IKB", naira(1_000_000), NOW9, for_empire=True)
    # ...and moving it a piece at a time does not get round the limit: what was moved this quarter counts.
    from simulation import empires
    room = empires.signing_limit(db, empires.seat_of(db, team["head"])) - naira(1_000_000)
    with pytest.raises(deposits.SavingsError, match="sign"):
        deposits.put_in(db, team["head"], "IKB", room + naira(1), NOW9, for_empire=True)
    assert deposits.saved(db, empire["account_id"], deposits.bank(db, "IKB")["asset"]) == naira(1_000_000)
    # A member never sees another saver's money; the view shows the empire's only to its own people.
    view = deposits.view(db, team["accountant"], NOW9)
    assert next(b for b in view["banks"] if b["ticker"] == "IKB")["empire"] == naira(1_000_000)
    outsider, _ = pro(db, "lawyer", "outsider")
    assert all(b["empire"] is None for b in deposits.view(db, outsider, NOW9)["banks"])


def test_l4_a_closed_bank_takes_and_pays_nothing_trades_nothing_and_cannot_be_bought_cheaply_or_by_itself(db):
    p, account = pro(db, "accountant", "frozen", cash_naira=20_000_000)
    deposits.put_in(db, p, "OTB", naira(10_000_000), NOW9)
    b = weaken(db, "OTB", -100)
    crisis.cannot_pay(db, b, P, 10, NOW9)
    for move in (deposits.put_in, deposits.take_out):
        with pytest.raises(deposits.SavingsError, match="closed"):
            move(db, p, "OTB", naira(1_000_000), NOW9)
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    with pytest.raises(PropertyError, match="lowest bid"):
        auctions.place_bid(db, account, a["id"], a["start_price"] - 1, NOW9 + timedelta(minutes=1), player_id=p)
    with pytest.raises(PropertyError, match="itself"):
        auctions.place_bid(db, b["account_id"], a["id"], a["start_price"] * 2, NOW9 + timedelta(minutes=1))
    with pytest.raises(PropertyError, match="outright"):
        auctions.ask_partner(db, account, a["id"], ledger.account_id(db, ledger.TREASURY), 1000, NOW9)


def test_l5_savings_are_no_hiding_place_from_what_a_player_owes(db):
    """'I'll keep my money in savings so a margin call cannot reach it.'"""
    p, account = pro(db, "asset_manager", "dodger", cash_naira=30_000_000)
    deposits.put_in(db, p, "IKB", naira(25_000_000), NOW9)
    before = deposits.savings_of(db, account)
    # Savings count as security for a loan, and a forced sale takes them first, before any share is sold.
    assert lending.holdings_value(db, account, NOW9)["cash"] >= before
    raised = lending._raise_cash(db, account, naira(10_000_000), P, NOW9, "Margin call not met")
    assert raised >= naira(10_000_000)
    assert deposits.savings_of(db, account) == before - naira(10_000_000)


def test_l6_no_new_short_sales_in_a_bank_while_its_savers_run(db):
    """'A run is coming: I'll sell the bank short.'"""
    b = weaken(db, "KCB", 300)
    days(db, 12)
    from simulation import exchange
    today, _ = exchange.session_of(NOW9)
    assert lending.short_ban(db, b["id"], today) is not None


def test_l7_a_planted_rumour_that_comes_before_a_run_is_kept_for_the_courts_but_pulling_money_out_is_lawful(db):
    j, _ = pro(db, "journalist", "whisperer", level=20)
    b = deposits.bank(db, "KCB")
    item = intel.make(db, kind="rumour", topic="company", company_id=b["id"], tone=-1, words="Kainji Commercial Bank is in trouble.",
                      truth="unknown", basis="planted", planted_by=j, period=P, day=1, now=NOW9)
    db.execute("INSERT INTO stories (author_id, status, facts, checked, angle, tickers, tone, headline, body, readers, period, day,"
               " started_at, published_at, lead) VALUES (%s, 'published', '[]', '[]', 'plain', %s, -1, 'Trouble at Kainji', 'Words.', 1000,"
               " %s, 1, %s, %s, %s)", (j, [b["ticker"]], P, NOW9, NOW9,
                                        Jsonb({"item_id": item["id"], "tone": -1})))
    weaken(db, "KCB", 300)
    days(db, 6)
    kept = _one(db, "SELECT * FROM run_stories WHERE company_id = %s", (b["id"],))
    assert kept and kept["planted_by"] == j
    # Never shown: nothing on the website names it.
    assert "run_stories" not in repr(crisis.bank_view(db, NOW9)) and "planted" not in repr(crisis.crises_view(db, NOW9))
    # Pulling one's own money out, even in a run, is allowed (and is not recorded as anything).
    saver, _ = pro(db, "lawyer", "careful", cash_naira=8_000_000)
    deposits.put_in(db, saver, "IKB", naira(6_000_000), NOW9)
    deposits.take_out(db, saver, "IKB", naira(6_000_000), NOW9)


def test_l8_the_guarantee_protects_the_first_5_million_and_a_full_guarantee_protects_all(db):
    small, small_account = pro(db, "lawyer", "small", cash_naira=5_000_000)
    deposits.put_in(db, small, "ZCB", naira(5_000_000), NOW9)
    b = weaken(db, "ZCB", -500)
    crisis.cannot_pay(db, b, P, 15, NOW9)
    assert deposits.saved(db, small_account, b["asset"]) == naira(5_000_000)
    # Under the Government's full guarantee, nobody's savings are written down at all.
    db.execute("INSERT INTO blanket_guarantees (from_period, from_day, reason, at) VALUES (%s, 1, 'test', %s)", (P, NOW9))
    big, big_account = pro(db, "accountant", "big", cash_naira=80_000_000)
    deposits.put_in(db, big, "HMB", naira(70_000_000), NOW9)
    h = weaken(db, "HMB", -300)
    r = crisis.cannot_pay(db, h, P, 16, NOW9)
    assert _one(db, "SELECT bail_in FROM bank_resolutions WHERE id = %s", (r,))["bail_in"] == 0
    assert deposits.saved(db, big_account, h["asset"]) == naira(70_000_000)
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_l9_working_through_a_game_day_twice_changes_nothing(db):
    """'Can the server be made to run a day's withdrawals twice?'"""
    weaken(db, "KCB", 300)
    days(db, 10)
    flows = _one(db, "SELECT count(*) AS n, coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE period = %s", (P,))
    assert crisis.run_days(db, P, 10, NOW9) == 0
    assert crisis.run_days(db, P, 5, NOW9) == 0
    assert _one(db, "SELECT count(*) AS n, coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE period = %s", (P,)) == flows


def test_l10_nothing_private_reaches_the_website(db, client):
    """Never sent: anybody else's savings, an open crisis's hidden weakness, a bank auction's lowest price or anyone else's limit,
    the stories kept for the courts."""
    assert join(client, ADULT).status_code == 201
    rich, _ = pro(db, "accountant", "rich", cash_naira=50_000_000)
    deposits.put_in(db, rich, "IKB", naira(45_000_000), NOW9)
    weaken(db, "KCB", 300)
    days(db, 20)
    page = client.get("/api/crisis").json()
    text = repr(page)
    for secret in ("weakness", "reserve", "limit_price", "run_stories", "planted", "covered"):
        if secret == "weakness":
            assert all("weakness" not in repr(c) for c in page["crises"] if c["status"] == "open")
        else:
            assert secret not in text
    mine = client.get("/api/savings").json()
    assert all(b["mine"] == "0" for b in mine["banks"])
    assert str(naira(45_000_000)) not in repr(mine)
    # No route runs the crisis test, or works through game days, from the website.
    from server.main import app
    assert not any("crisis_test" in r.path or "run_days" in r.path for r in app.routes)
