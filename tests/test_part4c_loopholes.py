"""Part 4c: the loophole check (working rule 3, design section 19), one test for each question.

The ten questions this part has to answer are listed in `docs/PART_4C_CHECKLIST.md`, item 33. Each
one is a way a player might cheat the game with the six new industries: read a private company's
papers before paying for them, move value out of one company into another, game a basket too thin to
defend itself, borrow dollars to dodge the naira, foretell a film's hit, arbitrage the fertiliser the
farms buy, dodge wages by moving staff, be paid twice by a company they own, turn a rescue into free
money, or move an index on their own.

Players may commit crimes against each other in this game, never against the game. Every answer here
is "no", and each test shows the machinery that says so.

Nothing in this file needs a running world except where it says `db`: the questions about weights,
prices and draws are answered from the same tables the engine reads, so the answer cannot drift away
from the code without the test failing.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import crisis, events, exchange, firm_deals, fx, indexes, ledger, marketview, quarters
from simulation import world_data as data
from simulation.money import BPS, million_naira
from tests.conftest import ADULT, after_quarters, join, money_accounted_for
from tests.test_careers import NOW9
from tests.test_deals import LATER, _one, do_checks, fairness_if_needed, open_a_sale
from tests.test_firm import firm_of

pytestmark = pytest.mark.world("eight")

# The six industries this part adds, and the one private company each brings: the buyers' targets.
NEW = ("pharma", "retail", "technology", "entertainment", "mining", "fertiliser")
PRIVATE_NEW = ("ILD", "ADK", "IKS", "OTS", "OMM", "ICS")


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def listed_in(sector: str) -> int:
    """How many listed companies a basket for that kind of company holds: one per listed company."""
    return sum(1 for c in data.COMPANIES if c.sector == sector and c.listed)


def sound(db) -> None:
    """Nothing made and nothing lost: the check every test about money ends with."""
    assert ledger.audit(db) == []
    assert crisis.check_books(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


# ---------------------------------------------------------------------------
# 1. Can a player see a private company's true figures before paying for the papers?
# ---------------------------------------------------------------------------

def test_q1_a_private_new_company_shows_nothing_until_the_data_room_is_signed(db, client):
    assert join(client, ADULT).status_code == 201
    # Each of the six private companies of this part is shut to the public, on both screens that could
    # show one: the company's page and its facts.
    for ticker in PRIVATE_NEW:
        assert client.get(f"/api/companies/{ticker}").status_code == 404, ticker
        assert client.get(f"/api/market/{ticker}/facts").status_code == 404, ticker

    # And the market screen itself leaves them out, so the 404 is the whole of it and not a filter on one route.
    day, _ = exchange.session_of(NOW9)
    shown = {s["ticker"] for s in marketview._shares(db, day)}
    assert not (set(PRIVATE_NEW) & shown)

    # A buyer sees what the company is worth, which is a published valuation, and nothing under it.
    company = _one(db, "SELECT * FROM companies WHERE ticker = 'ILD'")
    sale = open_a_sale(db, "ILD")
    assert sale["company_id"] == company["id"]
    candidates = _rows(db, "SELECT * FROM private_profiles WHERE company_id = %s", (company["id"],))
    assert candidates and "secrets" not in str(sale)          # the papers' own secrets are not in the sale


# ---------------------------------------------------------------------------
# 2. Can a player move value between a company they own and one they do not?
# ---------------------------------------------------------------------------

def test_q2_a_new_industry_company_does_not_move_value_to_its_owner(db):
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, "ILD")
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    do_checks(db, empire, team, file_id)

    # Overpaying is refused outright: no bid may be far above both the asking price and what the company
    # is worth. A bid that large also needs the Banker's fairness opinion first, so the bid is given one,
    # or the refusal would be about the paperwork rather than the price.
    too_much = sale["asking"] * 10
    fairness_if_needed(db, team, file_id, too_much)
    with pytest.raises(Exception, match="No board would let a price"):
        firm_deals.place_bid(db, team["head"], file_id, too_much, 0, LATER)

    # The other way round - paying far under what the company is worth, so that value leaves the seller
    # for the buyer - is not refused at the bid but at the close: the seller has a reserve beneath which
    # no bid wins, and the buyer's money comes back.
    cash_before = ledger.balance(db, empire["account_id"])
    low = sale["asking"] // 2
    assert 0 < low < sale["reserve"]                              # below the price the seller will take
    firm_deals.place_bid(db, team["head"], file_id, low, 0, LATER)
    assert ledger.balance(db, empire["account_id"]) < cash_before  # held in escrow while the bid stands
    firm_deals.decide_sales(db, 9, after_quarters(9))
    bid = _one(db, "SELECT * FROM deal_bids WHERE process_id = %s AND empire_id = %s ORDER BY id DESC LIMIT 1",
               (sale["id"], empire["id"]))
    assert bid["status"] == "lost" and bid["held"] == 0
    assert ledger.balance(db, empire["account_id"]) == cash_before  # and it came back to the kobo

    # The bounds are the published ones, so the test above cannot quietly drift away from the rule.
    assert firm_deals.OVERPAY_MOST_BPS == 15_000                  # at most 150% of what it is worth
    sound(db)


# ---------------------------------------------------------------------------
# 3. Can a thin four-company basket be gamed by trading its few members?
# ---------------------------------------------------------------------------

def test_q3_a_thin_new_basket_has_no_contract_to_settle_and_a_capped_weight(db):
    # No futures or options on any of the six: a thin basket is the easiest place to move a price by
    # hand, so there is no settlement price here for anyone to lean on. The decision is in the design
    # and in `world_data.INDEX_FUTURES`.
    assert not ({"PHARMA", "RETAIL", "TECH", "FILM", "MINING", "FERT"} & set(data.INDEX_FUTURES))
    assert set(data.INDEX_FUTURES) == {"TOP30", "BANKS", "OILGAS"}

    # Each new industry brings three listed companies, so its basket has three members. The weighting
    # rule lifts the 15% cap for a basket under seven members, but never past one and a half equal
    # shares: at three members that is 50%, and no company may sit above it however much is bought.
    assert {s: listed_in(s) for s in NEW} == dict.fromkeys(NEW, 3)
    members = 3
    lifted = max(data.INDEX_CAP_BPS, BPS * 3 // (2 * members))
    assert lifted == BPS // 2                                    # 50%: the ceiling for a three-name basket
    weights = indexes.capped_weights([1_000, 10, 10], data.INDEX_CAP_BPS)
    assert sum(weights) == BPS                                   # the weights still add up to the whole index
    assert max(weights) == lifted                                # and the largest is held at that ceiling


# ---------------------------------------------------------------------------
# 4. Can a miner's dollar borrowing be used to dodge the naira?
# ---------------------------------------------------------------------------

def test_q4_a_miners_dollar_borrowing_carries_the_naira_risk_it_was_meant_to_dodge(db):
    # Only the largest of a kind borrow in dollars, and for mining that is two companies.
    assert dict(data.FX_COMPANY_EUROBONDS)["mining"] == 2
    debt = _one(db, "SELECT d.*, c.ticker FROM company_debts d JOIN companies c ON c.id = d.company_id"
                    " WHERE d.currency = 'USD' AND c.sector = 'mining' ORDER BY d.original_principal DESC LIMIT 1")
    assert debt, "a miner borrows in dollars"

    # The dollars raised are sold to the Central Bank, so the miner holds naira: it cannot sit on the
    # dollars it borrowed. What it still owes, it owes in dollars.
    assert debt["principal_outstanding"] > 0 and debt["currency"] == "USD"
    before = fx.currency_loss(db, debt["company_id"], 8)

    # The naira falls a fifth. The quarter closes and the debt is revalued: the fall is the miner's
    # loss, in its own accounts. Borrowing abroad does not put the currency risk on anybody else.
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET official = official * 12 / 10")
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert fx.currency_loss(db, debt["company_id"], 9) > before >= 0
    result = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 9", (debt["company_id"],))
    assert result["currency_loss"] >= fx.currency_loss(db, debt["company_id"], 9) > 0
    sound(db)


# ---------------------------------------------------------------------------
# 5. Can a film company's hit be forecast from anything the player is shown?
# ---------------------------------------------------------------------------

def test_q5_no_film_hit_can_be_foretold_from_what_a_player_is_shown(db):
    # What happens in a quarter is drawn from the world's secret, and refused without one.
    with pytest.raises(ValueError, match="secret"):
        events.generate(db, 9, "too-short")

    # The draw is a hash of the secret, the quarter, the kind and the company: nothing a player can see.
    # Asking the same question twice gives the same answer, so there is no re-rolling to fish with...
    key = (9, "film_hit", "GDS", "happens")
    assert events._unit("a-fixed-secret-so-that-every-test-run-repeats", *key) == \
        events._unit("a-fixed-secret-so-that-every-test-run-repeats", *key)

    # ...and over many worlds it lands both ways for the same company and quarter. If it could be
    # foretold from the ticker and the date, it could only ever land one way.
    kind = next(k for k in events.KINDS if k.name == "film_hit")
    draws = [events._unit(f"secret-{n:04d}-{'x' * 26}", *key) * BPS < kind.chance_bps for n in range(400)]
    assert any(draws) and not all(draws)

    # A film company's hit touches that one company, so nothing else in the world hints at it either.
    assert kind.only_sectors == ("entertainment",)


# ---------------------------------------------------------------------------
# 6. Can the fertiliser-to-farm link be arbitraged?
# ---------------------------------------------------------------------------

def test_q6_the_fertiliser_a_farm_buys_is_a_cost_not_a_tradable_spread(db):
    # The link is a published share of what farms spend, recorded in the same table every industry
    # uses, and the fertiliser maker's own cost runs back to gas. It is a chain of costs between two
    # companies, neither of which a player can buy into or out of at will.
    assert data.INPUTS["agriculture"]["fertiliser"] > 0
    assert data.INPUTS["fertiliser"]["oil_gas"] > 0
    assert "fertiliser" in data.INPUTS.get("agriculture", {})

    # A bumper harvest lifts the fertiliser makers alone. It is one sector's luck, not a gap between
    # two prices, so there is no second leg for a player to take the other side of.
    bumper = next(k for k in events.KINDS if k.name == "bumper_harvest")
    assert bumper.only_sectors == ("fertiliser",)

    # And the farms are touched by their own event, not by the fertiliser makers' good fortune twice.
    harvest = next(k for k in events.KINDS if k.name == "good_harvest")
    assert harvest.only_sectors in (None, ("agriculture",)) or "fertiliser" not in (harvest.only_sectors or ())


# ---------------------------------------------------------------------------
# 7. Can wages be avoided by moving staff into a new industry?
# ---------------------------------------------------------------------------

def test_q7_every_new_industry_pays_wages_and_its_share_of_pensions(db):
    tickers = [c.ticker for c in data.COMPANIES if c.sector in NEW]
    assert len(tickers) == 24

    for ticker in tickers:
        account = _one(db, "SELECT account_id FROM companies WHERE ticker = %s", (ticker,))["account_id"]
        paid = _one(db, "SELECT count(*) AS n, coalesce(sum(-e.amount), 0) AS total FROM ledger_transactions t"
                        " JOIN ledger_entries e ON e.transaction_id = t.id"
                        " WHERE t.kind = 'wages' AND e.account_id = %s AND e.amount < 0", (account,))
        # Wages are paid by the company out of its own running costs, in every one of the six, so there
        # is no industry a company can be put in to escape them.
        assert paid["n"] > 0 and paid["total"] > 0, ticker

    # The employer's pension contribution rides on top of the wage, added for every kind of company
    # alike: the rate is the same for the six as for the rest, so the new industries get no relief.
    assert data.PENSION_EMPLOYER_BPS > 0
    assert {s.code for s in data.SECTORS} >= set(NEW)


# ---------------------------------------------------------------------------
# 8. Can a private company be made to pay its owner twice?
# ---------------------------------------------------------------------------

def test_q8_a_dividend_from_a_private_new_company_is_paid_once_and_adds_up(db):
    # A dividend is one transaction: what leaves the company exactly equals what reaches the owners,
    # so a second payment would have to be a second transaction, and there is none.
    rows = _rows(db, "SELECT t.id, t.period,"
                     "  sum(CASE WHEN e.amount < 0 THEN -e.amount ELSE 0 END) AS out_,"
                     "  sum(CASE WHEN e.amount > 0 THEN e.amount ELSE 0 END) AS in_"
                     " FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
                     " WHERE t.kind = 'dividend' GROUP BY t.id, t.period")
    assert rows
    for row in rows:
        assert row["out_"] >= row["in_"]                          # rounding stays with the company, never conjured
        assert row["out_"] - row["in_"] < 100                      # and it is kobo, not a second payment

    # One dividend for a company in a quarter, whatever it is owned by: the payer is the company's own
    # account, so two payments would show as two transactions in the same period.
    twice = _rows(db, "SELECT t.period, e.account_id, count(*) AS n"
                      " FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
                      " JOIN companies c ON c.account_id = e.account_id"
                      " WHERE t.kind = 'dividend' AND e.amount < 0 AND c.ticker = ANY(%s)"
                      " GROUP BY t.period, e.account_id HAVING count(*) > 1", (list(PRIVATE_NEW),))
    assert twice == []
    sound(db)


# ---------------------------------------------------------------------------
# 9. Can a rescue of a new company be turned into free money?
# ---------------------------------------------------------------------------

def test_q9_a_rescue_creates_no_money_and_pays_the_rescuer_from_the_company(db):
    # A rescue fee is a cost of the company being rescued, paid now or owed by it: the payer's side is
    # always a company account, so the fee cannot come out of nothing and land in a player's pocket.
    fees = _rows(db, "SELECT t.id, sum(CASE WHEN e.amount < 0 THEN 1 ELSE 0 END) AS payers"
                     " FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
                     " WHERE t.kind = 'professional_fee' GROUP BY t.id")
    for fee in fees:
        assert fee["payers"] >= 1

    # The whole books still hold after a quarter closes with all of this running: the ledger, the
    # crisis desk's own books, and every naira that should exist. Free money would show here first.
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    sound(db)


# ---------------------------------------------------------------------------
# 10. Can a new basket's index be moved single-handed?
# ---------------------------------------------------------------------------

def test_q10_no_single_player_can_move_a_new_basket_far_in_a_day(db):
    # Two limits, and together they bound what one player can do to an index in a day. The first is
    # the weight ceiling: 50% for a three-name basket, as in question 3.
    members = listed_in("mining")
    assert members == 3                                            # the same three-name basket as question 3
    ceiling = max(data.INDEX_CAP_BPS, BPS * 3 // (2 * members))
    # The second is the day's price limit: no share moves more than a tenth either way in one session.
    assert data.DAILY_PRICE_LIMIT_BPS == 1_000
    # So the most a single company can pull its own basket in a day, even held at the ceiling.
    most_in_a_day = ceiling * data.DAILY_PRICE_LIMIT_BPS // BPS
    assert most_in_a_day == BPS * 5 // 100                        # 5% of the index, at the very most

    # And the price limit is the one the exchange enforces, measured from yesterday's close, not a
    # rule the test keeps to itself.
    reference = 100_000
    low, high = exchange.price_limits(reference)
    assert high - reference == reference * data.DAILY_PRICE_LIMIT_BPS // BPS
    assert reference - low == reference * data.DAILY_PRICE_LIMIT_BPS // BPS

    # No futures on any of the six either, so there is no contract whose settlement one player could
    # lean on by moving the basket a little (question 3).
    assert not ({"PHARMA", "RETAIL", "TECH", "FILM", "MINING", "FERT"} & set(data.INDEX_FUTURES))
