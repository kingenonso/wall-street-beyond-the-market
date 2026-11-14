"""The crises stage, Part 1: money kept at named banks, trust in each bank, bank runs that spread and can be stopped,
the Central Bank's emergency lending, the deposit guarantee, closures, rescues, public hands, the Crisis Watch and the
record of every crisis."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import (
    auctions,
    clock,
    crisis,
    crisis_test,
    crisiswatch,
    deposits,
    exchange,
    ledger,
    quarters,
)
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9

pytestmark = pytest.mark.world("eight")
P = 9                 # the running quarter at NOW9


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _bank(db, ticker):
    return deposits.bank(db, ticker)


def weaken(db, ticker, capital_bps):
    """Give a bank losses until its owners' funds are `capital_bps` of its loans (below zero: a hole)."""
    b = _bank(db, ticker)
    filed = crisis._filed(db, b["id"])
    want = crisis.loans_of(filed) * capital_bps // BPS
    cut = filed["total_equity"] - want
    # The losses come off its loans to households, and off its owners' funds: the books still balance.
    unlocked(db, "UPDATE company_results SET total_equity = total_equity - %s, retained_earnings = retained_earnings - %s,"
                 " customer_loans = customer_loans - %s, total_assets = total_assets - %s, loan_losses = loan_losses + %s"
                 " WHERE company_id = %s AND period = %s", (cut, cut, cut, cut, max(cut, 0), b["id"], filed["period"]))
    return b


def unlocked(db, sql, params=()):
    """Change a permanent record, for a test only (filed accounts cannot otherwise be changed)."""
    db.execute("SET session_replication_role = replica")
    try:
        db.execute(sql, params)
    finally:
        db.execute("SET session_replication_role = origin")


def days(db, through, now=NOW9):
    return crisis.run_days(db, P, through, now)


def state(db, ticker):
    return crisis._last(db, _bank(db, ticker)["id"])


def test_every_banks_savers_are_written_into_the_ledger_and_add_up(db):
    banks = deposits.banks(db)
    assert {b["ticker"] for b in banks} >= set(data.PLAYER_BANKS)
    for b in banks:
        filed = crisis._filed(db, b["id"])
        owes = deposits.owed(db, b["id"])
        # What it owes its savers is what its accounts say, and it is exactly what its savers hold.
        assert owes == filed["customer_funds"] > 0
        held = _one(db, "SELECT coalesce(sum(balance), 0)::bigint AS t FROM ledger_balances WHERE asset = %s AND balance > 0", (b["asset"],))["t"]
        assert held == owes
    assert ledger.audit(db) == [] and crisis.check_books(db) == []
    # Companies keep part of their spare cash as savings; households keep theirs; trust was measured every game day.
    assert _one(db, "SELECT count(*) AS n FROM deposit_flows WHERE holder = 'company' AND kind = 'placed'")["n"] > 0
    assert _one(db, "SELECT count(*) AS n FROM crisis_days")["n"] == 8 * clock.GAME_DAYS_PER_QUARTER
    # Sound banks stayed calm, and no crisis grew from nothing.
    assert all(t["state"] == "calm" for t in crisis.trust_now(db).values())
    assert not _one(db, "SELECT 1 AS x FROM economic_crises WHERE status = 'open' AND step >= 3")


