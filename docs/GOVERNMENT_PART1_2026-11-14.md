# Government, part 1: the elected leader, the budget, the Assembly and the stand-in

Built 14 November 2026 on the owner's choice ("Government, part 1"), on the branch `government`. It follows the
decisions of 3 October 2026 (`notes/owner-notes-crosscheck-2026-10-03.md`): an elected Government Leader, every empire
head in the Assembly beside computer-run members, a vote of no confidence, and a stand-in run by rules with a personality
drawn at random and published.

## Who governs

- **The election.** Each game year the players elect a Government Leader.
  - Candidates stand in a year's last quarter, up to day 30. A candidate needs a reputation of 80, Level 20 or more, and
    no tribunal ban.
  - From day 31, every player past Level 5 has one vote. It is cast once and kept.
  - The count is made as the year closes, and the winner governs the next year. A tie is decided by lot, never by who
    stood first.
- **The stand-in.** When nobody governs, a stand-in run by rules does. That is when nobody stood, nobody voted, the
  leader was removed, or the leader put no budget by the deadline. Its personality is drawn by lot each year and shown
  on the page:
  - **steady** keeps the rates;
  - **a hawk** raises every rate a point when the Treasury has been running down;
  - **a dove** cuts every rate a point when the Treasury has been filling up.

## The budget

The leader puts one budget a year, in the year's first quarter, by day 30. It sets four rates, each within limits:

| Tax | Started at | Limits |
|---|---|---|
| Income tax | 12% | 5% to 25% |
| Company tax | 30% | 15% to 40% |
| Property tax | 1% a year | 0.5% to 3% |
| Land tax | 0.5% a year | 0.25% to 1.5% |

The Assembly passes the budget or throws it out, and the vote is counted as the quarter closes. A budget that passes
changes what everybody pays from then on: salaries, companies' profits, buildings and land.

## The Assembly

- **Its members:**
  - the head of every empire run by players, with one vote each;
  - 15 computer-run members, whose leanings are drawn by lot and shown on the page:
    - some vote against any rise;
    - some vote against any cut;
    - some vote against any move of more than a point.
- **Voting:** a head votes once for their empire's seat.
- **No confidence:** any head may table a vote of no confidence in the leader, counted as the quarter closes.
  - The computer-run members turn on a leader whose budget passed against their leaning.
  - A leader who is removed is replaced by the stand-in for the rest of the year.

## Where it is

- **On the website:** Economy → Government. It is a tab, not a new sidebar item.
- **Server:** `server/government_routes.py`.
- **Engine:** `simulation/government.py`, and migration 050.
- **Taxes read the budget:**
  - income tax in `careers.split_salary`;
  - property and land tax in the property close;
  - company tax in the world's own rate, which the quarter close uses.
- **Tests:** `tests/test_government.py`.

## Part 2, not yet built

- **Decree:** the leader overrides the Central Bank's rate, at a cost to prices and trust.
- **Targeting an empire:** needs an Assembly vote, and can be challenged at the tribunal.
- **Lobbying and the Influence Network.**
- **Licences and permits, and tax season.**
- **Riots, and the leader's answer to them.**
- **Dirty elections:** vote buying as a crime.
- **Pay for the leader.**
- **The teaching figures:** the valuation figures used in property teaching still use the starting tax rates.
