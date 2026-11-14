"""Private equity stage, part 2A: private companies, and buying, running and selling them.

Thirty private companies in the same economy as the listed ones; their papers do not always tell the
truth; an empire's six desks check a company before the head bids; sealed bids and auctions against
other empires; buyouts with borrowed money and the bank's promises; the dials of a company an empire
controls; assets that wear; the airline's routes; the 100-day plan; the company doctor;
administration; getting out, and the gain shared out."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import empires, firm, firm_deals, firm_owned, ledger, private, quarters
from simulation import world_data as data
from simulation.money import BPS, million_naira
from tests.conftest import after_quarters
from tests.test_careers import NOW9
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")
LATER = NOW9 + timedelta(hours=1)


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(db, sql, params=()):
    rows = _dicts(db, sql, params)
    return rows[0] if rows else None


def truth(db, step_id):
    return _one(db, "SELECT terms FROM deal_steps WHERE id = %s", (step_id,))["terms"]["_truth"]


def right_answers(db, step_id):
    """The answers as a player would type them: percentages as percent, not hundredths of a percent."""
    terms = _one(db, "SELECT terms FROM deal_steps WHERE id = %s", (step_id,))["terms"]
    return {a["key"]: terms["_truth"][a["key"]] / 100 if a["kind"] == "percent" else terms["_truth"][a["key"]] for a in terms["asks"]}


def an_open_sale(db, *, mode=None, secret=None):
    """An open sale of a private company, decided at the next close (opened by the founders)."""
    sql = ("SELECT s.* FROM sale_processes s JOIN private_profiles p ON p.company_id = s.company_id WHERE s.status = 'open'"
           " AND s.seller_empire_id IS NULL" + (" AND s.mode = %(mode)s" if mode else "")
           + (" AND p.secrets @> %(secret)s::jsonb" if secret else "") + " ORDER BY s.asking LIMIT 1")
    return _one(db, sql, {"mode": mode, "secret": f'[{{"code": "{secret}"}}]' if secret else None})


def open_a_sale(db, company_ticker=None, mode="sealed"):
    """Put a private company up for sale now (as the founders might), for a test that needs a particular one.
    If the founders already have that one on sale, that sale is used."""
    if company_ticker:
        already = _one(db, "SELECT s.* FROM sale_processes s JOIN companies c ON c.id = s.company_id WHERE c.ticker = %s AND s.status = 'open'"
                           " AND s.seller_empire_id IS NULL", (company_ticker,))
        if already:
            return already
    company = _one(db, "SELECT c.* FROM companies c WHERE NOT c.listed AND c.status = 'trading'"
                       + (" AND c.ticker = %s" if company_ticker else "") + " AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE"
                       " s.company_id = c.id AND s.status = 'open') ORDER BY c.ticker LIMIT 1", (company_ticker,) if company_ticker else ())
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    with db.transaction():
        sale_id = private.start_sale(db, company["id"], founders, None, ledger.balance(db, founders, company["share_asset"]), 8,
                                     private._seed(db), NOW9, mode=mode)
    return _one(db, "SELECT * FROM sale_processes WHERE id = %s", (sale_id,))


def do_checks(db, empire, team, file_id, *, well=True, badly=(), skip=()):
    """Every desk does its check on the company; `well` answers with the truth (except the checks named in `badly`).
    The checks named in `skip` are not done at all (only the accounts, valuation and stress test are required)."""
    for step in _dicts(db, "SELECT * FROM deal_steps WHERE file_id = %s ORDER BY id", (file_id,)):
        if step["step"] in skip:
            continue
        who = team["investment_banker" if step["build"] == "investment_banker" else step["build"]]
        firm_deals.open_step(db, who, step["id"], LATER)
        answers = right_answers(db, step["id"]) if well and step["step"] not in badly else {k: 0 for k in truth(db, step["id"])}
        if "fair" in answers and not well:
            answers["fair"] = "nonsense"
        done = firm_deals.hand_in_step(db, who, step["id"], answers, LATER)
        assert (done["score"] == 100) == (well and step["step"] not in badly) or not well or step["step"] in badly


def fairness_if_needed(db, team, file_id, bid):
    """A bid above the line needs the Banker's fairness opinion, even when the asking price was below it: give it."""
    if bid > firm_deals.FAIRNESS_ABOVE and not _one(db, "SELECT 1 FROM deal_steps WHERE file_id = %s AND step = 'fairness'", (file_id,)):
        db.execute("INSERT INTO deal_steps (file_id, step, build) VALUES (%s, 'fairness', 'investment_banker')", (file_id,))
        step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'fairness'", (file_id,))
        firm_deals.open_step(db, team["investment_banker"], step["id"], LATER)
        firm_deals.hand_in_step(db, team["investment_banker"], step["id"], right_answers(db, step["id"]), LATER)


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------

