"""The currency desk: ten ways a player might try to cheat it, and why each fails."""

from __future__ import annotations

from datetime import timedelta

import pytest

from simulation import fx, ledger, swaps
from simulation import world_data as data
from tests.test_fx import DAY, TRADING, _one, opened, person, ring, sound


def test_l1_dollars_from_the_window_cannot_be_sold_to_a_bureau_either(db, monkeypatch):
    """Round-tripping through a bureau instead of the street."""
    opened(db)
    player, _ = person(db, "ada", cash_naira=200_000_000)
    fx.window_ask(db, player, 1_000_000, TRADING)
    ring(db, DAY)
    db.execute("INSERT INTO bdcs (empire_id, name, buy_bps, sell_bps, licensed_at) SELECT id, 'Test Bureau', 0, 0, now() FROM empires ORDER BY id LIMIT 1")
    bdc = _one(db, "SELECT id FROM bdcs")
    with pytest.raises(fx.FxError, match="official window"):
        fx.bdc_deal(db, player, bdc["id"], "sell", 1_000_000, TRADING + timedelta(days=1))


def test_l2_withdrawing_a_part_filled_request_does_not_reopen_the_limit(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    ask = fx.window_ask(db, player, data.FX_WINDOW_LIMIT_PLAYER_CENTS, TRADING)
    db.execute("UPDATE fx_window SET filled = 1000000 WHERE id = %s", (ask["request_id"],))   # (as if part had been handed out)
    fx.window_cancel(db, player, ask["request_id"], TRADING)
    with pytest.raises(fx.FxError, match="at most"):
        fx.window_ask(db, player, data.FX_WINDOW_LIMIT_PLAYER_CENTS, TRADING)
    fx.window_ask(db, player, data.FX_WINDOW_LIMIT_PLAYER_CENTS - 1_000_000, TRADING)          # what is left of the limit is fine


def test_l3_buying_and_selling_straight_back_always_loses(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=200_000_000)
    cash = ledger.balance(db, account)
    for c in ("USD", "GBP", "EUR"):
        fx.street_deal(db, player, "buy", c, 5_000_000, TRADING)
        fx.street_deal(db, player, "sell", c, 5_000_000, TRADING)
    assert ledger.balance(db, account) < cash
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    fx.street_deal(db, player, "buy", "USD", 1_000_000, TRADING)
    usd = ledger.balance(db, account, "USD")
    fx.eurobond_deal(db, player, eb["id"], "buy", 3, TRADING)
    fx.eurobond_deal(db, player, eb["id"], "sell", 3, TRADING)
    assert ledger.balance(db, account, "USD") < usd
    sound(db)


def test_l4_no_amount_that_is_not_a_whole_positive_number_is_taken(db):
    opened(db)
    player, _ = person(db, "ada")
    for bad in (0, -5, True, 10**13, 1.5, "100"):
        with pytest.raises(fx.FxError):
            fx.street_deal(db, player, "buy", "USD", bad, TRADING)
        with pytest.raises(fx.FxError):
            fx.window_ask(db, player, bad if bad != 10**13 else 0, TRADING)
    with pytest.raises(fx.FxError):
        fx.street_deal(db, player, "buy", "JPY", 1_000_000, TRADING)


def test_l5_nobody_sells_what_they_do_not_hold(db):
    opened(db)
    player, _ = person(db, "ada")
    with pytest.raises(fx.FxError, match="do not have"):
        fx.street_deal(db, player, "sell", "EUR", 100_000, TRADING)
    with pytest.raises(fx.FxError, match="do not have"):
        fx.window_sell(db, player, 100_000, TRADING)
    eb = _one(db, "SELECT * FROM eurobonds ORDER BY id LIMIT 1")
    with pytest.raises(fx.FxError, match="do not hold"):
        fx.eurobond_deal(db, player, eb["id"], "sell", 1, TRADING)


def test_l6_only_the_head_or_the_investment_banker_deals_for_an_empire(db):
    opened(db)
    player, _ = person(db, "ada")
    with pytest.raises(fx.FxError, match="no seat"):
        fx.street_deal(db, player, "buy", "USD", 100_000, TRADING, for_empire=True)
    with pytest.raises(fx.FxError, match="no seat"):
        fx.open_bdc(db, player, "My Bureau", 50, 50, TRADING)
    with pytest.raises(fx.FxError, match="no seat"):
        fx.open_remitter(db, player, "My Remit", 100, 2, TRADING)


def test_l7_another_players_balances_requests_and_alerts_are_never_sent(db):
    opened(db)
    ada, _ = person(db, "ada", cash_naira=200_000_000)
    bola, _ = person(db, "bola", cash_naira=200_000_000)
    fx.street_deal(db, ada, "buy", "USD", 3_333_300, TRADING)
    fx.window_ask(db, ada, 2_222_200, TRADING)
    ring(db, DAY)
    seen = repr(fx.page(db, bola, TRADING + timedelta(days=1)))
    assert "3333300" not in seen and "2222200" not in seen
    assert all(a["kind"] != "window" for a in fx.alerts_for(db, bola, 0, TRADING + timedelta(days=1))["alerts"])
    assert any(a["kind"] == "window" for a in fx.alerts_for(db, ada, 0, TRADING + timedelta(days=1))["alerts"])
    assert "noise" not in seen and "seed" not in seen


def test_l8_the_central_banks_next_move_is_not_in_what_anybody_sees(db):
    opened(db)
    player, _ = person(db, "ada")
    page = fx.page(db, player, TRADING)
    for q in page["quarters"]:
        assert set(q) <= {"period", "label", "official", "market", "regime", "reserves", "cover_bps", "sold", "backlog", "event", "words"}
    assert "next" not in repr(page).lower()


def test_l9_a_currency_forward_counts_against_how_much_a_player_may_have_at_risk(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=1_000_000)
    from tests.test_derivatives import ready
    ready(db, player)
    bank = _one(db, "SELECT id FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY ticker LIMIT 1")
    with pytest.raises(swaps.SwapError, match="worth"):
        swaps.propose(db, player, kind="fx", counterparty={"bank": str(bank["id"])}, side="pay_fixed", quarters=4, now=TRADING,
                      notional=data.SWAP_MOST_DOLLARS_CENTS)


@pytest.mark.world("eight")
def test_l10_a_bureau_cannot_deal_with_its_own_empire_or_its_members_and_cannot_use_the_window(db):
    from tests.test_careers import NOW9
    from tests.test_fx import empire_head
    ring(db, NOW9.date() - timedelta(days=1))
    head, account, empire = empire_head(db)
    got = fx.open_bdc(db, head, "Lagoon Bureau", 50, 50, NOW9)
    with pytest.raises(fx.FxError, match="own empire"):
        fx.bdc_deal(db, head, got["bdc_id"], "buy", 100_000, NOW9)
    with pytest.raises(fx.FxError, match="own empire"):
        fx.bdc_deal(db, head, got["bdc_id"], "buy", 100_000, NOW9, for_empire=True)
    with pytest.raises(fx.FxError, match="street"):
        fx.window_ask(db, head, 100_000, NOW9, for_empire=True)
    sound(db)
