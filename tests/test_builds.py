"""Stage 6: the other four builds and their work."""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import bonds, careers, objectives, objectives_more, quarters
from simulation import world_data as data
from simulation.money import BPS
from tests.conftest import after_quarters
from tests.test_careers import NOW9, professional, sound
from tests.test_objectives import bell, give_shares, state_of

pytestmark = pytest.mark.world("eight")
EMPLOYER = {"investment_banker": "IKB", "risk_manager": "IKB", "lawyer": "IDC", "journalist": "ONN",
            "asset_manager": "IKB", "accountant": "IDC"}


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def pro(db, build, name=None, level=4, cash_naira=0):
    player, account = professional(db, name or build, build=build, employer=EMPLOYER[build], now=NOW9, cash_naira=cash_naira)
    if level > 1:
        careers.add_experience(db, player, build, careers.experience_for(level), NOW9)
    return player, account


def right_answers(db, objective_id) -> dict:
    """The right answers, read back from a paper marked with nothing on it (in a twin of the moment)."""
    row = state_of(db, objective_id)
    with db.transaction(force_rollback=True):
        marked = objectives.submit(db, row["player_id"], objective_id, {}, NOW9)
        return marked["result"]["answers"]


def test_there_are_six_builds_to_start_in_and_ceo_cannot_be_chosen(db):
    assert set(careers.BUILDS) == {"asset_manager", "accountant", "investment_banker", "risk_manager", "lawyer", "journalist"}
    player, _ = professional(db, "ada", employer=None, bank=None, now=NOW9)
    with pytest.raises(careers.CareerError):
        careers.choose_build(db, player, "ceo", NOW9)
    accents = {b["accent"] for b in careers.BUILDS.values()}
    assert accents == {"violet", "green", "purple", "orange", "red", "blue"}


def test_each_build_is_hired_by_the_right_kind_of_company(db):
    for build, wrong in (("investment_banker", "IDC"), ("risk_manager", "GGM"), ("journalist", "IKB")):
        player, _ = professional(db, build, build=build, employer=None, now=NOW9)
        with pytest.raises(careers.CareerError, match="does not hire"):
            careers.take_job(db, player, wrong, NOW9)
        assert careers.take_job(db, player, EMPLOYER[build], NOW9)["ticker"] == EMPLOYER[build]
    # The media houses are small, and still have room for a newsroom of players.
    reporter, _ = professional(db, "reporter", build="journalist", employer=None, now=NOW9)
    places = {o["ticker"]: o["places_left"] for o in careers.openings(db, reporter, NOW9)}
    assert set(places) == {"ONN", "TLH", "TNL"} and sum(places.values()) >= 60


def test_the_library_now_has_work_for_all_six_builds():
    for build in careers.BUILDS:
        mine = [t for t in objectives.TEMPLATES.values() if t.build == build]
        assert len(mine) >= 5 and len({t.module for t in mine}) == len(mine), build
        assert min(t.level for t in mine) == 1 and max(t.level for t in mine) <= 4
    words = " ".join(f"{t.module} {t.title} {t.idea}" for t in objectives.TEMPLATES.values()).upper().split()
    for body in ("CFA", "ACCA", "ICAN", "FRM", "CPA", "CRM"):
        assert body not in words