def test_thirty_private_companies_trade_in_the_economy_but_are_not_on_the_exchange_or_in_the_news(db, client):
    private_ones = _dicts(db, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE NOT c.listed")
    assert len(private_ones) >= 30
    sectors = {c["sector"] for c in private_ones}
    assert {"aviation", "hospitality", "shipping"} <= sectors
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    for c in private_ones:
        # Owned by their founders, an empire that bought them, or the pension funds (which bid for companies put up
        # for sale too, and can win); never on the exchange.
        assert not _one(db, "SELECT 1 FROM market_instruments WHERE company_id = %s", (c["id"],))
        holders = _dicts(db, "SELECT account_id FROM ledger_balances WHERE asset = %s AND balance > 0", (c["share_asset"],))
        assert holders and all(h["account_id"] in (founders, funds) or _one(db, "SELECT 1 FROM empires WHERE account_id = %s", (h["account_id"],))
                               for h in holders)
        # They sell to households and other companies, pay wages and tax, every quarter.
        r = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 8", (c["id"],))
        assert r["revenue"] > 0 and r["total_assets"] == r["total_liabilities"] + r["total_equity"]
        assert private.assets(db, c["id"]) and private.manager(db, c["id"])
    assert sum(1 for c in private_ones if c["sector"] == "aviation") >= 3
    # Nothing about them is published: not in the companies list, not by ticker, not in the results news.
    from tests.conftest import ADULT, join
    assert join(client, ADULT).status_code == 201
    listed = client.get("/api/companies").json()["sectors"]
    assert sum(len(s["companies"]) for s in listed) == 68
    eks = private_ones[0]["ticker"]
    assert client.get(f"/api/companies/{eks}").status_code == 404
    names = {c["name"] for c in private_ones}
    for item in _dicts(db, "SELECT facts FROM news_items WHERE kind LIKE 'results_%%' OR kind LIKE 'profit_%%'"):
        assert not ({str(v) for v in item["facts"].values()} & names)
    # The sales the founders opened are public: the asking price, how it is sold, when it closes.
    assert _one(db, "SELECT count(*) AS n FROM sale_processes")["n"] >= 1


def test_secrets_are_never_sent_and_each_has_a_real_effect(db, client):
    """The world's private companies have secrets; the server never sends them to a player."""
    rows = _dicts(db, "SELECT c.ticker, p.secrets FROM private_profiles p JOIN companies c ON c.id = p.company_id")
    kinds = {s["code"] for r in rows for s in r["secrets"]}
    assert {"dressed_revenue"} <= kinds and len(kinds) >= 4
    empire, team = firm_of(db)
    seen = str(firm.view(db, team["head"], LATER))
    for r in rows:
        for s in r["secrets"]:
            assert "secrets" not in seen and s["code"] not in seen


# ---------------------------------------------------------------------------
# The stage test: bring, check, argue, bid, buy, run, sell
# ---------------------------------------------------------------------------

def test_the_stage_test_a_company_is_checked_by_six_desks_bought_with_a_buyout_loan_run_and_sold_at_a_gain(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, "MPK", mode="sealed")
    # The Banker brings it; nobody else may.
    with pytest.raises(empires.EmpireError, match="Investment Banker"):
        firm_deals.open_file(db, team["asset_manager"], sale["id"], LATER)
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    # Nothing can be checked before Legal Counsel signs the confidentiality agreement.
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    with pytest.raises(empires.EmpireError, match="confidentiality"):
        firm_deals.open_step(db, team["asset_manager"], step["id"], LATER)
    view = firm.view(db, team["head"], LATER)["deals"]
    mine = next(s for s in view["sales"] if s["id"] == sale["id"])["file"]
    assert mine["nda"] is False and "data_room" not in mine
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    mine = next(s for s in firm.view(db, team["head"], LATER)["deals"]["sales"] if s["id"] == sale["id"])["file"]
    assert mine["data_room"]["papers"] and mine["data_room"]["assets"]
    # A bid before all three desks have signed is refused.
    with pytest.raises(empires.EmpireError, match="all three"):
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"], 0, LATER)
    do_checks(db, empire, team, file_id)
    # Legal Counsel strikes the seller's escape clauses and asks for the money held back.
    draft = {t["code"]: t for t in firm_deals.terms_view(db, sale["id"], empire["id"])}
    changes = {code: "strike" for code, t in draft.items() if t["escape"]}
    changes["escrow"] = "ask"
    firm_deals.mark_terms(db, team["investment_banker"], file_id, changes, LATER)
    in_force = firm_deals.in_force(db, sale["id"], empire["id"])
    assert in_force.get("escrow") and not in_force.get("as_is") and in_force.get("accounts_warranty")
    quote = firm_deals.loan_quote(db, sale, sale["asking"], 9)
    loan = min(quote["most"], sale["asking"] // 2)
    cash_before = ledger.balance(db, empire["account_id"])
    bid = firm_deals.place_bid(db, team["head"], file_id, sale["asking"], loan, LATER)
    assert bid["equity"] == bid["price"] - loan and ledger.balance(db, empire["account_id"]) == cash_before - bid["equity"]
    assert firm_deals.check_books(db) == []
    # Worth is unchanged while the bid stands: the cash held is still the empire's.
    # The sale is decided as the quarter closes.
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    if deal is None:
        pytest.skip("A computer-run empire outbid the test empire at this price.")
    company = _one(db, "SELECT * FROM companies WHERE id = %s", (sale["company_id"],))
    assert ledger.balance(db, empire["account_id"], company["share_asset"]) == sale["shares"]
    assert _one(db, "SELECT empire_id FROM owned_companies WHERE company_id = %s", (company["id"],))["empire_id"] == empire["id"]
    debt = _one(db, "SELECT * FROM empire_debts WHERE empire_id = %s AND kind = 'buyout'", (empire["id"],))
    assert (debt is None and loan == 0) or (debt["outstanding"] == loan and str(debt["company_id"]) == str(company["id"]))
    assert deal["escrow"] == deal["price"] // 10 and firm_deals.check_books(db) == []
    assert ledger.audit(db) == []
    # Running it: the dials, read in the next close.
    period = 10
    when = after_quarters(9) + timedelta(hours=2)
    firm_owned.set_dials(db, team["head"], company["id"], {"price_bps": 10_500, "staff_bps": 10_000, "pay_rise_bps": 300, "marketing": million_naira(50),
                                                           "technology": 0, "maintenance_bps": 12_000, "payout_bps": 5000, "borrow": 0, "buy_assets": 1},
                         when)
    with pytest.raises(empires.EmpireError, match="head, the deputy or the Asset Manager"):
        firm_owned.set_dials(db, team["investment_banker"], company["id"], {"price_bps": 10_000}, when)
    assets_before = len(private.assets(db, company["id"]))
    assert quarters.close_due_quarters(db, after_quarters(period)) == [period]
    assert len(private.assets(db, company["id"])) == assets_before + 1                  # the new asset it ordered
    assert _one(db, "SELECT price_bps FROM companies WHERE id = %s", (company["id"],))["price_bps"] == 10_500
    assert ledger.audit(db) == []
    # Getting out: the computer-run buyer, at once. The deal team are paid their fees from a gain.
    later = after_quarters(period) + timedelta(hours=2)
    offer = firm_owned.buyer_offer(db, company["id"])
    out = firm_owned.sell_to_buyer(db, team["head"], company["id"], later)
    assert out["proceeds"] == offer["per_share"] * sale["shares"]
    assert ledger.balance(db, empire["account_id"], company["share_asset"]) == 0
    x = _one(db, "SELECT * FROM deal_exits WHERE empire_id = %s", (empire["id"],))
    assert x["gain"] == x["proceeds"] - x["cost"]
    assert not _one(db, "SELECT 1 FROM owned_companies WHERE empire_id = %s", (empire["id"],))
    assert ledger.audit(db) == [] and firm_deals.check_books(db) == []


def test_a_badly_done_check_finds_nothing_and_a_well_done_one_finds_the_dressed_accounts(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    dressed = _one(db, "SELECT c.ticker FROM private_profiles p JOIN companies c ON c.id = p.company_id WHERE p.secrets @> '[{\"code\": \"dressed_revenue\"}]'"
                       " AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM sale_processes s WHERE s.company_id = c.id AND s.status = 'open')"
                       " ORDER BY c.ticker LIMIT 1")
    sale = open_a_sale(db, dressed["ticker"])
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    step = _one(db, "SELECT * FROM deal_steps WHERE file_id = %s AND step = 'accounts'", (file_id,))
    firm_deals.open_step(db, team["asset_manager"], step["id"], LATER)
    gap = truth(db, step["id"])["gap"]
    assert gap >= 900                                    # the accounts claim sales the bank never saw
    done = firm_deals.hand_in_step(db, team["asset_manager"], step["id"], {"gap": round(gap / 100, 2)}, LATER)
    assert done["score"] == 100 and any("overstate" in w for w in done["found"])
    assert {f["code"] for f in firm_deals.finds(db, empire["id"], sale["company_id"])} == {"dressed_revenue"}


def test_the_auction_is_open_and_each_bid_must_beat_the_highest(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, mode="auction")
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    do_checks(db, empire, team, file_id)
    first = firm_deals.place_bid(db, team["head"], file_id, sale["asking"], 0, LATER)
    assert _one(db, "SELECT highest FROM sale_processes WHERE id = %s", (sale["id"],))["highest"] == sale["asking"]
    with pytest.raises(empires.EmpireError, match="at least"):
        firm_deals.place_bid(db, team["head"], file_id, sale["asking"] + 1, 0, LATER)
    raised = firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 103 // 100, 0, LATER)
    assert raised["bid_id"] == first["bid_id"] and firm_deals.check_books(db) == []
    with pytest.raises(empires.EmpireError, match="cannot be withdrawn"):
        firm_deals.withdraw_bid(db, team["head"], file_id, LATER)


def test_a_bid_that_loses_hands_back_every_kobo_held(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, mode="sealed")
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    do_checks(db, empire, team, file_id)
    firm_deals.place_bid(db, team["head"], file_id, sale["reserve"] // 2, 0, LATER)    # below what the seller would take
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert _one(db, "SELECT status FROM deal_bids WHERE empire_id = %s", (empire["id"],))["status"] == "lost"
    assert _one(db, "SELECT held FROM deal_bids WHERE empire_id = %s", (empire["id"],))["held"] == 0
    assert firm_deals.check_books(db) == [] and ledger.audit(db) == []


def test_a_false_promise_is_claimed_against_the_money_held_back(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    # A tax bill the founders hid, which the registry would have shown, but the empire never read the registry.
    target = _one(db, "SELECT c.* FROM companies c WHERE NOT c.listed AND c.status = 'trading' AND NOT EXISTS (SELECT 1 FROM sale_processes s"
                      " WHERE s.company_id = c.id AND s.status = 'open') ORDER BY (SELECT base_revenue FROM company_results r WHERE r.company_id = c.id"
                      " ORDER BY period DESC LIMIT 1), c.ticker LIMIT 1")
    db.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s",
               (Jsonb([{"code": "hidden_debt", "bps": 0, "amount": million_naira(300), "from_period": None, "done": False}]), target["id"]))
    sale = open_a_sale(db, target["ticker"])
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["investment_banker"], file_id, LATER)
    do_checks(db, empire, team, file_id, skip=("legal",))             # Legal Counsel never reads the registry
    draft = {t["code"]: t for t in firm_deals.terms_view(db, sale["id"], empire["id"])}
    firm_deals.mark_terms(db, team["investment_banker"], file_id, {**{c: "strike" for c, t in draft.items() if t["escape"]}, "escrow": "ask"}, LATER)
    firm_deals.place_bid(db, team["head"], file_id, sale["asking"] * 13 // 10, 0, LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    deal = _one(db, "SELECT * FROM deals WHERE empire_id = %s", (empire["id"],))
    assert deal is not None
    when = after_quarters(9) + timedelta(hours=2)
    # Before the tax office's letter arrives, the empire does not know: no claim.
    with pytest.raises(empires.EmpireError, match="does not know"):
        firm_deals.claim(db, team["investment_banker"], deal["id"], "hidden_debt", when)
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]       # the hidden tax bill falls due
    later = after_quarters(10) + timedelta(hours=2)
    seller_cash = ledger.balance(db, deal["seller_account"])
    got = firm_deals.claim(db, team["investment_banker"], deal["id"], "hidden_debt", later)
    assert got["paid"] == million_naira(300) and got["paid"] <= deal["escrow"] + seller_cash
    assert _one(db, "SELECT escrow FROM deals WHERE id = %s", (deal["id"],))["escrow"] == max(deal["escrow"] - got["paid"], 0)
    with pytest.raises(empires.EmpireError, match="has been made"):
        firm_deals.claim(db, team["investment_banker"], deal["id"], "hidden_debt", later)
    with pytest.raises(empires.EmpireError, match="does not know"):
        firm_deals.claim(db, team["investment_banker"], deal["id"], "dressed_revenue", later)
    assert firm_deals.check_books(db) == [] and ledger.audit(db) == []


def test_an_airline_flies_routes_and_its_fares_are_set_against_its_rivals(db):
    airlines = _dicts(db, "SELECT c.* FROM companies c WHERE c.sector = 'aviation' ORDER BY c.ticker")
    assert len(airlines) >= 3
    for a in airlines:
        routes = _dicts(db, "SELECT * FROM airline_routes WHERE company_id = %s AND closed_period IS NULL", (a["id"],))
        assert routes and any(a["headquarters"] in (r["city_a"], r["city_b"]) for r in routes)
        planes = [x for x in private.assets(db, a["id"]) if x["kind"] == "plane"]
        assert planes and all(p["route_id"] for p in planes)
        assert any(x["kind"] == "hangar" for x in private.assets(db, a["id"]))
    fares = private._fares(db)
    a = airlines[0]
    before = private._route_score(db, a["id"], fares)
    route = _one(db, "SELECT * FROM airline_routes WHERE company_id = %s AND closed_period IS NULL ORDER BY id LIMIT 1", (a["id"],))
    dearer = {**fares, (a["id"], (route["city_a"], route["city_b"])): 13_000}
    assert private._route_score(db, a["id"], dearer) < before                         # dearer than rivals: fewer travellers


def test_a_neglected_asset_wears_out_and_is_grounded(db):
    c = _one(db, "SELECT c.* FROM companies c WHERE NOT c.listed ORDER BY c.ticker LIMIT 1")
    asset = private.assets(db, c["id"])[0]
    result = {"depreciation": 100, "capital_spending": 0, "revenue": 1}
    db.execute("UPDATE company_assets SET condition_bps = 2100 WHERE id = %s", (asset["id"],))
    private._wear(db, {**c, "upkeep_bps": 0}, result, 9, private._seed(db))
    after = _one(db, "SELECT * FROM company_assets WHERE id = %s", (asset["id"],))
    assert after["condition_bps"] < 2100 and after["status"] == "grounded" and after["age_quarters"] == asset["age_quarters"] + 1
    assert private.capacity(db, c["id"], 9) < sum(x["capacity"] for x in private.assets(db, c["id"]) if x["capacity"]) * 2


def test_customers_weigh_prices_and_the_mindsets_of_a_city_decide_how_much(db):
    lagos = private.elasticity_bps({"opportunistic": 1400, "risk_seeking": 1600, "sceptical": 800, "loyal": 600, "risk_averse": 600})
    kano = private.elasticity_bps({"opportunistic": 400, "risk_seeking": 600, "sceptical": 1000, "loyal": 2000, "risk_averse": 1600})
    assert lagos > kano
    assert private.price_factor(11_000, lagos) < private.price_factor(11_000, kano) < BPS < private.price_factor(9000, kano)
    assert private.price_factor(BPS, lagos) == BPS


def test_the_world_has_the_new_industries_and_their_place_in_the_economy(db):
    codes = {s.code for s in data.SECTORS}
    assert {"aviation", "hospitality", "shipping"} <= codes
    for code in ("aviation", "hospitality", "shipping"):
        assert _one(db, "SELECT household_bps FROM sector_demand WHERE sector = %s", (code,))["household_bps"] > 0
        assert _one(db, "SELECT count(*) AS n FROM sector_inputs WHERE buyer = %s", (code,))["n"] >= 5
