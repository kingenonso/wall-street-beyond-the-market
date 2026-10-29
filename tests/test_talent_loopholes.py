"""The talent and funds stage, Part 1 (Proven Talent): ten questions a player or a firm might ask to get round the rules,
each answered by a test."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import challenges, exchange, firms, ledger, talent
from simulation.money import naira
from tests.conftest import ADULT, join
from tests.test_crises import unlocked
from tests.test_market import OPEN, place, reference, trader
from tests.test_talent import T0, _approved_firm, _boarded, _paper, bell, filed_later, history, player_of


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _computers_step_away(db, ticker="IDC"):
    """Take the computer-run investors' orders off the book, so two players' orders meet each other."""
    others = [r["id"] for r in _rows(db, "SELECT id FROM ledger_accounts WHERE player_id IS NULL")]
    exchange.withdraw(db, others, OPEN, "Test: the computer-run investors step away")


def test_l1_an_empire_selling_shares_cheaply_to_its_head_is_a_gift_not_a_return(db):
    """'I head an empire: it can sell me shares far below the market, and my own record jumps.'"""
    head_account = trader(db, "head", cash_naira=50_000_000)
    head = player_of(db, head_account)
    empire_account = ledger.create_account(db, kind="empire", name="Lagoon House")
    db.execute("INSERT INTO empires (name, kind, head_player_id, account_id) VALUES ('Lagoon House', 'player', %s, %s)", (head, empire_account))
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire_account, amount=10_000, asset="SHR-IDC",
                    kind="test_shares", memo="Test: the empire's shares")
    _computers_step_away(db)
    price = reference(db)
    cheap = price * 92 // 100            # inside the day's price limits, but well below the market
    place(db, head_account, "buy", 5_000, cheap)
    place(db, empire_account, "sell", 5_000, cheap)
    day = OPEN.date()
    assert talent.check_trades(db, day, OPEN) == 1
    flag = _one(db, "SELECT * FROM talent_flags WHERE player_id = %s AND kind = 'off_market_trade'", (head,))
    assert flag and flag["amount"] == 5_000 * (price - cheap) and flag["other_id"] == head
    # The value handed over is taken out of the head's return as money from outside.
    history(db, head_account, [naira(10_000_000), naira(10_000_000) + flag["amount"]], first=day - timedelta(days=1))
    assert talent.investing(db, head)["total_bps"] == 0


def test_l2_shares_given_from_outside_are_not_a_return(db):
    """'A friend's empire hands me shares as a present: my record shows a great day.'"""
    account = trader(db, "presented")
    pid = player_of(db, account)
    price = reference(db)
    history(db, account, [naira(1_000_000), naira(1_000_000) + 10_000 * price])
    with db.transaction():
        ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=10_000, asset="SHR-IDC",
                        kind="a_present_of_shares", memo="Test: shares given")
        unlocked(db, "UPDATE ledger_transactions SET created_at = %s WHERE id = (SELECT transaction_id FROM ledger_entries WHERE account_id = %s"
                     " ORDER BY id DESC LIMIT 1)", (bell(T0 + timedelta(days=1)) - timedelta(hours=2), account))
    assert talent.investing(db, pid)["total_bps"] == 0


def test_l3_one_small_trade_at_the_end_does_not_move_a_paper_portfolio(db):
    """'I hold paper shares: one real share bought at the top of the day's limit, just before the end, lifts my score.'"""
    firm = _approved_firm(db)
    c = _paper(db, firm)
    me = player_of(db, trader(db, "pumper", cash_naira=50_000_000))
    challenges.join(db, c["id"], me, False, OPEN)
    price = reference(db)
    challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=1_000, now=OPEN)
    _computers_step_away(db)
    seller, buyer = trader(db, "s1", shares=2_000), trader(db, "b1", cash_naira=50_000_000)
    place(db, seller, "sell", 2_000, price)
    place(db, buyer, "buy", 2_000, price)
    mine = player_of(db, trader(db, "lastone", cash_naira=1_000_000))
    pump_seller = trader(db, "s2", shares=1)
    place(db, pump_seller, "sell", 1, price * 11 // 10)
    place(db, ledger.player_account_id(db, mine), "buy", 1, price * 11 // 10)
    day = OPEN.date()
    assert _one(db, "SELECT last_price FROM market_instruments WHERE company_id = (SELECT id FROM companies WHERE ticker = 'IDC')")[
        "last_price"] == price * 11 // 10
    entry = _one(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (c["id"],))
    held_at_day = challenges.paper_value(db, entry, day) - entry["cash"]
    assert held_at_day <= 1_000 * price * 10_001 // 10_000             # the day's average price, not the last trade
    db.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, '{}')", (day, bell(day)))
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    score = _one(db, "SELECT score_words FROM challenge_entries WHERE id = %s", (entry["id"],))["score_words"]
    assert score.startswith("-")                                       # the dealing fee, and no lift


def test_l4_a_paper_portfolio_cannot_buy_more_than_the_market_could_supply(db):
    """'Paper money is free: I'll buy a billion shares of a quiet company at the last price.'"""
    firm = _approved_firm(db)
    c = _paper(db, firm)
    me = player_of(db, trader(db, "whale"))
    challenges.join(db, c["id"], me, False, OPEN)
    with pytest.raises(challenges.ChallengeError, match="real market"):
        challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=challenges.PAPER_LEAST_SHARES + 1, now=OPEN)
    challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=challenges.PAPER_LEAST_SHARES, now=OPEN)
    # ...nor get round it a piece at a time, the same day.
    with pytest.raises(challenges.ChallengeError, match="real market"):
        challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=1, now=OPEN + timedelta(minutes=5))
    # The next day there is room again.
    challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=1, now=OPEN + timedelta(days=1))


