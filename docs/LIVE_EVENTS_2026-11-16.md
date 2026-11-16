# Live events, part 1, 16 November 2026

Built on the owner's "build", on the branch `live-events`. The owner left the open questions to us ("your call"); the
decisions are in the project note `notes/live-events-matches-decisions-2026-11-16.md`. Part 2 (head-to-head matches
between two empires) comes next.

## When

**Monday, Wednesday and Friday at 20:00 Lagos time, for thirty minutes.** The market is open (12:00 to 22:00), so it is
played in the real market with real money, and the results are permanent.

- The Desk shows a strip with the countdown to the next bell; while an event runs it turns red and shows the clock.
- Work → **Live events** (a tab, not a new sidebar item) has the full page. Typing `LIVE` on the desk's command line
  opens it.
- A server that was down at the bell may still ring it up to ten minutes late; after that the bell is missed.

## What happens: five kinds, each real

Which kind, and whom it strikes, is decided at the bell from the world's secret, so nobody can know it in advance. The
same kind never comes twice in a row. Where it can, it strikes a company some player-run empire holds.

| Kind | The real effect |
| --- | --- |
| **Fraud Uncovered** | A scandal is added to the quarter at a listed company: its sales this quarter fall, and its accounts show it at the close |
| **Fuel Crisis** | Energy prices jump across the country (in the quarter's commodity prices). Oil and gas companies are marked up; airlines, shippers, transport, factories and cement makers down |
| **Bank Run** | Savers' trust in one bank falls 15 points for six game days, so the crisis desk really sees money leave, day by day, and the Central Bank may step in. Other banks are marked down a little |
| **Emergency Rate Move** | The Central Bank's next rate will be a point higher (inflation above target) or lower, from the quarter's close. Banks, builders and cement makers are marked up or down |
| **Takeover Battle** | A company makes a real bid for another, paid from cash it has to spare (no borrowing in the middle of a quarter). The target is repriced to what the bid makes it worth; the bid runs and settles at the close like any other |

**How the market takes it.** Investors who read the news at once mark the touched shares within minutes (the server
sends them back to their screens the moment the bell rings); the institutions a day later; the founders not at all. The
mark is at most 8% and fades over three trading days. It changes only how investors price, never anybody's money. The
news carries the bell at once and the result at the end.

## How empires are scored

Every empire in the league is in the field: what it was worth at the bell and what it held of the touched shares are
written down and cannot be changed.

- **The prediction (10, 6, 3 points).** In the first ten minutes every member of a player-run empire seals their own
  prediction of how far the featured share will move from the bell to the end (owner, 16 November 2026: "every member
  predicts and the best one counts"). One each, and it cannot be changed. The empire's closest prediction counts. The
  closest three empires earn points if they missed by no more than five points, and only if at least two empires
  predicted. On a tie, the earlier prediction wins. Once scored, the table names whose prediction counted.
- **The money (10, 6, 3 points).** What the event did to each empire's money: the touched shares it held at the bell
  and what it traded in them during the window, with fees, against what it was worth at the bell, so a small empire can
  beat a big one. The best three that made money earn points.
- **Taking part (2 points).** For a player-run empire that predicted, traded a touched share, or whose standing plan
  acted.

Computer-run empires are in the field too. Their analysts predict from what anybody could see: the direction, and a
guess at the size.

**Sealed until the end.** While the event runs, a rival sees only how many of an empire's members have predicted, and
the empire's result as a share of its worth. It never sees a figure, or the empire's money. An empire's own members see
each other's predictions, so they can talk them over. Everything is shown once the event is scored, with how far each
member missed.

## The standing plan

The head may leave a plan for when nobody from the empire can be there. It is carried out at the bell by the head's own
authority, inside every limit an order from the head would meet: the trading limit, the Risk Manager's gate, and the 30%
rule.

- **Hold:** do nothing (the default).
- **Cut:** sell half of any holding the news hurts.
- **Buy the fall:** buy the featured share, up to a budget, if the news hurts it.
- **Ride the rise:** buy it, up to a budget, if the news helps it.

What the plan did, or why a limit refused it, is shown to the empire. A plan cannot be changed while an event runs.

## Where it is

- **Engine:**
  - `simulation/liveevents.py`;
  - migration `054_live_events.sql`;
  - settings `LIVE_*` in `simulation/world_data.py`;
  - news kinds `live_event_open` and `live_event_result` (`simulation/news_wordings/live.py`).
- **Hooks into the rest of the world:**
  - the investors read the event's mark as they read other news (`investors.py`);
  - the crisis desk counts the run in a bank's trust (`crisis.py`, part `live_event`);
  - the quarter's close adds the emergency move to the Central Bank's decision (`quarters.py`);
  - a takeover can be limited to one target (`corporate._propose_takeover(only_target=...)`).
- **Server:**
  - `server/live_routes.py`: `GET /api/live`, `POST /api/live/predict`, `POST /api/live/plan`;
  - the bell and the scoring run in the server's loop, before the investors act.
- **Website:**
  - `web/src/Live.tsx`: the page and the desk strip;
  - the Work tab;
  - the `LIVE` command.

## Tests

`tests/test_live_events.py`, 13 tests:

- the timetable;
- one bell only;
- each kind's real effect;
- the investors' reading, at once and a day later, and fading;
- the choice from the world's secret, never the same kind twice;
- the sealed prediction and its loopholes;
- the standing plan;
- scoring and points once only;
- a late bell;
- the page.

Also updated: the news counts in `tests/test_news.py`, and the capitals rule in `web/src/design.test.ts`.

## Honest limits

- The five kinds are the first set. The October list's other themes (Election Weekend, The Great Auction, the Wildcard
  hour, sudden death, trophies, the highlight reel and the rest) are still on the list for later parts.
- A takeover needs a company with cash to spare and a target in its own industry. When none can bid, another kind
  happens at that bell instead.
- An event's result counts only the shares it touched: an empire that hedged with something else is not credited for it.
- Because the closest member counts, a bigger empire can spread its members' predictions across a range and is more
  likely to have one close. Seats are limited (seven at most), and the computer-run empires are scored on one analyst's
  guess. If this proves too strong, the fix is to score on the members' average, or to give fewer points the more
  members predicted.
