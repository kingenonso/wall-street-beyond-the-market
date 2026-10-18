"""Stage 10, Part 2: the Intelligence Market (M29), the Sealed Tip (M31), sources (Journalist 4) and rumours that move
prices (M32)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, events, exchange, intel, ledger, newsroom, quarters
from simulation import world_data as data
from simulation.money import naira
from tests.conftest import after_quarters
from tests.test_builds import pro
from tests.test_careers import NOW9

pytestmark = pytest.mark.world("eight")
SECRET = ("truth", "basis", "planted_by", "resolves_period", "resolves_day")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _coming_events(db):
    """Something still to come this quarter: a scandal at one company, and a surge in demand across one kind of business."""
    w = careers.world_now(db, NOW9)
    a, b = _rows(db, "SELECT id, sector FROM companies WHERE listed AND sector NOT IN ('banking', 'insurance') ORDER BY ticker LIMIT 2")
    db.execute("INSERT INTO events (period, day, kind, company_id, sales_bps) VALUES (%s, %s, 'scandal', %s, -1500)", (w["period"], w["day"] + 20, a["id"]))
    db.execute("INSERT INTO events (period, day, kind, sector, sales_bps) VALUES (%s, %s, 'sector_demand_surge', %s, 600)",
               (w["period"], w["day"] + 40, b["sector"]))


def _no_secrets(value):
    text = repr(value)
    for word in SECRET:
        assert f"'{word}'" not in text, word


def _player(db, build, name, level=20, cash=5_000_000):
    p, _ = pro(db, build, name, level=level, cash_naira=cash)
    return p


def _held_item(db, player, *, truth="true", company=None, tone=1, kind="tip", status="rumour", confidential=False, useful_hours=4,
               resolves=None, basis=None):
    w = careers.world_now(db, NOW9)
    company = company or _one(db, "SELECT id, name FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    item = intel.make(db, kind=kind, topic="company", words=f"Word around {company['name']}: good news is coming before the quarter is out.",
                      truth=truth, period=w["period"], day=w["day"], now=NOW9, company_id=company["id"], tone=tone, status=status,
                      confidential=confidential, useful_until=NOW9 + timedelta(hours=useful_hours), resolves=resolves, basis=basis)
    intel.hold(db, item["id"], player, "found", NOW9)
    return item


def test_one_sealed_tip_a_day_matched_to_the_build_sealed_until_opened_and_useful_for_four_hours(db):
    p = _player(db, "asset_manager", "tipper")
    sealed = intel.sealed_tip(db, p, NOW9)
    assert sealed["opened"] is False and "words" in sealed and "about" not in sealed and sealed["for"] == "Asset Manager"
    assert intel.sealed_tip(db, p, NOW9 + timedelta(hours=1)) == sealed               # the same tip all day: no extra tips
    assert _one(db, "SELECT count(*) AS n FROM sealed_tips WHERE player_id = %s", (p,))["n"] == 1
    opened = intel.open_tip(db, p, NOW9)
    _no_secrets(opened)
    assert opened["opened"] and opened["words"] and opened["useful"]
    assert opened["useful_until"] == NOW9 + timedelta(hours=data.TIP_USEFUL_HOURS)
    assert intel.open_tip(db, p, NOW9 + timedelta(hours=2))["useful_until"] == opened["useful_until"]   # opening again does not extend it
    assert not intel.sealed_tip(db, p, NOW9 + timedelta(hours=5))["useful"]
    # The next real day brings the next tip.
    tomorrow = NOW9 + timedelta(days=1)
    assert intel.sealed_tip(db, p, tomorrow)["opened"] is False
    assert _one(db, "SELECT count(*) AS n FROM sealed_tips WHERE player_id = %s", (p,))["n"] == 2


def test_tips_are_a_third_real_a_third_false_a_third_already_public_and_the_real_ones_are_about_what_is_coming(db):
    _coming_events(db)
    w = careers.world_now(db, NOW9)
    player = {"id": None, "build": "asset_manager"}
    drawn = [intel.draw(db, player, w["period"], w["day"], NOW9, f"spread:{i}") for i in range(150)]
    share = {t: sum(1 for d in drawn if d["truth"] == t) for t in ("true", "false", "worthless")}
    assert all(30 <= n <= 70 for n in share.values()), share
    for d in drawn:
        company = _one(db, "SELECT id, sector, headquarters FROM companies WHERE id = %s", (d["company_id"],))
        still = intel.coming(db, company, w["period"], w["day"])
        if d["truth"] == "true":
            assert still and intel._effect_tone(still) == d["tone"]           # something real, still to come, the right way
        elif d["truth"] == "false":
            assert not still                                                  # nothing is coming there
        assert not any(ch.isdigit() for ch in d["words"])                     # never a day or a size
    confidential = sum(1 for d in drawn if d["confidential"])
    assert 0 < confidential < 40                                              # about one in ten, and only real ones
    assert all(d["truth"] == "true" for d in drawn if d["confidential"])


def test_a_journalists_tips_include_pacts_and_thefts_and_a_lawyers_pacts(db):
    w = careers.world_now(db, NOW9)
    topics = {intel.draw(db, {"id": None, "build": "journalist"}, w["period"], w["day"], NOW9, f"j:{i}")["topic"] for i in range(60)}
    assert "company" in topics
    # With no hidden pact or theft in the world, the tip falls back to a company or a false or public one.
    assert topics <= {"company", "pact", "theft"}


def test_checking_costs_a_fee_is_mostly_right_and_the_verdict_is_the_holders_own(db):
    p = _player(db, "risk_manager", "checker", level=30, cash=50_000_000)
    account = ledger.player_account_id(db, p)
    before = ledger.balance(db, account)
    right = 0
    items = [_held_item(db, p, truth="true" if i % 2 else "false") for i in range(40)]
    for item in items:
        got = intel.check(db, p, item["ref"], NOW9)
        right += got["verdict"] == ("holds" if item["truth"] == "true" else "fails")
    assert ledger.balance(db, account) == before - 40 * naira(data.CHECK_FEE_NAIRA)
    assert right >= 30                                                        # about 85% at level 30
    with pytest.raises(intel.IntelError, match="already been checked"):
        intel.check(db, p, items[0]["ref"], NOW9)
    leads = _one(db, "SELECT count(*) AS n FROM intel_items WHERE id = ANY(%s) AND status = 'lead'", ([i["id"] for i in items],))["n"]
    assert leads == 0                                                         # one holder's check never changes what others see
    # Nobody checks what they do not hold.
    other = _player(db, "risk_manager", "nosy")
    with pytest.raises(intel.IntelError, match="do not hold"):
        intel.check(db, other, items[1]["ref"], NOW9)


def test_the_market_sells_copies_the_words_only_to_buyers_and_keeps_who_knew_what_when(db):
    seller = _player(db, "accountant", "seller")
    buyer = _player(db, "asset_manager", "buyer", cash=10_000_000)
    item = _held_item(db, seller)
    before = ledger.balance(db, ledger.player_account_id(db, seller))
    listing = intel.offer(db, seller, item["ref"], naira(250_000), NOW9)["listing_id"]
    seen = next(r for r in intel.market(db, buyer, NOW9) if r["listing_id"] == listing)
    assert "words" not in seen and seen["about"]["company"] and seen["status"] == "rumour" and seen["holders"] == 1
    _no_secrets(intel.market(db, buyer, NOW9))
    got = intel.buy(db, buyer, listing, NOW9)
    assert got["words"] == item["words"]
    assert ledger.balance(db, ledger.player_account_id(db, seller)) == before + naira(250_000)
    with pytest.raises(intel.IntelError, match="already hold"):
        intel.buy(db, buyer, listing, NOW9)
    with pytest.raises(intel.IntelError, match="your own"):
        intel.buy(db, seller, listing, NOW9)
    record = _rows(db, "SELECT player_id, how, from_player FROM intel_holders WHERE item_id = %s ORDER BY at, how", (item["id"],))
    assert {(r["player_id"], r["how"]) for r in record} == {(seller, "found"), (buyer, "bought")}
    # Once it has stopped being useful it is not sold.
    late = _player(db, "asset_manager", "late", cash=10_000_000)
    with pytest.raises(intel.IntelError, match="no longer useful"):
        intel.buy(db, late, listing, NOW9 + timedelta(hours=5))
    assert all(r["listing_id"] != listing for r in intel.market(db, late, NOW9 + timedelta(hours=5)))


def test_information_is_given_or_leaked_only_to_a_journalist(db):
    p = _player(db, "lawyer", "giver")
    j = _player(db, "journalist", "receiver")
    other = _player(db, "accountant", "notajournalist")
    item = _held_item(db, p)
    with pytest.raises(intel.IntelError, match="Financial Journalist"):
        intel.give(db, p, item["ref"], "notajournalist", NOW9)
    intel.give(db, p, item["ref"], "receiver", NOW9)
    assert _one(db, "SELECT how, from_player FROM intel_holders WHERE item_id = %s AND player_id = %s", (item["id"], j)) == \
        {"how": "given", "from_player": p}
    assert other


def test_a_source_takes_two_quarters_is_asked_once_a_day_and_is_right_about_as_often_as_it_is_reliable(db):
    j = _player(db, "journalist", "sourcer", level=20)
    company = _one(db, "SELECT ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    intel.cultivate(db, j, "company", company["ticker"], NOW9)
    with pytest.raises(intel.IntelError, match="One new source a quarter"):
        intel.cultivate(db, j, "ministry", None, NOW9)
    s = intel.sources(db, j, NOW9)[0]
    assert s["status"] == "cultivating" and s["reliability_bps"] == data.SOURCE_RELIABILITY_BPS
    with pytest.raises(intel.IntelError, match="not ready"):
        intel.ask_source(db, j, s["id"], NOW9)
    # Two quarters on, it is ready.
    db.execute("UPDATE sources SET ready_period = started_period WHERE id = %s", (s["id"],))
    intel.at_close(db, 8, NOW9)
    hint = intel.ask_source(db, j, s["id"], NOW9)
    assert hint["status"] == "lead" and hint["reliability_bps"] == data.SOURCE_RELIABILITY_BPS and hint["confidential"]
    _no_secrets(hint)
    with pytest.raises(intel.IntelError, match="today"):
        intel.ask_source(db, j, s["id"], NOW9 + timedelta(hours=2))
    # Over many days, it is right about four times in five.
    right = 0
    for d in range(1, 41):
        h = intel.ask_source(db, j, s["id"], NOW9 + timedelta(days=d))
        right += _one(db, "SELECT truth FROM intel_items WHERE ref = %s", (h["ref"],))["truth"] == "true"
    assert 25 <= right <= 39


def test_selling_or_printing_a_sources_hint_may_burn_the_source(db):
    j = _player(db, "journalist", "burner", level=20)
    burned = 0
    for i, c in enumerate(_rows(db, "SELECT id, ticker FROM companies WHERE listed ORDER BY ticker LIMIT 10")):
        db.execute("INSERT INTO sources (journalist_id, kind, company_id, started_period, ready_period, reliability_bps, status, at)"
                   " VALUES (%s, 'company', %s, 1, 3, 8000, 'active', %s)", (j, c["id"], NOW9))
        s = _one(db, "SELECT id FROM sources WHERE journalist_id = %s AND company_id = %s", (j, c["id"]))
        hint = intel.ask_source(db, j, s["id"], NOW9)
        intel.offer(db, j, hint["ref"], naira(50_000), NOW9)
        burned += _one(db, "SELECT status FROM sources WHERE id = %s", (s["id"],))["status"] == "burned"
    assert 0 < burned < 10
    assert all(s["status"] in ("active", "burned") for s in intel.sources(db, j, NOW9))


def test_an_unconfirmed_report_is_printed_as_such_moves_investors_less_and_is_settled_against_what_happened(db):
    _coming_events(db)
    j = _player(db, "journalist", "rumourer", level=30)
    db.execute("INSERT INTO journalist_profiles (player_id, following) VALUES (%s, 200000) ON CONFLICT (player_id) DO UPDATE SET following = 200000", (j,))
    w = careers.world_now(db, NOW9)
    live = None
    for c in _rows(db, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE listed ORDER BY ticker"):
        evs = intel.coming(db, c, w["period"], w["day"])
        if evs and intel._effect_tone(evs):
            live = (c, evs)
            break
    assert live, "this world has an event still to come"
    company, evs = live
    item = intel.make(db, kind="tip", topic="company", words=f"Word around {company['name']}: something is coming before the quarter is out.",
                      truth="true", period=w["period"], day=w["day"], now=NOW9, company_id=company["id"], tone=intel._effect_tone(evs),
                      basis="event:" + ",".join(str(e["id"]) for e in evs), resolves=(w["period"], min(e["day"] for e in evs)),
                      useful_until=NOW9 + timedelta(hours=4))
    intel.hold(db, item["id"], j, "found", NOW9)
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, item["ref"], NOW9)
    with pytest.raises(exchange.ExchangeError, match="No trading"):
        exchange.place_order(db, account=ledger.player_account_id(db, j), ticker=company["ticker"], side="buy", kind="market",
                             quantity=1, limit_price=None, now=NOW9)
    out = newsroom.publish(db, j, NOW9)
    assert out["unconfirmed"]
    story = _one(db, "SELECT * FROM stories WHERE id = %s", (out["story_id"],))
    assert story["headline"].startswith("Unconfirmed:") and "has not been confirmed" in story["body"]
    for n in out["nudges"]:
        assert abs(n["bps"]) <= data.NUDGE_MOST_BPS * data.RUMOUR_NUDGE_SHARE_BPS // 10_000      # half the most a confirmed story moves
    belief = _one(db, "SELECT * FROM rumour_beliefs WHERE story_id = %s", (out["story_id"],))
    assert belief["outcome"] is None
    # The day of the event comes: the report is borne out and the author's credibility rises.
    first = min(e["day"] for e in evs)
    cred = newsroom.profile(db, j)["credibility"]
    when = NOW9 + timedelta(hours=(first - w["day"]) * 24 * 7 / 90 + 2)
    intel.tick(db, when)
    assert _one(db, "SELECT lead_outcome FROM stories WHERE id = %s", (out["story_id"],))["lead_outcome"] == "confirmed"
    assert newsroom.profile(db, j)["credibility"] == cred + data.RUMOUR_CONFIRMED_CREDIBILITY
    assert _one(db, "SELECT outcome FROM rumour_beliefs WHERE story_id = %s", (out["story_id"],))["outcome"] == "true"


def test_a_report_proved_wrong_must_be_corrected_and_investors_take_back_what_they_marked(db):
    j = _player(db, "journalist", "wrongun", level=30)
    db.execute("INSERT INTO journalist_profiles (player_id, following) VALUES (%s, 300000) ON CONFLICT (player_id) DO UPDATE SET following = 300000", (j,))
    w = careers.world_now(db, NOW9)
    quiet = next(c for c in _rows(db, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE listed ORDER BY ticker")
                 if not intel.coming(db, c, w["period"], w["day"]))
    item = _held_item(db, j, truth="false", company=quiet, tone=1, basis="none", resolves=(w["period"], 90))
    newsroom.start(db, j, NOW9)
    newsroom.add_lead(db, j, item["ref"], NOW9)
    out = newsroom.publish(db, j, NOW9)
    marked = _one(db, "SELECT bps FROM rumour_beliefs WHERE story_id = %s", (out["story_id"],))["bps"]
    # The quarter closes and nothing came: the report was wrong.
    quarters.close_due_quarters(db, after_quarters(9))
    story = _one(db, "SELECT * FROM stories WHERE id = %s", (out["story_id"],))
    assert story["lead_outcome"] == "disproved" and story["correction_due"]
    assert _one(db, "SELECT status FROM intel_items WHERE id = %s", (item["id"],))["status"] == "disproved"
    if marked:
        back = _one(db, "SELECT sum(bps) AS b FROM story_nudges WHERE company_id = %s AND bps < 0", (quiet["id"],))["b"]
        assert back and back <= -marked
    fixed = newsroom.correct(db, j, out["story_id"], after_quarters(9) + timedelta(hours=1))
    body = _one(db, "SELECT body FROM news_items WHERE id = %s", (fixed["news_item_id"],))["body"]
    assert "has not been borne out" in body
    # A disproved piece can no longer be printed or sold.
    with pytest.raises(intel.IntelError, match="no longer useful"):
        intel.offer(db, j, item["ref"], naira(50_000), after_quarters(9) + timedelta(hours=1))


def test_trading_on_confidential_information_is_kept_for_the_courts(db):
    p = _player(db, "asset_manager", "insider", cash=50_000_000)
    company = _one(db, "SELECT id, name, ticker FROM companies WHERE listed ORDER BY ticker LIMIT 1")
    item = _held_item(db, p, company=company, confidential=True)
    account = ledger.player_account_id(db, p)
    try:
        exchange.place_order(db, account=account, ticker=company["ticker"], side="buy", kind="market", quantity=10, limit_price=None, now=NOW9)
    except exchange.ExchangeError:
        pass
    dealt = _one(db, "SELECT * FROM confidential_dealings WHERE player_id = %s", (p,))
    assert dealt and dealt["item_id"] == item["id"] and dealt["company_id"] == company["id"]
    # After it has stopped being useful, a trade is just a trade.
    other = _player(db, "asset_manager", "afterwards", cash=50_000_000)
    _held_item(db, other, company=company, confidential=True, useful_hours=1)
    try:
        exchange.place_order(db, account=ledger.player_account_id(db, other), ticker=company["ticker"], side="buy", kind="market",
                             quantity=10, limit_price=None, now=NOW9 + timedelta(hours=2))
    except exchange.ExchangeError:
        pass
    assert _one(db, "SELECT 1 AS x FROM confidential_dealings WHERE player_id = %s", (other,)) is None


def test_a_ministry_source_is_settled_at_the_close_against_the_central_banks_decision(db):
    j = _player(db, "journalist", "ministry", level=20)
    db.execute("INSERT INTO sources (journalist_id, kind, started_period, ready_period, reliability_bps, status, at)"
               " VALUES (%s, 'ministry', 1, 3, 8000, 'active', %s)", (j, NOW9))
    s = _one(db, "SELECT id FROM sources WHERE journalist_id = %s", (j,))
    hint = intel.ask_source(db, j, s["id"], NOW9)
    assert hint["about"]["topic"] in ("rate", "infrastructure")
    quarters.close_due_quarters(db, after_quarters(9))
    settled = _one(db, "SELECT status FROM intel_items WHERE ref = %s", (hint["ref"],))["status"]
    assert settled in ("verified", "disproved")


def test_each_build_sees_its_own_part_of_the_public_record_and_nothing_hidden(db):
    for build in ("lawyer", "accountant", "investment_banker", "asset_manager", "risk_manager", "journalist"):
        p = _player(db, build, f"feed{build}")
        feed = intel.desk_feed(db, p, NOW9)
        assert feed["build"] in intel.BUILD_WORDS.values()
        _no_secrets(feed)
    # The risk desk lists only events whose day has come.
    w = careers.world_now(db, NOW9)
    p = _player(db, "risk_manager", "riskfeed")
    later = [e for e in events.load(db, w["period"]) if e["day"] > w["day"] and e["severe"]]
    words = " ".join(i["what"] for i in intel.desk_feed(db, p, NOW9)["items"])
    for e in later:
        assert f"on day {e['day']}" not in words