def test_l5_two_entries_from_one_device_are_scored_but_not_placed(db):
    """'I'll enter my firm's challenge from three accounts and keep whichever does best.'"""
    firm = _approved_firm(db)
    c = _paper(db, firm)
    a, b, honest = (player_of(db, trader(db, n)) for n in ("sock1", "sock2", "honest"))
    mark = talent.visitor_mark("k" * 40, "10.1.1.1", "Browser")
    talent.note_visit(db, a, mark, OPEN)
    talent.note_visit(db, b, mark, OPEN)
    for p in (a, b, honest):
        challenges.join(db, c["id"], p, True, OPEN)
    challenges.paper_trade(db, c["id"], a, ticker="IDC", side="buy", quantity=1_000, now=OPEN)
    db.execute("UPDATE market_instruments SET reference_price = reference_price * 2 WHERE company_id = (SELECT id FROM companies WHERE ticker = 'IDC')")
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    places = {r["player_id"]: r for r in _rows(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (c["id"],))}
    assert places[honest]["place"] == 1 and places[a]["place"] is None and places[b]["place"] is None
    assert places[a]["score"] is not None and "held back" in places[a]["score_words"]


def test_l6_a_valuation_cannot_be_copied_from_figures_already_out(db):
    """'The game's valuation from the last accounts can be worked out with a calculator: I'll just answer that.'"""
    firm = _approved_firm(db)
    old = _one(db, "SELECT v.value_per_share, c.id FROM company_valuations v JOIN companies c ON c.id = v.company_id WHERE c.ticker = 'IDC'"
                   " ORDER BY v.period DESC LIMIT 1")
    c = _paper(db, firm, kind="valuation", ticker="IDC")
    assert c["target_period"] is not None
    copier, thinker = player_of(db, trader(db, "copier")), player_of(db, trader(db, "thinker"))
    for p in (copier, thinker):
        challenges.join(db, c["id"], p, True, OPEN)
    challenges.answer(db, c["id"], copier, OPEN, amount=old["value_per_share"])
    challenges.answer(db, c["id"], thinker, OPEN, amount=old["value_per_share"] * 13 // 10)
    # Not scored until the quarter's accounts are filed and the company valued afresh.
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    assert _one(db, "SELECT status FROM talent_challenges WHERE id = %s", (c["id"],))["status"] == "open"
    filed_later(db, old["id"], c["target_period"], old["value_per_share"] * 13 // 10)
    challenges.tick(db, c["ends_at"] + timedelta(minutes=2))
    places = {r["player_id"]: r["place"] for r in _rows(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (c["id"],))}
    assert places == {thinker: 1, copier: 2}


def test_l7_a_firm_sees_names_and_records_only_where_the_player_agreed(db):
    """'As a firm: I'll read the names off my challenge's full scoreboard, and keep reading a record after the player has left
    the board.'"""
    firm = _approved_firm(db)
    c = _paper(db, firm)
    shy, open_ = player_of(db, trader(db, "shy")), player_of(db, trader(db, "open"))
    challenges.join(db, c["id"], shy, False, OPEN)
    challenges.join(db, c["id"], open_, True, OPEN)
    challenges.paper_trade(db, c["id"], shy, ticker="IDC", side="buy", quantity=1_000, now=OPEN)
    db.execute("UPDATE market_instruments SET reference_price = reference_price * 2 WHERE company_id = (SELECT id FROM companies WHERE ticker = 'IDC')")
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    seen = challenges.firm_list(db, firm["id"], c["ends_at"] + timedelta(minutes=2))[0]
    assert "shy" not in repr(seen) and [f["name"] for f in seen["finishers"]] == ["open"]
    with pytest.raises(firms.FirmError):
        firms.record_for_firm(db, firm["id"], shy)
    # On the board, then off it again: the firm can no longer read the record.
    _, boarded = _boarded(db, "leaver")
    assert firms.record_for_firm(db, firm["id"], boarded)
    talent.set_board(db, boarded, False, "", OPEN)
    with pytest.raises(firms.FirmError):
        firms.record_for_firm(db, firm["id"], boarded)


def test_l8_nobody_can_type_in_or_change_a_record(db, client):
    """'I'll send my own figures with the request' / 'I'll change the stored record.'"""
    assert join(client, ADULT).status_code == 201
    refused = client.post("/api/talent/sections", json={"sections": ["work"], "record": {"investing": {"total_bps": 99_999}}})
    assert refused.status_code == 422
    refused = client.post("/api/talent/board", json={"on": False, "summary": {"days": 999}})
    assert refused.status_code == 422
    # A stored record that has been changed is put right the next time it is worked out from the books.
    account = trader(db, "tamper")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(1_010_000)])
    talent.refresh(db, pid, OPEN)
    db.execute("UPDATE talent_records SET summary = jsonb_set(summary, '{total_bps}', '99999') WHERE player_id = %s", (pid,))
    talent.refresh(db, pid, OPEN)
    assert _one(db, "SELECT summary FROM talent_records WHERE player_id = %s", (pid,))["summary"]["total_bps"] == 100
    # And no part of the record can be hidden by naming conduct among the parts shown or not.
    talent.choose_sections(db, pid, [], OPEN)
    s = talent.share(db, pid, True, OPEN)
    assert "conduct" in talent.public_view(db, s["slug"])["record"]


