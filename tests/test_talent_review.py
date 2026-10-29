"""The talent and funds stage, Part 1 (Proven Talent): each finding of the independent review, fixed, with its test."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import challenges, clock, derivatives, firms, ledger, talent
from simulation.money import naira
from tests.conftest import ADULT, join
from tests.test_crises import unlocked
from tests.test_market import OPEN, place, reference, trader
from tests.test_talent import T0, _approved_firm, _boarded, _paper, bell, bell_after, filed_later, history, player_of


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _paid(db, account, amount, kind, day, *, hours_before_bell=3, payer=None):
    """Money of a kind reaching (or, negative, leaving) an account, at a moment before a day's bell."""
    payer = payer or ledger.account_id(db, ledger.TREASURY)
    with db.transaction():
        if amount >= 0:
            ledger.transfer(db, payer=payer, receiver=account, amount=amount, kind=kind, memo="Test")
        else:
            ledger.transfer(db, payer=account, receiver=payer, amount=-amount, kind=kind, memo="Test")
        unlocked(db, "UPDATE ledger_transactions SET created_at = %s WHERE id = (SELECT transaction_id FROM ledger_entries WHERE account_id = %s"
                     " ORDER BY id DESC LIMIT 1)", (bell(day) - timedelta(hours=hours_before_bell), account))


def test_r1_conduct_shows_what_was_proved_and_when_never_the_sums(db):
    account = trader(db, "convicted")
    pid = player_of(db, account)
    db.execute("INSERT INTO legal_records (player_id, kind, words, at) VALUES (%s, 'theft', 'Proved to have taken ₦4,000,000; fine of ₦2,000,000;"
               " ₦1,000,000 is still owed and is taken from salary.', %s)", (pid, OPEN))
    talent.refresh(db, pid, OPEN)
    s = talent.share(db, pid, True, OPEN)
    page = repr(talent.public_view(db, s["slug"]))
    assert "₦" not in page and "owed" not in page and "salary" not in page
    assert talent.public_view(db, s["slug"])["record"]["conduct"]["entries"][0]["words"] == "Proved to have taken money from an empire"


def test_r2_a_hidden_part_of_the_record_stays_hidden_from_the_board_the_badges_and_the_shared_page(db):
    firm = _approved_firm(db)
    account = trader(db, "private")
    pid = player_of(db, account)
    start = talent._start(db)
    worths, w = [], naira(1_000_000)
    for _ in range(29):
        worths.append(w)
        w = w * 101 // 100
    history(db, account, worths, first=start.date())
    talent.refresh(db, pid, OPEN)
    assert any(b["code"] == "beat_market_4" for b in talent.badges(db, pid))
    talent.choose_sections(db, pid, ["work"], OPEN)
    talent.set_board(db, pid, True, "Hiding my returns", OPEN)
    row = next(p for p in firms.board(db, firm["id"]) if p["player_id"] == pid)
    assert row["versus_index_bps"] is None and row["total_bps"] is None and row["worst_fall_bps"] is None and row["badges"] == 0
    assert firms.board(db, firm["id"], badge="beat_market_4") == []
    s = talent.share(db, pid, True, OPEN)
    assert "beat_market" not in repr(talent.public_view(db, s["slug"]))
    assert "beat_market" not in repr(firms.record_for_firm(db, firm["id"], pid))


def test_r3_a_fund_managers_fee_is_pay_for_work_not_a_return(db):
    account = trader(db, "manager")
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(1_100_000), naira(1_000_000)])
    _paid(db, account, naira(100_000), "fund_fee", T0 + timedelta(days=1))
    # ...but a fee the player pays (as an investor in a fund) is part of their return.
    _paid(db, account, -naira(100_000), "fund_fee", T0 + timedelta(days=2))
    inv = talent.investing(db, pid)
    assert abs(inv["total_bps"] - (-909)) <= 1                 # day 1: +0% (the fee is pay); day 2: -100k of 1.1m = -9.09%


