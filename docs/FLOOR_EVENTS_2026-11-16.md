# The Floor's features and events, 16 November 2026

Built on the owner's "ok build" after The Floor, on the branch `floor-events`, in the order agreed with him: duels on the
Floor, then big client orders and the live deal tape, then the Archegos moment.

## Duels on the Floor

The owner chose a duel on the Floor in the real world over the October idea of a private copy of the world.

- **The challenge.** An empire's head challenges another empire for the next live event, until ten minutes before its
  bell. An empire the computer runs always accepts; a player-run empire's head accepts or declines. One duel for an
  empire at each bell.
- **The score.** For each side: what the event did to its money (its event result, which counts its trades and Floor
  deals in the touched shares), plus what its members earned as banks on the Floor during the event, both as a share of
  what the empire was worth at the bell, so a small empire can beat a big one. Both see the score live, split into
  the event's part and the Floor's.
- **Points.** The winner gets 8 league points; a draw gets 3 each. Once only.
- **Declines.** Free, but three in a season (not answering by the bell counts) are shown beside the empire's name, as
  the owner decided. No point penalty.
- **Where.** The Floor → Duels (a tab), and `DUEL` on the desk's command line.

Where: migration `058_floor_duels.sql`; `simulation/duels.py`; settings `DUEL_*`; routes `GET /api/floor/duels`,
`POST /api/floor/duels/challenge|answer|withdraw`; `web/src/Duels.tsx`. Tests: `tests/test_duels.py` (3).

## Big client orders, and the deal tape

- **Big client orders.** Now and then a computer pension fund or insurer hands a free asset manager a big order: buy so
  many shares of a company. At a live event's bell every free asset manager is offered one in the featured share. The
  manager has five minutes to take it on or turn it down, then thirty minutes (or until the live event ends) to buy the
  shares, with their own cash, on the exchange or from the banks on the Floor. It is worth up to 60% of their free cash.
  At the deadline the fund takes what they bought for it (never more than it asked for) at the market's average price
  over the window (every trade on the exchange and the Floor, weighted by size) and pays 0.15% commission. Buying below
  the average is the manager's gain; above it, their loss. Scored as the manager's average against the market's, and
  counted on Proven Talent's "On the Floor" (orders, done in full, average against the market).
- **The deal tape.** A strip along the top of the trading floor: every deal on the Floor and every exchange trade of
  ₦10 million or more, newest first. A computer bank is named; a player's desk is "a desk"; a client never is. Blocks are
  marked.
- **The squawk.** A switch on the tape: the Floor's notes (the bell, halfway, big moves, the floor hour) are read out
  loud as they come. Off at first; remembered in the player's own browser.

Where: migration `059_floor_mandates.sql`; `simulation/floor.py` (`mandates_tick`, `answer_mandate`, `settle_mandate`,
`tape`); settings `FLOOR_MANDATE_*`, `FLOOR_TAPE_EXCHANGE_NAIRA`; the route `POST /api/floor/mandate`. Tests:
`tests/test_floor.py` (1 more).

**Honest limit:** big client orders are orders to buy only, for now. An order to sell would need the fund to hand the
manager its shares first; it can come later.
