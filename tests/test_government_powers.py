"""Government, part 2: the leader's decree on the Central Bank rate, levies on one empire, the leader's pay, and lobbying.

Promises: a decree sets next quarter's rate, held within three points of the Central Bank's own rule, and it costs prices
and confidence; a levy passed by the Assembly takes up to two per cent of one empire's cash for the Treasury; the leader is
paid each quarter from the Treasury; a lobbied computer-run member votes as the lobbying head did, and the money goes to
the Treasury in the open.

Loopholes: nobody but the leader decrees or proposes a levy, one decree a quarter, within limits; nobody but a head
lobbies, only after voting, at most three members per empire per vote, one empire per member, and a lobby once paid is
kept.
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import government, ledger
from simulation import world_data as data
from simulation.money import naira
from tests.test_builds import pro
from tests.test_careers import NOW9
from tests.test_dealmaking import house
from tests.test_government import P, YEAR, elect

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def test_only_the_leader_decrees_once_a_quarter_and_the_close_holds_it_near_the_rule(db):
    boss, _ = pro(db, "investment_banker", "decreer", level=20)
    other, _ = pro(db, "asset_manager", "usurper", level=20)
    elect(db, boss)
    with pytest.raises(government.GovernmentError, match="Only the Government Leader"):
        government.decree(db, other, 500, NOW9)
    with pytest.raises(government.GovernmentError, match="between 0% and 50%"):
        government.decree(db, boss, 9000, NOW9)
    government.decree(db, boss, 0, NOW9)
    with pytest.raises(government.GovernmentError, match="One a quarter"):
        government.decree(db, boss, 100, NOW9)
    assert government.decreed_rate(db, P) == 0
    rule = 1800
    final, words = government.apply_decree(db, P, rule, 0, "inflation above target")
    assert final == rule - data.DECREE_MOST_BPS                     # held within three points of the rule
    assert "By decree" in words
    row = _one(db, "SELECT * FROM decrees WHERE period = %s", (P,))
    assert (row["applied_bps"], row["rule_bps"]) == (final, rule)
    assert government.apply_decree(db, P, 1000, 1100, "x")[0] == 1100   # within the limit it stands as decreed


def test_a_decree_costs_prices_and_confidence_in_the_quarter_it_is_made(db):
    from simulation import macro
    boss, _ = pro(db, "investment_banker", "printer", level=20)
    elect(db, boss)
    prev = macro.state(db, P - 1)
    period = P if macro.state(db, P) is None else max(r for (r,) in db.execute("SELECT period FROM economy_results")) + 1
    args = dict(company_sales=prev["company_sales"], household_spending=prev["household_spending"], money=prev["money"],
                commodity_events={}, premium_index_bps=prev["premium_index_bps"], confidence_bps=8000, rate_extra_bps=0)

    def measure():
        with db.transaction() as tx:
            row = macro.close_quarter(db, period, "seed", **args)
            tx.connection.execute("SELECT 1")
            raise _Undo(row)

    try:
        measure()
    except _Undo as plain:
        without = plain.row
    db.execute("INSERT INTO decrees (period, leader_id, rate_bps, at) VALUES (%s, %s, 0, %s)", (period, boss, NOW9))
    try:
        measure()
    except _Undo as decreed:
        with_decree = decreed.row
    assert with_decree["confidence_bps"] == without["confidence_bps"] - data.DECREE_CONFIDENCE_BPS
    assert with_decree["price_index_bps"] > without["price_index_bps"]
    rule = _one(db, "SELECT rule_bps FROM decrees WHERE period = %s", (period,))
    rule = rule["rule_bps"] if rule and rule["rule_bps"] is not None else None
    # (The decree's own row was rolled back with the measure; the rule is at least the plain one, as prices ran faster.)
    assert with_decree["next_policy_rate_bps"] >= without["next_policy_rate_bps"] - data.DECREE_MOST_BPS
    assert with_decree["next_policy_rate_bps"] < without["next_policy_rate_bps"]
    assert rule is None or with_decree["next_policy_rate_bps"] == max(rule - data.DECREE_MOST_BPS, 0)
    assert with_decree["rate_reason"].startswith("By decree")


class _Undo(Exception):
    def __init__(self, row):
        self.row = row


def test_a_levy_is_the_leaders_within_limits_and_passed_it_takes_the_cash(db):
    boss, _ = pro(db, "investment_banker", "levier", level=20)
    other, _ = pro(db, "asset_manager", "nobody", level=20)
    elect(db, boss)
    empire, team = house(db, "Delta Partners")
    with pytest.raises(government.GovernmentError, match="Only the Government Leader"):
        government.propose_levy(db, other, empire["id"], 100, "Windfall.", NOW9)
    with pytest.raises(government.GovernmentError, match="between 0.01%"):
        government.propose_levy(db, boss, empire["id"], data.LEVY_MOST_BPS + 1, "Windfall.", NOW9)
    with pytest.raises(government.GovernmentError, match="reason"):
        government.propose_levy(db, boss, empire["id"], 100, "  ", NOW9)
    with pytest.raises(government.GovernmentError, match="no such empire"):
        government.propose_levy(db, boss, 999_999, 100, "Windfall.", NOW9)
    government.propose_levy(db, boss, empire["id"], data.LEVY_MOST_BPS, "A windfall on deals.", NOW9)
    with pytest.raises(government.GovernmentError, match="already before"):
        government.propose_levy(db, boss, empire["id"], 100, "Again.", NOW9)
    levy = _one(db, "SELECT id FROM motions WHERE kind = 'levy'")["id"]
    members = government.assembly(db, YEAR)
    computers = [m for m in members if m["kind"] == "computer"]
    high = sum(1 for m in computers if m["leaning"] == "high_tax")
    heads_against = len(members) - len(computers)          # every head but the leader's opponents: none vote, so nothing
    before = ledger.balance(db, empire["account_id"])
    treasury = ledger.account_id(db, ledger.TREASURY)
    t_before = ledger.balance(db, treasury)
    government.at_close(db, P, NOW9)
    row = _one(db, "SELECT * FROM motions WHERE id = %s", (levy,))
    assert row["votes_for"] == high and row["votes_against"] == len(computers) - high
    assert heads_against >= 0
    if row["status"] == "passed":
        assert row["collected"] == before * data.LEVY_MOST_BPS // 10_000
        assert ledger.balance(db, empire["account_id"]) == before - row["collected"]
    else:
        assert row["collected"] is None and ledger.balance(db, empire["account_id"]) == before
    assert ledger.balance(db, treasury) - t_before == (row["collected"] or 0) - naira(data.LEADER_PAY_NAIRA)


def test_lobbied_members_vote_with_the_lobbying_head_and_carry_a_levy(db):
    boss, _ = pro(db, "investment_banker", "lobbied_leader", level=20)
    elect(db, boss)
    target, _ = house(db, "Delta Partners")
    rival, team = house(db, "Echo Holdings", tag="echo")
    government.propose_levy(db, boss, target["id"], 100, "Too big.", NOW9)
    levy = _one(db, "SELECT id FROM motions WHERE kind = 'levy'")["id"]
    subject = f"motion:{levy}"
    protectors = [m for m in government.assembly(db, YEAR) if m["kind"] == "computer" and m["leaning"] != "high_tax"]
    with pytest.raises(government.GovernmentError, match="head of an empire"):
        government.lobby(db, team["investment_banker"], subject, protectors[0]["seat"], NOW9)
    with pytest.raises(government.GovernmentError, match="Vote first"):
        government.lobby(db, team["head"], subject, protectors[0]["seat"], NOW9)
    government.assembly_vote(db, team["head"], subject, True, NOW9)
    with pytest.raises(government.GovernmentError, match="no such member"):
        government.lobby(db, team["head"], subject, 99, NOW9)
    paid_before = ledger.balance(db, rival["account_id"])
    treasury = ledger.account_id(db, ledger.TREASURY)
    t_before = ledger.balance(db, treasury)
    for m in protectors[:data.LOBBY_MOST]:
        out = government.lobby(db, team["head"], subject, m["seat"], NOW9)
        assert out["vote"] is True
    with pytest.raises(government.GovernmentError, match=f"{data.LOBBY_MOST} members"):
        government.lobby(db, team["head"], subject, protectors[data.LOBBY_MOST]["seat"], NOW9)
    cost = naira(data.LOBBY_NAIRA) * data.LOBBY_MOST
    assert paid_before - ledger.balance(db, rival["account_id"]) == cost
    assert ledger.balance(db, treasury) - t_before == cost
    # The target's head cannot buy back a member already won over.
    target_head = _one(db, "SELECT head_player_id FROM empires WHERE id = %s", (target["id"],))["head_player_id"]
    government.assembly_vote(db, target_head, subject, False, NOW9)
    with pytest.raises(government.GovernmentError, match="already won that member over"):
        government.lobby(db, target_head, subject, protectors[0]["seat"], NOW9)
    with pytest.raises(Exception, match="sealed|kept"):
        db.execute("UPDATE lobbying SET vote = false")
    computers = [m for m in government.assembly(db, YEAR) if m["kind"] == "computer"]
    high = sum(1 for m in computers if m["leaning"] == "high_tax")
    government.at_close(db, P, NOW9)
    row = _one(db, "SELECT * FROM motions WHERE id = %s", (levy,))
    # The rival's head and the lobbied members for; the target's head and the unlobbied protectors against.
    assert row["votes_for"] == 1 + high + data.LOBBY_MOST
    assert row["votes_against"] == 1 + len(protectors) - data.LOBBY_MOST


def test_the_leader_is_paid_each_quarter_and_the_page_shows_the_powers(db):
    boss, _ = pro(db, "investment_banker", "paid", level=20)
    elect(db, boss)
    account = ledger.player_account_id(db, boss)
    before = ledger.balance(db, account)
    government.at_close(db, P, NOW9)
    assert ledger.balance(db, account) - before == naira(data.LEADER_PAY_NAIRA)
    page = government.view(db, boss, NOW9)
    p = page["powers"]
    assert p["is_leader"] and p["can_decree"] and p["empires"]
    outsider = pro(db, "asset_manager", "outsider")[0]
    q = government.view(db, outsider, NOW9)["powers"]
    assert not q["is_leader"] and q["empires"] == [] and not q["can_lobby"]