def test_r4_a_building_or_an_option_sold_between_players_far_from_its_value_is_a_gift(db):
    from simulation import property as prop
    seller_acc, buyer_acc = trader(db, "landlord", cash_naira=1_000_000), trader(db, "friend", cash_naira=1_000_000)
    seller, buyer = player_of(db, seller_acc), player_of(db, buyer_acc)
    p = _one(db, "SELECT * FROM properties WHERE status = 'standing' ORDER BY id LIMIT 1")
    fair = prop.value(p, prop.districts(db)[p["district_id"]], prop.policy_rate(db))
    db.execute("INSERT INTO property_sales (property_id, seller, buyer, price, status, period, at, done_at) VALUES (%s, %s, %s, %s, 'done', 1, %s, %s)",
               (p["id"], seller_acc, buyer_acc, fair * 3, OPEN, OPEN))
    assert talent.check_other_deals(db, OPEN.date(), OPEN) == 1
    flag = _one(db, "SELECT * FROM talent_flags WHERE player_id = %s AND kind = 'off_market_trade'", (seller,))
    assert flag["amount"] == fair * 2 and flag["other_id"] == buyer
    assert _one(db, "SELECT amount FROM talent_flags WHERE player_id = %s", (buyer,))["amount"] == -fair * 2
    # An option dealt between two players at three times the dealers' price: the same.
    derivatives.ensure(db, OPEN)
    s = _one(db, "SELECT * FROM derivative_series WHERE kind = 'call' ORDER BY id LIMIT 1")
    price = derivatives.fair(db, s, OPEN)
    db.execute("INSERT INTO derivative_trades (series_id, price, contracts, buyer, seller, with_makers, at) VALUES (%s, %s, 2, %s, %s, false, %s)",
               (s["id"], price * 3, buyer_acc, seller_acc, OPEN))
    assert talent.check_other_deals(db, OPEN.date(), OPEN) == 2
    assert _one(db, "SELECT count(*) AS n FROM talent_flags WHERE player_id = %s AND reference LIKE 'derivative:%%'", (seller,))["n"] == 1


def test_r5_money_brought_in_just_before_the_bell_does_not_water_down_a_losing_day(db):
    account = trader(db, "diluter")
    pid = player_of(db, account)
    # Worth 1m; the day's bet loses half (0.5m left); 10m arrives a minute before the bell: worth 10.5m at the bell.
    history(db, account, [naira(1_000_000), naira(10_500_000)])
    _paid(db, account, naira(10_000_000), "empire_capital", T0 + timedelta(days=1), hours_before_bell=0.02)
    assert talent.investing(db, pid)["total_bps"] <= -4_900     # about -50%, not -4.5%


def test_r6_a_forced_buy_in_is_a_loss_on_the_record_not_money_taken_out(db):
    account = trader(db, "squeezed", cash_naira=1_000_000)
    pid = player_of(db, account)
    history(db, account, [naira(1_000_000), naira(800_000)])
    _paid(db, account, -naira(200_000), "buy_in", T0 + timedelta(days=1))
    assert abs(talent.investing(db, pid)["total_bps"] - (-2_000)) <= 1


