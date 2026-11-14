# Competition, part 1: contested mandates and ranked work

Built 14 November 2026 on the owner's "build", on the branch `competition`. It was asked for because "the main aim for
this game is to compete with other empires and players". The plan is in `docs/TASKS_TRIM_AND_COMPETITION_PLAN_2026-11-14.md`.

## Contested mandates

When a company announces a sale of new shares (a rights issue or a sale to the public), the sale is put out to pitch.
Every empire may pitch, through its Investment Banker or its head.

**A pitch** has two parts:

- a fee, from 0.25% to 5% of what is raised;
- a forecast of how much of the sale will be taken up.

Each empire may pitch once. A pitch is sealed: nobody else sees it, and it cannot be changed. Pitches close on day 45 of
the quarter.

**The company chooses** as the quarter closes, before the sale settles. It chooses from the record, never by who asked
first: it takes the lowest fee once it allows for how far it trusts the banker.

- **Trust:** half a point a level, up to 30% at Level 60. Up to 10% more for an empire whose past forecasts of take-up
  came close.
- **A tie** is decided by lot.

**The winner** is paid its fee on what was actually raised, from the company's own account. Its empire earns 8 league
points. The others get nothing. Every forecast is scored against what was taken up, and the score becomes part of the
empire's record for its next pitches.

## Ranked work

Each quarter, each build gets one company, chosen by lot, and one figure about it to forecast:

| Build | The figure |
|---|---|
| Asset Manager | its share price when the quarter closes |
| Investment Banker | its sales for the quarter, as filed |
| Risk Manager | its profit or loss for the quarter, as filed |

**Entering:** forecasts close on day 30, so nobody forecasts what they can already see. Each player hands in one forecast,
for their own build only, and it is sealed until the quarter closes.

**Scoring:** when the quarter closes, the figure is read from the record and everybody is ranked by how far they missed.

- An empire earns points from its best entry only: 6, 4 or 2 for first, second or third. So a second account in the same
  empire buys nothing.
- There are no points for a miss of more than 25%, or when fewer than two empires took part.
- A public table names the sharpest analysts.

## A protected start

Up to Level 5, a player's work is marked alone, as before. Competing opens at Level 6.

## Where it is

- **On the website:** Work → Competition. It is a tab, not a new sidebar item.
- **Server:** `server/competition_routes.py`.
- **Engine:**
  - `simulation/competition.py`;
  - migration 048;
  - in the quarter close (`simulation/quarters.py`), companies choose before sales settle, winners are paid after, and
    forecasts are judged once the accounts are filed.
- **Tests:** `tests/test_competition.py`, one test per promise and per loophole.

## Loopholes, and what stops each

| Loophole | What stops it |
|---|---|
| A beginner thrown in against experienced empires | Level 5 and below are refused |
| Copying a better analyst's figure | Sealed until judged; the server never sends others' entries |
| Changing an answer after seeing news | One entry, sealed by the database, and nothing after the deadline |
| Pitching against your own empire, or twice | One pitch for each empire, enforced by the database |
| Second accounts | Only an empire's best entry scores |
| Winning by asking first | The company chooses from fee and trust; a tie is decided by lot |
| Two empires taking turns to win | A hidden pact to share mandates is a pact, and pacts are already a matter for the Tribunal |
| The page naming its own figures | The server refuses fields it did not ask for |

## Part 2, not yet built

- Work aimed at rivals: shorting a rival empire's overvalued company, defending a client against a rival's takeover, and
  spotting a rival bank's weak point.
- The empire league as the full scoreboard.
- Mandates for companies selling a division or looking for a buyer.
