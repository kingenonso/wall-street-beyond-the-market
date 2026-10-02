"""The small formulas everything else is built from. No database needed."""

from __future__ import annotations

import pytest

from simulation import clock, credit
from simulation.companies import principal_due, quarterly_interest
from simulation.money import apply_bps, is_whole_amount, million_naira, naira


@pytest.mark.world("empty")
class TestMoney:
    def test_naira_is_held_as_kobo(self):
        assert naira(500_000) == 50_000_000
        assert million_naira(1) == 100_000_000

    def test_rates_round_to_the_nearest_kobo_with_halves_up(self):
        assert apply_bps(1_000, 3_000) == 300         # 30%
        assert apply_bps(5, 1_000) == 1               # 0.5 kobo rounds up
        assert apply_bps(4, 1_000) == 0               # 0.4 kobo rounds down
        assert apply_bps(10**15, 10_000) == 10**15    # 100% of a very large amount is exact

    def test_only_real_whole_numbers_count_as_amounts(self):
        assert is_whole_amount(5) and is_whole_amount(-5)
        assert not any(is_whole_amount(x) for x in (5.0, "5", None, True, False))


@pytest.mark.world("empty")
class TestDebt:
    def test_a_quarter_of_the_yearly_interest(self):
        assert quarterly_interest(naira(1_000_000), 2_000) == naira(50_000)    # 20% a year is 5% a quarter
        assert quarterly_interest(0, 2_000) == 0
        assert quarterly_interest(3, 1_000) == 0                                # under half a kobo

    def test_an_amortising_loan_is_repaid_in_equal_slices(self):
        assert principal_due(2_400, "amortising", maturity_period=24, period=1) == 100
        assert principal_due(100, "amortising", maturity_period=24, period=24) == 100      # the last slice
        assert principal_due(1_000, "amortising", maturity_period=3, period=1) == 334      # rounded up, never short

    def test_slices_always_clear_the_loan_by_its_end_date(self):
        outstanding = 1_000_003
        for period in range(1, 8):
            outstanding -= principal_due(outstanding, "amortising", maturity_period=7, period=period)
        assert outstanding == 0

    def test_a_bullet_bond_is_repaid_all_at_once_at_the_end(self):
        assert principal_due(5_000, "bullet", maturity_period=32, period=31) == 0
        assert principal_due(5_000, "bullet", maturity_period=32, period=32) == 5_000

    def test_a_late_debt_is_due_in_full(self):
        assert principal_due(700, "amortising", maturity_period=10, period=12) == 700
        assert principal_due(0, "bullet", maturity_period=10, period=12) == 0


@pytest.mark.world("empty")
class TestQuarterNumbers:
    def test_quarter_numbers_map_to_game_years(self):
        assert clock.period_to_date(1) == (1, 1)
        assert clock.period_to_date(4) == (1, 4)
        assert clock.period_to_date(5) == (2, 1)
        assert clock.period_label(8) == "Year 2 Q4"
        assert clock.period_label(0) == "Opening"
        with pytest.raises(ValueError):
            clock.period_to_date(0)


def _filing(**overrides) -> dict:
    """A healthy trading company's filing, with chosen figures changed."""
    figures = {
        "income_statement": {"revenue": 1_000, "interest_income": 0, "operating_profit": 300,
                             "interest_expense": 20, "net_profit": 200, "operating_expenses": 100,
                             "depreciation": 50, "ebitda": 350},
        "balance_sheet": {"total_equity": 5_000, "total_assets": 6_000, "borrowings": 500,
                          "customer_funds": 0, "cash": 800, "payables": 0},
        "notes": {"principal_overdue": 0},
    }
    for path, value in overrides.items():
        section, line = path.split("__")
        figures[section][line] = value
    return figures


@pytest.mark.world("empty")
class TestCreditRating:
    def test_a_strong_company_rates_at_the_top(self):
        filing = _filing()
        rating, reasons = credit.rate(filing, [filing])
        assert rating == "AAA"
        assert len(reasons) >= 3 and all(isinstance(r, str) for r in reasons)

    def test_more_debt_means_a_weaker_rating(self):
        scale = credit.SCALE
        light = _filing(balance_sheet__borrowings=500)
        heavy = _filing(balance_sheet__borrowings=9_000, income_statement__interest_expense=250)
        assert scale.index(credit.rate(heavy, [heavy])[0]) > scale.index(credit.rate(light, [light])[0])

    def test_a_loss_maker_rates_below_a_profit_maker(self):
        loss = _filing(income_statement__net_profit=-50, income_statement__operating_profit=-10)
        rating, reasons = credit.rate(loss, [loss])
        assert credit.SCALE.index(rating) > credit.SCALE.index("AAA")
        assert "It is making a loss." in reasons

    def test_unpaid_bills_cap_the_rating_at_ccc(self):
        filing = _filing(balance_sheet__payables=10)
        rating, reasons = credit.rate(filing, [filing])
        assert rating == "CCC"
        assert reasons[0] == "It has bills it could not pay on time."

    def test_debt_that_is_many_years_of_ebitda_caps_the_rating(self):
        scale = credit.SCALE
        # Borrowings of 500 against yearly EBITDA of 4 x 20 = 80: more than six years.
        filing = _filing(income_statement__ebitda=20)
        rating, reasons = credit.rate(filing, [filing])
        assert scale.index(rating) >= scale.index("B")
        assert any("years of EBITDA" in r for r in reasons)

    def test_a_business_that_produces_no_cash_but_has_debts_rates_ccc_at_best(self):
        filing = _filing(income_statement__ebitda=-5)
        rating, reasons = credit.rate(filing, [filing])
        assert credit.SCALE.index(rating) >= credit.SCALE.index("CCC")
        assert any("EBITDA" in r for r in reasons)

    def test_a_filing_from_before_ebitda_was_filed_is_still_rated(self):
        filing = _filing()
        del filing["income_statement"]["ebitda"]
        assert credit.rate(filing, [filing])[0] == "AAA"

    def test_debt_past_its_date_is_a_default(self):
        filing = _filing(notes__principal_overdue=1)
        assert credit.rate(filing, [filing])[0] == "D"

    def test_owing_more_than_it_owns_is_a_default(self):
        filing = _filing(balance_sheet__total_equity=-1)
        assert credit.rate(filing, [filing])[0] == "D"

    def test_with_no_trading_history_the_rating_says_so(self):
        rating, reasons = credit.rate(_filing(), [])
        assert rating in credit.SCALE
        assert any("no trading history" in r for r in reasons)