def test_r7_paper_deals_are_made_at_the_days_average_and_valued_on_the_day_the_challenge_ends(db):
    firm = _approved_firm(db)
    c = _paper(db, firm)
    me = player_of(db, trader(db, "dealer"))
    challenges.join(db, c["id"], me, False, OPEN)
    price = reference(db)
    s1, b1 = trader(db, "s1", shares=5_000), trader(db, "b1", cash_naira=50_000_000)
    for k in range(3):
        place(db, s1, "sell", 1_000, price)
        place(db, b1, "buy", 1_000, price)
    # One small real trade pushes the last price down by the most a day allows: paper deals ignore it.
    place(db, s1, "sell", 1, price * 91 // 100)
    place(db, b1, "buy", 1, price * 91 // 100)
    dealt = challenges.paper_trade(db, c["id"], me, ticker="IDC", side="buy", quantity=500, now=OPEN + timedelta(minutes=5))
    assert dealt["price"] >= price * 9_999 // 10_000
    # The end: valued on the trading day ending with or after it, not the day before.
    assert challenges._final_day(db, c) is None
    challenges.tick(db, c["ends_at"] + timedelta(minutes=1))
    assert _one(db, "SELECT status FROM talent_challenges WHERE id = %s", (c["id"],))["status"] == "open"
    assert bell_after(db, c["ends_at"]) == challenges._final_day(db, c)


def test_r8_answering_or_scoring_twice_at_once_changes_nothing(db):
    firm = _approved_firm(db)
    _, p = _boarded(db, "twice")
    inv = firms.invite(db, firm["id"], p, "Would you like to talk to us?", OPEN)
    firms.answer(db, p, inv["id"], True, "twice@example.com", OPEN)
    with pytest.raises(firms.FirmError, match="already"):
        firms.answer(db, p, inv["id"], False, "", OPEN)
    c = _paper(db, firm, kind="weak_bank")
    challenges.join(db, c["id"], p, True, OPEN)
    first = challenges.score_challenge(db, c, c["ends_at"] + timedelta(minutes=1))
    assert first is not None and challenges.score_challenge(db, c, c["ends_at"] + timedelta(minutes=2)) is None


def test_r8b_a_request_on_the_website_is_saved_whole_or_not_at_all(db):
    from server import talent_routes
    pid = player_of(db, trader(db, "halfway"))
    talent.settings(db, pid)

    def half_then_refused(now):
        db.execute("UPDATE talent_settings SET headline = 'half done' WHERE player_id = %s", (pid,))
        raise talent.TalentError("Refused after the first step.")
    with pytest.raises(Exception):
        talent_routes._act(db, "x", half_then_refused)
    assert talent.settings(db, pid)["headline"] == ""


def test_r9_innocent_players_are_not_linked_and_a_cleared_pair_can_be_linked_again(db):
    a_acc, b_acc = trader(db, "pal1", cash_naira=10_000_000), trader(db, "pal2", shares=10_000)
    a, b = player_of(db, a_acc), player_of(db, b_acc)
    price = reference(db)
    cheap = price * 92 // 100
    for _ in range(3):
        place(db, b_acc, "sell", 100, cheap)
        place(db, a_acc, "buy", 100, cheap)
    talent.check_trades(db, OPEN.date(), OPEN)
    assert talent.held_back(db, a)
    for f in _rows(db, "SELECT id FROM talent_flags WHERE kind = 'linked'"):
        talent.clear_flag(db, f["id"], "Looked at.", OPEN + timedelta(hours=1))
    assert not talent.held_back(db, a)
    # The same old deals do not link them again; three new ones do.
    talent._maybe_linked(db, a, b, OPEN + timedelta(hours=2))
    assert not talent.held_back(db, a)
    later = OPEN + timedelta(days=1)
    # (the market went on trading at the old price, so that is still the fair price)
    db.execute("UPDATE market_instruments SET reference_price = %s, last_price = %s WHERE company_id = (SELECT id FROM companies"
               " WHERE ticker = 'IDC')", (price, price))
    for _ in range(3):
        place(db, b_acc, "sell", 100, cheap, now=later)
        place(db, a_acc, "buy", 100, cheap, now=later)
    talent.check_trades(db, later.date(), later + timedelta(hours=10))
    assert talent.held_back(db, a) and talent.held_back(db, b)
    # Device marks are not kept for long.
    talent.note_visit(db, a, "m" * 32, OPEN - timedelta(days=5))
    talent.tick(db, OPEN)
    assert _one(db, "SELECT count(*) AS n FROM visitor_marks WHERE day < %s", (OPEN.date() - timedelta(days=2),))["n"] == 0


def test_r10_one_record_that_cannot_be_worked_out_never_stops_the_rest(db, monkeypatch):
    ok_acc, bad_acc = trader(db, "fine"), trader(db, "broken")
    ok, bad = player_of(db, ok_acc), player_of(db, bad_acc)
    history(db, ok_acc, [naira(1_000_000), naira(1_010_000)])
    real = talent.refresh

    def refresh(conn, player_id, now):
        if player_id == bad:
            raise RuntimeError("broken")
        return real(conn, player_id, now)
    monkeypatch.setattr(talent, "refresh", refresh)
    assert talent.tick(db, OPEN) >= 1
    assert _one(db, "SELECT 1 AS x FROM talent_records WHERE player_id = %s", (ok,))
    # Paper portfolios are marked once a day, not on every turn of the loop.
    firm = _approved_firm(db)
    c = _paper(db, firm, starts=OPEN - timedelta(days=1))
    db.execute("UPDATE talent_challenges SET opens_at = %s WHERE id = %s", (T0 - timedelta(days=1), c["id"]))
    challenges.join(db, c["id"], ok, False, OPEN)
    challenges._mark_days(db, OPEN)
    challenges._mark_days(db, OPEN)
    assert _one(db, "SELECT count(*) AS n FROM challenge_days")["n"] == 1


def test_r11_a_quarter_sat_out_breaks_a_run_of_quarters_beating_the_market(db):
    account = trader(db, "sitter")
    pid = player_of(db, account)
    start = talent._start(db).date()
    worths, w = [], naira(1_000_000)
    for k in range(36):
        quarter = k // 7
        worths.append(naira(50_000) if quarter in (2, 3) else w)        # quarters 3 and 4: too little to count
        w = w * 101 // 100
    history(db, account, worths, first=start)
    inv = talent.investing(db, pid)
    assert inv["best_streak"] < 4 and inv["quarters_counted"] >= 3


def test_r12_badges_ties_and_challenges_that_cannot_be_scored(db):
    # A crisis badge is never given to somebody who lost savings in it.
    rec = {"investing": talent.investing(db, player_of(db, trader(db, "lost"))), "calls": {"right": 0, "wrong": 0, "right_bps": None},
           "audits": {"filed": 0, "rightly_named": 0, "wrongly_named": 0, "missed_proved_later": 0},
           "journalism": {"leads_held": 0, "leads_failed": 0}, "leadership": {"good": 0, "bad": 0},
           "crisis": {"pulled_out_in_time": 1, "lost_savings": True, "crises_lived_through": 1, "banks_closed_with_savings": 1, "rescues_won": 0},
           "conduct": {"proved": 0}, "work": {"builds": []}, "challenges": {"results": []}}
    assert "came_through_crisis" not in {c for c, _, _ in talent.badges_from(rec)}
    firm = _approved_firm(db)
    # Ties on the weakest bank: the earlier answer comes first, not the earlier entrant.
    from simulation import deposits
    deposits.setup(db, 0, OPEN)
    w = _paper(db, firm, kind="weak_bank")
    early, late = player_of(db, trader(db, "joined_first")), player_of(db, trader(db, "answered_first"))
    challenges.join(db, w["id"], early, False, OPEN)
    challenges.join(db, w["id"], late, False, OPEN + timedelta(minutes=1))
    challenges.answer(db, w["id"], late, OPEN + timedelta(minutes=2), ticker="KCB")
    challenges.answer(db, w["id"], early, OPEN + timedelta(minutes=3), ticker="KCB")
    challenges.tick(db, w["ends_at"] + timedelta(minutes=1))
    places = {r["player_id"]: r["place"] for r in _rows(db, "SELECT * FROM challenge_entries WHERE challenge_id = %s", (w["id"],))}
    assert places == {late: 1, early: 2}
    # A valuation whose figures never come is closed two weeks after its end, nobody placed: it no longer counts against the firm.
    v = _paper(db, firm, kind="valuation", ticker="IDC")
    p = player_of(db, trader(db, "waiter"))
    challenges.join(db, v["id"], p, True, OPEN)
    challenges.tick(db, v["ends_at"] + challenges.GIVE_UP_AFTER + timedelta(minutes=1))
    done = _one(db, "SELECT * FROM talent_challenges WHERE id = %s", (v["id"],))
    assert done["status"] == "scored" and done["results"]["placed"] == 0


def test_r13_a_firm_proves_its_email_before_it_can_be_approved(db, client):
    from fastapi.testclient import TestClient

    from server.main import app
    with TestClient(app) as firm:
        made = firm.post("/api/firms/signup", json={"name": "Real Bank Ltd", "email": "someone@realbank.example.com",
                                                    "password": "a-long-password-3", "contact_name": "Kemi"}).json()
        assert made["email_confirmed"] is False and made["code_shown_on_screen"]
        with pytest.raises(firms.FirmError, match="confirmed"):
            firms.approve(db, made["id"], OPEN)
        wrong = "000000" if made["code_shown_on_screen"] != "000000" else "111111"
        assert firm.post("/api/firms/confirm", json={"code": wrong}).status_code == 400
        assert firm.post("/api/firms/confirm", json={"code": made["code_shown_on_screen"]}).status_code == 200
        firms.approve(db, made["id"], OPEN)
        assert firm.get("/api/firms/me").json()["status"] == "approved"


@pytest.mark.world("eight")
def test_extra_a_contract_whose_quarter_has_ended_is_settled_at_the_close_not_closed_by_force(db):
    from tests.test_careers import NOW9
    from tests.test_derivatives import series, trader as dtrader
    from tests.conftest import after_quarters
    player, account = dtrader(db, "asset_manager", "writer", cash_naira=50_000_000)
    s = series(db, "call", "IDC", nearest=derivatives.spot(db, series(db, "call", "IDC"), NOW9))
    done = derivatives.open_position(db, account, s["id"], "short", 10, NOW9, player_id=player)
    db.execute("UPDATE derivative_positions SET margin = 0 WHERE id = %s", (done["position_id"],))
    # The quarter has ended, its close not yet run: the bell leaves the contract to be settled at the close.
    late = after_quarters(9) + timedelta(minutes=30)
    derivatives.at_bell(db, late, clock.to_lagos(late).date())
    assert _one(db, "SELECT status FROM derivative_positions WHERE id = %s", (done["position_id"],))["status"] == "open"