@pytest.mark.parametrize("build", ["investment_banker", "risk_manager", "lawyer", "journalist"])
def test_every_piece_of_new_work_can_be_taken_done_right_and_is_paid_by_its_named_payer(db, build):
    """Each hand-in piece: the right answers pass and are paid; a blank sheet does not. Each call
    is handed in and judged when the quarter closes. Nothing raises, and no money is made."""
    codes = [t.code for t in objectives.TEMPLATES.values() if t.build == build and t.code != "lw_pact"]
    judged = 0
    for index, code in enumerate(codes):
        template = objectives.TEMPLATES[code]
        player, account = pro(db, build, f"{build}{index}", cash_naira=300_000)
        offer = next(o for o in objectives.board(db, player, NOW9)["offers"] if o["template"] == code)
        if not offer["available"]:
            assert code == "ib_outcome", (code, offer["why_not"])        # only offered while a takeover offer is open
            continue
        taken = objectives.accept(db, player, code, NOW9)
        assert "company_id" not in taken["terms"] and taken["result"] is None
        if template.bell is not None:
            give_shares(db, account, "IDC", 40_000), give_shares(db, account, "GGM", 40_000), give_shares(db, account, "EKC", 40_000)
            bonds.trade(db, account=account, code=next(b for b in bonds.listing(db, NOW9) if b["kind"] == "bill")["code"],
                        side="buy", units=100, now=NOW9)
            for n in range(1, 4):
                bell(db, n)
            done = state_of(db, taken["id"])
            assert done["state"] == "passed", done["result"]
        elif template.close is None:
            answers = right_answers(db, taken["id"])
            other, _ = pro(db, build, f"{build}{index}b")
            blank = objectives.accept(db, other, code, NOW9)
            assert objectives.submit(db, other, blank["id"], {}, NOW9)["state"] == "failed"
            done = objectives.submit(db, player, taken["id"], answers, NOW9)
            assert done["state"] == "passed" and done["result"]["score"] >= 96, (code, done["result"])
            done = state_of(db, taken["id"])
        else:
            field = taken["terms"]["fields"][0]
            answer = "IDC" if field["kind"] == "ticker" else field["options"][0]["code"]
            try:
                objectives.submit(db, player, taken["id"], {field["key"]: answer}, NOW9)
            except objectives.ObjectiveError:
                objectives.submit(db, player, taken["id"], {field["key"]: "GGM"}, NOW9)
            continue
        judged += 1
        assert done["paid"] == done["reward"] > 0
        payer = _dicts(db, "SELECT c.name FROM companies c WHERE c.account_id = %s", (done["payer_account_id"],))[0]["name"]
        assert done["payer_name"] == payer
    assert judged >= 3
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    left = _dicts(db, "SELECT template, state, result FROM objectives WHERE state = 'active'")
    assert not left, left
    for row in _dicts(db, "SELECT template, state, result FROM objectives WHERE judged_period = 10"):
        assert row["state"] in ("passed", "failed") and row["result"]["debrief"]["plain"]
    sound(db)


def test_a_bond_price_is_worked_out_the_way_the_desk_does(db):
    """The banker's price and the desk's own fair value agree for a bond at the start of a quarter."""
    for coupon, quarters_left, wanted in ((1200, 4, 1300), (1500, 8, 1100), (900, 2, 1400)):
        mine = objectives_more._present_value(coupon, quarters_left, wanted)
        bond = {"kind": "fixed", "coupon_bps": coupon, "maturity_period": quarters_left, "issuer": "government", "face": bonds.FACE,
                "redeemed_period": None, "conversion_shares": None, "company_id": None}
        state = {"period": 0, "policy": 0, "left": 1.0, "index": BPS, "companies": {}, "shares": {}}
        desk = sum(amount / (1 + wanted / BPS) ** years for years, amount in bonds.payments(bond, state)) / 100
        assert abs(mine - desk) < 0.01
    assert objectives_more._present_value(1100, 4, 1300) < 1000 < objectives_more._present_value(1500, 4, 1300)


def test_the_takeover_rules_in_the_work_are_the_rules_of_the_exchange():
    scenario = {"price": 10_000, "shares": 1_000_000, "worth": 12_000, "premium_bps": 2500, "bidder_value": 20_000_000_000}
    n = objectives_more._bid_numbers(scenario)
    assert n["offer"] == 12_500 and n["stake"] == 600_000 and n["cost"] == 7_500_000_000
    assert not n["board"] and n["funds"] and n["vote"]                  # 25% is below the board's 30%; the cost is over a quarter of the bidder
    assert data.BOARD_ACCEPTS_PREMIUM_BPS == 3000 and data.FUNDS_ACCEPT_PREMIUM_BPS == 2500


def test_a_journalists_claims_to_check_are_never_all_true_or_all_false(db):
    seen = set()
    for n in range(12):
        player, _ = pro(db, "journalist", f"reporter{n}")
        company = objectives._filed(db, 8)[n]
        claims = objectives_more._claims_about(db, company, 8, player)
        flags = tuple(c["true"] for c in claims)
        assert any(flags) and not all(flags)
        seen.add(flags)
    assert len(seen) >= 3


def test_a_scoop_must_name_a_company_that_is_paying_its_way_today(db):
    player, _ = pro(db, "journalist")
    taken = objectives.accept(db, player, "jr_scoop", NOW9)
    behind = next((c for c in objectives._filed(db, 8) if objectives_more._behind(c["figures"])), None)
    if behind:
        with pytest.raises(objectives.ObjectiveError, match="already behind"):
            objectives.submit(db, player, taken["id"], {"ticker": behind["ticker"]}, NOW9)
    with pytest.raises(objectives.ObjectiveError, match="no company"):
        objectives.submit(db, player, taken["id"], {"ticker": "ZZZ"}, NOW9)
    assert state_of(db, taken["id"])["submission"] is None
