"""Stage 11: ten questions a player might ask to get round the court's rules, each answered by a test.

The court is a docket, not a courtroom: it proves a number from the record and makes it be paid. So the questions are
about standing, the bond, the number, the ban, and the money — not about guilt.
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import courts, exchange, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.test_careers import NOW9
from tests.test_courts import (P, T, company, insider_wrong, open_regulator_case, player_of, short_wrong, stake_wrong,
                               wash_wrong)
from tests.test_firm import firm_of
from tests.test_market import trader
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def bystander(db, name="bystander", cash=1_000_000_000):
    account = trader(db, name, cash_naira=cash)
    return account, player_of(db, account)


# 1. Can a player learn the world's secret, or the regulator's reasoning, from the court's pages?
def test_l1_no_page_sends_the_worlds_secret_or_the_regulators_reasoning(client, player, db, monkeypatch):
    from server import court_routes
    monkeypatch.setattr(court_routes, "_exchange_time", lambda conn: NOW9)
    got = client.get("/api/court")
    assert got.status_code == 200
    for hidden in ("fortune_seed", "secret", "_roll", "enforce_bps", "COURT_ENFORCE"):
        assert hidden not in got.text
    # The docket says what a case is worth and what proves it, never why the regulator chose it.
    for case in got.json()["docket"]:
        assert "reason" not in case and "chance" not in case


# 2. Can a player bring a case they have no standing for?
def test_l2_a_player_cannot_bring_a_case_they_have_no_standing_for(db):
    c = company(db)
    _, claimant = bystander(db)
    # Manipulation and a naked short are the regulator's alone.
    wash = wash_wrong(db)
    with pytest.raises(courts.CourtError, match="Only the regulator"):
        courts.bring(db, claimant, kind="manipulation", defendant_id=wash["pid"], company_id=c["id"], period=P, now=NOW9)
    short = short_wrong(db)
    with pytest.raises(courts.CourtError, match="Only the regulator"):
        courts.bring(db, claimant, kind="naked_short", defendant_id=short["pid"], company_id=c["id"], period=P, now=NOW9)
    # An insider case needs the other side of the dealing.
    insider = insider_wrong(db)
    with pytest.raises(courts.CourtError, match="other side"):
        courts.bring(db, claimant, kind="insider", defendant_id=insider["pid"], company_id=c["id"], period=P, now=NOW9)
    # An undisclosed stake needs a shareholding.
    stake = stake_wrong(db)
    with pytest.raises(courts.CourtError, match="shareholder"):
        courts.bring(db, claimant, kind="undisclosed_stake", defendant_id=stake["team"]["head"], company_id=c["id"],
                     period=P, now=NOW9)


# 3. Can a player bring a case against themselves?
def test_l3_a_player_cannot_bring_a_case_against_themselves(db):
    c = company(db)
    insider = insider_wrong(db)
    with pytest.raises(courts.CourtError, match="against yourself"):
        courts.bring(db, insider["pid"], kind="insider", defendant_id=insider["pid"], company_id=c["id"], period=P, now=NOW9)


# 4. Can a player name a number the record does not support?
def test_l4_a_player_cannot_name_a_number_the_record_does_not_support(db):
    c = company(db)
    insider = insider_wrong(db)
    seller = _one(db, "SELECT seller_account_id FROM market_trades WHERE company_id = %s AND buyer_account_id = %s"
                       " ORDER BY id LIMIT 1", (c["id"], insider["insider"]))["seller_account_id"]
    give_cash(db, seller, 10_000_000)
    case = courts.bring(db, player_of(db, seller), kind="insider", defendant_id=insider["pid"], company_id=c["id"],
                        period=P, now=NOW9)
    # The court found the number itself: it is the profit on the record, not anything the claimant said.
    assert case["amount"] == insider["wrong"]["amount"]
    assert case["evidence"]["total"] == insider["wrong"]["amount"]


# 5. Can a player bring a case without the bond, or lose it by winning?
def test_l5_the_bond_is_posted_and_returned_when_the_claim_is_proved(db):
    c = company(db)
    stake = stake_wrong(db)
    # A player with no money cannot bring a case at all, even holding the shares that give them standing. (Asked
    # first: a wrong is tried once, so the poor player must try before the rich one opens the case and spends it.)
    poor_account, poor = bystander(db, "poor", cash=0)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=poor_account, amount=1_000,
                    asset=f"SHR-{T}", kind="test_shares", memo="Test: a shareholding")
    with pytest.raises(courts.CourtError, match="bond"):
        courts.bring(db, poor, kind="undisclosed_stake", defendant_id=stake["team"]["head"], company_id=c["id"],
                     period=P, now=NOW9)
    bond = max(apply_bps(stake["wrong"]["amount"], data.COURT_BOND_BPS), naira(data.COURT_BOND_FLOOR_NAIRA))
    claimant = trader(db, "claimant", cash_naira=bond // 100 + 1_000_000)
    claimant_pid = player_of(db, claimant)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=claimant, amount=1_000,
                    asset=f"SHR-{T}", kind="test_shares", memo="Test: a shareholding")
    before = ledger.balance(db, claimant)
    case = courts.bring(db, claimant_pid, kind="undisclosed_stake", defendant_id=stake["team"]["head"],
                        company_id=c["id"], period=P, now=NOW9)
    bond = case["bond"]
    assert bond >= naira(data.COURT_BOND_FLOOR_NAIRA)
    assert ledger.balance(db, claimant) == before - bond
    # The defendant fights and loses; the bond comes back, because the claim was proved.
    give_cash(db, ledger.player_account_id(db, stake["team"]["head"]), 1_000_000_000)
    courts.respond(db, stake["team"]["head"], case["id"], "fight", P, NOW9)
    assert _one(db, "SELECT 1 AS x FROM ledger_transactions WHERE kind = 'court_bond_return' AND memo LIKE %s",
                (f"%{case['id']}%",))
    assert ledger.balance(db, claimant) > before - bond


# 6. Can somebody else answer a case, or can a case be answered twice?
def test_l6_only_the_defendant_can_answer_and_only_once(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"])
    _, other = bystander(db)
    with pytest.raises(courts.CourtError, match="Only the person"):
        courts.respond(db, other, case_id, "settle", P, NOW9)
    courts.respond(db, pid, case_id, "settle", P, NOW9)
    with pytest.raises(courts.CourtError, match="already been decided"):
        courts.respond(db, pid, case_id, "fight", P, NOW9)


# 7. Can a defendant with no money escape the judgment?
def test_l7_a_defendant_with_no_money_still_owes_and_is_collected_later(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=0)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    courts.ensure(db)
    case = courts.judge(db, case_id, P, NOW9)
    owed = case["disgorgement"] + case["fine"] + case["costs"]
    assert case["paid"] == 0 and case["owed"] == owed
    # The debt does not vanish: it is collected as the defendant earns.
    give_cash(db, defendant, 100_000_000)
    assert courts.pay(db, case_id, P + 1, NOW9) == owed
    assert courts.case(db, case_id)["owed"] == 0


# 8. Can a banned player trade through an empire instead?
def test_l8_a_banned_head_cannot_trade_through_the_empire(db):
    empire, team = firm_of(db)
    c = company(db)
    case_id = open_regulator_case(db, kind="manipulation", defendant_id=team["head"], company_id=c["id"])
    courts.ensure(db)
    courts.judge(db, case_id, P, NOW9)
    with pytest.raises(exchange.ExchangeError, match="banned"):
        courts.check_trade(db, empire["account_id"], NOW9)
    # A member who is not the head is not banned by the head's order.
    courts.check_trade(db, ledger.player_account_id(db, team["asset_manager"]), NOW9)


# 9. Can a continuing breach fill the docket with cases?
def test_l9_a_continuing_breach_does_not_fill_the_docket(db):
    c = company(db)
    wash = wash_wrong(db)
    # Wash trading is one wrong, not also a ramp.
    mine = [w for w in courts._wrongs(db, P, NOW9)
            if w["kind"] == "manipulation" and str(w["defendant_id"]) == str(wash["pid"])]
    assert len(mine) == 1
    # Once a case is open for it, the same wrong is not brought again.
    courts.open_case(db, kind="manipulation", defendant_id=wash["pid"], claimant_id=None, company_id=c["id"],
                     amount=mine[0]["amount"], evidence={"key": mine[0]["key"], "total": mine[0]["amount"],
                                                         "lines": mine[0]["lines"]},
                     words=mine[0]["words"], period=P, now=NOW9)
    assert not [w for w in courts._wrongs(db, P, NOW9) if w["key"] == mine[0]["key"]]


# 10. Can a player take money from the compensation fund?
def test_l10_a_player_cannot_take_money_from_the_compensation_fund(db):
    courts.ensure(db)
    fund = ledger.account_id(db, courts.COMPENSATION_FUND)
    # The fund is an escrow account, not anybody's: no player owns it.
    assert _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (fund,))["player_id"] is None
    # A claimant is paid only what the defendant actually pays; the fund does not cover the shortfall.
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=0)
    pid = player_of(db, defendant)
    claimant = trader(db, "claimant", cash_naira=1_000_000)
    claimant_pid = player_of(db, claimant)
    case_id = courts.open_case(db, kind="insider", defendant_id=pid, claimant_id=claimant_pid, company_id=c["id"],
                               amount=naira(10_000_000), evidence={"key": "insider:test", "total": naira(10_000_000),
                                                                   "lines": []}, words="A case brought by a player.",
                               period=P, now=NOW9)
    before = ledger.balance(db, claimant)
    case = courts.judge(db, case_id, P, NOW9)
    assert case["paid"] == 0
    assert ledger.balance(db, claimant) == before
    assert ledger.balance(db, fund) == 0
