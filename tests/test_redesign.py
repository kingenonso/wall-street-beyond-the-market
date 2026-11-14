"""The front-end redesign (owner, 12 October 2026): what the server adds for it.

The player's own settings (look, sound, the first-time tour), faster early levels, "How to do this"
before a piece of work starts, the last five closing prices beside each share, each share's name in
the command bar, how prices moved after a story, and the count of work in hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from psycopg.rows import dict_row

from simulation import careers, clock, marketview, news, objectives
from simulation import world_data as data
from tests.conftest import ADULT, join
from tests.test_careers import NOW9, professional

pytestmark = pytest.mark.world("eight")


def trade_days(db, ticker=None, days=6):
    """Real trades on several days in a row, each a little above the last, so a share has closing prices.
    It uses a share whose last trading day was before these days (some shares trade during the quarter closes,
    which move their trading day on), or the share asked for. Returns the share's code."""
    from simulation import exchange
    from tests.test_market import OPEN, place, reference, trader
    if ticker is None:
        ticker = db.execute("SELECT c.ticker FROM market_instruments m JOIN companies c ON c.id = m.company_id"
                            " WHERE m.session_date < %s AND m.last_price IS NULL ORDER BY c.ticker LIMIT 1", (OPEN.date(),)).fetchone()[0]
    seller = trader(db, f"seller{ticker.lower()}", shares=100_000, ticker=ticker)
    buyer = trader(db, f"buyer{ticker.lower()}", cash_naira=50_000_000, ticker=ticker)
    price = reference(db, ticker)
    for n in range(days):
        price = min(exchange.price_limits(price)[1], price + price // 50)
        when = OPEN + timedelta(days=n)
        place(db, seller, "sell", 100, price, now=when, ticker=ticker)
        place(db, buyer, "buy", 100, price, now=when, ticker=ticker)
    return ticker


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# The player's own settings
# ---------------------------------------------------------------------------

def test_a_player_sets_their_own_look_sound_and_tour(db, client):
    assert client.patch("/api/me/settings", json={"theme": "light"}).status_code == 401
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    assert (me["theme"], me["sound_on"], me["sound_volume"], me["tour_done"]) == ("dark", True, 30, False)   # the owner's defaults
    changed = client.patch("/api/me/settings", json={"theme": "light", "sound_volume": 60})
    assert changed.status_code == 200 and changed.json()["theme"] == "light" and changed.json()["sound_volume"] == 60
    assert client.patch("/api/me/settings", json={"sound_on": False, "tour_done": True}).json()["sound_on"] is False
    again = client.get("/api/me").json()
    assert (again["theme"], again["sound_on"], again["sound_volume"], again["tour_done"]) == ("light", False, 60, True)
    for bad in ({"theme": "neon"}, {"sound_volume": 101}, {"sound_volume": -1}, {"sound_volume": "50"}, {"sound_on": "yes please"},
                {}, {"theme": "dark", "cash_kobo": 1}, {"theme": "dark", "player_id": me["id"]}):
        assert client.patch("/api/me/settings", json=bad).status_code == 422, bad


def test_settings_change_nothing_but_the_players_own_four(db, client):
    other, _ = professional(db, "other", now=NOW9)
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    before = _dicts(db, "SELECT * FROM players WHERE id = %s", (me["id"],))[0]
    client.patch("/api/me/settings", json={"theme": "light", "sound_on": False, "sound_volume": 0, "tour_done": True})
    after = _dicts(db, "SELECT * FROM players WHERE id = %s", (me["id"],))[0]
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"theme", "sound_on", "sound_volume", "tour_done"}
    assert _dicts(db, "SELECT theme, sound_on FROM players WHERE id = %s", (other,))[0] == {"theme": "dark", "sound_on": True}


# ---------------------------------------------------------------------------
# Faster early levels
# ---------------------------------------------------------------------------

def test_levels_one_to_ten_come_twice_as_fast_and_level_twenty_is_unchanged():
    assert careers.experience_for(10) == 15 * 10 * 9 == 1350            # was 2,700
    assert careers.experience_for(20) == data.LEVEL_EXPERIENCE * 20 * 19 == 11400
    for level in range(21, 101):
        assert careers.experience_for(level) == data.LEVEL_EXPERIENCE * level * (level - 1)
    steps = [careers.experience_for(n + 1) - careers.experience_for(n) for n in range(1, 20)]
    assert all(s > 0 for s in steps) and steps[:9] == sorted(steps[:9]) and steps[9:] == sorted(steps[9:])
    assert careers.level_for(careers.experience_for(10)) == 10 and careers.level_for(careers.experience_for(10) - 1) == 9
    assert careers.level_for(careers.experience_for(20)) == 20 and careers.level_for(10**9) == 20    # the gate still holds


# ---------------------------------------------------------------------------
# How to do this, before starting
# ---------------------------------------------------------------------------