def test_l9_a_firm_has_no_powers_in_the_world_and_a_suspended_firm_is_shut_out(db, client):
    """'As a firm, I'll trade, or keep running my challenges after I'm suspended.'"""
    from fastapi.testclient import TestClient

    from server.main import app
    with TestClient(app) as firm:
        made = firm.post("/api/firms/signup", json={"name": "Quay Bank", "email": "q@quay.example.com", "password": "a-long-password-2",
                                                    "contact_name": "Tobi"})
        assert made.status_code == 201
        fid = made.json()["id"]
        when = OPEN.isoformat()
        assert firm.post("/api/firms/challenges", json={"kind": "paper", "title": "Too early", "opens_at": when,
                                                        "ends_at": (OPEN + timedelta(days=2)).isoformat()}).status_code == 403
        firms.approve(db, fid, OPEN)
        for path, body in (("/api/orders", {"ticker": "IDC", "side": "buy", "kind": "market", "quantity": 1}),
                           ("/api/talent/share", {"on": True}), ("/api/savings/IKB/in", {"amount_naira": 1})):
            assert firm.post(path, json=body).status_code in (401, 404, 405)
        c = challenges.create(db, fid, kind="paper", title="Quay paper", brief="", opens_at=OPEN, locks_at=None,
                              ends_at=OPEN + timedelta(days=2), now=OPEN)
        firms.suspend(db, fid)
        assert firm.get("/api/firms/me").status_code == 401
        assert _one(db, "SELECT status FROM talent_challenges WHERE id = %s", (c["id"],))["status"] == "cancelled"
        login = firm.post("/api/firms/login", json={"email": "q@quay.example.com", "password": "a-long-password-2"})
        assert login.status_code == 401


def test_l10_a_firm_cannot_pester_a_player(db, monkeypatch):
    """'As a firm: invite again and again until they say yes.'"""
    firm = _approved_firm(db)
    _, p = _boarded(db, "pestered")
    inv = firms.invite(db, firm["id"], p, "Would you like to talk to us?", OPEN)
    firms.answer(db, p, inv["id"], False, "", OPEN)
    with pytest.raises(firms.FirmError, match="declined"):
        firms.invite(db, firm["id"], p, "Please reconsider, we insist.", OPEN + timedelta(days=5))
    firms.invite(db, firm["id"], p, "A month on: still interested?", OPEN + timedelta(days=31))
    monkeypatch.setattr(firms, "INVITES_PER_DAY", 1)
    _, q = _boarded(db, "another")
    with pytest.raises(firms.FirmError, match="a day"):
        firms.invite(db, firm["id"], q, "Hello, a second invitation today.", OPEN + timedelta(days=31, minutes=1))
    # A player who blocks the firm never hears from it again, and its invitations disappear from their page.
    firms.block(db, p, firm["id"], OPEN + timedelta(days=32))
    assert firms.invitations_for_player(db, p) == []
