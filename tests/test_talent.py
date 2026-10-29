"""The talent and funds stage, Part 1: Proven Talent.

A record worked out from the game's own books; badges; a page the player may share; firms, the board and invitations;
challenges; and the checks that keep the record honest.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from psycopg.rows import dict_row

from simulation import challenges, clock, deposits, firms, ledger, talent
from simulation.money import naira
from tests.conftest import ADULT, WORLD_START, join
from tests.test_crises import unlocked
from tests.test_market import OPEN, place, reference, trader

T0 = WORLD_START.date()


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def player_of(db, account):
    return _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"]


def bell(day):
    return datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)


def history(db, account, worths, *, index=None, first=T0, outside=None):
    """Write a player's worth at a run of closing bells (and the market index), as the closing bell would.
    `outside` maps a day number to money paid in from outside investing that day (a salary)."""
    for k, worth in enumerate(worths):
        day = first + timedelta(days=k)
        db.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, '{}') ON CONFLICT DO NOTHING", (day, bell(day)))
        db.execute("INSERT INTO net_worth_days (account_id, session_date, cash, investments) VALUES (%s, %s, %s, 0)", (account, day, worth))
        level = (index or [1000] * len(worths))[k]
        db.execute("INSERT INTO index_days (session_date, level) VALUES (%s, %s) ON CONFLICT (session_date) DO NOTHING", (day, level))
    for k, amount in (outside or {}).items():
        day = first + timedelta(days=k)
        with db.transaction():
            ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=amount, kind="salary",
                            memo="Test: a salary")
            unlocked(db, "UPDATE ledger_transactions SET created_at = %s WHERE id = (SELECT transaction_id FROM ledger_entries"
                         " WHERE account_id = %s ORDER BY id DESC LIMIT 1)", (bell(day) - timedelta(hours=3), account))


def test_the_investing_record_takes_out_money_from_outside_before_working_out_the_return(db):
    account = trader(db, "saver")
    pid = player_of(db, account)
    # 100m -> 110m (+10%), then a 5m salary arrives and worth is 115.5m: the salary is not a return, so +0.0% that day... and
    # then +5% from 115.5m.
    history(db, account, [naira(1_000_000), naira(1_100_000), naira(1_155_000), naira(1_212_750)],
            index=[1000, 1020, 1020, 1020], outside={2: naira(55_000)})
    inv = talent.investing(db, pid)
    assert inv["days_counted"] == 3
    assert abs(inv["total_bps"] - 1550) <= 1                     # 1.10 x 1.00 x 1.05 = +15.5%, not the +21% worth grew by
    assert inv["index_bps"] == 200 and abs(inv["versus_index_bps"] - 1350) <= 1
    assert inv["worst_fall_bps"] == 0


def test_money_of_any_kind_not_known_to_be_investing_counts_as_outside_money(db):
    account = trader(db, "gifted")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(2_000_000)])
    with db.transaction():
        ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(1_000_000), kind="a_new_kind_of_gift",
                        memo="Test: a gift of a kind nobody listed")
        unlocked(db, "UPDATE ledger_transactions SET created_at = %s WHERE id = (SELECT transaction_id FROM ledger_entries WHERE account_id = %s"
                     " ORDER BY id DESC LIMIT 1)", (bell(T0 + timedelta(days=1)) - timedelta(hours=2), account))
    assert talent.investing(db, pid)["total_bps"] == 0


def test_a_fall_and_quarters_against_the_market_are_counted_and_earn_badges(db):
    account = trader(db, "steady")
    pid = player_of(db, account)
    start = talent._start(db)
    first = start.date()
    worths, levels = [], []
    w = naira(1_000_000)
    for k in range(29):                                           # four game quarters of daily bells, and one more
        worths.append(w)
        levels.append(1000)
        w = w * 101 // 100
    history(db, account, worths, index=levels, first=first)
    inv = talent.investing(db, pid)
    assert inv["quarters_counted"] >= 4 and inv["best_streak"] >= 4
    assert inv["swing_bps"] is not None and inv["risk_ratio"] is not None
    codes = {c for c, _, _ in talent.badges_from(talent.work_out(db, pid, OPEN))}
    assert {"beat_market_4", "steady_hand"} <= codes
    talent.refresh(db, pid, OPEN)
    assert {b["code"] for b in talent.badges(db, pid)} >= {"beat_market_4", "steady_hand"}
    # A badge earned is kept; one that rests on a clean record is lost again when that stops being true.
    db.execute("INSERT INTO talent_badges (player_id, code, label, words, earned_at) VALUES (%s, 'clean_record', 'Clean record', 'x', %s)",
               (pid, OPEN))
    db.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, 'theft', 'Proved to have taken money.', %s)", (pid, OPEN))
    talent.refresh(db, pid, OPEN)
    codes = {b["code"] for b in talent.badges(db, pid)}
    assert "clean_record" not in codes and "beat_market_4" in codes


def test_a_shared_record_shows_only_what_the_player_chose_and_always_their_conduct(db):
    account = trader(db, "sharer")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(1_050_000), naira(1_100_000)])
    db.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, 'theft', 'Proved to have taken ₦1m.', %s)", (pid, OPEN))
    talent.refresh(db, pid, OPEN)
    s = talent.settings(db, pid)
    assert not s["shared"] and s["slug"] is None
    s = talent.share(db, pid, True, OPEN)
    talent.choose_sections(db, pid, ["work"], OPEN)
    view = talent.public_view(db, s["slug"])
    assert set(view["record"]) == {"work", "conduct"} and view["record"]["conduct"]["proved"] == 1
    # No money figure of any kind is on the page: only percentages and counts.
    assert str(naira(1_100_000)) not in repr(view) and "worth" not in repr(view["record"])
    with pytest.raises(talent.TalentError):
        talent.choose_sections(db, pid, ["work", "bank_balance"], OPEN)
    # A new address: the old one stops working at once. Turning sharing off hides it.
    old = s["slug"]
    new = talent.new_link(db, pid, OPEN)["slug"]
    assert new != old and talent.public_view(db, old) is None and talent.public_view(db, new)
    talent.share(db, pid, False, OPEN)
    assert talent.public_view(db, new) is None


def test_the_board_needs_a_long_enough_record(db):
    account = trader(db, "newcomer")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000)] * 5)
    talent.refresh(db, pid, OPEN)
    with pytest.raises(talent.TalentError, match="at least"):
        talent.set_board(db, pid, True, "Analyst", OPEN)
    history(db, account, [naira(1_000_000)] * 20, first=T0 + timedelta(days=5))
    talent.refresh(db, pid, OPEN)
    assert talent.set_board(db, pid, True, "  Analyst,   banks  ", OPEN)["headline"] == "Analyst, banks"


def _approved_firm(db, name="Lagoon Capital"):
    firm = firms.sign_up(db, name=name, email=f"{firms.name_key(name)}@example.com", email_key=f"{firms.name_key(name)}@example.com",
                         password_hash="x", contact_name="Ife Ade", website="https://example.com", tagline="We hire", colour="#123456", now=OPEN)
    firms.approve(db, firm["id"], OPEN)
    return firm


def _boarded(db, name):
    account = trader(db, name)
    pid = player_of(db, account)
    if not _one(db, "SELECT 1 AS x FROM net_worth_days WHERE account_id = %s", (account,)):
        history(db, account, [naira(1_000_000 + 10_000 * k) for k in range(20)])
    talent.refresh(db, pid, OPEN)
    talent.set_board(db, pid, True, "Looking", OPEN)
    return account, pid


def test_firms_see_only_the_board_and_a_players_contact_only_if_they_accept(db):
    firm = _approved_firm(db)
    pending = firms.sign_up(db, name="Waiting Bank", email="w@example.com", email_key="w@example.com", password_hash="x",
                            contact_name="Wale", website="", tagline="", colour="#000000", now=OPEN)
    with pytest.raises(firms.FirmError, match="approved"):
        firms.board(db, pending["id"])
    _, on = _boarded(db, "visible")
    hidden = player_of(db, trader(db, "hidden"))
    names = [p["name"] for p in firms.board(db, firm["id"])]
    assert names == ["visible"]
    with pytest.raises(firms.FirmError):
        firms.record_for_firm(db, firm["id"], hidden)
    assert firms.record_for_firm(db, firm["id"], on)["record"]["conduct"]["proved"] == 0
    inv = firms.invite(db, firm["id"], on, "We liked your record. Would you talk to us?", OPEN)
    with pytest.raises(firms.FirmError, match="not answered"):
        firms.invite(db, firm["id"], on, "Second message before an answer.", OPEN)
    with pytest.raises(firms.FirmError, match="board"):
        firms.invite(db, firm["id"], hidden, "Hello there, would you talk?", OPEN)
    assert all(i["contact"] is None for i in firms.invitations_for_firm(db, firm["id"]))
    with pytest.raises(firms.FirmError, match="reach you"):
        firms.answer(db, on, inv["id"], True, "", OPEN)
    firms.answer(db, on, inv["id"], True, "visible@example.com", OPEN)
    assert firms.invitations_for_firm(db, firm["id"])[0]["contact"] == "visible@example.com"
    # Blocked: never again, and off that firm's board.
    firms.block(db, on, firm["id"], OPEN)
    assert firms.board(db, firm["id"]) == []
    with pytest.raises(firms.FirmError):
        firms.invite(db, firm["id"], on, "Trying again after a block.", OPEN + timedelta(days=40))


def _paper(db, firm, *, starts=OPEN, days=3, kind="paper", ticker=None, top=10):
    return challenges.create(db, firm["id"], kind=kind, title="Manage the money", brief="Grow it.", opens_at=starts,
                             locks_at=None, ends_at=starts + timedelta(days=days), now=starts, ticker=ticker,
                             starting_cash=naira(5_000_000_000), top_shown=top)


def test_a_paper_portfolio_challenge_deals_at_live_prices_touches_nothing_real_and_is_scored(db):
    firm = _approved_firm(db)
    c = _paper(db, firm)
    a, b = player_of(db, trader(db, "alpha")), player_of(db, trader(db, "beta"))
    challenges.join(db, c["id"], a, True, OPEN)
    challenges.join(db, c["id"], b, False, OPEN)
    trades_before = _one(db, "SELECT count(*) AS n FROM market_trades")["n"]
    money_before = ledger.amount_in_existence(db)
    price = reference(db, "IDC")
    dealt = challenges.paper_trade(db, c["id"], a, ticker="IDC", side="buy", quantity=1000, now=OPEN)
    assert dealt["price"] == price and dealt["fee"] == price * 1000 * challenges.PAPER_FEE_BPS // 10_000
    with pytest.raises(challenges.ChallengeError, match="short"):
        challenges.paper_trade(db, c["id"], b, ticker="IDC", side="sell", quantity=1, now=OPEN)
    with pytest.raises(challenges.ChallengeError, match="open"):
        challenges.paper_trade(db, c["id"], a, ticker="IDC", side="buy", quantity=1, now=OPEN.replace(hour=23))
    with pytest.raises(challenges.ChallengeError, match="Not enough"):
        challenges.paper_trade(db, c["id"], a, ticker="IDC", side="buy", quantity=10**12, now=OPEN)
    # Nothing real moved.
    assert _one(db, "SELECT count(*) AS n FROM market_trades")["n"] == trades_before and ledger.amount_in_existence(db) == money_before
    # The price rises (no trades on the last day: the reference price is the day's price): alpha (holding) comes first.
    db.execute("UPDATE market_instruments SET reference_price = %s WHERE company_id = (SELECT id FROM companies WHERE ticker = 'IDC')",
               (price * 11 // 10,))
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    scored = {r["player_id"]: r for r in _rows(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (c["id"],))}
    assert scored[a]["place"] == 1 and scored[b]["place"] == 2
    # The firm sees only the finishers who agreed to be seen.
    mine = challenges.firm_list(db, firm["id"], c["ends_at"] + timedelta(minutes=2))[0]
    assert [f["name"] for f in mine["finishers"]] == ["alpha"]
    assert talent.stored(db, a, OPEN)["challenges"]["wins"] == 1
    assert any(x["code"] == f"won_challenge_{c['id']}" for x in talent.badges(db, a))
    # ...and may invite them, though alpha is not on the board.
    firms.invite(db, firm["id"], a, "Well done in our challenge: shall we talk?", OPEN, c["id"])
    with pytest.raises(firms.FirmError):
        firms.invite(db, firm["id"], b, "You did well too: shall we talk?", OPEN)


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def filed_later(db, company_id, period, per_share):
    """The valuation the game works out from the accounts filed when the quarter closes."""
    db.execute("INSERT INTO company_valuations (company_id, period, value_per_share, method, yearly_profit, growth_bps, discount_bps,"
               " long_run_bps, book_per_share, shares_in_issue) SELECT company_id, %s, %s, method, yearly_profit, growth_bps, discount_bps,"
               " long_run_bps, book_per_share, shares_in_issue FROM company_valuations WHERE company_id = %s ORDER BY period DESC LIMIT 1"
               " ON CONFLICT (company_id, period) DO UPDATE SET value_per_share = EXCLUDED.value_per_share", (period, per_share, company_id))


def test_valuation_forecast_and_weakest_bank_challenges_are_scored_on_what_cannot_be_traded(db):
    firm = _approved_firm(db)
    value = _one(db, "SELECT v.value_per_share, c.id FROM company_valuations v JOIN companies c ON c.id = v.company_id WHERE c.ticker = 'IDC'"
                     " ORDER BY v.period DESC LIMIT 1")
    c = _paper(db, firm, kind="valuation", ticker="IDC")
    filed_later(db, value["id"], c["target_period"], value["value_per_share"])
    near, far = player_of(db, trader(db, "near")), player_of(db, trader(db, "far"))
    for p in (near, far):
        challenges.join(db, c["id"], p, True, OPEN)
    challenges.answer(db, c["id"], near, OPEN, amount=value["value_per_share"] * 101 // 100, reasons="Cash flows.")
    challenges.answer(db, c["id"], far, OPEN, amount=value["value_per_share"] * 3, reasons="Hope.")
    with pytest.raises(challenges.ChallengeError, match="between"):
        challenges.answer(db, c["id"], near, c["locks_at"] + timedelta(minutes=1), amount=1)
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    places = {r["player_id"]: r["place"] for r in _rows(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (c["id"],))}
    assert places == {near: 1, far: 2}

    deposits.setup(db, 0, OPEN)
    w = _paper(db, firm, kind="weak_bank")
    picker = player_of(db, trader(db, "picker"))
    challenges.join(db, w["id"], picker, False, OPEN)
    challenges.answer(db, w["id"], picker, OPEN, ticker="KCB")
    with pytest.raises(challenges.ChallengeError, match="banks"):
        challenges.answer(db, w["id"], picker, OPEN, ticker="IDC")
    challenges.tick(db, w["ends_at"] + timedelta(minutes=1))
    assert _one(db, "SELECT score FROM challenge_entries WHERE challenge_id = %s", (w["id"],))["score"] is not None


def test_a_live_challenge_must_be_joined_before_it_starts(db):
    firm = _approved_firm(db)
    c = _paper(db, firm, kind="live", starts=OPEN + timedelta(hours=1))
    late = player_of(db, trader(db, "late"))
    early = player_of(db, trader(db, "early"))
    challenges.join(db, c["id"], early, True, OPEN)
    with pytest.raises(challenges.ChallengeError, match="closed"):
        challenges.join(db, c["id"], late, True, OPEN + timedelta(hours=2))
    with pytest.raises(challenges.ChallengeError, match="no answer"):
        challenges.answer(db, c["id"], early, OPEN + timedelta(hours=2), amount=1)


def test_a_trade_between_two_players_at_an_odd_price_is_a_gift_not_a_return_and_repeated_it_links_them(db):
    price = reference(db)
    # Two other players trade at the market price that day: not odd.
    x, y = trader(db, "x1", cash_naira=1_000_000), trader(db, "y1", shares=1_000)
    place(db, y, "sell", 100, price)
    place(db, x, "buy", 100, price)
    giver, taker = trader(db, "giver", shares=10_000), trader(db, "taker", cash_naira=10_000_000)
    cheap = price * 92 // 100
    for _ in range(3):
        place(db, giver, "sell", 1000, cheap)
        place(db, taker, "buy", 1000, cheap)
    day = OPEN.date()
    assert talent.check_trades(db, day, OPEN) == 3
    t, g = player_of(db, taker), player_of(db, giver)
    handed = _one(db, "SELECT sum(amount)::bigint AS s FROM talent_flags WHERE player_id = %s AND kind = 'off_market_trade'", (t,))["s"]
    assert handed == 3 * 1000 * (price - cheap)
    assert talent.held_back(db, t) and talent.held_back(db, g)
    # The gift is taken out of the taker's return as outside money.
    history(db, taker, [naira(10_000_000), naira(10_000_000) + handed], first=day - timedelta(days=1))
    assert talent.investing(db, t)["total_bps"] == 0
    # Held back: off the board, and out of the places, until an administrator clears it.
    history(db, taker, [naira(10_000_000)] * 20, first=day + timedelta(days=1))
    talent.refresh(db, t, OPEN)
    assert talent.board_ready(db, t)[0] is False
    for f in _rows(db, "SELECT id FROM talent_flags WHERE player_id = %s AND kind = 'linked'", (t,)):
        talent.clear_flag(db, f["id"], "Brothers sharing a laptop; looked at.", OPEN)
    assert not talent.held_back(db, t)


def test_players_from_one_device_who_trade_with_each_other_are_linked(db):
    a, b = player_of(db, trader(db, "twin1")), player_of(db, trader(db, "twin2"))
    mark = talent.visitor_mark("k" * 40, "10.0.0.1", "Browser")
    talent.note_visit(db, a, mark, OPEN)
    talent.note_visit(db, b, mark, OPEN)
    assert _one(db, "SELECT count(*) AS n FROM talent_flags WHERE kind = 'shared_device'")["n"] == 2
    assert not talent.held_back(db, a)                       # one device alone is not wrong: families share them
    price = reference(db)
    a_acc, b_acc = ledger.player_account_id(db, a), ledger.player_account_id(db, b)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=a_acc, amount=naira(1_000_000), kind="test_cash", memo="t")
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=b_acc, amount=100, asset="SHR-IDC", kind="test_shares",
                    memo="t")
    place(db, b_acc, "sell", 100, price)
    place(db, a_acc, "buy", 100, price)
    talent.note_visit(db, a, mark, OPEN + timedelta(days=1))
    talent.note_visit(db, b, mark, OPEN + timedelta(days=1))
    assert talent.held_back(db, a) and talent.held_back(db, b)
    # The address itself is never kept: only a keyed mark of it.
    assert "10.0.0.1" not in repr(_rows(db, "SELECT * FROM visitor_marks"))


def test_the_website_for_players_the_public_and_firms(db, client):
    assert join(client, ADULT).status_code == 201
    page = client.get("/api/talent").json()
    assert page["settings"]["shared"] is False and page["settings"]["slug"] is None
    shared = client.post("/api/talent/share", json={"on": True}).json()
    slug = shared["settings"]["slug"]
    assert client.get(f"/api/talent/shared/{slug}").status_code == 200
    # Nobody else's view is reachable with a guess.
    assert client.get("/api/talent/shared/" + "a" * 24).status_code == 404
    # Firms: their own login; a firm's pass is no use as a player's, nor a player's as a firm's.
    from fastapi.testclient import TestClient

    from server.main import app
    with TestClient(app) as firm:
        made = firm.post("/api/firms/signup", json={"name": "Harbour Partners", "email": "hr@harbour.example.com", "password": "a-long-password-1",
                                                    "contact_name": "Bisi", "website": "https://harbour.example.com"})
        assert made.status_code == 201, made.text
        assert firm.get("/api/me").status_code == 401
        assert firm.get("/api/firms/board").status_code == 403                 # waiting for approval
        firms.approve(db, made.json()["id"], OPEN)
        assert firm.get("/api/firms/board").json()["players"] == []
        assert firm.post("/api/talent/share", json={"on": True}).status_code == 401
    assert client.get("/api/firms/me").status_code == 401
    # Never sent: the honesty checks.
    assert "flag" not in repr(client.get("/api/talent").json()).lower()
    from server.main import app as the_app
    assert not any("flag" in r.path or "talent_admin" in r.path for r in the_app.routes)


def test_after_the_bell_records_are_worked_out_and_the_days_trades_checked(db):
    account = trader(db, "bellringer")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(1_010_000)])
    assert talent.tick(db, OPEN) >= 1
    row = _one(db, "SELECT * FROM talent_records WHERE player_id = %s", (pid,))
    assert row["summary"]["days"] == 1 and row["worked_on"] == T0 + timedelta(days=1)
    assert _one(db, "SELECT checked_through FROM talent_progress")["checked_through"] == T0 + timedelta(days=1)
    assert talent.tick(db, OPEN) == 0                                     # nothing new: nothing worked out again