def test_how_to_do_this_is_the_general_method_and_never_the_answer(db):
    found = [t for t in objectives.TEMPLATES.values() if objectives.how_to(t)]
    assert len(found) >= 120
    player, _ = professional(db, now=NOW9)
    # After hand-in, the debrief's professional method is the very text shown before starting.
    from tests.test_careers import pass_one
    done = pass_one(db, player, NOW9)
    board = objectives.board(db, player, NOW9)
    offer = next(o for o in board["offers"] if o["template"] == "ac_ratios_e")
    assert offer["how"] and done["result"]["debrief"]["method"] == offer["how"] == objectives.how_to(objectives.TEMPLATES["ac_ratios"])
    # A piece of work in hand carries it too, and it holds none of that work's own figures.
    taken = objectives.accept(db, player, "ac_cash_flow", NOW9)
    active = next(o for o in objectives.board(db, player, NOW9)["active"] if o["id"] == taken["id"])
    assert active["how"] == objectives.how_to(objectives.TEMPLATES["ac_cash_flow"])
    terms = _dicts(db, "SELECT terms FROM objectives WHERE id = %s", (taken["id"],))[0]["terms"]
    for line in terms.get("given", []) + [{"kobo": i.get("kobo")} for f in terms.get("fields", []) for i in f.get("items", [])]:
        if line.get("kobo"):
            assert f"{line['kobo'] / 1e8:,.2f}" not in active["how"] and str(line["kobo"]) not in active["how"]
    assert "_truth" not in str(active)


# ---------------------------------------------------------------------------
# The market's small trend lines, names in the command bar, work in hand
# ---------------------------------------------------------------------------

def test_each_share_carries_its_last_five_closes(db, client):
    trade_days(db)
    assert join(client, ADULT).status_code == 201
    shares = client.get("/api/market").json()["shares"]
    with_closes = [s for s in shares if s["closes"]]
    assert with_closes, "the eight-quarter world has trading history"
    for s in with_closes[:10]:
        history = marketview.history(db, s["ticker"])
        assert s["closes"] == [str(d["close"]) for d in history[-5:]]
        assert len(s["closes"]) <= 5
    ticker = client.get("/api/market/ticker").json()["shares"]
    assert all(t["name"] and t["sector"] for t in ticker)


def test_work_in_hand_is_counted_for_the_dot_on_work(db, client):
    assert join(client, ADULT).status_code == 201
    assert client.get("/api/me").json()["work_in_hand"] == 0
    assert client.put("/api/career/build", json={"build": "accountant"}).status_code == 200
    me = client.get("/api/me").json()
    db.execute("UPDATE players SET build = 'accountant' WHERE id = %s", (me["id"],))
    careers.choose_bank(db, me["id"], "IKB", NOW9)
    careers.take_job(db, me["id"], "IDC", NOW9)
    objectives.accept(db, me["id"], "ac_ratios", NOW9)
    assert client.get("/api/me").json()["work_in_hand"] == 1


# ---------------------------------------------------------------------------
# How prices moved after a story
# ---------------------------------------------------------------------------

def test_a_storys_price_move_runs_from_the_last_close_before_it_to_the_price_now(db):
    world = _dicts(db, "SELECT world_start, weeks_ahead FROM world_state")[0]
    start = clock.effective_start(world["world_start"], world["weeks_ahead"])
    traded = trade_days(db)
    days = marketview.history(db, traded)
    story_day = days[-1]["session_date"]                       # a story that came out on the last trading day
    moment = datetime.combine(story_day, datetime.min.time(), tzinfo=timezone(timedelta(hours=1))) + timedelta(hours=13)
    elapsed = moment - start
    quarter = timedelta(days=clock.REAL_DAYS_PER_QUARTER)
    period = elapsed // quarter + 1
    day = int((elapsed - (period - 1) * quarter) / quarter * clock.GAME_DAYS_PER_QUARTER) + 1
    item = {"period": period, "day": day, "tickers": [traded]}
    now = datetime.now(UTC) + timedelta(days=3650)
    moves = news.price_moves(db, [item], start, now)
    current = _dicts(db, "SELECT coalesce(m.last_price, m.reference_price) AS p FROM market_instruments m JOIN companies c"
                         " ON c.id = m.company_id WHERE c.ticker = %s", (traded,))[0]["p"]
    before = [d for d in days if d["session_date"] < clock.to_lagos(start + (period - 1) * quarter + quarter * (day - 1) / 90).date()]
    assert before, "there is a close before the story"
    expected = (current - before[-1]["close"]) * 10_000 // before[-1]["close"]
    assert moves[(period, day, traded)] == expected
    # A story dated after "now", or about more than six companies, shows no move.
    assert news.price_moves(db, [item], start, start) == {}
    assert news.price_moves(db, [{**item, "tickers": [traded] * 7}], start, now) == {}


def test_the_news_route_gives_moves_only_for_stories_already_out(db, client):
    assert join(client, ADULT).status_code == 201
    items = client.get("/api/news", params={"limit": 120}).json()["items"]
    assert all(set(i["moves"]) <= set(i["tickers"]) for i in items)
    assert all(isinstance(v, int) for i in items for v in i["moves"].values())


def _judge_two_texts(conn, objective, answers, now):
    if answers:
        return dict(passed=True, method="Divide profit by sales.")
    return dict(passed=False, method="Look again at the cash.")


def _judge_built_text(conn, objective, answers, now):
    figure = objective["terms"]["_truth"]["margin"]
    return dict(passed=True, method=f"The margin was {figure}.")


def _judge_one_text(conn, objective, answers, now):
    if answers:
        return dict(passed=True, method="Divide profit by sales.")
    return dict(passed=False, method="Divide profit by sales.")


def test_how_to_is_shown_only_when_the_judging_code_has_one_fixed_text():
    from dataclasses import replace
    real = objectives.TEMPLATES["ac_ratios"]
    for n, (judge, expected) in enumerate(((_judge_two_texts, None), (_judge_built_text, None), (_judge_one_text, "Divide profit by sales."))):
        made_up = replace(real, code=f"zz_test_how_{n}", base=None, submit=judge, bell=None, close=None)
        assert objectives.how_to(made_up) == expected, judge.__name__
        objectives._HOW.pop(made_up.code, None)
