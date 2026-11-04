"""Part 4c: what the independent review found, one test for each thing that was real.

Checklist item 34. A second reviewer that did not write this part read the six industries, their baskets,
their events, the private-company doors and the trouble paths, and was told to break them. It raised seven
things. One was real and is fixed here; one was a wrong sentence in the checklist, now corrected; four were
checked against the code and are not faults; and the last is the running of the older suite, which is item
37 and cannot be settled by reading. The four that were refuted are named in this file so that nobody has to
chase them twice:

- "The severe flag on a mine accident is read by nothing." Not so: the flag is written onto the event row
  (`simulation/events.py:137`) and read back by the intelligence desk (`simulation/intel.py:754`), so a
  serious mine accident is reported as one.
- "A mine accident gets no aftermath story and can never be the cause of an insurance claim." Not so:
  `_aftermath_news` takes every kind named in `EVENT_NAMES`, and `mine_accident` is one of them
  (`simulation/news.py:255`); the claim names the worst event of whatever kind it was (`simulation/news.py:547`).
- "A private company's figures might still come out of the per-ticker screens." Closed by `test_r2` below,
  which knocks on all five doors rather than the two that were already proved.
- "The dividend test only bounds the leak at under a naira." True, and it stays: the bound is the kobo left
  over from rounding a dividend down, which the company keeps. The loophole file proves nobody is paid twice
  and no money is conjured; an exact-dust assertion would pin a number the accountancy never promised.

Nothing here has been seen to pass: the sandbox that wrote it has no test runner and no database.
"""

from __future__ import annotations

import pytest

from simulation import economy
from simulation import world_data as data
from simulation.money import BPS
from tests.test_part4c_more import NEW_LISTED, NEW_PRIVATE

pytestmark = pytest.mark.world("eight")


def test_r1_the_non_oil_export_weights_add_up_to_a_whole():
    # Found by the review. Part 4c put mining on the list of what the country sells abroad at 3,000, beside
    # farms at 6,000 and factories at 4,000 — 13,000 of a 10,000 whole. Nothing failed, because the split
    # divides by the sum of the weights: the miners' arrival quietly cut every exporter's share instead. The
    # three now add up, and mining is paid the share it was already being paid (2,300 of 10,000, or 3 of 13).
    assert sum(data.NON_OIL_EXPORTS.values()) == BPS
    assert set(data.NON_OIL_EXPORTS) == {"agriculture", "manufacturing", "mining"}

    # Each is paid exactly its published share, in whole kobo, and the shares together are the whole amount
    # but for the kobo the rule rounds down and leaves with the payer.
    amount = 130_000_000
    paid = economy.split(amount, dict(data.NON_OIL_EXPORTS))
    for sector, weight in data.NON_OIL_EXPORTS.items():
        assert paid[sector] == amount * weight // BPS, sector
    assert 0 <= amount - sum(paid.values()) < len(paid)


def test_r2_no_private_company_gives_a_figure_away_on_any_screen_that_names_it(client, player, db):
    # Found by the review. Two doors on a private company had been tried — its page and its facts — and both
    # were shut. Nobody had knocked on the other three. Every route a player can name a ticker on answers for
    # a private company with a refusal and a reason, and never with a payload: the reason is the whole answer.
    for ticker in NEW_PRIVATE:
        for path in (f"/api/companies/{ticker}", f"/api/market/{ticker}/facts", f"/api/market/{ticker}/results",
                     f"/api/market/{ticker}/why", f"/api/market/{ticker}/analysis"):
            answer = client.get(path)
            assert answer.status_code == 404, (path, answer.status_code)
            assert set(answer.json()) == {"detail"}, path

    # And the same door on one of the listed companies of the six still opens, so the refusal is about being
    # held privately and not about the six new industries being broken.
    assert client.get(f"/api/market/{NEW_LISTED[0]}/facts").status_code == 200
    assert client.get(f"/api/companies/{NEW_LISTED[0]}").status_code == 200