def test_a_player_saves_takes_out_and_is_paid_interest_on_the_least_kept(db):
    p, account = pro(db, "accountant", "saver", cash_naira=20_000_000)
    with pytest.raises(deposits.SavingsError, match="at least"):
        deposits.put_in(db, p, "IKB", naira(5_000), NOW9)
    with pytest.raises(deposits.SavingsError, match="six banks"):
        deposits.put_in(db, p, "SCM", naira(1_000_000), NOW9)
    deposits.put_in(db, p, "IKB", naira(12_000_000), NOW9)
    b = _bank(db, "IKB")
    assert deposits.saved(db, account, b["asset"]) == naira(12_000_000)
    view = deposits.view(db, p, NOW9)
    ikb = next(x for x in view["banks"] if x["ticker"] == "IKB")
    assert ikb["mine"] == naira(12_000_000) and ikb["mine_guaranteed"] == naira(5_000_000)
    with pytest.raises(deposits.SavingsError, match="You have"):
        deposits.take_out(db, p, "IKB", naira(13_000_000), NOW9)
    deposits.take_out(db, p, "IKB", naira(2_000_000), NOW9)
    # Savings count in what the player is worth.
    from simulation import objectives
    assert objectives.wealth(db, account, NOW9)["cash"] >= naira(20_000_000) - naira(1)
    # Interest is paid on the least kept through the whole quarter: nothing for the quarter it was put in mid-way...
    quarters.close_due_quarters(db, after_quarters(9))
    first = _one(db, "SELECT * FROM savings_interest WHERE account_id = %s AND company_id = %s AND period = %s", (account, b["id"], P))
    assert first and first["lowest"] == 0 and first["amount"] == 0
    # ...and on the ₦10 million kept through all of the next, at the bank's savings rate.
    quarters.close_due_quarters(db, after_quarters(10))
    paid = _one(db, "SELECT * FROM savings_interest WHERE account_id = %s AND company_id = %s AND period = %s", (account, b["id"], P + 1))
    assert paid and paid["lowest"] == naira(10_000_000) and paid["amount"] > 0
    assert paid["amount"] == (naira(10_000_000) * paid["rate_bps"] + 2 * BPS) // (4 * BPS)
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_a_weak_bank_loses_trust_its_savers_run_the_central_bank_lends_and_the_run_spreads_and_is_stopped(db):
    """The stage test (added to the design's): a bank run spreads to a second bank and is stopped, with no naira created
    or lost."""
    weak = weaken(db, "KCB", 300)                       # owners' funds of 3% of its loans
    weaken(db, "ZCB", 600)                              # a second bank, much less sound than the rest
    before = ledger.amount_in_existence(db)
    lent_before = _one(db, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS t FROM company_debts WHERE kind = 'central_bank_loan'")["t"]
    days(db, 30)
    days_ = _rows(db, "SELECT day, state, score, withdrawn FROM bank_confidence WHERE company_id = %s AND period = %s ORDER BY day", (weak["id"], P))
    states = [d["state"] for d in days_]
    assert "run" in states or "panic" in states
    assert sum(d["withdrawn"] for d in days_) > 0
    # Most of what was drawn out went the same day to banks still trusted.
    moved = _one(db, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM deposit_flows WHERE kind = 'returned' AND period = %s", (P,))["t"]
    assert moved > 0
    # The Central Bank lent against its loans, at a penalty, and only to a sound bank; the regulator stopped short sales.
    support = _one(db, "SELECT coalesce(sum(amount), 0)::bigint AS t FROM central_bank_support WHERE company_id = %s", (weak["id"],))["t"]
    emergency = _one(db, "SELECT * FROM company_debts WHERE company_id = %s AND name LIKE 'emergency%%'", (weak["id"],))
    if support:
        assert emergency["annual_rate_bps"] > crisis._policy_rate(db)
    assert _one(db, "SELECT 1 AS x FROM short_bans WHERE company_id = %s", (weak["id"],))
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind IN ('bank_run', 'bank_panic')")
    # It spread: other banks' trust fell with it, and the crisis record reached its tipping point.
    c = _one(db, "SELECT * FROM economic_crises WHERE kind IN ('banking', 'confidence') ORDER BY id DESC LIMIT 1")
    assert c and c["step"] >= 6 and len(c["banks"]) >= 2
    others = [crisis._last(db, b["id"]) for b in deposits.banks(db) if b["id"] != weak["id"]]
    assert any((o["parts"] or {}).get("other_banks", 0) < 0 for o in others)
    # It was stopped: the Government's promise, the Central Bank's lending, new money; by the end trust was coming back.
    assert crisis.national(db) > 0
    stopped = (_one(db, "SELECT 1 AS x FROM blanket_guarantees") or support or _one(db, "SELECT 1 AS x FROM emergency_placements")
               or _one(db, "SELECT 1 AS x FROM bank_resolutions"))
    assert stopped
    days(db, 90)
    last = crisis._last(db, weak["id"])
    assert last["state"] in ("calm", "worried", "closed")
    # No naira was created or lost on the way: all that is new is what the banks owe the Central Bank.
    lent_after = _one(db, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS t FROM company_debts WHERE kind = 'central_bank_loan'")["t"]
    assert ledger.amount_in_existence(db) - before == lent_after - lent_before
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_a_bank_whose_losses_ate_its_owners_funds_is_closed_savers_above_the_guarantee_bear_the_hole_and_it_is_rescued(db):
    p, account = pro(db, "accountant", "bigsaver", cash_naira=60_000_000)
    small, small_account = pro(db, "lawyer", "smallsaver", cash_naira=3_000_000)
    deposits.put_in(db, p, "KCB", naira(50_000_000), NOW9)
    deposits.put_in(db, small, "KCB", naira(3_000_000), NOW9)
    b = weaken(db, "KCB", -200)                         # a hole of 2% of its loans
    rid = crisis.cannot_pay(db, b, P, 10, NOW9, reason="its losses had eaten all its owners' funds")
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    assert r["status"] == "open" and r["equity"] < 0
    # Savers above the guarantee bore the hole (the player's ₦45 million above it among them); the small saver lost nothing.
    assert r["bail_in"] > 0
    assert deposits.saved(db, small_account, b["asset"]) == naira(3_000_000)
    assert deposits.saved(db, account, b["asset"]) < naira(50_000_000)
    assert deposits.saved(db, account, b["asset"]) >= naira(5_000_000)
    # Frozen: no savings in or out, and no trading in its shares.
    with pytest.raises(deposits.SavingsError, match="closed"):
        deposits.take_out(db, small, "KCB", naira(1_000_000), NOW9)
    with pytest.raises(exchange.ExchangeError, match="No trading"):
        exchange.place_order(db, account=account, ticker="KCB", side="buy", kind="limit", quantity=1, limit_price=100, now=NOW9)
    # The Auction House sells it to whoever puts in the most new money; a sound bank bids.
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    assert a and a["reason"] == "rescue" and a["reserve"] == r["capital_needed"]
    view = auctions.bank_view(db, NOW9)
    assert view and "reserve" not in view[0] and "limit_price" not in repr(view)
    shares_before = ledger.amount_in_existence(db, _one(db, "SELECT share_asset FROM companies WHERE id = %s", (b["id"],))["share_asset"])
    cash_before = ledger.balance(db, b["account_id"])
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    assert r["status"] in ("sold", "public")
    asset = _one(db, "SELECT share_asset FROM companies WHERE id = %s", (b["id"],))["share_asset"]
    assert ledger.amount_in_existence(db, asset) == shares_before * 20           # the old owners keep 5%
    assert ledger.balance(db, r["new_owner"], asset) == shares_before * 19
    assert ledger.balance(db, b["account_id"]) >= cash_before + r["capital_needed"]
    assert not deposits.closed(db, b["id"])
    assert _one(db, "SELECT halted_reason FROM market_instruments WHERE company_id = %s", (b["id"],))["halted_reason"] is None
    deposits.take_out(db, small, "KCB", naira(1_000_000), NOW9 + timedelta(hours=30))
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind IN ('bank_rescued', 'bank_public')")
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_with_no_buyer_a_closed_bank_goes_into_public_hands_and_is_sold_again_a_year_later(db):
    b = weaken(db, "OBB", -100)
    # No other bank is strong enough to bid, so nobody bids.
    for other in deposits.banks(db):
        if other["id"] != b["id"]:
            weaken(db, other["ticker"], 50)
    rid = crisis.cannot_pay(db, b, P, 20, NOW9)
    a = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open'", (b["id"],))
    assert not _rows(db, "SELECT 1 FROM auction_bids WHERE auction_id = %s", (a["id"],))
    treasury_before = ledger.balance(db, ledger.account_id(db, ledger.TREASURY))
    auctions.run(db, a["ends_at"] + timedelta(minutes=1))
    r = _one(db, "SELECT * FROM bank_resolutions WHERE id = %s", (rid,))
    fund = ledger.account_id(db, deposits.GUARANTEE_FUND)
    assert r["status"] == "public" and r["new_owner"] == fund and r["resale_period"] == P + data.PUBLIC_RESALE_QUARTERS
    # The fund borrowed what it lacked from the Treasury, on the record.
    assert _one(db, "SELECT coalesce(sum(outstanding), 0)::bigint AS t FROM guarantee_fund_loans")["t"] > 0
    assert ledger.balance(db, ledger.account_id(db, ledger.TREASURY)) < treasury_before
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'bank_public'")
    # A year on, its shares go back on sale.
    crisis.resell_public(db, P + data.PUBLIC_RESALE_QUARTERS, NOW9)
    sale = _one(db, "SELECT * FROM auctions WHERE bank_id = %s AND status = 'open' AND reason = 'public_sale'", (b["id"],))
    assert sale and sale["seller"] == fund
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_the_government_guarantees_every_saving_when_two_banks_run_and_lifts_it_once_trust_is_back(db):
    for t in ("KCB", "ZCB"):
        weaken(db, t, 200)
    days(db, 40)
    g = _one(db, "SELECT * FROM blanket_guarantees ORDER BY id LIMIT 1")
    assert g is not None and g["until_period"] is None
    assert deposits.blanket(db)
    assert deposits.guaranteed_part(db, naira(80_000_000)) == naira(80_000_000)
    assert _one(db, "SELECT 1 AS x FROM news_items WHERE kind = 'savings_guarantee'")
    # Under it, savers above ₦5 million have no reason to run first.
    hh = _one(db, "SELECT account_id, location FROM households ORDER BY location LIMIT 1")
    above, _ = deposits.household_split(db, _bank(db, "KCB"), hh["location"], hh["account_id"])
    assert above == 0
    # Trust back: lifted at a close.
    db.execute("UPDATE crisis_days SET national = 80")
    db.execute("UPDATE bank_resolutions SET status = 'sold' WHERE status = 'open'")
    crisis.blanket_lift(db, P, NOW9)
    assert not deposits.blanket(db)


def test_trust_is_made_only_of_public_signals_and_an_open_crisis_never_shows_its_hidden_weakness(db):
    weaken(db, "KCB", 400)
    days(db, 12)
    for b in crisis.bank_view(db, NOW9):
        assert set(p["part"] for p in b["parts"]) <= set(crisis.PART_NAMES)
    for c in crisis.crises_view(db, NOW9):
        if c["status"] == "open":
            assert c["report"] is None and "weakness" not in repr(c)
    # The ripple can answer "Why?" for the crisis.
    c = _one(db, "SELECT id FROM economic_crises ORDER BY id DESC LIMIT 1")
    if c:
        from simulation import ripple
        assert ripple.chain(db, f"crisis:{c['id']}")["chain"]


def test_most_warnings_fade_and_an_ended_crisis_leaves_a_permanent_report(db):
    b = weaken(db, "KCB", 900)
    days(db, 6)
    # Then it is made sound again: trust comes back.
    weaken(db, "KCB", 3_000)
    filed = crisis._filed(db, b["id"])
    unlocked(db, "UPDATE company_results SET loan_losses = 0 WHERE company_id = %s AND period = %s", (b["id"], filed["period"]))
    days(db, 60)
    c = _one(db, "SELECT * FROM economic_crises WHERE %s = ANY(banks) ORDER BY id LIMIT 1", (b["id"],))     # (another may open later)
    if c is not None:
        assert c["status"] in ("faded", "ended")
        assert c["report"]["summary"] and c["report"]["weakness"] and c["report"]["stopped_by"]
        view = next(v for v in crisis.crises_view(db, NOW9) if v["id"] == c["id"])
        assert view["report"] is not None


def test_the_crisis_watch_reads_every_sign_at_the_close_and_shows_the_history(db):
    quarters.close_due_quarters(db, after_quarters(9))
    r = _one(db, "SELECT readings FROM crisis_watch WHERE period = %s", (P,))["readings"]
    assert set(r) == set(crisiswatch.LEVELS)
    assert all(v["level"] in ("green", "amber", "red") and v["words"] for v in r.values())
    view = crisiswatch.view(db, NOW9)
    assert view["period"] == P and len(view["signs"]) == len(crisiswatch.LEVELS)
    assert ledger.audit(db) == [] and crisis.check_books(db) == []


def test_a_bank_whose_savers_are_leaving_lends_less(db):
    b = weaken(db, "KCB", 300)
    days(db, 30)
    s = crisis._last(db, b["id"])["state"]
    assert crisis.lending_bps(db, b["id"]) == data.CRISIS_LENDING_BPS[s]
    assert crisis.lending_bps(db, _bank(db, "IKB")["id"]) in (data.CRISIS_LENDING_BPS["calm"], data.CRISIS_LENDING_BPS["worried"])


def test_the_crisis_test_runs_in_a_sealed_copy_and_leaves_nothing_behind(db):
    before = (_one(db, "SELECT count(*) AS n FROM bank_confidence")["n"], _one(db, "SELECT count(*) AS n FROM ledger_transactions")["n"],
              _one(db, "SELECT count(*) AS n FROM news_items")["n"])
    found = None
    try:
        with db.transaction():
            found = crisis_test.run(db, "KCB", loss_pct=8, days=15, now=NOW9)
            raise crisis_test.Rollback()
    except crisis_test.Rollback:
        pass
    assert found and found["days"]
    after = (_one(db, "SELECT count(*) AS n FROM bank_confidence")["n"], _one(db, "SELECT count(*) AS n FROM ledger_transactions")["n"],
             _one(db, "SELECT count(*) AS n FROM news_items")["n"])
    assert after == before


def test_the_website_shows_trust_and_the_players_own_savings_only(db, client):
    assert join(client, ADULT).status_code == 201
    other, other_account = pro(db, "accountant", "rich", cash_naira=30_000_000)
    deposits.put_in(db, other, "IKB", naira(25_000_000), NOW9)
    page = client.get("/api/savings").json()
    assert all(b["mine"] == "0" for b in page["banks"])          # never anybody else's savings
    crisis_page = client.get("/api/crisis").json()
    assert {"watch", "banks", "crises", "auctions", "blanket", "national"} <= set(crisis_page)
    assert "weakness" not in repr([c for c in crisis_page["crises"] if c["status"] == "open"])
    assert client.post("/api/savings/IKB/in", json={"amount_naira": 5}).status_code == 409


def test_a_bank_in_trouble_pops_up_on_every_screen_and_says_so_when_your_savings_are_there(db, client):
    assert join(client, ADULT).status_code == 201
    me = _one(db, "SELECT a.id AS account, a.player_id FROM ledger_accounts a WHERE a.kind = 'player' ORDER BY a.id DESC LIMIT 1")
    from tests.test_objectives import give_cash
    give_cash(db, me["account"], 20_000_000)
    b = deposits.bank(db, "KCB")
    deposits._place(db, me["account"], b, naira(15_000_000), "savings_placed", "Test: savings at KCB", P)
    first = client.get("/api/crisis/alerts").json()
    weaken(db, "KCB", 300)
    days(db, 30)
    found = client.get(f"/api/crisis/alerts?after={first['mark']}").json()
    kinds = {i["kind"] for i in found["items"]}
    assert kinds & {"bank_run", "bank_panic", "bank_closed"}
    mine = [i for i in found["items"] if i["ticker"] == "KCB"]
    assert mine and all(i["yours"] == "you" for i in mine)
    # Once seen, it does not pop up again.
    again = client.get(f"/api/crisis/alerts?after={found['mark']}").json()
    assert again["items"] == []
