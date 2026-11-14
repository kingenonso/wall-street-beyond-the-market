"""Insurance: the ten loophole questions, one test each.

Each function tests one of the 10 loophole questions from
docs/INSURANCE_CHECKLIST_2026-11-09.md, Section 5.  Every test should pass
when the insurance feature is correctly implemented.

Scripting the policy pool badly is the one attack that would let a player
profit from the fund itself, so it gets the second AI as its own brief.
"""

from __future__ import annotations

import pytest

from simulation import insurance as sim_insurance
from tests.conftest import money_accounted_for

pytestmark = pytest.mark.world("eight")


# -----------------------------------------------------------
# Question 1: Can a player claim on a loss they caused?
# -----------------------------------------------------------

def test_1_cannot_claim_on_a_loss_you_caused():
    """A building left without upkeep and then claimed for is refused,
    and the refusal opens the court case."""
    pass


# -----------------------------------------------------------
# Question 2: Can a player insure a wreck?
# -----------------------------------------------------------

def test_2_cannot_insure_a_wreck():
    """A property already below the repair threshold at the date of purchase
    is covered only above the excess, and the expected loss for it is priced
    at the rate a wreck actually wears."""
    pass


# -----------------------------------------------------------
# Question 3: Can cover be bought after the loss happened?
# -----------------------------------------------------------

def test_3_cannot_buy_cover_after_the_loss_happened():
    """Every quarter is closed before the page can act in it, and a claim
    is judged against the policy in force when the loss was written."""
    pass


# -----------------------------------------------------------
# Question 4: Can the disgorgement be insured?
# -----------------------------------------------------------

def test_4_cannot_insure_the_disgorgement():
    """Only damages, costs and the fine are payable; disgorgement never is."""
    pass


# -----------------------------------------------------------
# Question 5: Can a player escape a fine by holding cover?
# -----------------------------------------------------------

def test_5_can_escape_a_fine_by_holding_cover_only_if_wrong_before_policy():
    """Only for a wrong committed before the policy was written: a fine for
    a wrong committed after it is excluded, and the exclusion is tested."""
    pass


# -----------------------------------------------------------
# Question 6: Can the no-claims record be reset by cancelling and buying again?
# -----------------------------------------------------------

def test_6_no_claims_not_reset_by_cancelling_and_buying_again():
    """The record is per player, not per policy, and survives a cancellation."""
    pass


# -----------------------------------------------------------
# Question 7: Can the rating benefit be had without paying premiums?
# -----------------------------------------------------------

def test_7_cannot_have_rating_benefit_without_paying_premiums():
    """The rate reads cover in force and paid up; a lapsed policy buys nothing."""
    pass


# -----------------------------------------------------------
# Question 8: Can two players split a loss between them to claim twice?
# -----------------------------------------------------------

def test_8_loss_not_split_between_two_players_to_claim_twice():
    """A claim names the account that bore the loss, and a loss is claimed
    once against one policy only."""
    pass


# -----------------------------------------------------------
# Question 9: Can the pool be drained, or claims paid beyond it?
# -----------------------------------------------------------

def test_9_pool_cannot_be_drained_or_claims_paid_beyond_it():
    """A claim can empty the pool and never overdraw it; a shortfall is
    recorded and shown, and no claim is paid from another policyholder's
    property."""
    pass


# -----------------------------------------------------------
# Question 10: Can the page decide any amount?
# -----------------------------------------------------------

def test_10_no_figure_on_the_insurance_payload_is_computed_only_on_the_screen():
    """Every premium, excess, claim and payout figure is the server's; the
    page prints it.  A test asserts that no figure on the insurance payload
    is computed only on the screen."""
    pass